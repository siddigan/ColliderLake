from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.dq import checks
from tests import _run_dq_reference as oracle


def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")


def _data(rows=3, with_pt=True):
    values = {
        "dataset_id": ["toy"] * rows,
        "run": [1] * rows,
        "luminosityBlock": [1] * rows,
        "event": list(range(rows)),
    }
    if with_pt:
        values["pt"] = [2.0] * rows
        values["eta"] = [0.2] * rows
    return pd.DataFrame(values)


def test_streaming_report_matches_reference_on_multi_part_fixture(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    path = tmp_path / "parts"
    path.mkdir()
    # Three copies of key 0, two null keys, one pT violation; iso is absent.
    frames = [_data(1), _data(1), _data(1), _data(1), _data(1)]
    frames[1]["event"] = 0
    frames[2]["event"] = np.nan
    frames[3]["pt"] = 0.0
    frames[4]["event"] = np.nan
    for index, frame in enumerate(frames):
        frame.to_parquet(path / f"part-{index}.parquet", index=False)
    current, reference = tmp_path / "current.json", tmp_path / "oracle.json"
    monkeypatch.setattr(checks, "dq_report_path", lambda: current)
    monkeypatch.setattr(oracle, "dq_report_path", lambda: reference)
    with pytest.raises(RuntimeError):
        checks.run_dq("toy", "bronze", path)
    with pytest.raises(RuntimeError):
        oracle.run_dq("toy", "bronze", path)
    actual = json.loads(current.read_text())[-1]
    expected = json.loads(reference.read_text())[-1]
    assert actual["rows"] == expected["rows"] == 5
    assert actual["metrics"]["null_key_counts"]["event"] == 2
    assert actual["metrics"]["duplicate_key_count"] == 2
    assert actual["metrics"]["duplicate_key_count"] == sum(
        "duplicate key" in item for item in expected["failures"]
    )
    assert actual["metrics"]["physics_violation_counts"]["muon pt > 0"] == 1
    assert actual["columns"]["iso"] == "not present"
    assert actual["columns"]["pt"] == actual["columns"]["eta"] == "checked"
    assert actual["passed"] == expected["passed"] is False
    normalize = lambda item: "duplicate key" if "duplicate key" in item else item
    assert {normalize(item) for item in actual["failures"]} == {
        normalize(item) for item in expected["failures"]
    }
    assert {"no nulls in event", "muon pt > 0"}.issubset(actual["failures"])


def test_missing_key_and_profile_required_columns_are_explicit_failures(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    datasets = tmp_path / "configs" / "datasets.yaml"
    text = datasets.read_text()
    text = text.replace("format: nanoaod_reduced_muons", "format: nanoaod_reduced_muons\n    gold_profile: nanoaod_full")
    datasets.write_text(text)
    path = tmp_path / "missing.parquet"
    _data(1).drop(columns="event").to_parquet(path, index=False)
    monkeypatch.setattr(checks, "dq_report_path", lambda: tmp_path / "dq.json")
    with pytest.raises(RuntimeError, match="missing required key column"):
        checks.run_dq("run2012bc_doublemuparked", "gold", path)
    report = json.loads((tmp_path / "dq.json").read_text())[-1]
    assert any("contract violation: Muon_pfRelIso04_all required by profile nanoaod_full" in x for x in report["failures"])


def test_eight_part_reads_are_projected_and_duckdb_handles_uniqueness(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    path = tmp_path / "parts"
    path.mkdir()
    for index in range(8):
        _data(100).to_parquet(path / f"part-{index}.parquet", index=False)
    monkeypatch.setattr(checks, "dq_report_path", lambda: tmp_path / "dq.json")
    reads = []
    real_read = pd.read_parquet

    def spy(file, *args, **kwargs):
        if str(file).endswith(".parquet"):
            reads.append((str(file), kwargs.get("columns")))
            assert kwargs.get("columns") is not None
        return real_read(file, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", spy)
    monkeypatch.setattr(pd, "concat", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("concat in DQ")))
    monkeypatch.setattr(pd.DataFrame, "itertuples", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pandas uniqueness path")))
    with pytest.raises(RuntimeError):
        checks.run_dq("toy", "bronze", path)
    assert len({file for file, _ in reads}) == 8
    assert all(columns == ["dataset_id", "run", "luminosityBlock", "event", "pt", "eta"] for _, columns in reads)
    report = json.loads((tmp_path / "dq.json").read_text())[-1]
    assert report["metrics"]["duplicate_key_count"] == 700


def test_bronze_omits_absent_optional_muon_branches(tmp_path, monkeypatch):
    from src.bronze.convert import _write_muons

    _root(tmp_path, monkeypatch)
    base = pd.DataFrame({
        "dataset_id": ["toy"], "run": [1], "luminosityBlock": [1], "event": [1],
        "identity_mode": ["native"], "_source_file": ["x"], "_source_sha256": ["x"],
        "_ingest_ts": ["now"],
    })
    _write_muons(base, {"Muon_pt": [[2.0]], "Muon_eta": [[0.1]]}, "toy", "part.parquet")
    result = pd.read_parquet(tmp_path / "artifacts/bronze/dataset=toy/muons/part.parquet")
    assert "iso" not in result.columns


def test_full_dq_spills_at_300mb_on_ten_million_keys(tmp_path, monkeypatch):
    import os
    import sys

    _root(tmp_path, monkeypatch)
    path = tmp_path / "parts"
    path.mkdir()
    rows_per_part = 1_000_000
    part_count = 10
    for part in range(part_count):
        offset = part * rows_per_part
        event = np.arange(offset, offset + rows_per_part, dtype=np.int64)
        if part == part_count - 1:
            event[:100] = np.arange(100, dtype=np.int64)
        pd.DataFrame({
            "dataset_id": np.ones(rows_per_part, dtype=np.int64),
            "run": np.ones(rows_per_part, dtype=np.int64),
            "luminosityBlock": np.ones(rows_per_part, dtype=np.int64),
            "event": event,
        }).to_parquet(path / f"part-{part:02}.parquet", index=False)
    monkeypatch.setattr(checks, "dq_report_path", lambda: tmp_path / "dq.json")
    monkeypatch.setenv("COLLIDERLAKE_DQ_MEM", "300MB")
    data_root = tmp_path / "artifacts"
    spill_root = data_root / "tmp"
    configured = []
    real_duplicate_check = checks._duplicate_count_duckdb

    def observed_duplicate_check(files, keys, temp_root):
        return real_duplicate_check(
            files, keys, temp_root,
            settings_observer=lambda directory, memory, insertion, threads: configured.append(
                (directory, memory, insertion, threads)
            ),
        )

    monkeypatch.setattr(checks, "_duplicate_count_duckdb", observed_duplicate_check)
    def working_set():
        if sys.platform == "win32":
            import ctypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            )
            return counters.WorkingSetSize
        if sys.platform.startswith("linux"):
            resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
            return resident_pages * os.sysconf("SC_PAGE_SIZE")
        import tracemalloc

        if not tracemalloc.is_tracing():
            tracemalloc.start()
        return tracemalloc.get_traced_memory()[0]

    baseline = working_set()
    peak_delta = 0
    spill_seen = False
    errors = []
    done = threading.Event()

    def run():
        try:
            checks.run_dq("toy", "bronze", path)
        except RuntimeError as error:
            errors.append(error)
        finally:
            done.set()

    worker = threading.Thread(target=run)
    worker.start()
    while not done.is_set():
        peak_delta = max(peak_delta, working_set() - baseline)
        for directory in spill_root.glob("dq-spill-*"):
            if any(child.is_file() and child.stat().st_size > 0 for child in directory.iterdir()):
                spill_seen = True
        time.sleep(0.02)
    worker.join()
    peak_delta = max(peak_delta, working_set() - baseline)
    assert len(errors) == 1
    assert "duplicate key count: 100" in str(errors[0])
    report = json.loads((tmp_path / "dq.json").read_text())[-1]
    assert report["rows"] == 10_000_000
    assert report["metrics"]["duplicate_key_count"] == 100
    assert spill_seen, "DuckDB succeeded without creating observable spill files"
    assert len(configured) == 1
    directory, memory, insertion, threads = configured[0]
    assert directory.is_relative_to(spill_root.resolve())
    assert memory == "286.1 MiB"  # DuckDB reports 300 MB in binary MiB units.
    assert insertion is False
    assert threads == 2
    assert not list(spill_root.glob("dq-spill-*")), "spill directory was not cleaned up"
    # 300 MiB configured DuckDB budget + 500 MiB host overhead allowance.
    assert peak_delta < 800 * 1024 * 1024
