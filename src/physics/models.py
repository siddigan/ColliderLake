from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from src.physics.pdg import (
    JPSI_MASS_GEV,
    PSI2S_MASS_GEV,
    UPSILON_1S_MASS_GEV,
    UPSILON_2S_MASS_GEV,
    UPSILON_3S_MASS_GEV,
    Z_MASS_GEV,
    Z_WIDTH_GEV,
)

Array = np.ndarray
Pdf = Callable[[Array, dict[str, float], tuple[float, float]], Array]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    parameter_defaults: dict[str, float]
    parameter_limits: dict[str, tuple[float | None, float | None]]
    pdf: Pdf
    mass_parameter: str
    width_parameter: str


def signal_model(name: str, resonance: str, window: tuple[float, float]) -> ModelSpec:
    try:
        builder = SIGNALS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown signal model {name!r}; expected one of {sorted(SIGNALS)}") from exc
    return builder(resonance, window)


def background_model(name: str, window: tuple[float, float]) -> ModelSpec:
    try:
        builder = BACKGROUNDS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown background model {name!r}; expected one of {sorted(BACKGROUNDS)}") from exc
    return builder(window)


def normalized(values: Array) -> Array:
    total = float(np.sum(values))
    if not np.isfinite(total) or total <= 0.0:
        return np.full_like(values, 1.0 / len(values), dtype=float)
    return values / total


def gaussian_pdf(centers: Array, params: dict[str, float], window: tuple[float, float]) -> Array:
    sigma = max(params["sigma"], np.finfo(float).eps)
    values = np.exp(-0.5 * ((centers - params["mass"]) / sigma) ** 2)
    return normalized(values)


def double_gaussian_pdf(centers: Array, params: dict[str, float], window: tuple[float, float]) -> Array:
    sigma = max(params["sigma"], np.finfo(float).eps)
    wide_sigma = max(params["wide_sigma"], sigma)
    frac = np.clip(params["core_fraction"], 0.0, 1.0)
    core = np.exp(-0.5 * ((centers - params["mass"]) / sigma) ** 2)
    wide = np.exp(-0.5 * ((centers - params["mass"]) / wide_sigma) ** 2)
    return normalized(frac * core + (1.0 - frac) * wide)


def crystal_ball_pdf(centers: Array, params: dict[str, float], window: tuple[float, float]) -> Array:
    sigma = max(params["sigma"], np.finfo(float).eps)
    alpha = max(abs(params["alpha"]), np.finfo(float).eps)
    n = max(params["n"], 1.0 + np.finfo(float).eps)
    t = (centers - params["mass"]) / sigma
    gaussian = np.exp(-0.5 * t**2)
    a = (n / alpha) ** n * np.exp(-0.5 * alpha**2)
    b = n / alpha - alpha
    tail = a / np.maximum(b - t, np.finfo(float).eps) ** n
    return normalized(np.where(t > -alpha, gaussian, tail))


def triple_gaussian_pdf(centers: Array, params: dict[str, float], window: tuple[float, float]) -> Array:
    offset = params["offset"]
    sigma = max(params["sigma"], np.finfo(float).eps)
    scale = max(params["width_scale"], np.finfo(float).eps)
    weights = normalized(np.clip(np.array([params["frac_1s"], params["frac_2s"], params["frac_3s"]]), 0.0, None))
    masses = np.array(
        [
            UPSILON_1S_MASS_GEV + offset,
            UPSILON_1S_MASS_GEV + (UPSILON_2S_MASS_GEV - UPSILON_1S_MASS_GEV) + offset,
            UPSILON_1S_MASS_GEV + (UPSILON_3S_MASS_GEV - UPSILON_1S_MASS_GEV) + offset,
        ],
        dtype=float,
    )
    values = np.zeros_like(centers, dtype=float)
    for weight, mass in zip(weights, masses, strict=True):
        values += weight * np.exp(-0.5 * ((centers - mass) / (sigma * scale)) ** 2)
    return normalized(values)


def voigtian_pdf(centers: Array, params: dict[str, float], window: tuple[float, float]) -> Array:
    sigma = max(params["sigma"], np.finfo(float).eps)
    gamma = Z_WIDTH_GEV / 2.0
    gaussian_fwhm = 2.354820045 * sigma
    lorentz_fwhm = 2.0 * gamma
    ratio = lorentz_fwhm / max(lorentz_fwhm + gaussian_fwhm, np.finfo(float).eps)
    eta = np.clip(1.36603 * ratio - 0.47719 * ratio**2 + 0.11116 * ratio**3, 0.0, 1.0)
    x = centers - params["mass"]
    gaussian = np.exp(-0.5 * (x / sigma) ** 2)
    lorentz = gamma**2 / (x**2 + gamma**2)
    return normalized(eta * lorentz + (1.0 - eta) * gaussian)


def exponential_pdf(centers: Array, params: dict[str, float], window: tuple[float, float]) -> Array:
    low, _ = window
    values = np.exp(params["slope"] * (centers - low))
    return normalized(values)


def chebyshev1_pdf(centers: Array, params: dict[str, float], window: tuple[float, float]) -> Array:
    x = _scaled_x(centers, window)
    return normalized(np.clip(1.0 + params["c1"] * x, np.finfo(float).eps, None))


def chebyshev2_pdf(centers: Array, params: dict[str, float], window: tuple[float, float]) -> Array:
    x = _scaled_x(centers, window)
    values = 1.0 + params["c1"] * x + params["c2"] * (2.0 * x**2 - 1.0)
    return normalized(np.clip(values, np.finfo(float).eps, None))


def _scaled_x(centers: Array, window: tuple[float, float]) -> Array:
    low, high = window
    return 2.0 * (centers - low) / (high - low) - 1.0


def _mass_seed(resonance: str, window: tuple[float, float]) -> float:
    seeds = {"jpsi": JPSI_MASS_GEV, "psi2s": PSI2S_MASS_GEV, "upsilon": UPSILON_1S_MASS_GEV, "z": Z_MASS_GEV}
    return seeds.get(resonance, (window[0] + window[1]) / 2.0)


def _gaussian_spec(resonance: str, window: tuple[float, float]) -> ModelSpec:
    width = max((window[1] - window[0]) / 40.0, np.finfo(float).eps)
    return ModelSpec("gaussian", {"mass": _mass_seed(resonance, window), "sigma": width}, {"mass": window, "sigma": (np.finfo(float).eps, window[1] - window[0])}, gaussian_pdf, "mass", "sigma")


def _double_gaussian_spec(resonance: str, window: tuple[float, float]) -> ModelSpec:
    spec = _gaussian_spec(resonance, window)
    defaults = {**spec.parameter_defaults, "wide_sigma": spec.parameter_defaults["sigma"] * 2.0, "core_fraction": 0.8}
    limits = {**spec.parameter_limits, "wide_sigma": (np.finfo(float).eps, window[1] - window[0]), "core_fraction": (0.0, 1.0)}
    return ModelSpec("double_gaussian", defaults, limits, double_gaussian_pdf, "mass", "sigma")


def _crystal_ball_spec(resonance: str, window: tuple[float, float]) -> ModelSpec:
    spec = _gaussian_spec(resonance, window)
    defaults = {**spec.parameter_defaults, "alpha": 1.5, "n": 3.0}
    limits = {**spec.parameter_limits, "alpha": (0.1, 10.0), "n": (1.01, 50.0)}
    return ModelSpec("crystal_ball", defaults, limits, crystal_ball_pdf, "mass", "sigma")


def _triple_gaussian_spec(resonance: str, window: tuple[float, float]) -> ModelSpec:
    return ModelSpec(
        "triple_gaussian",
        {"offset": 0.0, "sigma": max((window[1] - window[0]) / 80.0, np.finfo(float).eps), "width_scale": 1.0, "frac_1s": 0.6, "frac_2s": 0.25, "frac_3s": 0.15},
        {"offset": (-0.25, 0.25), "sigma": (np.finfo(float).eps, window[1] - window[0]), "width_scale": (0.2, 5.0), "frac_1s": (0.0, 1.0), "frac_2s": (0.0, 1.0), "frac_3s": (0.0, 1.0)},
        triple_gaussian_pdf,
        "offset",
        "sigma",
    )


def _voigtian_spec(resonance: str, window: tuple[float, float]) -> ModelSpec:
    return ModelSpec("breit_wigner_conv_gaussian", {"mass": _mass_seed(resonance, window), "sigma": max((window[1] - window[0]) / 20.0, np.finfo(float).eps)}, {"mass": window, "sigma": (np.finfo(float).eps, window[1] - window[0])}, voigtian_pdf, "mass", "sigma")


def _exponential_spec(window: tuple[float, float]) -> ModelSpec:
    return ModelSpec("exponential", {"slope": -1.0 / (window[1] - window[0])}, {"slope": (-100.0, 100.0)}, exponential_pdf, "", "")


def _chebyshev1_spec(window: tuple[float, float]) -> ModelSpec:
    return ModelSpec("chebyshev1", {"c1": 0.0}, {"c1": (-0.95, 0.95)}, chebyshev1_pdf, "", "")


def _chebyshev2_spec(window: tuple[float, float]) -> ModelSpec:
    return ModelSpec("chebyshev2", {"c1": 0.0, "c2": 0.0}, {"c1": (-0.95, 0.95), "c2": (-0.95, 0.95)}, chebyshev2_pdf, "", "")


SIGNALS = {
    "gaussian": _gaussian_spec,
    "double_gaussian": _double_gaussian_spec,
    "crystal_ball": _crystal_ball_spec,
    "triple_gaussian": _triple_gaussian_spec,
    "breit_wigner_conv_gaussian": _voigtian_spec,
}

BACKGROUNDS = {
    "exponential": _exponential_spec,
    "chebyshev1": _chebyshev1_spec,
    "chebyshev2": _chebyshev2_spec,
}
