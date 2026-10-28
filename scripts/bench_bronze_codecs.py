from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = "run2012bc_doublemuparked"
ROOT_NAME = "Run2012BC_DoubleMuParked_Muons.root"


def _peak_rss_bytes() -> int:
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
        psapi, kernel32 = ctypes.WinDLL("psapi"), ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        query = psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        if not query(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return int(counters.PeakWorkingSetSize)
    import resource

    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _prepare_data_root(data_root: Path, source: Path) -> None:
    raw_dir = data_root / "raw" / DATASET
    raw_dir.mkdir(parents=True)
    os.link(source, raw_dir / ROOT_NAME)
    manifest = REPO_ROOT / "data" / "raw" / DATASET / "MANIFEST.json"
    (raw_dir / "MANIFEST.json").write_bytes(manifest.read_bytes())


def _worker(codec: str, batches: int, data_root: Path) -> dict[str, object]:
    os.environ["COLLIDERLAKE_DATA_ROOT"] = str(data_root)
    os.environ["COLLIDERLAKE_ROOT"] = str(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT))
    import pandas as pd

    from src.bronze.convert import build_bronze
    from src.utils.runlog import configure_logging

    configure_logging(quiet=True)
    original = pd.DataFrame.to_parquet
    write_seconds = 0.0

    def measured_write(self, path, *args, **kwargs):
        nonlocal write_seconds
        if codec == "current":
            kwargs["compression"] = "zstd"
            kwargs.pop("compression_level", None)
        elif codec == "snappy":
            kwargs["compression"] = "snappy"
            kwargs.pop("compression_level", None)
        elif codec == "zstd1":
            kwargs["compression"] = "zstd"
            kwargs["compression_level"] = 1
        started = time.perf_counter()
        try:
            return original(self, path, *args, **kwargs)
        finally:
            write_seconds += time.perf_counter() - started

    pd.DataFrame.to_parquet = measured_write
    started = time.perf_counter()
    build_bronze(DATASET, max_batches=batches)
    wall_seconds = time.perf_counter() - started
    output = data_root / "bronze" / f"dataset={DATASET}"
    output_bytes = sum(path.stat().st_size for path in output.rglob("*.parquet"))
    parts = len(list(output.rglob("*.parquet")))
    return {
        "codec": codec,
        "batches_requested": batches,
        "batches_written": parts // 2,
        "wall_seconds": wall_seconds,
        "write_seconds": write_seconds,
        "write_MB_per_second": output_bytes / 1_000_000 / write_seconds,
        "output_bytes": output_bytes,
        "peak_rss_bytes": _peak_rss_bytes(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--codec", choices=["current", "snappy", "zstd1"])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--batches", type=int, default=20)
    args = parser.parse_args()
    if args.worker:
        if args.codec is None or args.data_root is None:
            parser.error("worker mode requires --codec and --data-root")
        print(json.dumps(_worker(args.codec, args.batches, args.data_root)))
        return

    source = REPO_ROOT / "data" / "raw" / DATASET / ROOT_NAME
    if not source.is_file():
        raise FileNotFoundError(source)
    results = []
    with tempfile.TemporaryDirectory(prefix="cl_bronze_codec_", dir=REPO_ROOT) as temp:
        for codec in ("current", "snappy", "zstd1"):
            data_root = Path(temp) / codec / "data"
            _prepare_data_root(data_root, source)
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--codec",
                codec,
                "--data-root",
                str(data_root),
                "--batches",
                str(args.batches),
            ]
            completed = subprocess.run(
                command, cwd=REPO_ROOT, check=False, text=True, capture_output=True
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr)
            results.append(json.loads(completed.stdout.strip().splitlines()[-1]))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
