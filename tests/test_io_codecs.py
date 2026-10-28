from __future__ import annotations

import shutil

import pandas as pd

from src.gold.dimuon import build_gold
from src.silver.build import build_silver
from src.utils.config import parquet_write_options
from src.utils.paths import data_path, ensure_parent


def test_pipeline_reads_mixed_codec_parts(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("COLLIDERLAKE_WORKERS", "1")
    shutil.copytree("configs", tmp_path / "configs")
    event = {
        "dataset_id": "run2012bc_doublemuparked",
        "run": 1,
        "luminosityBlock": 1,
        "event": 7,
        "identity_mode": "synthetic",
    }
    bronze_events = ensure_parent(
        data_path("bronze", "dataset=run2012bc_doublemuparked", "events", "part.parquet")
    )
    bronze_muons = ensure_parent(
        data_path("bronze", "dataset=run2012bc_doublemuparked", "muons", "part.parquet")
    )
    pd.DataFrame([event]).to_parquet(bronze_events, index=False, compression="snappy")
    pd.DataFrame(
        [
            {
                **event,
                "muon_idx": 0,
                "pt": 10.0,
                "eta": 0.0,
                "phi": 0.0,
                "mass": 0.1056583755,
                "charge": 1,
            },
            {
                **event,
                "muon_idx": 1,
                "pt": 10.0,
                "eta": 0.0,
                "phi": 1.0,
                "mass": 0.1056583755,
                "charge": -1,
            },
        ]
    ).to_parquet(bronze_muons, index=False, compression="zstd")

    build_silver("run2012bc_doublemuparked")
    silver_events = data_path(
        "silver", "dataset=run2012bc_doublemuparked", "events", "part.parquet"
    )
    silver_muons = data_path("silver", "dataset=run2012bc_doublemuparked", "muons", "part.parquet")
    assert len(pd.read_parquet(silver_events)) == 1
    assert len(pd.read_parquet(silver_muons)) == 2

    # Make the silver event part Snappy while the muon part remains Zstd.
    events = pd.read_parquet(silver_events)
    events.to_parquet(silver_events, index=False, compression="snappy")
    output = build_gold("run2012bc_doublemuparked")
    pairs = pd.read_parquet(next(output.glob("*.parquet")))
    assert len(pairs) == 1
    assert parquet_write_options("bronze") == {"compression": "snappy"}
    assert parquet_write_options("silver") == {"compression": "zstd"}
    assert parquet_write_options("gold") == {"compression": "zstd"}
