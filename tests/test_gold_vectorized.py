from __future__ import annotations

import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd

from src.gold.dimuon import EVENT_KEYS, _build_pairs_for_part, _build_pairs_reference, build_gold
from src.physics.pdg import MUON_MASS_GEV
from src.utils.paths import data_path, ensure_parent

SELECTION = {
    "muon": {"pt_min": 3.0, "abs_eta_max": 2.4},
    "pair": {"opposite_charge": True},
    "trigger": {"paths": []},
    "mass_window": [0.25, 300.0],
}


def test_vectorized_pairing_matches_frozen_reference():
    events = pd.DataFrame(
        [
            {"dataset_id": "toy", "run": 1, "luminosityBlock": 1, "event": 1, "identity_mode": "synthetic"},
            {"dataset_id": "toy", "run": 1, "luminosityBlock": 1, "event": 2, "identity_mode": "synthetic"},
        ]
    )
    muons = pd.DataFrame(
        _muon_rows(
            [
                (1, [10.0, 8.0, 4.0], [1, -1, -1]),
                (2, [10.0, 9.0, 8.0, 7.0], [1, 1, -1, -1]),
            ]
        )
    )
    reference = _sorted_frame(_build_pairs_reference(events, muons, SELECTION, "deadbeef"))
    vectorized = _sorted_frame(_build_pairs_for_part(events, muons, SELECTION, "deadbeef"))
    pd.testing.assert_frame_equal(
        reference,
        vectorized,
        check_dtype=True,
        check_exact=False,
        rtol=0.0,
        atol=1e-9,
    )


def test_vectorized_gold_20k_events_under_five_seconds_and_records_peak_rss(tmp_path, monkeypatch, capsys):
    _prepare_project_root(tmp_path, monkeypatch)
    n_events = 20_000
    events = pd.DataFrame(
        {
            "dataset_id": "run2012bc_doublemuparked",
            "run": 1,
            "luminosityBlock": 1,
            "event": np.arange(n_events, dtype=np.int64),
            "identity_mode": "synthetic",
        }
    )
    muons = pd.DataFrame(
        {
            "dataset_id": np.repeat("run2012bc_doublemuparked", n_events * 2),
            "run": 1,
            "luminosityBlock": 1,
            "event": np.repeat(np.arange(n_events, dtype=np.int64), 2),
            "muon_idx": np.tile([0, 1], n_events),
            "pt": 10.0,
            "eta": 0.0,
            "phi": np.tile([0.0, 1.0], n_events),
            "mass": MUON_MASS_GEV,
            "charge": np.tile([1, -1], n_events),
        }
    )
    events_path = ensure_parent(data_path("silver", "dataset=run2012bc_doublemuparked", "events", "part.parquet"))
    muons_path = ensure_parent(data_path("silver", "dataset=run2012bc_doublemuparked", "muons", "part.parquet"))
    events.to_parquet(events_path, index=False)
    muons.to_parquet(muons_path, index=False)

    peak_kind, peak_before = _peak_rss_start()
    started = time.monotonic()
    build_gold("run2012bc_doublemuparked")
    elapsed = time.monotonic() - started
    peak_bytes = _peak_rss_end(peak_kind, peak_before)
    print(f"gold vectorized: elapsed={elapsed:.3f}s peak_rss={peak_bytes}B")
    assert elapsed < 5.0
    assert capsys.readouterr().out.endswith("B\n")


def test_pairing_rejects_more_than_sixteen_muons_with_event_key():
    events = pd.DataFrame(
        [{"dataset_id": "toy", "run": 1, "luminosityBlock": 1, "event": 99, "identity_mode": "synthetic"}]
    )
    muons = pd.DataFrame(_muon_rows([(99, [10.0] * 17, [1, -1] * 8 + [1])]))
    try:
        _build_pairs_for_part(events, muons, {**SELECTION, "max_muons_per_event": 16}, "deadbeef")
    except ValueError as exc:
        assert "('toy', 1, 1, 99)" in str(exc)
        assert "max_muons_per_event=16" in str(exc)
    else:
        raise AssertionError("expected the per-event muon guard to fail")


def test_forty_muons_pass_default_tripwire_and_make_all_os_pairs():
    events = pd.DataFrame(
        [{"dataset_id": "toy", "run": 1, "luminosityBlock": 1, "event": 101, "identity_mode": "synthetic"}]
    )
    charges = [1] * 20 + [-1] * 20
    muons = pd.DataFrame(_muon_rows([(101, [10.0] * 40, charges)]))
    selection = {**SELECTION, "mass_window": [0.0, 300.0]}

    rows = _build_pairs_for_part(events, muons, selection, "default128")

    assert len(rows) == 20 * 20
    assert {row["pair_idx"] for row in rows} == set(range(20 * 20))


def _sorted_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    return frame.sort_values(EVENT_KEYS + ["pair_idx"], kind="mergesort").reset_index(drop=True)


def _muon_rows(specs: list[tuple[int, list[float], list[int]]]) -> list[dict[str, object]]:
    rows = []
    for event, pts, charges in specs:
        for index, (pt, charge) in enumerate(zip(pts, charges, strict=True)):
            rows.append(
                {
                    "dataset_id": "toy",
                    "run": 1,
                    "luminosityBlock": 1,
                    "event": event,
                    "muon_idx": index,
                    "pt": pt,
                    "eta": 0.0,
                    "phi": 0.7 * index,
                    "mass": MUON_MASS_GEV,
                    "charge": charge,
                }
            )
    return rows


def _prepare_project_root(tmp_path: Path, monkeypatch) -> None:
    import shutil

    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")


def _peak_rss_start() -> tuple[str, int]:
    try:
        import resource
    except ImportError:
        tracemalloc.start()
        return "tracemalloc", 0
    return "resource", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _peak_rss_end(kind: str, before: int) -> int:
    if kind == "tracemalloc":
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return peak
    import resource
    import sys

    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = max(after, before)
    return int(peak * (1024 if sys.platform != "darwin" else 1))
