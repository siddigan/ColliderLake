# ColliderLake 2.0 — Architecture & Design

**Status:** Approved design, implementation in progress
**Supersedes:** ColliderLake 1.0 (single-dataset exploration pipeline)
**First consumer:** Project RESONANCE (dimuon resonance ladder, arXiv `physics.data-an`)
**Second consumer (planned):** DIAMOND anomaly-detection layer (paper #2)

---

## 1. Purpose and identity

ColliderLake 2.0 is a **laptop-scale analysis platform for CERN Open Data**, built with
industry lakehouse patterns (medallion layers, Parquet, DuckDB, Airflow) rather than
HEP-native infrastructure. It is deliberately positioned as the small-scale analog of
HL-LHC analysis facilities (coffea-casa, ServiceX, the IRIS-HEP Analysis Grand
Challenge), translating the HEP data-tier chain (RAW → AOD → MiniAOD → NanoAOD) into
the bronze/silver/gold vocabulary of commercial data engineering.

The identity shift from 1.0: **1.0 was a pipeline that produced plots; 2.0 is a
platform that produces claims** — certified data, fitted results with uncertainties,
and one-command reproducibility.

### Goals
1. Ingest and co-manage heterogeneous CMS Open Data datasets (2012 DoubleMuParked,
   2016 SingleMuon UL NanoAODv9) in one lakehouse.
2. Produce the full dimuon resonance ladder (J/ψ, ψ′, Υ(nS), Z) with
   maximum-likelihood fits compared against PDG reference values.
3. Certified-data guarantees: golden-JSON lumi filtering as a first-class transform.
4. Full-pipeline reproducibility: `git clone` → one command → publication figures.
5. A stable gold-layer contract that paper #2 (anomaly detection) can build on
   without touching ingestion.

### Non-goals
- Competitive precision with CMS/LHCb measurements (this is methodology, not metrology).
- Distributed/cloud execution (documented as a scaling path, not implemented).
- Simulation (MC) processing and full systematic uncertainties (NanoAOD open data
  limits acknowledged in the paper).
- Graph/GNN event representations (deferred to DIAMOND phase 2, post-paper-#2).
- Custom dissemination infrastructure (outsourced to Zenodo, GitHub Pages, REANA).

### Constraints
- Single machine, ~10 GB raw-data budget, nights-and-weekends development.
- Windows-friendly local dev (existing JDK/winutils handling stays) with Docker
  as the canonical execution environment.
- Python 3.11 pinned (PySpark compatibility).

---

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATION SHELL — Airflow (Docker Compose)                         │
│  one DAG per dataset · idempotent tasks · lineage in XCom + manifest    │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ ACQUIRE  │→ │  BRONZE  │→ │  SILVER  │→ │   GOLD   │→ │ RESULTS  │  │
│  │ download │  │ ROOT →   │  │ certify +│  │ dimuon   │  │ fits +   │  │
│  │ verify   │  │ Parquet  │  │ clean    │  │ pairs    │  │ figures  │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│        ↑             ↑             ↑             ↑             ↑        │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ DATASET REGISTRY (datasets.yaml) + SELECTION CONFIGS (cuts/*.yaml)│ │
│  └───────────────────────────────────────────────────────────────────┘ │
│        ↓ every layer boundary                                           │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ DATA QUALITY GATES (dq.py) — row counts, nulls, physics sanity    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
        ┌───────────────────┐              ┌────────────────────────┐
        │ DuckDB access     │              │ DIAMOND interface      │
        │ views over gold   │              │ (paper #2 contract)    │
        └───────────────────┘              └────────────────────────┘
```

**Design principle: configuration over code.** Everything that varies between
datasets or analyses — file URLs, trigger paths, kinematic cuts, fit windows —
lives in versioned YAML, not in Python. The pipeline code is dataset-agnostic.

---

## 3. Storage layout and data model

```
data/
├── raw/                     # immutable ROOT files, checksummed on download
│   ├── run2012bc_doublemuparked/
│   └── run2016h_singlemuon/
├── bronze/                  # ROOT → Parquet, schema-preserving, no cuts
│   └── dataset=<id>/part-*.parquet
├── silver/                  # certified + object-cleaned, trigger FLAGS kept
│   └── dataset=<id>/muons/ · events/
├── gold/                    # analysis-specific tables, trigger CUTS applied
│   └── analysis=resonance/dataset=<id>/dimuon/
└── results/                 # fit outputs, figures, PDG comparison tables
    └── analysis=resonance/
```

### 3.1 Partitioning and keys
- Every table is Hive-partitioned by `dataset=<id>`; gold adds `analysis=<name>`.
- Event identity: `(dataset_id, run, luminosityBlock, event)` — the composite key
  used for lineage joins and dedup checks.
- Bronze rows carry `_ingest_ts`, `_source_file`, `_source_sha256` lineage columns.

### 3.2 Layer contracts

| Layer  | Contract | Mutations allowed |
|--------|----------|-------------------|
| raw    | byte-identical to CERN portal, SHA-256 verified | none (immutable) |
| bronze | 1:1 with ROOT branches, typed, jagged arrays exploded to long format for muons | schema evolution only |
| silver | certified lumi sections only (where golden JSON exists); muon object quality (ID, kinematic range sanity); **trigger flags preserved as columns, never filtered** | re-derivable from bronze |
| gold   | analysis-specific: trigger selection applied, dimuon pairing, derived physics quantities | re-derivable from silver + config |
| results| fit parameters, uncertainties, PDG deltas, figure metadata | re-derivable from gold + config |

The silver/gold trigger split is a deliberate 1.0 bug-fix promoted to a design rule:
**flags are data (silver); selections are analysis decisions (gold).** This is what
lets the Z analysis (IsoMu24) and the ladder analysis (low-threshold dimuon paths)
share silver.

### 3.3 Gold dimuon schema (the RESONANCE + DIAMOND contract)

```
gold.dimuon
  dataset_id        string
  run, lumi, event  int64
  mass              float64   -- invariant mass, GeV
  pt_pair, rapidity float64
  delta_r           float64
  mu1_pt, mu1_eta, mu1_phi, mu1_iso, mu1_charge   float64/int8
  mu2_pt, mu2_eta, mu2_phi, mu2_iso, mu2_charge   float64/int8
  trigger_path      string    -- which path admitted this pair
  selection_id      string    -- config hash: which cuts produced this row
```

`selection_id` = short hash of the resolved selection YAML. Every gold row is
traceable to the exact configuration that produced it. DIAMOND's anomaly work
consumes this table as-is (kinematic + isolation features are already the CATHODE
feature set), so paper #2 requires zero ingestion changes.

---

## 4. Dataset registry and selection configs

### 4.1 `configs/datasets.yaml`

```yaml
datasets:
  run2012bc_doublemuparked:
    portal_record: 12341
    doi: "10.7483/OPENDATA.CMS.YLIC.86ZZ"   # + .M5AD.Y3V3
    energy_tev: 8
    format: nanoaod_reduced_muons
    files:
      - url: <root-file-url>
        sha256: <checksum>
    certification: prefiltered        # validated runs only, upstream
    notes: "Low-threshold dimuon parking triggers; full ladder source"

  run2016h_singlemuon:
    portal_record: 30563
    doi: "10.7483/OPENDATA.CMS...."
    energy_tev: 13
    format: nanoaodv9_ul
    files: [...]
    certification:
      golden_json_record: 14220
      golden_json_file: Cert_271036-284044_13TeV_Legacy2016_Collisions16_JSON.txt
    notes: "IsoMu24 single-muon stream; certified Z showcase"
```

### 4.2 `configs/selections/*.yaml`

```yaml
# selections/resonance_ladder_2012.yaml
selection_id: ladder_2012_v1
dataset: run2012bc_doublemuparked
muon:
  pt_min: 3.0            # LOOSE — preserves J/psi
  abs_eta_max: 2.4
  quality: global_muon
pair:
  opposite_charge: true
trigger:
  paths: []              # parked data: no additional HLT requirement
mass_window: [0.25, 300] # log-scale full spectrum

# selections/z_certified_2016.yaml
selection_id: z_2016_v1
dataset: run2016h_singlemuon
muon:
  pt_min: 20.0
  abs_eta_max: 2.4
  quality: tight_id
  iso_max: 0.15
pair:
  opposite_charge: true
trigger:
  paths: [HLT_IsoMu24]
mass_window: [60, 120]
```

The selection engine resolves a YAML file into an awkward/PySpark filter expression.
Adding a new analysis = adding a YAML file, not editing pipeline code.

### 4.3 `configs/fits/*.yaml`

```yaml
# fits/resonance_ladder.yaml
fits:
  jpsi:    {window: [2.8, 3.4],  signal: crystal_ball, background: exponential, pdg_mass: 3.0969}
  psi2s:   {window: [3.4, 3.95], signal: gaussian,     background: exponential, pdg_mass: 3.6861}
  upsilon: {window: [8.5, 11.5], signal: triple_gaussian, background: chebyshev2,
            pdg_masses: [9.4603, 10.0233, 10.3552]}   # 1S/2S/3S partially merged
  z:       {window: [70, 110],   signal: breit_wigner_conv_gaussian, background: exponential,
            pdg_mass: 91.1876}
caveats:
  trigger_artifact_30gev: "Known trigger turn-on structure near 30 GeV in 2012
    parked data — excluded from all fit windows and documented in paper."
```

---

## 5. Component deep-dives

### 5.1 Acquire (`src/acquire/`)
- Downloads from CERN portal URLs in the registry; verifies SHA-256; writes an
  immutable manifest (`raw/<dataset>/MANIFEST.json`) with DOI, timestamp, checksums.
- Idempotent: existing verified files are skipped. The manifest is the provenance
  root cited in the paper.

### 5.2 Bronze conversion (`src/bronze/`)
- uproot chunked iteration → awkward arrays → Parquet (pyarrow), preserving all
  branches. Muon collections are exploded to a long-format `muons` table keyed by
  `(dataset_id, run, lumi, event, muon_idx)`; event-level scalars (trigger flags,
  MET, quality flags) go to an `events` table.
- Rationale for long format: PySpark and DuckDB both handle it natively; jagged
  logic is confined to the bronze boundary. (Trade-off: a pure awkward pipeline
  would keep jaggedness end-to-end and is faster for pair-building; we accept the
  explode/re-group cost to keep the SQL-lakehouse story coherent. Revisit if a
  coffea processing engine is added in 2.x.)

### 5.3 Certification (`src/silver/certify.py`)
- Parses golden JSON into a `(run, lumi_start, lumi_end)` interval table; broadcast
  range-join against events. Datasets flagged `prefiltered` pass through with a
  `certified=true` column and a documented upstream provenance note.
- Output metric logged per run: events before/after, certified fraction — reported
  in the paper's data section.

### 5.4 Selection engine (`src/silver/clean.py`, `src/gold/select.py`)
- Silver: object-quality cleaning only (ID validity, physical ranges). No triggers,
  no analysis cuts.
- Gold: resolves a selection YAML → filter → opposite-charge pairing (all OS pairs
  per event; leading pair flagged) → derived quantities (mass via 4-vector sum,
  ΔR, pair pT, rapidity) → writes `gold.dimuon` stamped with `selection_id`.
- Invariant mass computed in float64 from (pt, eta, phi, m) components; unit tests
  pin known values.

### 5.5 Fitting & statistics (`src/physics/fitting.py`) — the science layer
- iminuit binned extended maximum-likelihood fits per resonance window.
- Model registry: `gaussian`, `crystal_ball`, `double_gaussian`, `triple_gaussian`,
  `breit_wigner_conv_gaussian` signals; `exponential`, `chebyshev{1,2}` backgrounds.
- Outputs per fit: fitted mass ± stat. uncertainty, width, signal yield, χ²/ndf,
  covariance, pull distribution, and `delta_pdg_sigma = (m_fit − m_PDG)/σ_fit`.
- Persisted as `results/fits.parquet` + JSON sidecar; the PDG comparison table in
  the paper is generated from this file — no hand-transcribed numbers anywhere.
- Explicit scope note: statistical uncertainties only; NanoAOD open data does not
  support full detector systematics. Stated as a limitation, not hidden.

### 5.6 Data-quality gates (`src/dq/`)
Every layer boundary runs a gate; DAG fails fast on breach:
- structural: row counts within tolerance of previous run, no nulls in key columns,
  no duplicate event keys;
- physics sanity: muon pT > 0, |η| ≤ 2.4, isolation ≥ 0, mass > 2·m_μ;
- certification: certified fraction within expected band.
Gate results land in `results/dq_report.json` — cited in the paper as evidence of
engineering discipline.

### 5.7 Orchestration (`dags/`)
- One DAG per dataset (`resonance_2012`, `resonance_2016`) with the linear task
  chain `acquire → bronze → certify → clean → gold → fit → figures`, plus a
  `resonance_paper` DAG that fans in both `fit` outputs to build combined figures.
- Tasks are thin wrappers over `src/` functions (pipeline code never imports
  Airflow); the same functions back a plain CLI (`colliderlake run --stage gold ...`)
  so CI and REANA can execute without Airflow.
- Idempotency: every task writes to a staging path and atomically renames; re-runs
  are safe. Lineage manifest updated per task.

### 5.8 Access layer (`src/access/`)
- DuckDB views over gold/results (`CREATE VIEW dimuon AS SELECT * FROM
  read_parquet('data/gold/analysis=resonance/*/dimuon/*.parquet')`).
- Notebooks consume views only — never raw Parquet paths.

---

## 6. Reproducibility and CI

- **Environment:** `uv`-locked `pyproject.toml`; Python 3.11; Docker image pinned
  by digest. Java/PySpark confined to the image (kills the winutils class of issues
  for canonical runs; local Windows dev path retained for iteration).
- **CI (GitHub Actions):** a ~50 MB sample ROOT file (first N events of the 2012
  file, fetched at CI time from a Zenodo sample deposit) runs the full chain
  acquire→fit; asserts DQ gates pass and the J/ψ fit converges within a loose mass
  tolerance. Every commit proves the pipeline end-to-end.
- **REANA:** `reana.yaml` describing the same CLI stages — HEP-native
  reproducibility credibility, near-zero extra cost given the Airflow-free CLI core.
- **One-command claim:** `docker compose up pipeline` → figures in `results/`.
  This sentence appears verbatim in the paper; CI is what keeps it true.

## 7. Repository layout

```
ColliderLake/
├── configs/            # datasets.yaml, selections/, fits/
├── src/
│   ├── acquire/  bronze/  silver/  gold/
│   ├── physics/        # fitting.py, models.py, pdg.py
│   ├── dq/  access/  cli.py
├── dags/               # airflow DAGs (thin wrappers)
├── docker/             # compose + images
├── tests/              # unit + sample-data integration
├── notebooks/          # exploration; consume DuckDB views only
├── docs/               # this file, ADRs, paper figures pipeline notes
├── reana.yaml
└── paper/              # LaTeX source, generated tables/figures
```

## 8. Trade-offs and explicit decisions

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Pair-building engine | Explode to long format, SQL-style joins | End-to-end awkward jaggedness | Coherent lakehouse story; DuckDB/Spark-native; revisit in 2.x with a coffea engine option |
| Orchestrator | Airflow (Docker) | Dagster, Prefect, Snakemake | User expertise; industry-recognizable; REANA covers the HEP-native angle |
| Trigger handling | Flags in silver, cuts in gold | Filter at silver (1.0 behavior) | Multiple analyses per dataset; the 1.0 approach silently killed quarkonia |
| Fit framework | iminuit direct | zfit, RooFit | Minimal deps, transparent likelihoods, standard in Scikit-HEP; RooFit drags in ROOT runtime |
| Table format | Plain Parquet + Hive partitions | Delta Lake / Iceberg | No concurrent writers on a laptop; ACID adds complexity without benefit at this scale; noted as scaling path in paper |
| Precision | float64 physics columns | float32 | Fit stability; NanoAOD already reduced precision upstream — don't compound it |

## 9. Risks and mitigations

1. **Υ(1S/2S/3S) partially merged at NanoAOD resolution** → triple-Gaussian with
   PDG-fixed mass splittings; report 1S cleanly, 2S/3S as constrained.
2. **30 GeV trigger artifact (2012)** → excluded from fit windows; one honest
   paragraph in the paper. Reviewers know it; hiding it is the only failure mode.
3. **arXiv endorsement latency** → outreach starts at first-ladder-plot, not at
   submission (Phase 3, not Phase 4).
4. **PySpark overhead at 7.5 GB** → acceptable; DuckDB fallback exists for every
   silver/gold transform if Spark friction grows.
5. **Scope creep toward DIAMOND** → hard rule: nothing beyond the gold contract
   ships before the RESONANCE preprint is on arXiv.

## 10. What we'd revisit as the system grows

- **2.x:** RNTuple read path (ROOT's TTree successor); optional coffea/dask-awkward
  processing engine beside PySpark; Delta/Iceberg if multi-writer scenarios appear.
- **3.0 (DIAMOND):** anomaly-candidate store as a new gold-adjacent layer
  (CATHODE/CWoLa weakly-supervised search on dimuon sidebands, per the
  PRL 135, 021902 template); sample-weight and model-artifact management.
- **Scale-out:** the layer contracts are S3-path-compatible by construction;
  swapping `data/` for `s3://` + MWAA is a config change, not a redesign —
  deliberately mirroring the coffea-casa/object-store trajectory of HL-LHC
  analysis facilities.
