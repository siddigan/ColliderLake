# CL2.0.7 measured I/O decisions

Run: `python scripts/bench_io.py` on Windows, 2026-10-28. The script generated ROOT and Parquet inputs in a temporary directory; it did not touch `./data`. Uproot used 25 MB production-like chunks in code; the benchmark used 1 MB chunks to force a multi-batch read. Timings are a single run and are machine-specific.

## Uproot executor decision

| Fixture | Serial events/s | Four-worker events/s | Speedup | Batches |
|---|---:|---:|---:|---:|
| 20k events | 1,710,923 | 1,879,858 | 1.10x | 2 |
| 200k events | 957,225 | 944,330 | 0.99x | 20 |

Threshold is 1.30x. Uproot executor parallelism was not enabled because neither fixture met it.

## Parquet codec decision

Current codec was Pandas/PyArrow default Snappy. Benchmark data used a mass column plus int32 run and int64 event columns. Read was projected to `mass` only. Peak RSS is the sampled process working-set high-water mark during each write/read pair; because fixture construction is in the same process, it is an upper bound that includes the fixture.

| Fixture | Codec | Write time (s) | Mass-read time (s) | File bytes | Row groups | Process peak RSS (bytes) |
|---|---|---:|---:|---:|---:|---:|
| 20k | Snappy | 0.008195 | 0.021897 | 306,015 | 1 | 122,552,320 |
| 20k | Zstd | 0.005717 | 0.012810 | 235,434 | 1 | 125,243,392 |
| 200k | Snappy | 0.046398 | 0.011340 | 2,935,950 | 1 | 231,985,152 |
| 200k | Zstd | 0.030413 | 0.008342 | 2,167,306 | 1 | 231,985,152 |

Zstd reduced file size by 23.1% and 26.2%; measured mass-projection read time improved by 41.5% and 26.4% respectively. Corresponding write/read throughputs (rows/s) were Snappy 2,440,602/913,375 and Zstd 3,498,399/1,561,219 at 20k; Snappy 4,310,521/17,636,995 and Zstd 6,576,092/23,974,491 at 200k. Sampled process peak RSS was 2.7 MB higher at 20k and equal at 200k. Zstd is adopted as the explicit Parquet codec in `src/utils/paths.py` and used by bronze, silver, gold, and fit Parquet writes. Timings are small-fixture observations; production-scale RSS and throughput remain to be measured during the next full run.

Each test file occupied 0.31 MB or 2.94 MB with Snappy, far below the 128 MB row-group target. The measurements do not support setting a larger row-group size; the writer default remains in use.

## Reproduction

```powershell
.venv\Scripts\python.exe scripts/bench_io.py
```
