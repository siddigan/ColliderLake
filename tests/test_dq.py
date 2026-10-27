import json
import shutil

import pandas as pd
import pytest

from src.dq.checks import run_dq
from src.silver.build import build_silver
from src.utils.paths import data_path


def test_dq_passes_good_muons(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    path = data_path("silver", "dataset=run2012bc_doublemuparked", "muons", "part.parquet")
    _write_parquet(
        path,
        {
            "dataset_id": ["run2012bc_doublemuparked"],
            "run": [1],
            "luminosityBlock": [1],
            "event": [1],
            "muon_idx": [0],
            "pt": [3.0],
            "eta": [0.1],
            "iso": [None],
        },
    )
    report = run_dq("run2012bc_doublemuparked", "silver", path)
    assert report["passed"]


def test_dq_fails_bad_muon_pt(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    path = data_path("silver", "dataset=run2012bc_doublemuparked", "muons", "part.parquet")
    _write_parquet(
        path,
        {
            "dataset_id": ["run2012bc_doublemuparked"],
            "run": [1],
            "luminosityBlock": [1],
            "event": [1],
            "muon_idx": [0],
            "pt": [0.0],
            "eta": [0.1],
        },
    )
    with pytest.raises(RuntimeError, match="muon pt"):
        run_dq("run2012bc_doublemuparked", "silver", path)


def test_dq_fails_certification_fraction_band(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    path = data_path("silver", "dataset=run2012bc_doublemuparked", "events", "part.parquet")
    _write_parquet(
        path,
        {
            "dataset_id": ["run2012bc_doublemuparked"],
            "run": [1],
            "luminosityBlock": [1],
            "event": [1],
        },
    )
    metrics = data_path("silver", "dataset=run2012bc_doublemuparked") / "certification_metrics.json"
    metrics.write_text(
        json.dumps({"events_before": 10, "events_after": 5, "certified_fraction": 0.5}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="certified_fraction"):
        run_dq("run2012bc_doublemuparked", "silver", path)


def test_dq_fails_row_count_history_delta(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    path = data_path("bronze", "dataset=run2012bc_doublemuparked", "events", "part.parquet")
    _write_parquet(
        path,
        {
            "dataset_id": ["run2012bc_doublemuparked"] * 10,
            "run": [1] * 10,
            "luminosityBlock": [1] * 10,
            "event": list(range(10)),
        },
    )
    assert run_dq("run2012bc_doublemuparked", "bronze", path)["passed"]
    _write_parquet(
        path,
        {
            "dataset_id": ["run2012bc_doublemuparked"] * 20,
            "run": [1] * 20,
            "luminosityBlock": [1] * 20,
            "event": list(range(20)),
        },
    )
    with pytest.raises(RuntimeError, match="row count"):
        run_dq("run2012bc_doublemuparked", "bronze", path)


def test_eta_is_structural_in_bronze_and_cleaned_per_muon_in_silver(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    events = data_path("bronze", "dataset=run2012bc_doublemuparked", "events", "part.parquet")
    muons = data_path("bronze", "dataset=run2012bc_doublemuparked", "muons", "part.parquet")
    _write_parquet(
        events,
        {
            "dataset_id": ["run2012bc_doublemuparked"],
            "run": [1],
            "luminosityBlock": [1],
            "event": [1],
        },
    )
    _write_parquet(
        muons,
        {
            "dataset_id": ["run2012bc_doublemuparked"] * 3,
            "run": [1] * 3,
            "luminosityBlock": [1] * 3,
            "event": [1] * 3,
            "muon_idx": [0, 1, 2],
            "pt": [4.0, 5.0, 6.0],
            "eta": [1.0, -0.5, 2.6],
            "phi": [0.0, 1.0, 2.0],
            "mass": [0.1056583755] * 3,
            "charge": [1, -1, -1],
        },
    )

    assert run_dq("run2012bc_doublemuparked", "bronze", data_path("bronze", "dataset=run2012bc_doublemuparked"))["passed"]
    build_silver("run2012bc_doublemuparked")
    report = run_dq("run2012bc_doublemuparked", "silver", data_path("silver", "dataset=run2012bc_doublemuparked"))
    cleaned = pd.read_parquet(data_path("silver", "dataset=run2012bc_doublemuparked", "muons", "part.parquet"))
    assert set(cleaned["muon_idx"]) == {0, 1}
    assert report["passed"]
    assert report["metrics"]["muons_before"] == 3
    assert report["metrics"]["muons_after_eta"] == 2
    assert report["metrics"]["eta_drop_fraction"] == pytest.approx(1 / 3)
    assert report["metrics"]["events_before"] == 1
    assert report["metrics"]["events_after"] == 1
    assert report["metrics"]["certified_fraction"] == 1.0


def _prepare_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")


def _write_parquet(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(data).to_parquet(path, index=False)
