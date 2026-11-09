# CL2.1.3 gold-engine comparison

The gold stage now supports `vectorized` and `duckdb`; `vectorized` remains the
default. The DuckDB implementation self-joins silver Parquet, calculates the
full massive-muon four-vector quantities, and applies the same pair ordering
and schema as the vectorized path. The `nanoaod_full` profile carries the
contract-required muon features into `mu1_` and `mu2_` columns.

## Measured fixture

The Hodoscope benchmark used the first 20 silver parts from
`run2012bc_doublemuparked`: 6,893,480 event rows and 8,824,581 output pairs.
Both engines read those exact same silver files and produced the same pair
count with median output sizes of 560,077,345 bytes (vectorized) and
560,081,435 bytes (DuckDB). The selection ID was `4d93aea9` and fit config ID
was `4c5247e8`. DuckDB used two threads and a 2GB memory limit.

| Engine | Gold stage median | Range | Median pairs/s | Median peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Vectorized | 26.179 s | 25.832–26.439 s | 337,080 | 17.25 GiB |
| DuckDB | 65.737 s | 65.104–66.776 s | 134,241 | 1.48 GiB |

Cold start is reported separately from steady-state work in
[`data/results/engine_benchmark.json`](../data/results/engine_benchmark.json).
The median first-part cold-start measurements were 10.782 s for vectorized and
3.203 s for DuckDB; median subsequent per-part times were 10.625 s and 2.144 s,
respectively. Stage duration includes all parts, output writes and the gold DQ
gate. Peak RSS is sampled across the stage process tree; it reflects the
vectorized engine's automatic multi-process worker setting in this environment.

The benchmark records are in Hodoscope and tagged at the median runs:

- `engine-bench-vectorized`: `20261109T225720.033929Z-2d8f9b`
- `engine-bench-duckdb`: `20261109T230025.678731Z-a94a74`

Each JSON summary entry cites all three contributing run IDs. The measured
comparison favors vectorized for stage time and DuckDB for memory use on this
fixture. These 20-part results should not be read as full-dataset timings.

We did not locate prior published comparisons of these two implementations.
This reports the scope of our search and is not an exhaustive literature claim.
