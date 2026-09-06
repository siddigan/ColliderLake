from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import add_workspace_to_path

add_workspace_to_path()

from src.access.muon_db import connect_with_tables
from src.utils.paths import data_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the local muon_db Parquet lakehouse with DuckDB.")
    parser.add_argument("--root", default=str(data_dir("muon_db")), help="muon_db lakehouse root.")
    parser.add_argument("--list", action="store_true", help="List registered lakehouse tables.")
    parser.add_argument("--describe", help="Describe a registered table.")
    parser.add_argument("--table", help="Preview a registered table.")
    parser.add_argument("--sql", help="Run a SQL query against registered views.")
    parser.add_argument("--sql-file", help="Run SQL from a file.")
    parser.add_argument("--limit", type=int, default=20, help="Preview row limit.")
    parser.add_argument("--csv", help="Optional CSV output path for query results.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connection, tables = connect_with_tables(args.root)
    table_names = [table.name for table in tables]

    if args.list:
        for table in tables:
            count = connection.execute(f"SELECT count(*) FROM {table.name}").fetchone()[0]
            print(f"{table.layer:6} {table.name:16} {count:8} rows  {table.path}")
        return

    if args.describe:
        _require_table(args.describe, table_names)
        print(connection.execute(f"DESCRIBE {args.describe}").fetchdf().to_string(index=False))
        return

    sql = args.sql
    if args.sql_file:
        sql = Path(args.sql_file).read_text(encoding="utf-8")
    if args.table:
        _require_table(args.table, table_names)
        sql = f"SELECT * FROM {args.table} LIMIT {args.limit}"
    if not sql:
        sql = "SELECT * FROM event_summary LIMIT 20"

    result = connection.execute(sql).fetchdf()
    if args.csv:
        output = Path(args.csv)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
        print(output)
    else:
        print(result.to_string(index=False))


def _require_table(name: str, table_names: list[str]) -> None:
    if name not in table_names:
        raise SystemExit(f"Unknown or missing table {name!r}. Available tables: {', '.join(table_names)}")


if __name__ == "__main__":
    main()

