from __future__ import annotations

import argparse
import logging

from _bootstrap import add_workspace_to_path

add_workspace_to_path()

from src.features.parquet import convert_root_to_parquet
from src.ingestion.samples import DEFAULT_BRANCHES, SINGLE_MUON_RUN2016H_SAMPLE
from src.utils.logging_config import configure_logging
from src.utils.paths import data_dir

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert selected NanoAOD branches to chunked Parquet.")
    parser.add_argument("--input", default=SINGLE_MUON_RUN2016H_SAMPLE.http_url, help="Local ROOT file or remote URL.")
    parser.add_argument("--branches", nargs="+", default=DEFAULT_BRANCHES, help="Branches to convert.")
    parser.add_argument("--output-dir", default=data_dir("parquet"), help="Output Parquet directory.")
    parser.add_argument("--step-size", default="25 MB", help="uproot batch size, e.g. 10000 or '25 MB'.")
    parser.add_argument("--max-batches", type=int, default=2, help="Stop after this many batches.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    try:
        outputs = convert_root_to_parquet(
            args.input,
            list(args.branches),
            args.output_dir,
            step_size=args.step_size,
            max_batches=args.max_batches,
        )
        for path in outputs:
            print(path)
        LOGGER.info("Wrote %s Parquet part(s)", len(outputs))
    except Exception:
        LOGGER.exception("Parquet conversion failed")
        raise


if __name__ == "__main__":
    main()
