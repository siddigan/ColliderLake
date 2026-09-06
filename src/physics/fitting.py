from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.config import load_yaml
from src.utils.paths import config_path, data_path


def fit_resonance(dataset_id: str) -> Path:
    gold_dir = data_path("gold", "analysis=resonance", f"dataset={dataset_id}", "dimuon")
    files = sorted(gold_dir.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No gold dimuon files found under {gold_dir}")
    dimuon = pd.concat((pd.read_parquet(file) for file in files), ignore_index=True)
    fits = load_yaml(config_path("fits", "resonance_ladder.yaml"))["fits"]
    rows = [_fit_window(name, config, dimuon["mass"].to_numpy(dtype=float)) for name, config in fits.items()]
    output_dir = data_path("results", "analysis=resonance", f"dataset={dataset_id}")
    frame = pd.DataFrame(rows)
    parquet_path = output_dir / "fits.parquet"
    json_path = output_dir / "fits.json"
    frame.to_parquet(parquet_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return output_dir


def _fit_window(name: str, config: dict, masses: np.ndarray) -> dict:
    low, high = config["window"]
    selected = masses[(masses >= low) & (masses <= high)]
    pdg_mass = config.get("pdg_mass")
    if pdg_mass is None and config.get("pdg_masses"):
        pdg_mass = config["pdg_masses"][0]
    if selected.size == 0:
        return {
            "resonance": name,
            "status": "empty",
            "yield": 0,
            "mass_fit": None,
            "mass_stat_unc": None,
            "width": None,
            "pdg_mass": pdg_mass,
            "delta_pdg_sigma": None,
        }
    mass_fit = float(np.mean(selected))
    width = float(np.std(selected, ddof=1)) if selected.size > 1 else 0.0
    stat_unc = width / float(np.sqrt(selected.size)) if selected.size > 1 else None
    delta = ((mass_fit - float(pdg_mass)) / stat_unc) if stat_unc else None
    return {
        "resonance": name,
        "status": "converged_moment_estimate",
        "yield": int(selected.size),
        "mass_fit": mass_fit,
        "mass_stat_unc": stat_unc,
        "width": width,
        "pdg_mass": pdg_mass,
        "delta_pdg_sigma": delta,
    }
