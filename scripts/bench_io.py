from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import awkward as ak
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import uproot


def _rss_bytes() -> int:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        get_info = psapi.GetProcessMemoryInfo
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_info.restype = wintypes.BOOL
        if not get_info(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return int(counters.PeakWorkingSetSize)
    import resource

    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


class _RSSMonitor:
    def __enter__(self):
        self.peak = _rss_bytes()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()
        return self

    def _sample(self):
        while not self.stop.wait(0.002):
            self.peak = max(self.peak, _rss_bytes())

    def __exit__(self, *_args):
        self.stop.set()
        self.thread.join()
        self.peak = max(self.peak, _rss_bytes())


def _root_fixture(path: Path, entries: int) -> None:
    rng = np.random.default_rng(20261028)
    with uproot.recreate(path) as root:
        root["Events"] = {
            "run": np.ones(entries, dtype=np.uint32),
            "luminosityBlock": np.ones(entries, dtype=np.uint32),
            "event": np.arange(entries, dtype=np.uint64),
            "nMuon": np.full(entries, 2, dtype=np.int32),
            "Muon_pt": ak.Array(rng.uniform(3, 50, (entries, 2))),
            "Muon_eta": ak.Array(rng.uniform(-2.4, 2.4, (entries, 2))),
            "Muon_phi": ak.Array(rng.uniform(-3.14, 3.14, (entries, 2))),
            "Muon_mass": ak.Array(np.full((entries, 2), 0.1056583755)),
            "Muon_charge": ak.Array(np.tile([1, -1], (entries, 1))),
        }


def _read(path: Path, entries: int, workers: int) -> dict[str, float | int]:
    with uproot.open(path) as root:
        tree = root["Events"]
        executor = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
        started = time.perf_counter()
        total = 0
        batches = 0
        try:
            for arrays in tree.iterate(
                library="np",
                step_size="1 MB",
                decompression_executor=executor,
                interpretation_executor=executor,
            ):
                total += len(arrays["event"])
                batches += 1
        finally:
            if executor is not None:
                executor.shutdown()
        elapsed = time.perf_counter() - started
    return {
        "workers": workers,
        "entries": total,
        "batches": batches,
        "seconds": elapsed,
        "events_per_second": entries / elapsed,
    }


def _parquet(path: Path, frame: pd.DataFrame, codec: str) -> dict[str, float | int | str]:
    with _RSSMonitor() as rss:
        started = time.perf_counter()
        frame.to_parquet(path, index=False, compression=codec)
        write_seconds = time.perf_counter() - started
        size = path.stat().st_size
        started = time.perf_counter()
        pd.read_parquet(path, columns=["mass"])
        read_seconds = time.perf_counter() - started
    metadata = pq.ParquetFile(path).metadata
    return {
        "codec": codec,
        "write_seconds": write_seconds,
        "write_rows_per_second": len(frame) / write_seconds,
        "read_seconds_mass_projection": read_seconds,
        "read_rows_per_second": len(frame) / read_seconds,
        "bytes": size,
        "row_groups": metadata.num_row_groups,
        "peak_rss_bytes": rss.peak,
        "rows_per_row_group": [
            metadata.row_group(i).num_rows for i in range(metadata.num_row_groups)
        ],
    }


def main() -> None:
    results: dict[str, object] = {
        "note": "Synthetic reproducible I/O benchmarks; run from repository root."
    }
    with tempfile.TemporaryDirectory(prefix="colliderlake_bench_") as temp:
        root = Path(temp)
        for label, entries in (("fixture_20k", 20_000), ("mid_size_200k", 200_000)):
            source = root / f"{label}.root"
            _root_fixture(source, entries)
            results[label] = {
                "uproot": [
                    _read(source, entries, workers) for workers in (1, min(4, os.cpu_count() or 1))
                ]
            }
            frame = pd.DataFrame(
                {
                    "mass": np.linspace(0.0, 300.0, entries),
                    "run": np.ones(entries, dtype=np.int32),
                    "event": np.arange(entries, dtype=np.int64),
                }
            )
            results[label]["parquet"] = [
                _parquet(root / f"{label}_{codec}.parquet", frame, codec)
                for codec in ("snappy", "zstd")
            ]
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
