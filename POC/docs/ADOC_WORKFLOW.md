# Adoc Manual ROOT File Workflow

This document explains how to use manually downloaded ROOT files with the same lightweight ingestion and ETL pipeline.

In this workspace, `adoc` means manually supplied/ad-hoc test data. Use it when you downloaded a ROOT file yourself and want to test the pipeline without using `scripts/download_sample.py`.

## Folder

Place manual test ROOT files here:

```text
ColliderLake/data/adoc/
```

Example:

```text
ColliderLake/data/adoc/my_test_nanoaod.root
```

ROOT files in this folder are ignored by Git through `.gitignore`.

## Normal Workflow

The normal workflow uses the default CERN Open Data sample:

```powershell
cd "c:\Ewok\Abomination\Theory of E\V-TRY\ColliderLake"
python scripts/download_sample.py --insecure-ssl
python scripts/inspect_root.py --input data/raw/61FC1E38-F75C-6B44-AD19-A9894155874E.root
python scripts/extract_muons.py --input data/raw/61FC1E38-F75C-6B44-AD19-A9894155874E.root --max-batches 2
python scripts/convert_to_parquet.py --input data/raw/61FC1E38-F75C-6B44-AD19-A9894155874E.root --max-batches 2
```

Data flow:

```text
CERN URL -> data/raw/*.root -> inspect/extract -> outputs/*.png
                                 |
                                 `-> data/parquet/*.parquet
```

## Adoc Workflow

The Adoc workflow starts from a file you manually placed in `data/adoc/`:

```powershell
cd "c:\Ewok\Abomination\Theory of E\V-TRY\ColliderLake"
python scripts/inspect_root.py --input data/adoc/my_test_nanoaod.root --limit 80
python scripts/extract_muons.py --input data/adoc/my_test_nanoaod.root --max-batches 2 --output outputs/adoc_muon_pt.png
python scripts/convert_to_parquet.py --input data/adoc/my_test_nanoaod.root --max-batches 2 --output-dir data/parquet/adoc_test
```

Data flow:

```text
manual ROOT file -> data/adoc/*.root -> inspect/extract -> outputs/adoc_*.png
                                      |
                                      `-> data/parquet/adoc_test/*.parquet
```

## Notebook Workflow

Open:

```text
notebooks/adoc_basic_etl.ipynb
```

The notebook:

1. Finds the first `.root` file in `data/adoc/`.
2. Opens it with `uproot`.
3. Lists top-level ROOT objects and `Events` branches.
4. Reads a small event batch with selected branches.
5. Computes simple muon pT summaries.
6. Writes `outputs/adoc_muon_pt.png`.
7. Converts selected branches to `data/parquet/adoc_test/*.parquet`.
8. Reads one Parquet part back for verification.

## ETL Meaning

ETL means extract, transform, load.

Extract:

- Open the ROOT file.
- Read only selected branches.
- Use chunked/batched reading instead of loading the whole file.

Transform:

- Flatten jagged arrays only when needed for plots.
- Keep event-level arrays as Awkward Arrays for Parquet output.
- Compute first-pass summaries such as event count, muon count, mean muon pT, and max muon pT.

Load:

- Save plots to `outputs/`.
- Save selected branch batches as Parquet parts in `data/parquet/`.

## Memory Rule

Prefer this:

```python
events.iterate(branches, step_size="25 MB", library="ak")
```

Avoid this during early testing:

```python
events.arrays()
```

The first pattern is chunked and safer. The second can load all branches and all events into memory.
