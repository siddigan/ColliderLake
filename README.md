# ColliderLake

ColliderLake is a local CMS Open Data lakehouse workspace for downloading, inspecting, extracting, plotting, converting, and curating SingleMuon NanoAOD data. It is intentionally scoped for research prototyping, not CERN-scale production processing.

Primary starter dataset:

- CMS Open Data record: https://opendata.cern.ch/record/30563
- Dataset: `/SingleMuon/Run2016H-UL2016_MiniAODv2_NanoAODv9-v1/NANOAOD`
- DOI: `10.7483/OPENDATA.CMS.4BUS.64MV`
- Default sample file uses the CMS Open Data workshop `Run2016H/SingleMuon/NANOAOD` example.

## Structure

```text
ColliderLake/
|-- data/
|   |-- adoc/
|   |-- raw/
|   |-- processed/
|   `-- parquet/
|-- docs/
|-- notebooks/
|-- src/
|   |-- ingestion/
|   |-- physics/
|   |-- features/
|   |-- utils/
|   `-- visualization/
|-- scripts/
|   |-- download_sample.py
|   |-- inspect_root.py
|   |-- extract_muons.py
|   `-- convert_to_parquet.py
|-- outputs/
|-- requirements.txt
|-- README.md
`-- .gitignore
```

## Setup

Python 3.11 or newer is recommended.

Linux/macOS:

```bash
cd ColliderLake
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell with Python 3.11 installed:

```powershell
cd ColliderLake
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `py -3.11` is not available but `python` points to Python 3.11 or newer:

```powershell
cd ColliderLake
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optional future packages are listed but commented out in `requirements.txt`: `coffea`, `dask`, and `polars`.

## Example Workflow

Inspect a remote NanoAOD file through the HTTPS EOS endpoint:

```bash
python scripts/inspect_root.py --limit 60
```

If your Windows network has a custom/self-signed certificate chain and HTTPS reads fail with
`CERTIFICATE_VERIFY_FAILED`, allow insecure SSL for this test session:

```powershell
$env:CERN_ALLOW_INSECURE_SSL = "1"
python scripts/inspect_root.py --limit 60
```

Download the default sample file to `data/raw/`:

```bash
python scripts/download_sample.py
```

Inspect the local file:

```bash
python scripts/inspect_root.py --input data/raw/61FC1E38-F75C-6B44-AD19-A9894155874E.root
```

Extract a few chunked batches and save a muon pT histogram:

```bash
python scripts/extract_muons.py \
  --input data/raw/61FC1E38-F75C-6B44-AD19-A9894155874E.root \
  --step-size "25 MB" \
  --max-batches 2 \
  --output outputs/muon_pt.png
```

Convert selected branches to chunked Parquet:

```bash
python scripts/convert_to_parquet.py \
  --input data/raw/61FC1E38-F75C-6B44-AD19-A9894155874E.root \
  --branches Muon_pt Muon_eta Muon_phi Muon_mass MET_pt Jet_pt \
  --step-size "25 MB" \
  --max-batches 2 \
  --output-dir data/parquet
```

## Adoc Manual File Workflow

Use `data/adoc/` for ROOT files you downloaded manually for testing:

```text
data/adoc/my_test_nanoaod.root
```

The same scripts work with Adoc files:

```powershell
python scripts/inspect_root.py --input data/adoc/my_test_nanoaod.root --limit 80
python scripts/extract_muons.py --input data/adoc/my_test_nanoaod.root --max-batches 2 --output outputs/adoc_muon_pt.png
python scripts/convert_to_parquet.py --input data/adoc/my_test_nanoaod.root --max-batches 2 --output-dir data/parquet/adoc_test
```

Notebook:

```text
notebooks/adoc_basic_etl.ipynb
```

Detailed doc:

```text
docs/ADOC_WORKFLOW.md
```

## Memory Model

The scripts use `uproot` tree iteration and selected branch reads. Defaults are deliberately small:

- only selected branches are read,
- event data is processed in batches,
- `--max-batches` limits early exploration,
- Parquet output is written as separate part files.

Increase `--step-size` and `--max-batches` only after validating local memory and disk usage.

## Modules

- `src/ingestion/root_io.py`: open ROOT files, list branches, iterate selected event batches.
- `src/ingestion/samples.py`: dataset metadata and default sample URLs.
- `src/physics/muons.py`: small muon summary helpers.
- `src/visualization/histograms.py`: CMS-style histogram plotting with `hist` and `mplhep`.
- `src/features/parquet.py`: chunked ROOT-to-Parquet conversion.
- `src/lakehouse/`: PySpark ETL for the `muon_db` bronze, silver, and gold Parquet lakehouse.
- `src/utils/paths.py`: portable workspace-relative paths.
- `src/utils/logging_config.py`: consistent logging setup.

## Future Extension Points

The package layout leaves room for:

- Delphes simulation output ingestion,
- MadGraph/Pythia generated event workflows,
- feature extraction for ML and GNN models,
- event graph construction,
- Parquet lakehouse partitioning,
- Airflow or other orchestration layers,
- distributed execution with Dask or Coffea.

## muon_db PySpark Lakehouse ETL

After converting ROOT files to Parquet, build the data-engineering lakehouse with:

```powershell
python scripts/run_lakehouse_etl.py --source-parquet data/parquet/adoc_test --output-root data/muon_db
```

This writes partitioned Parquet tables under `data/muon_db/bronze`, `data/muon_db/silver`, and `data/muon_db/gold`. Local PySpark requires Java and a configured `JAVA_HOME`. See `docs/MUON_DB_LAKEHOUSE.md` for table details and scope.

Query or visualize the generated tables with:

```powershell
python scripts/query_muon_db.py --list
python scripts/query_muon_db.py --table event_summary --limit 10
python scripts/plot_muon_db.py --plot dimuon_mass
python sandbox/muon_db_playground.py
```

See `docs/MUON_DB_ACCESS.md` for the full access and sandbox structure.

Notebook sandboxes are also available:

```text
notebooks/muon_db_00_catalog_and_layers.ipynb
notebooks/muon_db_01_sql_sandbox.ipynb
notebooks/muon_db_02_visualization_sandbox.ipynb
```

Keep future additions modular and batch-oriented so exploratory scripts do not turn into full-scale processing jobs by accident.
