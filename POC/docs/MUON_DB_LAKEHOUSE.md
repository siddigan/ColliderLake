# muon_db Lakehouse ETL

This implements the data engineering portion of the CMS SingleMuon NanoAOD design after ROOT files have already been converted to Parquet.

## Scope

Implemented:

- Bronze Parquet projection from converted NanoAOD Parquet.
- Silver cleaned event, muon, jet, MET, and trigger tables.
- Gold analytical event summary, dimuon, jet, and MET datasets.
- Partitioned lakehouse writes by `dataset/year/run_period`.
- Reproducibility columns for dataset path, NanoAOD version, source file, and ingestion timestamp.

Not implemented:

- ROOT parsing inside Spark. Use `scripts/convert_to_parquet.py` first.
- Delta Lake transaction tables. The implementation writes Parquet to avoid extra runtime dependencies.
- ML tensor, GNN graph, anomaly model, feature-store serving, and model outputs.
- Certified luminosity JSON filtering. The table design leaves room for it, but this version only applies in-file quality and trigger flags.

## Run

Prerequisites:

- Python dependencies from `requirements.txt`, including `pyspark`.
- Java installed, because local PySpark starts a JVM. On Windows, the ETL auto-detects the common Eclipse Adoptium install path when `JAVA_HOME` is not already set.
- On Windows, the first run downloads a small pure-Java Hadoop local filesystem JAR into `.spark-jars/` so Spark can write local Parquet without `winutils.exe`.

Convert ROOT to Parquet first:

```powershell
python scripts/convert_to_parquet.py `
  --input data/adoc/576759DA-4A35-534B-B926-2A9E4A5A7268.root `
  --branches run luminosityBlock event Muon_pt Muon_eta Muon_phi Muon_mass Muon_charge Muon_tightId Muon_pfRelIso04_all Jet_pt Jet_eta Jet_phi Jet_mass Jet_btagDeepB MET_pt MET_phi PuppiMET_pt HLT_IsoMu24 HLT_Mu50 Flag_goodVertices Flag_METFilters `
  --output-dir data/parquet/singlemuon_run2016h
```

Build `muon_db`:

```powershell
python scripts/run_lakehouse_etl.py `
  --source-parquet data/parquet/singlemuon_run2016h `
  --output-root data/muon_db
```

## Output Layout

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

Each table is partitioned as:

```text
dataset=SingleMuon/year=2016/run_period=RunH/
```
