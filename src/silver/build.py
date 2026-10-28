from __future__ import annotations

import json
import logging
import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.utils.config import dataset_config
from src.utils.paths import (
    PARQUET_COMPRESSION,
    configured_data_path,
    data_dir,
    data_path,
    ensure_parent,
)
from src.utils.runlog import add_stage_stats, get_logger, safe_log


def build_silver(dataset_id: str) -> Path:
    config = dataset_config(dataset_id)
    logger = get_logger("silver")
    metrics = {
        "events_before": 0,
        "events_after": 0,
        "muons_before": 0,
        "muons_after_eta": 0,
    }
    event_files = sorted(data_path("bronze", f"dataset={dataset_id}", "events").glob("*.parquet"))
    workers = _worker_count(len(event_files))
    if workers > 1:
        completed: list[dict[str, Any]] = []
        failures: list[str] = []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_process_silver_part, str(path), dataset_id, config): path
                for path in event_files
            }
            for future in as_completed(futures):
                try:
                    completed.append(future.result())
                except Exception as exc:  # noqa: BLE001 - surface worker failures with traceback
                    path = futures[future]
                    failures.append(f"{path.name}: {exc!r}\n{traceback.format_exc()}")
        if failures:
            raise RuntimeError("Silver part processing failed:\n" + "\n".join(failures))
        for result in sorted(completed, key=lambda item: item["part"]):
            for key in ("events_before", "events_after", "muons_before", "muons_after_eta"):
                metrics[key] += result[key]
            safe_log(logger, logging.INFO, result["log"])
            add_stage_stats(
                "silver",
                batches=1,
                rows_out=result["events_after"] + result["muons_after_eta"],
                events=result["events_after"],
                muons=result["muons_after_eta"],
            )
    else:
        # Keep the original sequential path intact for reproducible debugging.
        for event_file in event_files:
            events = pd.read_parquet(event_file)
            certified = _apply_certification(events, config)
            kept_events = certified[certified["certified"].astype(bool)].reset_index(drop=True)
            metrics["events_before"] += len(events)
            metrics["events_after"] += len(kept_events)
            out_events = data_path("silver", f"dataset={dataset_id}", "events") / event_file.name
            kept_events.to_parquet(
                ensure_parent(out_events), index=False, compression=PARQUET_COMPRESSION
            )

            muons_before = 0
            muons_after_eta = 0
            muon_file = data_path("bronze", f"dataset={dataset_id}", "muons") / event_file.name
            if muon_file.exists():
                muons = pd.read_parquet(muon_file)
                cleaned_before_eta = _clean_muons(_filter_to_events(muons, kept_events))
                cleaned = cleaned_before_eta[cleaned_before_eta["eta"].abs() <= 2.4].reset_index(
                    drop=True
                )
                muons_before = len(cleaned_before_eta)
                muons_after_eta = len(cleaned)
                metrics["muons_before"] += len(cleaned_before_eta)
                metrics["muons_after_eta"] += len(cleaned)
                out_muons = data_path("silver", f"dataset={dataset_id}", "muons") / event_file.name
                cleaned.to_parquet(
                    ensure_parent(out_muons), index=False, compression=PARQUET_COMPRESSION
                )
            certified_fraction = len(kept_events) / len(events) if len(events) else 0.0
            eta_drop_fraction = (
                (muons_before - muons_after_eta) / muons_before if muons_before else 0.0
            )
            safe_log(
                logger,
                logging.INFO,
                "part %s | events %s -> %s certified (%.1f%%) | muons %s -> %s after eta cleaning (%.1f%% drop)",
                event_file.name,
                f"{len(events):,}",
                f"{len(kept_events):,}",
                100.0 * certified_fraction,
                f"{muons_before:,}",
                f"{muons_after_eta:,}",
                100.0 * eta_drop_fraction,
            )
            add_stage_stats(
                "silver",
                batches=1,
                rows_out=len(kept_events) + muons_after_eta,
                events=len(kept_events),
                muons=muons_after_eta,
            )
    if metrics["events_before"] == 0:
        raise FileNotFoundError(f"No bronze event files found for {dataset_id}")
    metrics["certified_fraction"] = metrics["events_after"] / metrics["events_before"]
    metrics["eta_drop_fraction"] = (
        (metrics["muons_before"] - metrics["muons_after_eta"]) / metrics["muons_before"]
        if metrics["muons_before"]
        else 0.0
    )
    metrics_path = data_dir("silver", f"dataset={dataset_id}") / "certification_metrics.json"
    ensure_parent(metrics_path).write_text(
        json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8"
    )
    return data_dir("silver", f"dataset={dataset_id}")


def _worker_count(n_parts: int) -> int:
    override = os.environ.get("COLLIDERLAKE_WORKERS")
    if override is not None:
        try:
            return max(1, min(int(override), n_parts))
        except ValueError as exc:
            raise ValueError("COLLIDERLAKE_WORKERS must be a positive integer") from exc
    return max(1, min((os.cpu_count() or 1) - 1, n_parts))


def _process_silver_part(
    event_path: str, dataset_id: str, config: dict[str, Any]
) -> dict[str, Any]:
    event_file = Path(event_path)
    events = pd.read_parquet(event_file)
    kept_events = _apply_certification(events, config)
    kept_events = kept_events[kept_events["certified"].astype(bool)].reset_index(drop=True)
    out_events = data_path("silver", f"dataset={dataset_id}", "events") / event_file.name
    kept_events.to_parquet(ensure_parent(out_events), index=False, compression=PARQUET_COMPRESSION)
    muons_before = muons_after_eta = 0
    muon_file = data_path("bronze", f"dataset={dataset_id}", "muons") / event_file.name
    if muon_file.exists():
        muons = pd.read_parquet(muon_file)
        cleaned_before_eta = _clean_muons(_filter_to_events(muons, kept_events))
        cleaned = cleaned_before_eta[cleaned_before_eta["eta"].abs() <= 2.4].reset_index(drop=True)
        muons_before, muons_after_eta = len(cleaned_before_eta), len(cleaned)
        out_muons = data_path("silver", f"dataset={dataset_id}", "muons") / event_file.name
        cleaned.to_parquet(ensure_parent(out_muons), index=False, compression=PARQUET_COMPRESSION)
    certified_fraction = len(kept_events) / len(events) if len(events) else 0.0
    eta_drop_fraction = (muons_before - muons_after_eta) / muons_before if muons_before else 0.0
    log = (
        f"part {event_file.name} | events {len(events):,} -> {len(kept_events):,} certified ({100 * certified_fraction:.1f}%) | "
        f"muons {muons_before:,} -> {muons_after_eta:,} after eta cleaning ({100 * eta_drop_fraction:.1f}% drop)"
    )
    return {
        "part": event_file.name,
        "events_before": len(events),
        "events_after": len(kept_events),
        "muons_before": muons_before,
        "muons_after_eta": muons_after_eta,
        "log": log,
    }


def _apply_certification(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    certification = config.get("certification")
    if certification == "prefiltered":
        output["certified"] = True
        output["certification_source"] = "prefiltered"
        return output
    if isinstance(certification, dict) and certification.get("golden_json_file"):
        json_path = configured_data_path(certification["golden_json_file"])
        if not json_path.exists():
            output["certified"] = False
            output["certification_source"] = "missing_golden_json"
            return output
        intervals = json.loads(json_path.read_text(encoding="utf-8"))
        output["certified"] = [
            _is_certified(int(run), int(lumi), intervals)
            for run, lumi in zip(output["run"], output["luminosityBlock"], strict=False)
        ]
        output["certification_source"] = str(json_path.relative_to(data_path()))
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
    mask &= np.isfinite(output["eta"])
    mask &= np.isfinite(output["phi"])
    if "iso" in output.columns:
        iso = pd.to_numeric(output["iso"], errors="coerce")
        mask &= iso.isna() | (np.isfinite(iso) & (iso >= 0.0))
    return output[mask].reset_index(drop=True)
