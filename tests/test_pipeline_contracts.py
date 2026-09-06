import math
import shutil
from pathlib import Path

import awkward as ak
import pandas as pd

from src.bronze.convert import build_bronze
from src.cli import run_pipeline
from src.physics.pdg import JPSI_MASS_GEV, MUON_MASS_GEV


def test_synthetic_identity_bronze_for_2012_six_branch_root(tmp_path, monkeypatch):
    _prepare_project_root(tmp_path, monkeypatch)
    _write_synthetic_2012_root(tmp_path / "data/raw/run2012bc_doublemuparked/sample.root")

    bronze_root = build_bronze("run2012bc_doublemuparked", max_batches=2)
    events = pd.read_parquet(bronze_root / "events/sample_part_0000.parquet")
    muons = pd.read_parquet(bronze_root / "muons/sample_part_0000.parquet")

    assert list(events["event"]) == [0, 1, 2]
    assert set(events["identity_mode"]) == {"synthetic"}
    assert {"dataset_id", "run", "luminosityBlock", "event", "_source_sha256"} <= set(muons.columns)
    assert len(muons) == 6


def test_stage_all_completes_on_synthetic_2012_file(tmp_path, monkeypatch):
    _prepare_project_root(tmp_path, monkeypatch)
    _write_synthetic_2012_root(tmp_path / "data/raw/run2012bc_doublemuparked/sample.root")

    run_pipeline("run2012bc_doublemuparked", "all", max_batches=2)

    fits = pd.read_parquet(
        tmp_path / "data/results/analysis=resonance/dataset=run2012bc_doublemuparked/fits.parquet"
    )
    jpsi = fits[fits["resonance"] == "jpsi"].iloc[0]
    assert jpsi["status"] == "valid"
    assert abs(jpsi["mass_fit"] - JPSI_MASS_GEV) < 0.05


def _prepare_project_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    shutil.copytree("configs", tmp_path / "configs")
    raw = tmp_path / "data/raw/run2012bc_doublemuparked"
    raw.mkdir(parents=True)


def _write_synthetic_2012_root(path: Path) -> None:
    import uproot

    mass = _opening_angle_mass(JPSI_MASS_GEV)
    pt = 10.0
    dphi = math.acos(1.0 - ((mass**2 - 2.0 * MUON_MASS_GEV**2) / (2.0 * pt**2)))
    with uproot.recreate(path) as root_file:
        root_file["Events"] = {
            "nMuon": ak.Array([2, 2, 2]),
            "Muon_pt": ak.Array([[pt, pt], [pt, pt], [pt, pt]]),
            "Muon_eta": ak.Array([[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]),
            "Muon_phi": ak.Array([[0.0, dphi], [0.0, dphi], [0.0, dphi]]),
            "Muon_mass": ak.Array([[MUON_MASS_GEV, MUON_MASS_GEV]] * 3),
            "Muon_charge": ak.Array([[1, -1], [1, -1], [1, -1]]),
        }


def _opening_angle_mass(target: float) -> float:
    return target
