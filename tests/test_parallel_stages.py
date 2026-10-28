from __future__ import annotations

import shutil

import pandas as pd

from src.cli import run_pipeline
from src.gold.dimuon import build_gold
from src.utils.paths import data_path, ensure_parent
from tests.test_pipeline_contracts import _prepare_project_root, _write_synthetic_2012_root


def _run(tmp_path, monkeypatch, workers: int):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _prepare_project_root(tmp_path, monkeypatch)
    _write_synthetic_2012_root(
        data_path("raw", "run2012bc_doublemuparked", "sample.root"), n_events=20_000
    )
    monkeypatch.setenv("COLLIDERLAKE_WORKERS", str(workers))
    run_pipeline("run2012bc_doublemuparked", "all", max_batches=3, quiet=True)
    gold_files = sorted(
        (
            data_path("gold", "analysis=resonance", "dataset=run2012bc_doublemuparked", "dimuon")
        ).glob("*.parquet")
    )
    gold = pd.concat([pd.read_parquet(path) for path in gold_files], ignore_index=True)
    fits = (
        pd.read_parquet(
            data_path(
                "results", "analysis=resonance", "dataset=run2012bc_doublemuparked", "fits.parquet"
            )
        )
        .sort_values("resonance")
        .reset_index(drop=True)
    )
    return gold.sort_values(
        ["dataset_id", "run", "luminosityBlock", "event", "pair_idx"]
    ).reset_index(drop=True), fits


def test_workers_one_and_four_preserve_gold_and_fit_outputs(tmp_path, monkeypatch):
    serial_gold, serial_fits = _run(tmp_path / "serial", monkeypatch, 1)
    parallel_gold, parallel_fits = _run(tmp_path / "parallel", monkeypatch, 4)
    pd.testing.assert_frame_equal(
        serial_gold, parallel_gold, check_dtype=True, check_exact=False, rtol=0, atol=1e-9
    )
    pd.testing.assert_frame_equal(
        serial_fits, parallel_fits, check_dtype=True, check_exact=False, rtol=0, atol=1e-9
    )


def test_gold_multiplicity_metrics_aggregate_max_and_count(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")
    events = pd.DataFrame(
        {
            "dataset_id": ["run2012bc_doublemuparked"] * 2,
            "run": [1, 1],
            "luminosityBlock": [1, 1],
            "event": [10, 11],
            "identity_mode": ["synthetic"] * 2,
        }
    )
    rows = []
    for event, multiplicity in ((10, 65), (11, 70)):
        for index in range(multiplicity):
            rows.append(
                {
                    "dataset_id": "run2012bc_doublemuparked",
                    "run": 1,
                    "luminosityBlock": 1,
                    "event": event,
                    "muon_idx": index,
                    "pt": 4.0,
                    "eta": 0.0,
                    "phi": index * 0.01,
                    "mass": 0.1056583755,
                    "charge": 1 if index % 2 == 0 else -1,
                }
            )
    events.to_parquet(
        ensure_parent(
            data_path("silver", "dataset=run2012bc_doublemuparked", "events", "part.parquet")
        ),
        index=False,
    )
    pd.DataFrame(rows).to_parquet(
        ensure_parent(
            data_path("silver", "dataset=run2012bc_doublemuparked", "muons", "part.parquet")
        ),
        index=False,
    )
    build_gold("run2012bc_doublemuparked")
    metrics = pd.read_json(
        data_path(
            "gold",
            "analysis=resonance",
            "dataset=run2012bc_doublemuparked",
            "dimuon",
            "multiplicity_metrics.json",
        ),
        typ="series",
    )
    assert metrics["muons_per_event_max"] == 70
    assert metrics["events_above_half_max"] == 2
