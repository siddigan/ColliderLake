from __future__ import annotations

import argparse
import logging

from _bootstrap import add_workspace_to_path

add_workspace_to_path()

from src.ingestion.root_io import get_tree, list_branches, top_level_keys
from src.ingestion.samples import DEFAULT_TREE_NAME, SINGLE_MUON_RUN2016H_SAMPLE
from src.utils.logging_config import configure_logging

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a NanoAOD ROOT file without loading all events.")
    parser.add_argument("--input", default=SINGLE_MUON_RUN2016H_SAMPLE.http_url, help="Local ROOT file or remote URL.")
    parser.add_argument("--tree", default=DEFAULT_TREE_NAME, help="ROOT tree name.")
    parser.add_argument("--limit", type=int, default=80, help="Maximum number of branches to print.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        LOGGER.info("Top-level objects:")
        for name, class_name in top_level_keys(args.input).items():
            print(f"{name:<32} {class_name}")

        tree = get_tree(args.input, args.tree)
        branches = list_branches(args.input, args.tree)
        print(f"\nTree: {args.tree}")
        print(f"Entries: {tree.num_entries}")
        print(f"Branches: {len(branches)}")
        print(f"\nFirst {min(args.limit, len(branches))} branches:")
        for branch in branches[: args.limit]:
            print(branch)
    except Exception:
        LOGGER.exception("ROOT inspection failed")
        raise


if __name__ == "__main__":
    main()
