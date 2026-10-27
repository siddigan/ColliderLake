from __future__ import annotations

import shutil

import pandas as pd
import pytest

from src.dq.checks import run_dq
from src.gold.dimuon import _event_pairs
from src.utils.paths import data_path, ensure_parent

SELECTION = {
    "muon": {"pt_min": 3.0, "abs_eta_max": 2.4},
    "pair": {"opposite_charge": True},
    "trigger": {"paths": []},
    "mass_window": [0.25, 300.0],
}


def test_three_muon_event_has_two_canonical_pairs_and_gold_gate_passes(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    event = _event(1)
    rows = _event_pairs(event, _muons([10.0, 8.0, 4.0], [1, -1, -1]), SELECTION, "deadbeef")
    assert len(rows) == 2
    assert {row["pair_idx"] for row in rows} == {0, 1}
    assert rows[0]["pt_pair"] > rows[1]["pt_pair"]
    assert all(row["mu1_idx"] < row["mu2_idx"] for row in rows)

    path = ensure_parent(data_path("gold", "analysis=resonance", "dataset=toy", "dimuon", "part.parquet"))
    pd.DataFrame(rows).to_parquet(path, index=False)
    report = run_dq("toy", "gold", path)
    assert report["passed"]


def test_four_muon_event_has_all_four_os_pairs():
    rows = _event_pairs(_event(2), _muons([10.0, 9.0, 8.0, 7.0], [1, 1, -1, -1]), SELECTION, "deadbeef")
    assert len(rows) == 4
    assert {row["pair_idx"] for row in rows} == {0, 1, 2, 3}
    assert all(row["mu1_idx"] < row["mu2_idx"] for row in rows)


def test_gold_gate_rejects_true_duplicate_pair_key(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    rows = _event_pairs(_event(3), _muons([10.0, 8.0, 4.0], [1, -1, -1]), SELECTION, "deadbeef")
    duplicate = pd.DataFrame([rows[0], rows[0]])
    path = ensure_parent(data_path("gold", "analysis=resonance", "dataset=toy", "dimuon", "duplicate.parquet"))
    duplicate.to_parquet(path, index=False)
    with pytest.raises(RuntimeError, match="duplicate key"):
        run_dq("toy", "gold", path)


def _prepare_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")


def _event(number: int) -> pd.Series:
    return pd.Series(
        {
            "dataset_id": "toy",
            "run": 1,
            "luminosityBlock": 1,
            "event": number,
            "identity_mode": "synthetic",
        }
    )


def _muons(pts: list[float], charges: list[int]) -> list[dict[str, float | int]]:
    return [
        {
            "muon_idx": index,
            "pt": pt,
            "eta": 0.0,
            "phi": 0.7 * index,
            "mass": 0.1056583755,
            "charge": charge,
        }
        for index, (pt, charge) in enumerate(zip(pts, charges, strict=True))
    ]
