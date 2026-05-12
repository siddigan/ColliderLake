from __future__ import annotations

from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))

from src.access.muon_db import connect_with_tables


def main() -> None:
    connection, tables = connect_with_tables(WORKSPACE / "data" / "muon_db")

    print("Available tables")
    for table in tables:
        print(f"- {table.name:16} {table.path}")

    print("\nEvent summary sample")
    print(
        connection.execute(
            """
            SELECT event_id, n_muons, n_jets, leading_muon_pt, MET_pt, HT, ST
            FROM event_summary
            ORDER BY ST DESC
            LIMIT 10
            """
        ).fetchdf()
    )

    print("\nDimuon mass window")
    print(
        connection.execute(
            """
            SELECT count(*) AS pairs_near_z, avg(invariant_mass) AS avg_mass
            FROM dimuon
            WHERE invariant_mass BETWEEN 70 AND 110
            """
        ).fetchdf()
    )

    # Edit this query while exploring.
    custom_sql = """
    SELECT
        floor(MET_pt / 25) AS met_bin,
        count(*) AS events,
        avg(n_jets) AS avg_jets
    FROM event_summary
    WHERE MET_pt IS NOT NULL
    GROUP BY met_bin
    ORDER BY met_bin
    """
    print("\nCustom query")
    print(connection.execute(custom_sql).fetchdf())


if __name__ == "__main__":
    main()
