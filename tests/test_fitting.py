import numpy as np
import pandas as pd
import pytest

from src.physics.fitting import fit_masses, fit_resonance
from src.physics.pdg import JPSI_MASS_GEV, Z_MASS_GEV
from src.utils.paths import data_dir
from tests.fit_assertions import assert_valid_fit


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
    assert_valid_fit(result, JPSI_MASS_GEV, 0.05)
    assert abs(result["mass_fit"] - JPSI_MASS_GEV) < 3.0 * result["mass_stat_unc"]
    assert abs(result["mass_fit"] - JPSI_MASS_GEV) < 0.01
    assert result["gof_flag"] == ("poor" if result["chi2"] / result["ndf"] > 5.0 else "ok")


def test_voigtian_exponential_fit_recovers_z_mass():
    rng = np.random.default_rng(54321)
    truth_sigma = 2.0
    from src.physics.models import background_model, signal_model

    window = (86.0, 96.0)
    edges = np.linspace(*window, 101)
    centers = 0.5 * (edges[:-1] + edges[1:])
    signal = signal_model("breit_wigner_conv_gaussian", "z", window).pdf(
        centers, {"mass": Z_MASS_GEV, "sigma": truth_sigma}, window
    )
    background = background_model("exponential", window).pdf(centers, {"slope": -0.1}, window)
    expected = 18_000 * signal + 12_000 * background
    masses = np.repeat(centers, rng.poisson(expected))
    result = fit_masses(
        "z",
        {
            "window": [86.0, 96.0],
            "n_bins": 100,
            "signal": "breit_wigner_conv_gaussian",
            "background": "exponential",
            "pdg_mass": Z_MASS_GEV,
        },
        masses,
    )
    assert_valid_fit(result, Z_MASS_GEV, 1.0)
    assert abs(result["mass_fit"] - Z_MASS_GEV) < 3.0 * result["mass_stat_unc"]
    assert abs(result["width"] - truth_sigma) < 3.0 * result["width_stat_unc"]
    assert result["gof_flag"] == ("poor" if result["chi2"] / result["ndf"] > 5.0 else "ok")


@pytest.mark.parametrize(
    ("engineered", "expected"),
    [
        ({"at_limit": True}, "invalid_at_limit"),
        ({"accurate_covar": False}, "invalid_covariance"),
        ({"posdef_covar": False}, "invalid_covariance"),
        ({"converged": False, "at_limit": True, "accurate_covar": False}, "failed"),
    ],
)
def test_fit_status_precedence_with_engineered_minuit_results(monkeypatch, engineered, expected):
    from types import SimpleNamespace

    from src.physics import fitting

    class EngineeredMinuit:
        def __init__(self, cost, **initial):
            self.parameters = tuple(initial)
            self.values = dict(initial)
            self.errors = {name: 0.02 for name in initial}
            self.limits = {}
            self.errordef = None
            self.fmin = SimpleNamespace(
                is_valid=engineered.get("converged", True),
                has_parameters_at_limit=engineered.get("at_limit", False),
                has_accurate_covar=engineered.get("accurate_covar", True),
                has_posdef_covar=engineered.get("posdef_covar", True),
            )

        @property
        def params(self):
            result = []
            for name in self.parameters:
                lower, upper = self.limits.get(name, (None, None))
                at_limit = engineered.get("at_limit", False) and name == "sigma"
                if at_limit and lower is not None:
                    self.values[name] = lower
                result.append(SimpleNamespace(
                    name=name, is_fixed=False,
                    has_lower_limit=lower is not None, lower_limit=lower,
                    has_upper_limit=upper is not None, upper_limit=upper,
                ))
            return result

        def migrad(self):
            pass

        def hesse(self):
            pass

    monkeypatch.setattr(fitting, "Minuit", EngineeredMinuit)
    rng = np.random.default_rng(123)
    masses = rng.normal(JPSI_MASS_GEV, 0.03, 1000)
    config = {
        "window": [2.8, 3.4], "n_bins": 50, "signal": "gaussian",
        "background": "exponential", "pdg_mass": JPSI_MASS_GEV,
    }
    first = fitting.fit_masses("jpsi", config, masses)
    assert first["status"] == expected
    if expected == "invalid_at_limit":
        second = fitting.fit_masses("jpsi", config, masses)
        assert second["status"] == first["status"]


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


def test_gaussian_pull_calibration_over_seeded_toys():
    pulls = []
    for seed in range(50):
        rng = np.random.default_rng(seed)
        signal = rng.normal(JPSI_MASS_GEV, 0.03, 4000)
        background = 2.8 + rng.exponential(0.25, 4000)
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
        pulls.append((result["mass_fit"] - JPSI_MASS_GEV) / result["mass_stat_unc"])
    pulls = np.asarray(pulls)
    assert abs(float(np.mean(pulls))) < 0.3
    assert 0.8 <= float(np.std(pulls, ddof=1)) <= 1.2


def test_fit_resonance_combines_gold_parts_before_fitting(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    gold = data_dir("gold", "analysis=resonance", "dataset=toy", "dimuon")
    rng = np.random.default_rng(2468)
    for part in range(2):
        signal = rng.normal(JPSI_MASS_GEV, 0.03, 2500)
        background = 2.8 + rng.exponential(0.25, 750)
        masses = np.concatenate([signal, background[background <= 3.4]])
        pd.DataFrame({"mass": masses, "selection_id": "abcd1234"}).to_parquet(
            gold / f"part-{part:04d}.parquet",
            index=False,
        )
    configs = tmp_path / "configs/fits"
    configs.mkdir(parents=True)
    (configs / "resonance_ladder.yaml").write_text(
        """
analysis: resonance
default_n_bins: 80
fits:
  jpsi:
    n_bins: 80
    window: [2.8, 3.4]
    signal: gaussian
    background: exponential
    pdg_mass: 3.0969
""".strip(),
        encoding="utf-8",
    )

    output_dir = fit_resonance("toy")
    fits = pd.read_parquet(output_dir / "fits.parquet")

    assert list(fits["resonance"]) == ["jpsi"]
    assert fits.iloc[0]["status"] == "valid"
    assert len(str(fits.iloc[0]["fit_config_id"])) == 8
