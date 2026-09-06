from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from iminuit import Minuit

from src.physics.models import ModelSpec, background_model, signal_model
from src.physics.pdg import UPSILON_1S_MASS_GEV
from src.utils.config import load_yaml
from src.utils.paths import config_path, data_path


def fit_resonance(dataset_id: str) -> Path:
    gold_dir = data_path("gold", "analysis=resonance", f"dataset={dataset_id}", "dimuon")
    files = sorted(gold_dir.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No gold dimuon files found under {gold_dir}")

    config = load_yaml(config_path("fits", "resonance_ladder.yaml"))
    rows: list[dict[str, Any]] = []
    for file in files:
        frame = pd.read_parquet(file, columns=["mass", "selection_id"])
        masses = frame["mass"].to_numpy(dtype=float)
        selection_ids = sorted(str(value) for value in frame["selection_id"].dropna().unique())
        selection_id = selection_ids[0] if selection_ids else ""
        for resonance, fit_config in config["fits"].items():
            window = tuple(float(value) for value in fit_config["window"])
            if _count_in_window(masses, window) == 0:
                continue
            rows.append(fit_masses(resonance, fit_config, masses, selection_id, config))

    if not rows:
        raise RuntimeError(f"No configured resonance windows contained data for {dataset_id}")

    output_dir = data_path("results", "analysis=resonance", f"dataset={dataset_id}")
    pd.DataFrame(rows).to_parquet(output_dir / "fits.parquet", index=False)
    (output_dir / "fits.json").write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return output_dir


def fit_masses(
    resonance: str,
    config: dict[str, Any],
    masses: np.ndarray,
    selection_id: str = "",
    root_config: dict[str, Any] | None = None,
    initial_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    window = (float(config["window"][0]), float(config["window"][1]))
    n_bins = int(config.get("n_bins", (root_config or {}).get("default_n_bins", 100)))
    selected = masses[np.isfinite(masses) & (masses >= window[0]) & (masses <= window[1])]
    if selected.size == 0:
        raise RuntimeError(f"No masses found in fit window for {resonance}: {window}")

    counts, edges = np.histogram(selected, bins=n_bins, range=window)
    signal = signal_model(str(config["signal"]), resonance, window)
    background = background_model(str(config["background"]), window)
    cost = ExtendedBinnedNLL(counts, edges, signal, background)
    initial = _initial_values(counts, signal, background, initial_overrides)
    _validate_initial(initial)

    minuit = Minuit(cost, **initial)
    minuit.errordef = Minuit.LIKELIHOOD
    for name, limits in cost.limits.items():
        minuit.limits[name] = limits
    minuit.migrad()
    minuit.hesse()
    if not minuit.fmin.is_valid:
        raise RuntimeError(
            f"Fit failed for {resonance}: fmin={minuit.fmin}, values={dict(minuit.values)}"
        )

    values = {name: float(minuit.values[name]) for name in minuit.parameters}
    errors = {name: float(minuit.errors[name]) for name in minuit.parameters}
    mass_fit = _mass_value(signal, values)
    mass_stat_unc = _mass_error(signal, errors)
    pdg_mass = _pdg_mass(config)
    return {
        "resonance": resonance,
        "status": "valid",
        "signal_yield": float(values["signal_yield"]),
        "background_yield": float(values["background_yield"]),
        "mass_fit": mass_fit,
        "mass_stat_unc": mass_stat_unc,
        "width": float(values[signal.width_parameter]),
        "chi2": _chi2(counts, cost.expected(values)),
        "ndf": int(max(len(counts) - len(values), 0)),
        "pdg_mass": pdg_mass,
        "delta_pdg_sigma": (mass_fit - pdg_mass) / mass_stat_unc if mass_stat_unc else None,
        "selection_id": selection_id,
        "n_bins": n_bins,
        "window": [window[0], window[1]],
    }


class ExtendedBinnedNLL:
    def __init__(
        self,
        counts: np.ndarray,
        edges: np.ndarray,
        signal: ModelSpec,
        background: ModelSpec,
    ) -> None:
        self.counts = counts.astype(float)
        self.edges = edges.astype(float)
        self.centers = 0.5 * (self.edges[:-1] + self.edges[1:])
        self.window = (float(self.edges[0]), float(self.edges[-1]))
        self.signal = signal
        self.background = background
        self.names = ["signal_yield", "background_yield"]
        self.names.extend(signal.parameter_defaults)
        self.names.extend(background.parameter_defaults)
        self.limits = {
            "signal_yield": (0.0, None),
            "background_yield": (0.0, None),
            **signal.parameter_limits,
            **background.parameter_limits,
        }
        self.__signature__ = inspect.Signature(
            [
                inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                for name in self.names
            ]
        )

    def __call__(self, *args: float) -> float:
        params = dict(zip(self.names, args, strict=True))
        expected = self.expected(params)
        if not np.all(np.isfinite(expected)) or np.any(expected <= 0.0):
            return math.inf
        return float(2.0 * np.sum(expected - self.counts * np.log(expected)))

    def expected(self, params: dict[str, float]) -> np.ndarray:
        signal_params = {name: params[name] for name in self.signal.parameter_defaults}
        background_params = {name: params[name] for name in self.background.parameter_defaults}
        signal = self.signal.pdf(self.centers, signal_params, self.window)
        background = self.background.pdf(self.centers, background_params, self.window)
        return params["signal_yield"] * signal + params["background_yield"] * background


def _initial_values(
    counts: np.ndarray,
    signal: ModelSpec,
    background: ModelSpec,
    overrides: dict[str, float] | None,
) -> dict[str, float]:
    total = float(np.sum(counts))
    values = {
        "signal_yield": max(total * 0.5, 1.0),
        "background_yield": max(total * 0.5, 1.0),
        **signal.parameter_defaults,
        **background.parameter_defaults,
    }
    if overrides:
        values.update(overrides)
    return values


def _validate_initial(values: dict[str, float]) -> None:
    for name in ("signal_yield", "background_yield", "sigma", "wide_sigma", "width_scale"):
        if name in values and values[name] <= 0.0:
            raise RuntimeError(f"Invalid non-positive initial value for {name}: {values[name]}")


def _pdg_mass(config: dict[str, Any]) -> float:
    if "pdg_mass" in config:
        return float(config["pdg_mass"])
    return float(config["pdg_masses"][0])


def _mass_value(signal: ModelSpec, values: dict[str, float]) -> float:
    if signal.name == "triple_gaussian":
        return UPSILON_1S_MASS_GEV + values["offset"]
    return float(values[signal.mass_parameter])


def _mass_error(signal: ModelSpec, errors: dict[str, float]) -> float | None:
    parameter = "offset" if signal.name == "triple_gaussian" else signal.mass_parameter
    value = errors.get(parameter)
    return float(value) if value else None


def _chi2(observed: np.ndarray, expected: np.ndarray) -> float:
    mask = expected > 0.0
    return float(np.sum((observed[mask] - expected[mask]) ** 2 / expected[mask]))


def _count_in_window(masses: np.ndarray, window: tuple[float, float]) -> int:
    return int(np.sum(np.isfinite(masses) & (masses >= window[0]) & (masses <= window[1])))
