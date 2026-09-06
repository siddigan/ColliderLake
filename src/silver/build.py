from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.utils.config import dataset_config
from src.utils.paths import data_path, ensure_parent, project_root


def build_silver(dataset_id: str) -> Path:
    config = dataset_config(dataset_id)
    metrics = {"events_before": 0, "events_after": 0}
    for event_file in sorted(data_path("bronze", f"dataset={dataset_id}", "events").glob("*.parquet")):
        events = pd.read_parquet(event_file)
        certified = _apply_certification(events, config)
        kept_events = certified[certified["certified"].astype(bool)].reset_index(drop=True)
        metrics["events_before"] += len(events)
        metrics["events_after"] += len(kept_events)
        out_events = data_path("silver", f"dataset={dataset_id}", "events") / event_file.name
        kept_events.to_parquet(ensure_parent(out_events), index=False)

        muon_file = data_path("bronze", f"dataset={dataset_id}", "muons") / event_file.name
        if muon_file.exists():
            muons = pd.read_parquet(muon_file)
            cleaned = _clean_muons(_filter_to_events(muons, kept_events))
            out_muons = data_path("silver", f"dataset={dataset_id}", "muons") / event_file.name
            cleaned.to_parquet(ensure_parent(out_muons), index=False)
    if metrics["events_before"] == 0:
        raise FileNotFoundError(f"No bronze event files found for {dataset_id}")
    metrics["certified_fraction"] = metrics["events_after"] / metrics["events_before"]
    metrics_path = data_path("silver", f"dataset={dataset_id}") / "certification_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return data_path("silver", f"dataset={dataset_id}")


def _apply_certification(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    certification = config.get("certification")
    if certification == "prefiltered":
        output["certified"] = True
        output["certification_source"] = "prefiltered"
        return output
    if isinstance(certification, dict) and certification.get("golden_json_file"):
        json_path = project_root() / certification["golden_json_file"]
        if not json_path.exists():
            output["certified"] = False
            output["certification_source"] = "missing_golden_json"
            return output
        intervals = json.loads(json_path.read_text(encoding="utf-8"))
        output["certified"] = [
            _is_certified(int(run), int(lumi), intervals)
            for run, lumi in zip(output["run"], output["luminosityBlock"], strict=False)
        ]
        output["certification_source"] = str(json_path.relative_to(project_root()))
        return output
    output["certified"] = True
    output["certification_source"] = "none"
    return output


def _is_certified(run: int, lumi: int, intervals: dict[str, list[list[int]]]) -> bool:
    for start, end in intervals.get(str(run), []):
        if start <= lumi <= end:
            return True
    return False


def _filter_to_events(muons: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if muons.empty or events.empty:
        return muons.iloc[0:0].copy()
    keys = ["dataset_id", "run", "luminosityBlock", "event"]
    keep = events[keys].drop_duplicates()
    return muons.merge(keep, on=keys, how="inner")


def _clean_muons(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    output = frame.copy()
    mask = np.isfinite(output["pt"]) & (output["pt"] > 0.0)
    mask &= np.isfinite(output["eta"]) & (output["eta"].abs() <= 2.4)
    mask &= np.isfinite(output["phi"])
    if "iso" in output.columns:
        iso = pd.to_numeric(output["iso"], errors="coerce")
        mask &= iso.isna() | (np.isfinite(iso) & (iso >= 0.0))
    return output[mask].reset_index(drop=True)
