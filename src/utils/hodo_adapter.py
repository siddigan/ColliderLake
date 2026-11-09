"""ColliderLake-specific context and preflight values for Hodoscope."""

from __future__ import annotations

import hashlib
import multiprocessing
import os
from typing import Any

from src.utils.config import (
    fit_config_id,
    gold_engine,
    load_yaml,
    selection_for_dataset,
)
from src.utils.paths import config_path, data_root


def resolved_inputs(
    dataset_id: str, engine: str | None = None, analysis: str | None = None
) -> dict[str, Any]:
    _selection_path, selection, selected_id = selection_for_dataset(dataset_id, analysis)
    fit_path = config_path("fits", "resonance_ladder.yaml")
    fit_config = load_yaml(fit_path)
    io_path = config_path("io.yaml")
    io_digest = hashlib.sha256(io_path.read_bytes()).hexdigest() if io_path.exists() else None
    gold_path = config_path("gold.yaml")
    gold_digest = hashlib.sha256(gold_path.read_bytes()).hexdigest() if gold_path.exists() else None
    figures_path = config_path("figures.yaml")
    figures_digest = (
        hashlib.sha256(figures_path.read_bytes()).hexdigest() if figures_path.exists() else None
    )
    requested_workers = os.environ.get("COLLIDERLAKE_WORKERS", "auto")
    cpu_limit = max(1, (multiprocessing.cpu_count() or 1) - 1)
    resolved_workers = (
        f"auto (up to {cpu_limit}; capped by available Parquet parts)"
        if requested_workers == "auto"
        else f"{max(1, int(requested_workers))} (capped by available Parquet parts)"
    )
    return {
        "dataset_id": dataset_id,
        "analysis": selection["analysis"],
        "engine": gold_engine(engine),
        "selection_id": selected_id,
        "fit_config_id": fit_config_id(fit_config),
        "fit_windows": {name: fit["window"] for name, fit in fit_config.get("fits", {}).items()},
        "io_config_sha256": io_digest,
        "gold_config_sha256": gold_digest,
        "figures_config_sha256": figures_digest,
        "workers": resolved_workers,
        "workers_requested": requested_workers,
        "data_root": str(data_root().resolve()),
    }


def context_provider(dataset_id: str, engine: str | None = None, analysis: str | None = None):
    def provider() -> dict[str, Any]:
        inputs = resolved_inputs(dataset_id, engine, analysis)
        return {
            "dataset_id": inputs["dataset_id"],
            "analysis": inputs["analysis"],
            "engine": inputs["engine"],
            "selection_id": inputs["selection_id"],
            "fit_config_id": inputs["fit_config_id"],
            "io_config_sha256": inputs["io_config_sha256"],
            "gold_config_sha256": inputs["gold_config_sha256"],
            "figures_config_sha256": inputs["figures_config_sha256"],
            "workers": inputs["workers"],
            "workers_requested": inputs["workers_requested"],
            "data_root": inputs["data_root"],
            "fixture_size": os.environ.get(
                "COLLIDERLAKE_BENCH_FIXTURE_SIZE", "configured silver input"
            ),
            "gold_max_parts": os.environ.get("COLLIDERLAKE_GOLD_MAX_PARTS", "all"),
            "duckdb_threads": int(os.environ.get("COLLIDERLAKE_DUCKDB_THREADS", "2")),
            "duckdb_memory_limit": os.environ.get("COLLIDERLAKE_DQ_MEM", "2GB"),
            **{f"fit_window_{key}": value for key, value in inputs["fit_windows"].items()},
        }

    provider.__name__ = "colliderlake_inputs"
    return provider


def preflight_values(run_id: str, inputs: dict[str, Any], git: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "commit": git.get("commit"),
        "dirty": git.get("dirty", False),
        "dirty_files": git.get("dirty_files", []),
        "selection_id": inputs["selection_id"],
        "analysis": inputs.get("analysis", "resonance"),
        "engine": inputs.get("engine", "vectorized"),
        "fit_config_id": inputs["fit_config_id"],
        "fit_windows": inputs["fit_windows"],
        "workers": inputs["workers"],
        "workers_requested": inputs["workers_requested"],
        "data_root": inputs["data_root"],
    }
