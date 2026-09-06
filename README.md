# ColliderLake 2.0

ColliderLake 2.0 is a laptop-scale CMS Open Data lakehouse for Project
RESONANCE. It keeps raw files immutable, derives bronze/silver/gold Parquet
layers, runs quality gates at layer boundaries, and writes reproducible fit
artifacts under `data/results`.

The original ColliderLake 1.0 proof of concept is preserved in `POC/`.

## Quick Start

Place local data in one of these folders:

```text
data/raw/run2012bc_doublemuparked/
data/raw/run2016h_singlemuon/
```

Then run stages with the Airflow-free CLI:

```powershell
python -m src.cli run --dataset run2012bc_doublemuparked --stage all
```

Individual stages are also available:

```powershell
python -m src.cli run --dataset run2012bc_doublemuparked --stage acquire
python -m src.cli run --dataset run2012bc_doublemuparked --stage bronze
python -m src.cli run --dataset run2012bc_doublemuparked --stage silver
python -m src.cli run --dataset run2012bc_doublemuparked --stage gold
python -m src.cli run --dataset run2012bc_doublemuparked --stage fit
```

Neither the experiment(s) (CMS) nor CERN endorse any works, scientific or
otherwise, produced using these data.

## Layout

```text
configs/      dataset, selection, and fit YAML
src/          Airflow-free pipeline core and CLI
dags/         thin Airflow wrappers
docker/       canonical local execution wrapper
tests/        unit and smoke tests
data/         raw, bronze, silver, gold, and results layers
docs/         architecture and operating notes
POC/          preserved ColliderLake 1.0 implementation
```
