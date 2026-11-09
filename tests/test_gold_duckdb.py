from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.gold.dimuon import EVENT_KEYS, _build_pairs_for_part
from src.gold.dimuon_duckdb import build_part
from src.physics.pdg import MUON_MASS_GEV


@pytest.mark.parametrize("profile", ["reduced", "nanoaod_full"])
def test_duckdb_gold_matches_vectorized_for_three_and_four_muon_events(tmp_path, profile):
    events, muons = _fixture()
    event_path, muon_path = _write_parts(tmp_path, events, muons)
    required = ["Muon_pfRelIso04_all"] if profile == "nanoaod_full" else []
    vectorized = pd.DataFrame(
        _build_pairs_for_part(
            events, muons, _selection(), "deadbeef", profile=profile, required_columns=required
        )
    )
    duckdb_frame, _ = build_part(
        event_path,
        muon_path,
        events,
        _selection(),
        "deadbeef",
        profile=profile,
        required_columns=required,
    )
    sort_keys = EVENT_KEYS + ["pair_idx"]
    vectorized = vectorized.sort_values(sort_keys).reset_index(drop=True)
    vectorized["pair_idx"] = vectorized["pair_idx"].astype("int32")
    duckdb_frame = duckdb_frame.sort_values(sort_keys).reset_index(drop=True)
    assert list(duckdb_frame.columns) == list(vectorized.columns)
    pd.testing.assert_series_equal(duckdb_frame.dtypes, vectorized.dtypes)
    pd.testing.assert_frame_equal(duckdb_frame[sort_keys], vectorized[sort_keys], check_dtype=True)
    numeric = vectorized.select_dtypes(include=["number"]).columns
    np.testing.assert_allclose(duckdb_frame[numeric], vectorized[numeric], rtol=0, atol=1e-7)
    assert duckdb_frame["pair_idx"].tolist() == vectorized["pair_idx"].tolist()
    if profile == "nanoaod_full":
        assert duckdb_frame["mu1_Muon_pfRelIso04_all"].dtype == muons["iso"].dtype


@pytest.mark.parametrize("engine", ["vectorized", "duckdb"])
@pytest.mark.parametrize("profile", ["reduced", "nanoaod_full"])
def test_feature_contract_is_profile_aware_for_both_engines(tmp_path, engine, profile):
    events, muons = _fixture()
    muons = muons.drop(columns="iso")
    event_path, muon_path = _write_parts(tmp_path, events, muons)
    if profile == "nanoaod_full":
        with pytest.raises(
            ValueError,
            match="contract violation: Muon_pfRelIso04_all required by profile nanoaod_full",
        ):
            if engine == "vectorized":
                _build_pairs_for_part(
                    events,
                    muons,
                    _selection(),
                    "deadbeef",
                    profile=profile,
                    required_columns=["Muon_pfRelIso04_all"],
                )
            else:
                build_part(
                    event_path,
                    muon_path,
                    events,
                    _selection(),
                    "deadbeef",
                    profile=profile,
                    required_columns=["Muon_pfRelIso04_all"],
                )
    elif engine == "vectorized":
        assert _build_pairs_for_part(events, muons, _selection(), "deadbeef", profile=profile)
    else:
        output, _ = build_part(
            event_path, muon_path, events, _selection(), "deadbeef", profile=profile
        )
        assert len(output) > 0


def _write_parts(tmp_path: Path, events: pd.DataFrame, muons: pd.DataFrame) -> tuple[Path, Path]:
    event_path, muon_path = tmp_path / "events.parquet", tmp_path / "muons.parquet"
    events.to_parquet(event_path, index=False)
    muons.to_parquet(muon_path, index=False)
    return event_path, muon_path


def _fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    events = pd.DataFrame(
        [
            {
                "dataset_id": "toy",
                "run": 1,
                "luminosityBlock": 1,
                "event": e,
                "identity_mode": "synthetic",
            }
            for e in (1, 2)
        ]
    )
    rows = []
    specs = [(1, [10.0, 8.0, 4.0], [1, -1, -1]), (2, [10.0, 9.0, 8.0, 7.0], [1, 1, -1, -1])]
    for event, pts, charges in specs:
        for idx, (pt, charge) in enumerate(zip(pts, charges, strict=True)):
            rows.append(
                {
                    "dataset_id": "toy",
                    "run": 1,
                    "luminosityBlock": 1,
                    "event": event,
                    "muon_idx": idx,
                    "pt": pt,
                    "eta": 0.1 * idx,
                    "phi": 0.7 * idx,
                    "mass": MUON_MASS_GEV,
                    "charge": charge,
                    "iso": np.float64(0.01 * idx),
                }
            )
    return events, pd.DataFrame(rows)


def _selection() -> dict:
    return {
        "muon": {"pt_min": 3.0, "abs_eta_max": 2.4},
        "pair": {"opposite_charge": True},
        "trigger": {"paths": []},
        "mass_window": [0.0, 300.0],
    }
