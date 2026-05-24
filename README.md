# ColliderLake

ColliderLake is a local CMS Open Data lakehouse and research sandbox for the CMS SingleMuon NanoAOD dataset. It supports ROOT inspection, ROOT-to-Parquet conversion, PySpark ETL into a physics lakehouse, SQL access, visualization notebooks, and a downstream DIAMOND research architecture.

The project is intentionally scoped for reproducible research prototyping, not CERN-scale production processing.

## Dataset

Primary starter dataset:

- CMS Open Data record: https://opendata.cern.ch/record/30563
- Dataset: `/SingleMuon/Run2016H-UL2016_MiniAODv2_NanoAODv9-v1/NANOAOD`
- DOI: `10.7483/OPENDATA.CMS.4BUS.64MV`
- Data type: CMS NanoAOD ROOT files

## Architecture

Implemented flow:

```text
ROOT NanoAOD files
  -> converted Parquet batches
  -> muon_db bronze layer
  -> muon_db silver layer
  -> muon_db gold layer
  -> DuckDB access layer
  -> notebooks, SQL sandbox, plots
```

Designed downstream flow:

```text
gold curated datasets
  -> DIAMOND certified physics
  -> physics marts
  -> object relations
  -> graph-ready tables
  -> anomaly candidates
  -> validation and publication layers
```

## Repository Layout

```text
ColliderLake/
|-- data/
|   |-- adoc/          # manually supplied ROOT files, ignored except .gitkeep
|   |-- raw/           # downloaded ROOT files, ignored except .gitkeep
|   |-- processed/
|   |-- parquet/       # ROOT-to-Parquet outputs, ignored except .gitkeep
|   `-- muon_db/       # generated lakehouse tables, ignored
|-- docs/
|-- notebooks/
|-- outputs/           # generated plots/reports, ignored except .gitkeep
|-- sandbox/
|-- scripts/
|-- src/
|   |-- access/
|   |-- features/
|   |-- ingestion/
|   |-- lakehouse/
|   |-- physics/
|   |-- research/
|   |-- utils/
|   `-- visualization/
|-- requirements.txt
`-- README.md
```

## Setup

Python 3.11 or newer is recommended. The current local development environment has also been used with Python 3.14.

Windows PowerShell:

```powershell
cd ColliderLake
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
cd ColliderLake
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PySpark requires Java. On Windows, the project auto-detects the common Eclipse Adoptium JDK install path and uses a pure-Java local Hadoop filesystem helper so local Parquet writes work without manually installing `winutils.exe`.

## ROOT Ingestion And Inspection

Inspect a remote NanoAOD file:

```powershell
python scripts/inspect_root.py --limit 60
```

If HTTPS certificate validation fails on your network:

```powershell
$env:CERN_ALLOW_INSECURE_SSL = "1"
python scripts/inspect_root.py --limit 60
```

Download the default sample file:

```powershell
python scripts/download_sample.py
```

Inspect a local ROOT file:

```powershell
python scripts/inspect_root.py --input data/raw/61FC1E38-F75C-6B44-AD19-A9894155874E.root
```

Extract a quick muon pT plot:

```powershell
python scripts/extract_muons.py `
  --input data/raw/61FC1E38-F75C-6B44-AD19-A9894155874E.root `
  --step-size "25 MB" `
  --max-batches 2 `
  --output outputs/muon_pt.png
```

## Manual ROOT Files

Use `data/adoc/` for ROOT files downloaded manually:

```text
data/adoc/my_test_nanoaod.root
```

Example:

```powershell
python scripts/inspect_root.py --input data/adoc/my_test_nanoaod.root --limit 80
python scripts/extract_muons.py --input data/adoc/my_test_nanoaod.root --max-batches 2 --output outputs/adoc_muon_pt.png
python scripts/convert_to_parquet.py --input data/adoc/my_test_nanoaod.root --max-batches 2 --output-dir data/parquet/adoc_test
```

Detailed workflow:

```text
docs/ADOC_WORKFLOW.md
notebooks/adoc_basic_etl.ipynb
```

## ROOT To Parquet

Convert selected NanoAOD branches to Parquet before running the Spark lakehouse ETL:

```powershell
python scripts/convert_to_parquet.py `
  --input data/adoc/my_test_nanoaod.root `
  --branches run luminosityBlock event Muon_pt Muon_eta Muon_phi Muon_mass Muon_charge Muon_tightId Muon_pfRelIso04_all Jet_pt Jet_eta Jet_phi Jet_mass Jet_btagDeepB MET_pt MET_phi PuppiMET_pt HLT_IsoMu24 HLT_Mu50 Flag_goodVertices Flag_METFilters `
  --step-size "25 MB" `
  --max-batches 2 `
  --output-dir data/parquet/adoc_test
```

## muon_db Lakehouse ETL

Build the PySpark lakehouse after ROOT files are converted to Parquet:

```powershell
python scripts/run_lakehouse_etl.py `
  --source-parquet data/parquet/adoc_test `
  --output-root data/muon_db
```

Generated tables:

```text
data/muon_db/
|-- bronze/
|   |-- bronze_event/
|   |-- bronze_muon/
|   |-- bronze_jet/
|   |-- bronze_met/
|   `-- bronze_trigger/
|-- silver/
|   |-- silver_event/
|   |-- silver_muon/
|   |-- silver_jet/
|   |-- silver_met/
|   `-- silver_trigger/
`-- gold/
    |-- event_summary/
    |-- dimuon/
    |-- jet/
    `-- met/
```

Implemented ETL logic:

- Bronze projection of selected event, muon, jet, MET, trigger, and quality branches.
- Event identifiers and lineage metadata.
- Event quality filters: `Flag_goodVertices`, `Flag_METFilters`.
- Trigger filter: `HLT_IsoMu24`.
- Cleaned muon filter: tight ID, isolation `< 0.15`, pT `> 20`.
- Flattened silver muon and jet object tables.
- Gold event summary with object counts, leading objects, `MET_pt`, `HT`, and `ST`.
- Gold dimuon table with opposite-sign pairs, invariant mass, and delta R.

More detail:

```text
docs/MUON_DB_LAKEHOUSE.md
```

## Query Access

The access layer uses DuckDB views over Spark-written Parquet folders. This is faster for local exploration than starting Spark every time.

List tables:

```powershell
python scripts/query_muon_db.py --list
```

Preview a table:

```powershell
python scripts/query_muon_db.py --table event_summary --limit 10
```

Describe a table:

```powershell
python scripts/query_muon_db.py --describe dimuon
```

Run SQL:

```powershell
python scripts/query_muon_db.py --sql "SELECT count(*) FROM dimuon WHERE invariant_mass BETWEEN 70 AND 110"
```

Run SQL from the sandbox:

```powershell
python scripts/query_muon_db.py --sql-file sandbox/sql/event_summary_top_st.sql
python scripts/query_muon_db.py --sql-file sandbox/sql/dimuon_z_window.sql
python scripts/query_muon_db.py --sql-file sandbox/sql/research_candidate_queries.sql
```

Export query results:

```powershell
python scripts/query_muon_db.py --sql-file sandbox/sql/event_summary_top_st.sql --csv outputs/top_st_events.csv
```

More detail:

```text
docs/MUON_DB_ACCESS.md
```

## Visualization

Create quick plots from lakehouse tables:

```powershell
python scripts/plot_muon_db.py --plot dimuon_mass
python scripts/plot_muon_db.py --plot muon_pt
python scripts/plot_muon_db.py --plot met_pt
python scripts/plot_muon_db.py --plot jet_pt
```

Generated images are written to `outputs/` unless `--output` is provided.

## Notebooks

Notebook sandboxes:

```text
notebooks/adoc_basic_etl.ipynb
notebooks/muon_db_00_catalog_and_layers.ipynb
notebooks/muon_db_01_sql_sandbox.ipynb
notebooks/muon_db_02_visualization_sandbox.ipynb
notebooks/muon_db_03_diamond_research_blueprint.ipynb
```

Recommended order:

1. `adoc_basic_etl.ipynb`: manual ROOT exploration.
2. `muon_db_00_catalog_and_layers.ipynb`: table catalog, layer definitions, transformations, and business logic.
3. `muon_db_01_sql_sandbox.ipynb`: SQL exploration.
4. `muon_db_02_visualization_sandbox.ipynb`: inline plots and graph-style exploratory visuals.
5. `muon_db_03_diamond_research_blueprint.ipynb`: downstream DIAMOND research design.

## DIAMOND Research Architecture

DIAMOND defines downstream research layers beyond the current bronze/silver/gold lakehouse:

```text
D - Detector and data-quality certification
I - Inference-ready physics features
A - Analysis marts and event selections
M - Multi-object relations and graph structures
O - Observability, validation, and lineage
N - Novelty and anomaly candidate stores
D - Dissemination-ready datasets and reports
```

Start here:

```text
docs/DIAMOND_RESEARCH_ARCHITECTURE.md
docs/RESEARCH_LAYER_TABLE_CONTRACTS.md
docs/RESEARCH_ROADMAP.md
```

List planned downstream layers:

```powershell
python scripts/list_research_layers.py
```

## Python Modules

- `src/ingestion/`: ROOT opening, branch listing, event batch iteration, sample metadata.
- `src/features/`: ROOT-to-Parquet conversion helpers.
- `src/physics/`: small physics helper functions.
- `src/lakehouse/`: PySpark bronze/silver/gold ETL for `muon_db`.
- `src/access/`: DuckDB access layer for querying generated lakehouse tables.
- `src/visualization/`: CMS-style histograms and reusable plotting helpers.
- `src/research/`: DIAMOND downstream research layer registry.
- `src/utils/`: workspace paths and logging.

## Data And Git Hygiene

Tracked:

- Source code
- Docs
- Notebook templates and sandboxes
- SQL sandbox files
- `.gitkeep` placeholders

Ignored:

- Python virtual environments
- ROOT files under `data/raw/` and `data/adoc/`
- Converted Parquet under `data/parquet/`
- Generated lakehouse tables under `data/muon_db/`
- Spark helper JAR cache under `.spark-jars/`
- Generated outputs under `outputs/`

This keeps GitHub lightweight while preserving the full reproducible pipeline.

## Current Scope

Implemented:

- ROOT inspection and chunked reading.
- ROOT-to-Parquet conversion.
- PySpark data-engineering ETL after Parquet conversion.
- Bronze, silver, and gold `muon_db` tables.
- DuckDB query layer.
- CLI and notebook exploration.
- DIAMOND downstream research architecture design.

Not yet implemented:

- Official CMS golden JSON certification.
- Delta Lake transaction tables.
- Full electron/photon/tau/fat-jet curation.
- Research marts and validation tables as physical outputs.
- Graph node/edge materialization.
- ML training, GNN training, anomaly model scoring.
- Publication artifact generation.

