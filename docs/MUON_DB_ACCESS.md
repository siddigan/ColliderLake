# muon_db Query And Visualization Access

The Spark ETL writes partitioned Parquet tables under:

```text
data/muon_db/
|-- bronze/
|-- silver/
`-- gold/
```

The access layer registers those folders as DuckDB SQL views so you can query them quickly without starting Spark.

## Tables

```text
bronze_event
bronze_muon
bronze_jet
bronze_met
bronze_trigger
silver_event
silver_muon
silver_jet
silver_met
silver_trigger
event_summary
dimuon
jet
met
```

## Query

List tables and row counts:

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

Run a sandbox SQL file:

```powershell
python scripts/query_muon_db.py --sql-file sandbox/sql/event_summary_top_st.sql
```

Export query results:

```powershell
python scripts/query_muon_db.py --sql-file sandbox/sql/event_summary_top_st.sql --csv outputs/top_st_events.csv
```

## Plot

```powershell
python scripts/plot_muon_db.py --plot dimuon_mass
python scripts/plot_muon_db.py --plot muon_pt
python scripts/plot_muon_db.py --plot met_pt
python scripts/plot_muon_db.py --plot jet_pt
```

Images are written to `outputs/` unless `--output` is provided.

## Sandbox

Use the editable Python sandbox:

```powershell
python sandbox/muon_db_playground.py
```

Edit `sandbox/muon_db_playground.py` or add SQL files under `sandbox/sql/` while exploring the lakehouse.

## Notebooks

Notebook versions of the access layer and sandbox are available under `notebooks/`:

```text
notebooks/muon_db_00_catalog_and_layers.ipynb
notebooks/muon_db_01_sql_sandbox.ipynb
notebooks/muon_db_02_visualization_sandbox.ipynb
```

Use them for layer definitions, table descriptions, SQL exploration, and inline plots.
