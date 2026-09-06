from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.physics.pdg import MUON_MASS_GEV
from src.utils.config import dataset_config
from src.utils.paths import data_path

EVENT_KEYS = ["dataset_id", "run", "luminosityBlock", "event"]
ROW_TOLERANCE = 0.05


def run_dq(dataset_id: str, layer: str, table_path: Path) -> dict[str, Any]:
    files = _parquet_files(table_path)
    report = {
        "dataset_id": dataset_id,
        "layer": layer,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "rows": 0,
        "metrics": {},
        "passed": True,
        "failures": [],
    }
    seen: set[tuple[Any, ...]] = set()
    for file in files:
        frame = pd.read_parquet(file)
        report["rows"] += len(frame)
        _check_keys(frame, seen, report)
        _check_physics(frame, layer, report)
    _require(report["rows"] > 0, "nonzero rows", report)
    _add_certification_metrics(dataset_id, layer, report)
    _check_row_count_history(report)
    append_report(report)
    if not report["passed"]:
        raise RuntimeError(f"DQ failed for {dataset_id} {layer}: {report['failures']}")
    return report


def append_report(entry: dict[str, Any]) -> None:
    output = dq_report_path()
    history: list[dict[str, Any]] = []
    if output.exists():
        history = json.loads(output.read_text(encoding="utf-8"))
    history.append(entry)
    output.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")


def dq_report_path() -> Path:
    return data_path("results") / "dq_report.json"


def _parquet_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.parquet"))


def _check_keys(frame: pd.DataFrame, seen: set[tuple[Any, ...]], report: dict[str, Any]) -> None:
    missing = [column for column in EVENT_KEYS if column not in frame.columns]
    _require(not missing, f"missing key columns: {missing}", report)
    if missing:
        return
    for column in EVENT_KEYS:
        _require(not frame[column].isna().any(), f"no nulls in {column}", report)
    key_columns = EVENT_KEYS + (["muon_idx"] if "muon_idx" in frame.columns else [])
    for key in frame[key_columns].itertuples(index=False, name=None):
        _require(key not in seen, f"duplicate key: {key}", report)
        seen.add(key)


def _check_physics(frame: pd.DataFrame, layer: str, report: dict[str, Any]) -> None:
    if "pt" in frame.columns:
        _require((np.isfinite(frame["pt"]) & (frame["pt"] > 0.0)).all(), "muon pt > 0", report)
    if "eta" in frame.columns:
        _require(
            (np.isfinite(frame["eta"]) & (frame["eta"].abs() <= 2.4)).all(),
            "muon |eta| <= 2.4",
            report,
        )
    if "iso" in frame.columns:
        iso = pd.to_numeric(frame["iso"], errors="coerce")
        _require((iso.isna() | (np.isfinite(iso) & (iso >= 0.0))).all(), "muon iso >= 0", report)
    if layer == "gold" and "mass" in frame.columns:
        _require((frame["mass"] > 2.0 * MUON_MASS_GEV).all(), "mass above two muon masses", report)


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
    if not bool(condition):
        report["passed"] = False
        report["failures"].append(message)
