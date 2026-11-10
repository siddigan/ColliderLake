from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.cli import main as cli_main
from src.cli import run_pipeline
from src.figures.ladder import _model_components, generate_figures
from src.physics.models import background_model, signal_model
from src.utils.config import fit_config_id, load_yaml, selection_for_dataset
from src.utils.paths import data_path


def test_figures_stage_is_recorded_and_tables_round_trip_fit_values(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    fit_path = _write_synthetic_inputs()

    run_pipeline("run2012bc_doublemuparked", "figures", quiet=True)

    from src.hodoscope.registry import all_records

    record = all_records(data_path("results"))[-1]
    assert record["state"] == "succeeded"
    assert [stage["name"] for stage in record["stages"]] == ["figures"]
    canonical = data_path("results", "runs", record["run_id"], "figures")
    pointer = data_path("results", "figures", record["run_id"])
    manifest = json.loads((canonical / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == record["run_id"]
    assert len(manifest["files"]) == 24  # canonical + pointer copies of 12 outputs
    assert all(
        (canonical / item["name"]).is_file()
        for item in manifest["files"]
        if item["location"] == "canonical"
    )
    assert all(
        (pointer / item["name"]).is_file()
        for item in manifest["files"]
        if item["location"] == "results/figures"
    )
    for item in manifest["files"]:
        directory = canonical if item["location"] == "canonical" else pointer
        assert hashlib.sha256((directory / item["name"]).read_bytes()).hexdigest() == item["sha256"]
    assert len(list(canonical.glob("*.pdf"))) == 5
    assert len(list(canonical.glob("*.png"))) == 5
    assert (canonical / "pdg_table.md").is_file()
    assert (
        (canonical / "pdg_table.tex")
        .read_text(encoding="utf-8")
        .startswith(r"\documentclass{article}")
    )
    assert r"\usepackage{booktabs}" in (canonical / "pdg_table.tex").read_text(encoding="utf-8")
    _assert_tables_match_parquet(canonical, fit_path)


def test_standalone_figures_command_creates_recorded_run(tmp_path, monkeypatch):
    _prepare_root(tmp_path, monkeypatch)
    fit_path = _write_synthetic_inputs()
    monkeypatch.setattr(sys, "argv", ["colliderlake", "figures", "--run", str(fit_path)])

    assert cli_main() == 0

    from src.hodoscope.registry import all_records

    record = all_records(data_path("results"))[-1]
    assert record["name"] == "colliderlake:figures"
    assert record["state"] == "succeeded"
    assert len(list((data_path("results", "runs", record["run_id"], "figures")).glob("*.pdf"))) == 5


@pytest.mark.parametrize("row_index", range(4))
def test_model_components_integrate_to_persisted_yields(row_index):
    row = _synthetic_fit_rows()[row_index]
    window = tuple(row["window"])
    centers = np.linspace(window[0], window[1], row["n_bins"], endpoint=False)
    signal_spec = signal_model(row["signal_model"], row["resonance"], window)
    background_spec = background_model(row["background_model"], window)
    params = json.loads(row["fit_parameters_json"])
    signal, background = _model_components(
        centers,
        window,
        row["signal_yield"],
        row["background_yield"],
        signal_spec,
        background_spec,
        {key: params[key] for key in signal_spec.parameter_defaults},
        {key: params[key] for key in background_spec.parameter_defaults},
    )
    assert signal.sum() == pytest.approx(row["signal_yield"])
    assert background.sum() == pytest.approx(row["background_yield"])


def test_missing_fits_file_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError, match="Fits Parquet file not found"):
        generate_figures(
            tmp_path / "missing.parquet",
            run_id="missing",
            canonical_dir=tmp_path / "canonical",
            results_dir=tmp_path / "pointer",
        )


def _prepare_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")


def _write_synthetic_inputs() -> Path:
    fit_path = data_path(
        "results",
        "analysis=resonance",
        "dataset=run2012bc_doublemuparked",
        "fits.parquet",
    )
    gold_path = data_path(
        "gold",
        "analysis=resonance",
        "dataset=run2012bc_doublemuparked",
        "dimuon",
        "part.parquet",
    )
    rows = _synthetic_fit_rows()
    fit_path.parent.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(fit_path, index=False)
    rng = np.random.default_rng(704)
    masses = np.concatenate(
        [rng.uniform(*row["window"], size=400) for row in rows]
        + [rng.uniform(20.0, 40.0, size=100)]
    )
    gold_path.parent.mkdir(parents=True)
    pd.DataFrame({"mass": masses, "ignored": np.ones(len(masses))}).to_parquet(
        gold_path, index=False
    )
    return fit_path


def _synthetic_fit_rows() -> list[dict]:
    config = load_yaml("configs/fits/resonance_ladder.yaml")
    selection_id = selection_for_dataset("run2012bc_doublemuparked", "resonance")[2]
    config_id = fit_config_id(config)
    rows = []
    for resonance, fit in config["fits"].items():
        window = [float(value) for value in fit["window"]]
        signal_spec = signal_model(fit["signal"], resonance, tuple(window))
        background_spec = background_model(fit["background"], tuple(window))
        parameters = {
            "signal_yield": 120.0,
            "background_yield": 80.0,
            **signal_spec.parameter_defaults,
            **background_spec.parameter_defaults,
        }
        pdg_mass = float(fit["pdg_mass"] if "pdg_mass" in fit else fit["pdg_masses"][0])
        mass = pdg_mass
        rows.append(
            {
                "resonance": resonance,
                "status": "valid",
                "gof_flag": "ok",
                "mass_fit": mass,
                "mass_stat_unc": 0.01,
                "signal_yield": parameters["signal_yield"],
                "background_yield": parameters["background_yield"],
                "pdg_mass": pdg_mass,
                "chi2": 20.0,
                "ndf": int(fit["n_bins"]) - len(parameters),
                "window": window,
                "n_bins": int(fit["n_bins"]),
                "selection_id": selection_id,
                "fit_config_id": config_id,
                "signal_model": fit["signal"],
                "background_model": fit["background"],
                "fit_parameters_json": json.dumps(parameters, sort_keys=True),
            }
        )
    return rows


def _assert_tables_match_parquet(directory: Path, fit_path: Path) -> None:
    fits = pd.read_parquet(fit_path).to_dict(orient="records")
    markdown_rows = [
        line.strip("| ").split("|")
        for line in (directory / "pdg_table.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| ") and not line.startswith("| Resonance")
    ]
    latex_lines = (directory / "pdg_table.tex").read_text(encoding="utf-8").splitlines()
    latex_rows = [
        [value.strip().replace(r"\_", "_").replace(r"$\pm$", "±") for value in line[:-2].split("&")]
        for line in latex_lines
        if " & " in line and not line.startswith("Resonance")
    ]
    assert len(markdown_rows) == len(fits)
    assert len(latex_rows) == len(fits)
    for index, row in enumerate(fits):
        markdown = [cell.strip() for cell in markdown_rows[index]]
        latex = latex_rows[index]
        display_name = "Υ(1S)" if row["resonance"] == "upsilon" else row["resonance"]
        expected_latex_name = r"$\Upsilon(1S)$" if row["resonance"] == "upsilon" else row["resonance"]
        assert markdown[0] == display_name
        assert latex[0] == expected_latex_name
        mass_value, mass_unc = markdown[2].split("±")
        latex_mass, latex_unc = latex[2].split("±")
        expected_mass, expected_unc = _expected_rounded_mass_uncertainty(
            row["mass_fit"], row["mass_stat_unc"]
        )
        assert (mass_value.strip(), mass_unc.strip()) == (expected_mass, expected_unc)
        assert (latex_mass.strip(), latex_unc.strip()) == (expected_mass, expected_unc)
        assert float(markdown[3]) == float(row["pdg_mass"])
        assert float(latex[3]) == float(row["pdg_mass"])
        expected_shift = (
            100.0 * (float(row["mass_fit"]) - float(row["pdg_mass"])) / float(row["pdg_mass"])
        )
        assert float(markdown[4]) == float(latex[4].replace(r"\%", "")) == expected_shift
        assert float(markdown[5]) == float(latex[5]) == float(row["signal_yield"])
        expected_chi2_ndf = float(row["chi2"]) / int(row["ndf"])
        assert float(markdown[6]) == float(latex[6]) == expected_chi2_ndf
        assert markdown[7] == latex[7] == row["gof_flag"]
        assert markdown[8] == latex[8] == row["status"]
        assert markdown[9] == latex[9] == row["selection_id"]
        assert markdown[10] == latex[10] == row["fit_config_id"]
        window_values = [float(value) for value in re.findall(r"[-+\deE.]+", markdown[1])]
        assert window_values == list(row["window"])
        latex_window = [float(value) for value in re.findall(r"[-+\deE.]+", latex[1])]
        assert latex_window == list(row["window"])
    assert "Υ(1S): 2S/3S constrained at PDG splittings in a shared fit." in (
        directory / "pdg_table.md"
    ).read_text(encoding="utf-8")
    assert r"\Upsilon(1S)$: 2S/3S constrained at PDG splittings in a shared fit" in (
        directory / "pdg_table.tex"
    ).read_text(encoding="utf-8")


def _expected_rounded_mass_uncertainty(mass: float, uncertainty: float) -> tuple[str, str]:
    unc = Decimal(str(float(uncertainty)))
    quantum = Decimal(1).scaleb(unc.adjusted() - 1)
    decimals = max(0, -quantum.as_tuple().exponent)
    rounded_unc = unc.quantize(quantum, rounding=ROUND_HALF_UP)
    rounded_mass = Decimal(str(float(mass))).quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{rounded_mass:.{decimals}f}", f"{rounded_unc:.{decimals}f}"
