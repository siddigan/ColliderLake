import numpy as np
import pytest

from src.physics.fitting import fit_masses
from src.physics.pdg import JPSI_MASS_GEV, Z_MASS_GEV, Z_WIDTH_GEV


def test_gaussian_exponential_fit_recovers_jpsi_mass():
    rng = np.random.default_rng(12345)
    signal = rng.normal(JPSI_MASS_GEV, 0.03, 5000)
    background = 2.8 + rng.exponential(0.25, 1500)
    masses = np.concatenate([signal, background[background <= 3.4]])
    result = fit_masses(
        "jpsi",
        {
            "window": [2.8, 3.4],
            "n_bins": 80,
            "signal": "gaussian",
            "background": "exponential",
            "pdg_mass": JPSI_MASS_GEV,
        },
        masses,
    )
    assert result["status"] == "valid"
    assert abs(result["mass_fit"] - JPSI_MASS_GEV) < 3.0 * result["mass_stat_unc"]
    assert abs(result["mass_fit"] - JPSI_MASS_GEV) < 0.01


def test_voigtian_exponential_fit_recovers_z_mass():
    rng = np.random.default_rng(54321)
    gaussian = rng.normal(0.0, 2.0, 5000)
    lorentz = rng.standard_cauchy(5000) * (Z_WIDTH_GEV / 2.0)
    signal = Z_MASS_GEV + gaussian + lorentz
    signal = signal[(signal >= 70.0) & (signal <= 110.0)]
    background = 70.0 + rng.exponential(18.0, 1800)
    masses = np.concatenate([signal[:5000], background[background <= 110.0]])
    result = fit_masses(
        "z",
        {
            "window": [70.0, 110.0],
            "n_bins": 100,
            "signal": "breit_wigner_conv_gaussian",
            "background": "exponential",
            "pdg_mass": Z_MASS_GEV,
        },
        masses,
    )
    assert result["status"] == "valid"
    assert abs(result["mass_fit"] - Z_MASS_GEV) < 3.0 * result["mass_stat_unc"]


def test_invalid_initial_values_raise():
    rng = np.random.default_rng(7)
    masses = rng.uniform(2.8, 3.4, 1000)
    with pytest.raises(RuntimeError):
        fit_masses(
            "jpsi",
            {
                "window": [2.8, 3.4],
                "n_bins": 50,
                "signal": "gaussian",
                "background": "exponential",
                "pdg_mass": JPSI_MASS_GEV,
            },
            masses,
            initial_overrides={"sigma": -1.0},
        )
