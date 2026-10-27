from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import awkward as ak
import numpy as np
import pandas as pd

from src.cli import run_pipeline
from src.physics.muons import invariant_mass
from src.physics.pdg import JPSI_MASS_GEV, MUON_MASS_GEV
from src.utils.paths import data_path, data_root, ensure_parent
from tests.fit_assertions import assert_valid_fit


def test_decay_correct_fixture_runs_isolated_pipeline(tmp_path, monkeypatch):
    repo_data = Path("data")
    before_repo_data = (
        {item: item.stat().st_mtime_ns for item in repo_data.rglob("*")}
        if repo_data.exists()
        else {}
    )
    _prepare_root(tmp_path, monkeypatch)
    source = ensure_parent(data_path("raw", "run2012bc_doublemuparked", "fixture.root"))
    _write_decay_fixture(source, n_events=20_000, seed=20261028)

    run_pipeline("run2012bc_doublemuparked", "all", max_batches=2)

    gold_files = sorted(data_path("gold").rglob("*.parquet"))
    gold = pd.concat((pd.read_parquet(path) for path in gold_files), ignore_index=True)
    event_count = gold[["dataset_id", "run", "luminosityBlock", "event"]].drop_duplicates().shape[0]
    assert len(gold) > event_count
    assert int(((gold["mass"] >= 2.80) & (gold["mass"] <= 3.00)).sum()) >= 500
    assert int(((gold["mass"] >= 3.20) & (gold["mass"] <= 3.40)).sum()) >= 500

    fits_path = data_path("results", "analysis=resonance", "dataset=run2012bc_doublemuparked", "fits.parquet")
    fits = pd.read_parquet(fits_path)
    jpsi = fits[fits["resonance"] == "jpsi"].iloc[0]
    assert_valid_fit(jpsi, JPSI_MASS_GEV, 0.05)

    report = json.loads((data_path("results") / "dq_report.json").read_text(encoding="utf-8"))
    assert report and all(entry["passed"] for entry in report)
    assert (data_root() / "raw" / "run2012bc_doublemuparked" / "MANIFEST.json").exists()
    assert (data_root() / "bronze").exists()
    assert (data_root() / "silver").exists()
    assert (data_root() / "gold").exists()
    assert (data_root() / "results").exists()
    after_repo_data = (
        {item: item.stat().st_mtime_ns for item in repo_data.rglob("*")}
        if repo_data.exists()
        else {}
    )
    assert after_repo_data == before_repo_data


def _prepare_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")


def _write_decay_fixture(path: Path, n_events: int, seed: int) -> None:
    import uproot

    rng = np.random.default_rng(seed)
    branches = {name: [] for name in ("nMuon", "Muon_pt", "Muon_eta", "Muon_phi", "Muon_mass", "Muon_charge")}
    for event_index in range(n_events):
        if event_index < 9_000:
            muons = list(_jpsi_decay(rng))
        elif event_index < 16_000:
            target = rng.uniform(2.80, 3.40)
            muons = _background_pair(target)
        else:
            muons = list(_jpsi_decay(rng))
            extra_eta = 0.3 if event_index % 2 else 2.6
            muons.append((3.5, extra_eta, 2.4, MUON_MASS_GEV, -1))
        branches["nMuon"].append(len(muons))
        branches["Muon_pt"].append([muon[0] for muon in muons])
        branches["Muon_eta"].append([muon[1] for muon in muons])
        branches["Muon_phi"].append([muon[2] for muon in muons])
        branches["Muon_mass"].append([muon[3] for muon in muons])
        branches["Muon_charge"].append([muon[4] for muon in muons])
    path.parent.mkdir(parents=True, exist_ok=True)
    with uproot.recreate(path) as root_file:
        root_file["Events"] = {name: ak.Array(values) for name, values in branches.items()}


def _jpsi_decay(rng: np.random.Generator) -> tuple[tuple[float, float, float, float, int], ...]:
    for _ in range(10_000):
        mass = float(rng.normal(JPSI_MASS_GEV, 0.03))
        pt_parent = float(rng.uniform(8.0, 20.0))
        rapidity = float(rng.uniform(-1.0, 1.0))
        phi_parent = float(rng.uniform(-math.pi, math.pi))
        mt = math.sqrt(mass**2 + pt_parent**2)
        p_parent = np.array(
            [pt_parent * math.cos(phi_parent), pt_parent * math.sin(phi_parent), mt * math.sinh(rapidity)],
            dtype=np.float64,
        )
        e_parent = math.sqrt(mass**2 + float(np.dot(p_parent, p_parent)))
        beta = p_parent / e_parent
        gamma = e_parent / mass
        p_star = math.sqrt(mass**2 / 4.0 - MUON_MASS_GEV**2)
        cos_theta = float(rng.uniform(-1.0, 1.0))
        sin_theta = math.sqrt(1.0 - cos_theta**2)
        phi_star = float(rng.uniform(-math.pi, math.pi))
        rest_p1 = p_star * np.array(
            [sin_theta * math.cos(phi_star), sin_theta * math.sin(phi_star), cos_theta],
            dtype=np.float64,
        )
        rest_p2 = -rest_p1
        rest_energy = mass / 2.0
        daughters = [_boost(rest_p1, rest_energy, beta, gamma), _boost(rest_p2, rest_energy, beta, gamma)]
        total_energy = daughters[0][0] + daughters[1][0]
        total_momentum = daughters[0][1] + daughters[1][1]
        assert abs(total_energy - e_parent) < 1e-9
        assert np.all(np.abs(total_momentum - p_parent) < 1e-9)
        converted = (
            _to_branch_values(daughters[0], 1),
            _to_branch_values(daughters[1], -1),
        )
        if all(pt > 3.0 and abs(eta) < 2.4 for pt, eta, _, _, _ in converted):
            assert abs(invariant_mass(*converted[0][:3], *converted[1][:3], MUON_MASS_GEV, MUON_MASS_GEV) - mass) < 1e-6
            return converted
    raise AssertionError("could not generate an accepted J/psi decay")


def _boost(momentum: np.ndarray, energy: float, beta: np.ndarray, gamma: float) -> tuple[float, np.ndarray]:
    beta2 = float(np.dot(beta, beta))
    coefficient = (gamma - 1.0) / beta2 if beta2 else 0.0
    dot = float(np.dot(beta, momentum))
    return gamma * (energy + dot), momentum + (coefficient * dot + gamma * energy) * beta


def _to_branch_values(energy_momentum: tuple[float, np.ndarray], charge: int) -> tuple[float, float, float, float, int]:
    _, momentum = energy_momentum
    px, py, pz = (float(value) for value in momentum)
    pt = math.hypot(px, py)
    total_p = math.sqrt(px**2 + py**2 + pz**2)
    eta = 0.5 * math.log((total_p + pz) / (total_p - pz))
    return pt, eta, math.atan2(py, px), MUON_MASS_GEV, charge


def _background_pair(mass: float) -> list[tuple[float, float, float, float, int]]:
    pt = 4.0
    cosine = 1.0 - (mass**2 - 4.0 * MUON_MASS_GEV**2) / (2.0 * pt**2)
    delta_phi = math.acos(cosine)
    return [
        (pt, 0.0, 0.0, MUON_MASS_GEV, 1),
        (pt, 0.0, delta_phi, MUON_MASS_GEV, -1),
    ]
