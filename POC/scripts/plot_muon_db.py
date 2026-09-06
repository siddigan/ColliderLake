from __future__ import annotations

import argparse

from _bootstrap import add_workspace_to_path

add_workspace_to_path()

from src.access.muon_db import connect_with_tables
from src.utils.paths import data_dir, outputs_dir
from src.visualization.histograms import save_histogram


PLOTS: dict[str, tuple[str, str, int, tuple[float, float], str, str]] = {
    "muon_pt": (
        "SELECT pt AS value FROM silver_muon WHERE pt IS NOT NULL",
        "Muon pT [GeV]",
        80,
        (0.0, 200.0),
        "Muon count",
        "muon_db: cleaned muon pT",
    ),
    "dimuon_mass": (
        "SELECT invariant_mass AS value FROM dimuon WHERE invariant_mass IS NOT NULL",
        "m(mu, mu) [GeV]",
        90,
        (0.0, 180.0),
        "Pair count",
        "muon_db: opposite-sign dimuon mass",
    ),
    "met_pt": (
        "SELECT met_pt AS value FROM met WHERE met_pt IS NOT NULL",
        "MET pT [GeV]",
        80,
        (0.0, 250.0),
        "Event count",
        "muon_db: MET",
    ),
    "jet_pt": (
        "SELECT pt AS value FROM jet WHERE pt IS NOT NULL",
        "Jet pT [GeV]",
        80,
        (0.0, 300.0),
        "Jet count",
        "muon_db: jet pT",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create quick plots from muon_db lakehouse tables.")
    parser.add_argument("--root", default=str(data_dir("muon_db")), help="muon_db lakehouse root.")
    parser.add_argument("--plot", choices=sorted(PLOTS), default="dimuon_mass", help="Plot to create.")
    parser.add_argument("--output", help="Output image path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connection, _ = connect_with_tables(args.root)
    sql, xlabel, bins, value_range, ylabel, title = PLOTS[args.plot]
    values = connection.execute(sql).fetchnumpy()["value"]

    output = args.output or str(outputs_dir() / f"muon_db_{args.plot}.png")
    written = save_histogram(values, output, bins=bins, value_range=value_range, xlabel=xlabel, ylabel=ylabel, title=title)
    print(written)


if __name__ == "__main__":
    main()

