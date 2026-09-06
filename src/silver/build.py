from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.config import dataset_config
from src.utils.paths import data_path, ensure_parent, project_root


def build_silver(dataset_id: str) -> Path:
    bronze_dir = data_path("bronze", f"dataset={dataset_id}", "events")
    frame = _read_parquet_dir(bronze_dir)
    if frame.empty:
        raise RuntimeError(f"Bronze layer is empty for {dataset_id}")
    certified = _apply_certification(frame, dataset_config(dataset_id))
    cleaned = _clean_events(certified)
    output_dir = data_path("silver", f"dataset={dataset_id}", "events")
    cleaned.to_parquet(ensure_parent(output_dir / "part-0000.parquet"), index=False)
    return output_dir


def _read_parquet_dir(path: Path) -> pd.DataFrame:
    files = sorted(path.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Parquet files found under {path}")
    return pd.concat((pd.read_parquet(file) for file in files), ignore_index=True)


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


def _clean_events(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for flag in ("HLT_IsoMu24", "HLT_Mu50", "Flag_goodVertices", "Flag_METFilters"):
        if flag not in output.columns:
            output[flag] = False
    return output[output["certified"].astype(bool)].reset_index(drop=True)
