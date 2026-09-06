from __future__ import annotations

from pathlib import Path

import duckdb

from src.utils.paths import data_path


def connect(database: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(database))
    connection.execute("INSTALL parquet")
    connection.execute("LOAD parquet")
    return connection


def register_gold_views(connection: duckdb.DuckDBPyConnection) -> None:
    dimuon_glob = (data_path("gold", "analysis=resonance") / "**" / "*.parquet").as_posix()
    connection.execute(
        """
        CREATE OR REPLACE VIEW gold_dimuon AS
        SELECT * FROM parquet_scan(?, hive_partitioning = true, union_by_name = true)
        """,
        [dimuon_glob],
    )
