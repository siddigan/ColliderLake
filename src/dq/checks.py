from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from pyarrow import parquet

from src.physics.pdg import MUON_MASS_GEV
from src.utils.config import dataset_config
from src.utils.paths import config_path, data_dir, data_path, ensure_parent
from src.utils.runlog import get_logger, safe_log

EVENT_KEYS = ["dataset_id", "run", "luminosityBlock", "event"]
ROW_TOLERANCE = 0.05


def run_dq(dataset_id: str, layer: str, table_path: Path) -> dict[str, Any]:
    logger = get_logger(layer)
    files = _parquet_files(table_path)
    report: dict[str, Any] = {
        "dataset_id": dataset_id, "layer": layer,
        "checked_at_utc": datetime.now(UTC).isoformat(), "rows": 0,
        "metrics": {}, "passed": True, "failures": [], "columns": {},
    }
    keys = EVENT_KEYS + (["pair_idx"] if layer == "gold" else [])
    if layer in {"bronze", "silver"} and any("muons" in part.parts for part in files):
        keys.append("muon_idx")
    profile, contract_columns = _contract_columns(dataset_id, layer)
    schema_columns = _schema_columns(files)
    missing = [c for c in keys if c not in schema_columns]
    for column in keys:
        report["columns"][column] = "checked" if column in schema_columns else "not present"
    _require(not missing, f"missing required key column: {missing[0]}" if missing else "", report)
    for column in contract_columns:
        if column not in schema_columns:
            report["columns"][column] = "not present"
            _require(False, f"contract violation: {column} required by profile {profile}", report)

    checked = [c for c in ("pt", "eta", "phi", "iso", "mass") if c in schema_columns]
    for column in ("pt", "eta", "phi", "iso", "mass"):
        report["columns"][column] = "checked" if column in schema_columns else "not present"
    for column in schema_columns:
        report["columns"].setdefault(column, "not present" if column in {"iso"} else "skipped")
    report["columns"].setdefault("iso", "not present")

    for file in files:
        available = set(_schema_columns([file]))
        projection = [c for c in keys + checked if c in available]
        frame = pd.read_parquet(file, columns=projection)
        report["rows"] += len(frame)
        for key in keys:
            if key in frame:
                null_count = int(frame[key].isna().sum())
                report["metrics"].setdefault("null_key_counts", {}).setdefault(key, 0)
                report["metrics"]["null_key_counts"][key] += null_count
                if null_count:
                    _require(False, f"no nulls in {key}", report)
        _check_physics(frame, layer, report)
    _require(report["rows"] > 0, "nonzero rows", report)

    dup_count = _duplicate_count_duckdb(files, keys, data_dir("tmp")) if files and not missing else 0
    report["metrics"]["duplicate_key_count"] = dup_count
    if dup_count:
        _require(False, f"duplicate key count: {dup_count}", report)
    _add_certification_metrics(dataset_id, layer, report)
    _check_row_count_history(report)
    append_report(report)
    if not report["passed"]:
        safe_log(logger, logging.ERROR, "DQ %s FAIL | %s | halting", layer, "; ".join(report["failures"]))
        raise RuntimeError(f"DQ failed for {dataset_id} {layer}: {report['failures']}")
    safe_log(logger, logging.INFO, "DQ %s PASS | %d checks", layer, _check_count(layer))
    return report


def _schema_columns(files: list[Path]) -> list[str]:
    columns: list[str] = []
    for file in files:
        for name in parquet.read_schema(file).names:
            if name not in columns:
                columns.append(name)
    return columns


def _contract_columns(dataset_id: str, layer: str) -> tuple[str | None, list[str]]:
    if layer != "gold":
        return None, []
    contract = config_path("contracts", "gold_dimuon.yaml")
    if not contract.exists():
        return None, []
    import yaml

    profiles = (yaml.safe_load(contract.read_text(encoding="utf-8")) or {}).get("profiles", {})
    try:
        profile = dataset_config(dataset_id).get("gold_profile")
    except KeyError:
        profile = None
    if not profile or profile not in profiles:
        return profile, []
    return profile, list(profiles[profile].get("required_columns", []))


def _duplicate_count_duckdb(
    files: list[Path], keys: list[str], temp_root: Path, memory_limit: str | None = None,
    settings_observer: Any = None,
) -> int:
    if not keys:
        return 0
    temp_root.mkdir(parents=True, exist_ok=True)
    # SQL NULLs are distinct for this count, matching the oracle's per-tuple null behavior.
    paths = [str(p).replace("'", "''") for p in files]
    source = "[" + ",".join("'" + p + "'" for p in paths) + "]"
    quoted = ", ".join('"' + k + '"' for k in keys)
    configured_memory = memory_limit or os.environ.get("COLLIDERLAKE_DQ_MEM", "2GB")
    with tempfile.TemporaryDirectory(prefix="dq-spill-", dir=temp_root) as spill, duckdb.connect() as con:
        con.execute("SET memory_limit = ?", [configured_memory])
        con.execute("SET temp_directory = ?", [spill])
        con.execute("SET preserve_insertion_order = false")
        con.execute("SET threads = 2")
        settings = con.execute(
            "SELECT current_setting('temp_directory'), current_setting('memory_limit'), "
            "current_setting('preserve_insertion_order'), current_setting('threads')"
        ).fetchone()
        if settings_observer is not None:
            settings_observer(Path(settings[0]), settings[1], settings[2], settings[3])
        if Path(settings[0]).resolve() != Path(spill).resolve():
            raise RuntimeError("DuckDB temp_directory did not resolve to the DQ spill directory")
        query = (
            f"SELECT COALESCE(SUM(c - 1), 0) FROM (SELECT COUNT(*) AS c "
            f"FROM read_parquet({source}, union_by_name=true) "
            f"WHERE " + " AND ".join(f'"{k}" IS NOT NULL' for k in keys) +
            f" GROUP BY {quoted} HAVING COUNT(*) > 1)"
        )
        return int(con.execute(query).fetchone()[0])


def append_report(entry: dict[str, Any]) -> None:
    output = dq_report_path()
    history: list[dict[str, Any]] = []
    if output.exists():
        history = json.loads(output.read_text(encoding="utf-8"))
    history.append(entry)
    ensure_parent(output).write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")


def dq_report_path() -> Path:
    return data_dir("results") / "dq_report.json"


def _parquet_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.parquet"))


def _check_physics(frame: pd.DataFrame, layer: str, report: dict[str, Any]) -> None:
    checks: list[tuple[str, pd.Series]] = []
    if "pt" in frame:
        checks.append(("muon pt > 0", np.isfinite(frame["pt"]) & (frame["pt"] > 0.0)))
    if "eta" in frame:
        checks.append(("finite muon eta", np.isfinite(frame["eta"])))
        if layer == "silver":
            checks.append(("muon |eta| <= 2.4", frame["eta"].abs() <= 2.4))
    for column in ("phi", "mass"):
        if column in frame:
            checks.append((f"finite muon {column}", np.isfinite(frame[column])))
    if "iso" in frame:
        iso = pd.to_numeric(frame["iso"], errors="coerce")
        checks.append(("muon iso >= 0", iso.isna() | (np.isfinite(iso) & (iso >= 0.0))))
    if layer == "gold" and "mass" in frame:
        checks.append(("mass above two muon masses", frame["mass"] > 2.0 * MUON_MASS_GEV))
    for message, valid in checks:
        count = int((~valid).sum())
        report["metrics"].setdefault("physics_violation_counts", {}).setdefault(message, 0)
        report["metrics"]["physics_violation_counts"][message] += count
        _require(count == 0, message, report)


def _add_certification_metrics(dataset_id: str, layer: str, report: dict[str, Any]) -> None:
    if layer != "silver":
        return
    metrics_path = data_path("silver", f"dataset={dataset_id}") / "certification_metrics.json"
    if not metrics_path.exists():
        return
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    report["metrics"].update(metrics)
    fraction = float(metrics.get("certified_fraction", 0.0))
    low, high = dataset_config(dataset_id).get("expected_certified_fraction", [0.0, 1.0])
    _require(float(low) <= fraction <= float(high), "certified_fraction within expected band", report)


def _check_row_count_history(report: dict[str, Any]) -> None:
    previous = _previous_success(report["dataset_id"], report["layer"])
    if previous is None:
        return
    expected = int(previous["rows"])
    if expected == 0:
        return
    delta = abs(int(report["rows"]) - expected) / expected
    report["metrics"]["previous_successful_rows"] = expected
    report["metrics"]["row_count_delta_fraction"] = delta
    _require(delta <= ROW_TOLERANCE, "row count within 5% of previous successful run", report)


def _previous_success(dataset_id: str, layer: str) -> dict[str, Any] | None:
    output = dq_report_path()
    if not output.exists():
        return None
    history = json.loads(output.read_text(encoding="utf-8"))
    for entry in reversed(history):
        if entry.get("dataset_id") == dataset_id and entry.get("layer") == layer and entry.get("passed"):
            return entry
    return None


def _require(condition: bool, message: str, report: dict[str, Any]) -> None:
    if message and not bool(condition):
        report["passed"] = False
        report["failures"].append(message)


def _check_count(layer: str) -> int:
    return {"bronze": 6, "silver": 7, "gold": 6}.get(layer, 0)
