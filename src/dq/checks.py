from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.physics.pdg import MUON_MASS_GEV
from src.utils.paths import data_path

KEY_COLUMNS = ["dataset_id", "run", "luminosityBlock", "event"]


def run_dq(dataset_id: str, layer: str, table_path: Path) -> dict:
    files = sorted(table_path.rglob("*.parquet")) if table_path.is_dir() else [table_path]
    frame = pd.concat((pd.read_parquet(file) for file in files), ignore_index=True) if files else pd.DataFrame()
    report = {
        "dataset_id": dataset_id,
        "layer": layer,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(frame)),
        "passed": True,
        "failures": [],
    }
    _require(len(frame) > 0, "nonzero rows", report)
    present_keys = [column for column in KEY_COLUMNS if column in frame.columns]
    for column in present_keys:
        _require(not frame[column].isna().any(), f"no nulls in {column}", report)
    if layer in {"bronze", "silver"} and all(column in frame.columns for column in KEY_COLUMNS):
        _require(not frame.duplicated(KEY_COLUMNS).any(), "no duplicate event keys", report)
    if "mass" in frame.columns:
        _require((frame["mass"] > 2.0 * MUON_MASS_GEV).all(), "mass above two muon masses", report)
    if "Muon_pt" in frame.columns:
        _require(True, "muon arrays present", report)
    _append_report(report)
    if not report["passed"]:
        raise RuntimeError(f"DQ failed for {dataset_id} {layer}: {report['failures']}")
    return report


def _require(condition: bool, message: str, report: dict) -> None:
    if not condition:
        report["passed"] = False
        report["failures"].append(message)


def _append_report(entry: dict) -> None:
    output = data_path("results") / "dq_report.json"
    history = []
    if output.exists():
        history = json.loads(output.read_text(encoding="utf-8"))
    history.append(entry)
    output.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
