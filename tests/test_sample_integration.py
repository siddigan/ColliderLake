from pathlib import Path

import pandas as pd
import pytest

from src.cli import run_pipeline
from src.physics.pdg import JPSI_MASS_GEV


@pytest.mark.skipif(
    not any(Path("data/raw/run2012bc_doublemuparked").glob("*.root")),
    reason="no local 2012 ROOT sample present",
)
def test_local_2012_sample_reaches_jpsi_fit():
    run_pipeline("run2012bc_doublemuparked", "all", max_batches=2)
    fits = pd.read_parquet(
        "data/results/analysis=resonance/dataset=run2012bc_doublemuparked/fits.parquet"
    )
    jpsi = fits[fits["resonance"] == "jpsi"].iloc[0]
    assert jpsi["status"] == "valid"
    assert abs(jpsi["mass_fit"] - JPSI_MASS_GEV) < 0.05
