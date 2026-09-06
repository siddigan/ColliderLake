import json
import shutil

import pandas as pd
import pytest

from src.dq.checks import run_dq


def test_dq_passes_good_muons(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    path = tmp_path / "data/silver/dataset=run2012bc_doublemuparked/muons/part.parquet"
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
    path = tmp_path / "data/silver/dataset=run2012bc_doublemuparked/muons/part.parquet"
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
    path = tmp_path / "data/silver/dataset=run2012bc_doublemuparked/events/part.parquet"
    _write_parquet(
        path,
        {
            "dataset_id": ["run2012bc_doublemuparked"],
            "run": [1],
            "luminosityBlock": [1],
            "event": [1],
        },
    )
    metrics = tmp_path / "data/silver/dataset=run2012bc_doublemuparked/certification_metrics.json"
    metrics.write_text(
        json.dumps({"events_before": 10, "events_after": 5, "certified_fraction": 0.5}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="certified_fraction"):
        run_dq("run2012bc_doublemuparked", "silver", path)


def test_dq_fails_row_count_history_delta(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    path = tmp_path / "data/bronze/dataset=run2012bc_doublemuparked/events/part.parquet"
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


def _prepare_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    shutil.copytree("configs", tmp_path / "configs")


def _write_parquet(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(data).to_parquet(path, index=False)
