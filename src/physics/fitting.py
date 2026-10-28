from __future__ import annotations

import inspect
import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from iminuit import Minuit

from src.physics.models import ModelSpec, background_model, signal_model
from src.physics.pdg import UPSILON_1S_MASS_GEV
from src.utils.config import fit_config_id, load_yaml
from src.utils.paths import config_path, data_dir, data_path, ensure_parent
from src.utils.runlog import add_stage_stats, get_logger, safe_log


def fit_resonance(dataset_id: str) -> Path:
    logger = get_logger("fit")
    gold_dir = data_path("gold", "analysis=resonance", f"dataset={dataset_id}", "dimuon")
    files = sorted(gold_dir.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No gold dimuon files found under {gold_dir}")

    config = load_yaml(config_path("fits", "resonance_ladder.yaml"))
    config_id = fit_config_id(config)
    masses_parts: list[np.ndarray] = []
    selection_ids: set[str] = set()
    for file in files:
        frame = pd.read_parquet(file, columns=["mass", "selection_id"])
        masses_parts.append(frame["mass"].to_numpy(dtype=float))
        selection_ids.update(str(value) for value in frame["selection_id"].dropna().unique())

    masses = np.concatenate(masses_parts) if masses_parts else np.array([], dtype=float)
    selection_id = min(selection_ids) if selection_ids else ""
    rows: list[dict[str, Any]] = []
    for resonance, fit_config in config["fits"].items():
        window = tuple(float(value) for value in fit_config["window"])
        entries = _count_in_window(masses, window)
        safe_log(
            logger,
            logging.INFO,
            "pre-fit %s | window=[%g, %g] | entries=%s | model=%s + %s",
            resonance,
            window[0],
            window[1],
            f"{entries:,}",
            fit_config["signal"],
            fit_config["background"],
        )
        if entries == 0:
            continue
        row = fit_masses(resonance, fit_config, masses, selection_id, config)
        row["fit_config_id"] = config_id
        rows.append(row)
        reasons = _fit_validity_reasons(row)
        if reasons:
            safe_log(
                logger,
                logging.WARNING,
                "INVALID %s | reasons=%s",
                resonance,
                ", ".join(reasons),
            )
        else:
            safe_log(
                logger,
                logging.INFO,
                "fit %s PASS | mass=%.6g +/- %.6g | yield=%.6g | status=%s",
                resonance,
                row["mass_fit"],
                row["mass_stat_unc"],
                row["signal_yield"],
                row["status"],
            )
        add_stage_stats("fit", batches=1, rows_out=1)

    if not rows:
        raise RuntimeError(f"No configured resonance windows contained data for {dataset_id}")

    output_dir = data_dir("results", "analysis=resonance", f"dataset={dataset_id}")
    pd.DataFrame(rows).to_parquet(ensure_parent(output_dir / "fits.parquet"), index=False)
    ensure_parent(output_dir / "fits.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8"
    )
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
    minuit.errordef = 1.0
    for name, limits in cost.limits.items():
        minuit.limits[name] = limits
    minuit.migrad()
    minuit.hesse()
    status = _fit_status(minuit)

    values = {name: float(minuit.values[name]) for name in minuit.parameters}
    errors = {name: float(minuit.errors[name]) for name in minuit.parameters}
    mass_fit = _mass_value(signal, values)
    mass_stat_unc = _mass_error(signal, errors)
    pdg_mass = _pdg_mass(config)
    chi2 = _chi2(counts, cost.expected(values))
    ndf = int(max(len(counts) - len(values), 0))
    chi2_ndf = chi2 / ndf if ndf > 0 else math.inf
    return {
        "resonance": resonance,
        "status": status,
        "converged": bool(minuit.fmin.is_valid),
        "parameters_at_limit": _free_parameter_at_limit(minuit),
        "covariance_accurate": bool(getattr(minuit.fmin, "has_accurate_covar", False)),
        "covariance_posdef": bool(getattr(minuit.fmin, "has_posdef_covar", False)),
        "signal_yield": float(values["signal_yield"]),
        "background_yield": float(values["background_yield"]),
        "mass_fit": mass_fit,
        "mass_stat_unc": mass_stat_unc,
        "width": float(values[signal.width_parameter]),
        "width_stat_unc": float(errors[signal.width_parameter]),
        "chi2": chi2,
        "ndf": ndf,
        "gof_flag": "poor" if chi2_ndf > 5.0 else "ok",
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


def _fit_validity_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if row.get("status") != "valid":
        reasons.append(f"status={row.get('status')}")
    convergence = row.get(
        "converged",
        row.get("is_valid", row.get("convergence", row.get("status") == "valid")),
    )
    if not bool(convergence):
        reasons.append("convergence=false")
    mass_fit = row.get("mass_fit")
    mass_unc = row.get("mass_stat_unc")
    if not isinstance(mass_fit, (int, float)) or not math.isfinite(float(mass_fit)):
        reasons.append("mass_fit=nonfinite")
    if not isinstance(mass_unc, (int, float)) or not math.isfinite(float(mass_unc)):
        reasons.append("mass_stat_unc=nonfinite")
    elif float(mass_unc) <= 0.0:
        reasons.append("mass_stat_unc<=0")
    signal_yield = row.get("signal_yield")
    if not isinstance(signal_yield, (int, float)) or not math.isfinite(float(signal_yield)):
        reasons.append("signal_yield=nonfinite")
    elif float(signal_yield) <= 0.0:
        reasons.append("signal_yield<=0")
    return reasons


def _minuit_values(minuit: Minuit) -> dict[str, float]:
    return {name: float(minuit.values[name]) for name in minuit.parameters}


def _fit_status(minuit: Minuit) -> str:
    """Classify fit quality with deterministic first-match precedence."""
    if not bool(minuit.fmin.is_valid):
        return "failed"
    if _free_parameter_at_limit(minuit):
        return "invalid_at_limit"
    if not bool(getattr(minuit.fmin, "has_accurate_covar", False)):
        return "invalid_covariance"
    if not bool(getattr(minuit.fmin, "has_posdef_covar", False)):
        return "invalid_covariance"
    return "valid"


def _free_parameter_at_limit(minuit: Minuit) -> bool:
    fmin_at_limit = bool(getattr(minuit.fmin, "has_parameters_at_limit", False))
    for parameter in minuit.params:
        if bool(getattr(parameter, "is_fixed", False)):
            continue
        explicit = getattr(parameter, "is_at_limit", None)
        if explicit is not None and bool(explicit):
            return True
        value = float(minuit.values[parameter.name])
        error = abs(float(minuit.errors[parameter.name]))
        for has_limit, bound in (
            (getattr(parameter, "has_lower_limit", False), getattr(parameter, "lower_limit", None)),
            (getattr(parameter, "has_upper_limit", False), getattr(parameter, "upper_limit", None)),
        ):
            if not has_limit or bound is None or not math.isfinite(float(bound)):
                continue
            scale_tolerance = 1e-7 * max(1.0, abs(float(bound)))
            minuit_tolerance = 0.5 * error if fmin_at_limit else 0.0
            if abs(value - float(bound)) <= max(scale_tolerance, minuit_tolerance):
                return True
    return False
