from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from src.utils.paths import data_dir


DEFAULT_TABLES: dict[str, str] = {
    "bronze_event": "bronze/bronze_event",
    "bronze_muon": "bronze/bronze_muon",
    "bronze_jet": "bronze/bronze_jet",
    "bronze_met": "bronze/bronze_met",
    "bronze_trigger": "bronze/bronze_trigger",
    "silver_event": "silver/silver_event",
    "silver_muon": "silver/silver_muon",
    "silver_jet": "silver/silver_jet",
    "silver_met": "silver/silver_met",
    "silver_trigger": "silver/silver_trigger",
    "event_summary": "gold/event_summary",
    "dimuon": "gold/dimuon",
    "jet": "gold/jet",
    "met": "gold/met",
}


@dataclass(frozen=True)
class LakehouseTable:
    name: str
    layer: str
    path: Path
    parquet_glob: str


def muon_db_root(root: str | Path | None = None) -> Path:
    if root is None:
        return data_dir("muon_db")
    return Path(root).expanduser().resolve()


def table_path(table: str, root: str | Path | None = None) -> Path:
    try:
        relative = DEFAULT_TABLES[table]
    except KeyError as exc:
        raise KeyError(f"Unknown table {table!r}; use one of {sorted(DEFAULT_TABLES)}") from exc
    return muon_db_root(root) / relative


def parquet_glob(path: Path) -> str:
    return (path / "**" / "*.parquet").as_posix()


def discover_tables(root: str | Path | None = None) -> list[LakehouseTable]:
    base = muon_db_root(root)
    tables: list[LakehouseTable] = []
    for name, relative in DEFAULT_TABLES.items():
        path = base / relative
        if not path.exists():
            continue
        layer = relative.split("/", 1)[0]
        tables.append(LakehouseTable(name=name, layer=layer, path=path, parquet_glob=parquet_glob(path)))
    return tables


def connect(database: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(database))
    connection.execute("INSTALL parquet")
    connection.execute("LOAD parquet")
    return connection


def register_tables(
    connection: duckdb.DuckDBPyConnection,
    root: str | Path | None = None,
    tables: list[str] | None = None,
) -> list[LakehouseTable]:
    discovered = discover_tables(root)
    if tables is not None:
        requested = set(tables)
        discovered = [table for table in discovered if table.name in requested]

    for table in discovered:
        glob_literal = _sql_string(table.parquet_glob)
        connection.execute(
            f"""
            CREATE OR REPLACE VIEW {table.name} AS
            SELECT *
            FROM parquet_scan({glob_literal}, hive_partitioning = true, union_by_name = true)
            """
        )
    return discovered


def connect_with_tables(root: str | Path | None = None) -> tuple[duckdb.DuckDBPyConnection, list[LakehouseTable]]:
    connection = connect()
    return connection, register_tables(connection, root=root)


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
