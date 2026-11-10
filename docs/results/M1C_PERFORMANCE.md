# M1c performance closeout

Evidence is read from Hodoscope run records under `data/results/runs/<run_id>/run.json`, `docs/results/engine_benchmark.json`, and the pinned raw manifest. Rates and speedups are derived with the formulas shown. Machine-state details not present in individual records are marked UNRESOLVED.

Published benchmark snapshot: `docs/results/engine_benchmark.json`; SHA-256 `32991b5470fc947ed695dc472dcd00d3e8f8e02376d7b116505e2b24e0796eaa`; producing run IDs: `20261110T084009.385033Z-88b429`, `20261110T084042.916422Z-1e921b`, `20261110T084118.746168Z-fb8cb4`, `20261110T084155.199631Z-a027f9`, `20261110T084244.373337Z-ec287e`, `20261110T084332.907829Z-90ca89`.

## Decision rule and verdict

idle bronze <= 16m30s -> ENVIRONMENTAL verdict -> proceed to Task 3  
idle bronze >= 19m00s -> REAL REGRESSION -> STOP after Task 2 report; await a bisect prompt; attempt NO fixes  
between -> INCONCLUSIVE -> STOP after Task 2 report

Idle bronze: 14.55 min, derived from run `20261110T080408.893920Z-e75d65`; ENVIRONMENTAL branch fired. Machine idleness attested by user at launch.

The verdict follows the predeclared rule; the historical comparison is contextual, not causal - the idle run's near-identity with the baseline (14m33s vs 14m28s) is the operative evidence.

## Run ledger

| Record | Bronze | Silver | Gold | Total | Note |
|---|---:|---:|---:|---:|---|
| `20261102T212222.616810Z-81e86a` (CL2.0.6 baseline) | 14.47 min (868.0 s) | 3.10 min (186.0 s) | 14.68 min (881.0 s) | 32.36 min (1941.4 s) | `succeeded` |
| `20261102T212222.888504Z-ea3c43` (CL2.1.0 afternoon; machine conditions uncontrolled; superseded by m1c-final) | 20.75 min (1245.0 s) | 2.87 min (172.0 s) | 2.63 min (158.0 s) | 26.35 min (1581.1 s) | `succeeded` |
| `20261110T080408.893920Z-e75d65` (Idle bronze verdict run) | 14.55 min (873.2 s) | N/A | N/A | 14.55 min (873.2 s) | `succeeded` |
| `20261110T082043.046113Z-e9f922` (m1c-final) | 14.77 min (886.0 s) | 1.37 min (82.3 s) | 2.36 min (141.4 s) | 18.59 min (1115.3 s) | `succeeded` |

Sources: each duration and state is the named run record above; duration units are seconds. The historical CL2.1.0 record is retained and annotated as superseded, never removed.

## Engine benchmark

Registry run records under `data/results/runs/` are authoritative; `docs/results/engine_benchmark.json` is the committed published snapshot, including the silver part-list fingerprint and per-engine Hodoscope context hashes. Medians are the median of three recorded gold-stage runs, ranges are min-max. Cold start is reported separately from steady-state query median.

| Engine | Wall median (range), s | Peak RSS median (range), MiB | Pairs/s median (range) | Cold start median (range), s | Steady query median (range), s | Contributing run IDs |
|---|---:|---:|---:|---:|---:|---|
| duckdb | 48.532 (48.383-48.968) | 2625.8 (2622.2-2703.7) | 181831.0 (180209.6-182390.7) | 1.610 (1.609-1.875) | 1.076 (1.058-1.098) | `20261110T084155.199631Z-a027f9`, `20261110T084244.373337Z-ec287e`, `20261110T084332.907829Z-90ca89` |
| vectorized | 35.715 (33.398-36.304) | 18001.3 (17838.3-18157.5) | 247084.2 (243073.7-264221.5) | 9.047 (8.984-10.235) | 8.890 (8.672-9.594) | `20261110T084009.385033Z-88b429`, `20261110T084042.916422Z-1e921b`, `20261110T084118.746168Z-fb8cb4` |

### Measured comparison

Vectorized is ~1.4x faster in gold-stage wall time; DuckDB uses ~6.9x less peak RSS (2.6 GiB vs 17.6 GiB) and has ~5.6x faster cold start. At this fixture scale, DuckDB offers a substantially lower-memory execution path.

Ratios are derived as vectorized median / DuckDB median. This comparison does not establish hardware-independent performance.

## Environment evidence

The preflight snapshot recorded CPU count 16, free RAM 16,513,966,080 bytes, free disk 106,905,944,064 bytes, timestamp 2026-11-10 13:32:41 +05:30, AC power online, and sleep timeout 0; the user attested machine idleness at launch. Source: session preflight snapshot recorded for CL2.1.7. Battery percentage was not available (AC power state was available). Individual Hodoscope records contain platform, Python, CPU count, total RAM and free disk; they do not contain free RAM, battery, or sleep state, so those per-run values are UNRESOLVED.

| Timed run | Recorded environment (run.json `env`) | Launch idleness |
|---|---|---|
| `20261102T212222.616810Z-81e86a` | UNRESOLVED - historical record has no `env` snapshot; context describes it as an early-morning idle baseline, but no run-level artifact verifies that condition. | UNRESOLVED |
| `20261102T212222.888504Z-ea3c43` | UNRESOLVED - historical record has no `env` snapshot; campaign context describes afternoon conditions as uncontrolled. | UNRESOLVED |
| `20261110T080408.893920Z-e75d65` | Windows-10-10.0.26300-SP0; Python 3.11.15; 16 CPUs; total RAM 31.398487091064453 GB; free disk 99.56073760986328 GB | User attested at launch; per-run attestation record UNRESOLVED |
| `20261110T082043.046113Z-e9f922` | Windows-10-10.0.26300-SP0; Python 3.11.15; 16 CPUs; total RAM 31.398487091064453 GB; free disk 108.91844177246094 GB | User attested at launch; per-run attestation record UNRESOLVED |
| `20261110T084009.385033Z-88b429` | Windows-10-10.0.26300-SP0; Python 3.11.15; 16 CPUs; total RAM 31.398487091064453 GB; free disk 98.33193588256836 GB | User attested at launch; per-run attestation record UNRESOLVED |
| `20261110T084042.916422Z-1e921b` | Windows-10-10.0.26300-SP0; Python 3.11.15; 16 CPUs; total RAM 31.398487091064453 GB; free disk 98.33662033081055 GB | User attested at launch; per-run attestation record UNRESOLVED |
| `20261110T084118.746168Z-fb8cb4` | Windows-10-10.0.26300-SP0; Python 3.11.15; 16 CPUs; total RAM 31.398487091064453 GB; free disk 98.3322639465332 GB | User attested at launch; per-run attestation record UNRESOLVED |
| `20261110T084155.199631Z-a027f9` | Windows-10-10.0.26300-SP0; Python 3.11.15; 16 CPUs; total RAM 31.398487091064453 GB; free disk 98.33222198486328 GB | User attested at launch; per-run attestation record UNRESOLVED |
| `20261110T084244.373337Z-ec287e` | Windows-10-10.0.26300-SP0; Python 3.11.15; 16 CPUs; total RAM 31.398487091064453 GB; free disk 98.32757949829102 GB | User attested at launch; per-run attestation record UNRESOLVED |
| `20261110T084332.907829Z-90ca89` | Windows-10-10.0.26300-SP0; Python 3.11.15; 16 CPUs; total RAM 31.398487091064453 GB; free disk 98.33624267578125 GB | User attested at launch; per-run attestation record UNRESOLVED |

## Speedups vs CL2.0.6 baseline

Formula: baseline stage duration / comparison stage duration; total uses sum of recorded stage durations. Baseline and comparison seconds come from the cited run records.

| Stage | CL2.0.6 baseline | m1c-final | Speedup |
|---|---:|---:|---:|
| bronze | 868.000 s | 885.987 s | 0.98x |
| silver | 186.000 s | 82.289 s | 2.26x |
| gold | 881.000 s | 141.362 s | 6.23x |
| End-to-end (sum of stages) | 1941.400 s | 1115.258 s | 1.74x |

## Integrity and adjudication log

### Adjudication 1 - benchmark input identity

Observed: each engine has three successful runs; same fixture part list and common selection/config/input fields across runs. Context hashes differ between engines because engine selection is part of the recorded context; hashes are stable within each engine. The benchmark JSON records the common input fingerprint, per-engine context hashes, and all six IDs.

Owner decision: compare the two engines on the shared silver input; engine is the only intended context distinction.

Action: generated the benchmark from registry records; no run record was edited.

### Adjudication 2 - manifest timestamp

Observed: working manifest content matches committed content (git diff empty; 481 bytes); manifest mtime changed from 1793180057612528200 ns to 1794298844416298400 ns. ROOT SHA-256 matches pinned value `f8a9d40dba9ee7131a4110f93b4e14a29f99255cbff777018848477f2f61b00b`, size 2244449133 bytes, and recorded mtime unchanged. Source: `data/raw/run2012bc_doublemuparked/MANIFEST.json` and pinned manifest.

Owner adjudication (accepted, not independently proven): content-identical rewrite attributed to acquire, consistent with observed dirty-flag timing after acquire during CL2.1.7.

Implementation response: acquire now skips rewriting a matching manifest; acquire run records carry manifest SHA-256, verification timestamp and run ID. Source: `src/acquire/local.py`, `src/cli.py`.

### Adjudication 3 - historical DuckDB tag

Observed: `20261109T230025.678731Z-a94a74` succeeded with engine=duckdb, a 20-part fixture, data root `colliderlake-cl213-engine-bench-slice20-20261110`, parent commit `29838aa`, and dirty files identifying CL2.1.3 work in progress.

Owner decision: confirmed as the expected historical twin; move authorized.

Action: guarded move executed from `20261109T230025.678731Z-a94a74` to `20261110T084332.907829Z-90ca89`; previous target was logged by Hodoscope. Historical run record preserved.

## Reproducibility

Benchmark values can be recomputed with `python -m scripts.m1c_closeout write-benchmark` and checked with `python -m scripts.m1c_closeout validate-benchmark`. Raw records are in `data/results/runs/`; JSON includes the contributing IDs and formulas.
