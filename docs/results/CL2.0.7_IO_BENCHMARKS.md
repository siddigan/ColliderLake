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

## CL2.1.1 real bronze codec attribution

The benchmark used `scripts/bench_bronze_codecs.py --batches 20` on the first 20 production-size batches of `data/raw/run2012bc_doublemuparked/Run2012BC_DoubleMuParked_Muons.root`. Each case called the existing `build_bronze` path with `COLLIDERLAKE_DATA_ROOT` isolated in a temporary directory. The raw input was hard-linked read-only; event and muon Parquet outputs were separate per case and removed when the run completed. The historical current-code path used Zstd at PyArrow's default level. `write MB/s` is total Parquet output MB divided by summed time inside the two Parquet writer calls; wall time includes read, conversion, and writes. RSS is the Windows process peak working set.

| Codec case | 20 batches wall (s) | Parquet writer time (s) | Write MB/s | Output bytes | Peak RSS (bytes) |
|---|---:|---:|---:|---:|---:|
| Existing codec (Zstd default) | 252.506 | 21.551 | 12.67 | 273,153,049 | 2,017,361,920 |
| Snappy | 249.778 | 19.440 | 20.56 | 399,737,424 | 2,016,718,848 |
| Zstd level 1 | 251.039 | 21.119 | 12.93 | 273,153,049 | 2,015,248,384 |

Snappy had the shortest writer time and highest write throughput: 9.8% less Parquet write time than existing Zstd, with 46.3% more output bytes. Total slice wall time was 1.1% shorter than existing Zstd. Existing default Zstd and explicit Zstd level 1 produced the same byte count; their wall times differed by 1.47 seconds.

### Previous codec decision and evidence

The CL2.0.7 report stated:

> ?Zstd is adopted as the explicit Parquet codec in `src/utils/paths.py` and used by bronze, silver, gold, and fit Parquet writes.?

That decision was based on the 20k and 200k synthetic ROOT/Parquet benchmark in `scripts/bench_io.py`. The codec comparison itself wrote a simple synthetic Pandas frame containing `mass`, `run`, and `event`, then timed a `mass`-only Parquet read. It measured smaller files and faster projected reads with Zstd; it did not measure the write cost of the real jagged-muon bronze path. The real bronze slice above shows why bronze needs a separate codec setting.

### Per-layer policy

`configs/io.yaml` is the single codec policy location. Bronze uses Snappy, the fastest writer on the measured real-file slice. Silver and gold retain Zstd; the CL2.1.0 comparison supplied with this task reports silver at 1.08x and gold at 5.58x versus the backfilled baseline, with gold's large improvement supporting retention of its existing codec. Result Parquet also remains Zstd. Readers rely on Parquet's self-described codec and accept mixed-codec parts; `tests/test_io_codecs.py` covers Snappy bronze input, Zstd muon input, and mixed Snappy/Zstd silver inputs through silver and gold readers.

## Reproduction

```powershell
.venv\Scripts\python.exe scripts/bench_io.py
```
