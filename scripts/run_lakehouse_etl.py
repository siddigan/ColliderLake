from __future__ import annotations

import argparse
import logging

from _bootstrap import add_workspace_to_path

add_workspace_to_path()

from src.lakehouse.config import MuonDbConfig
from src.lakehouse.pipeline import MuonDbPipeline
from src.lakehouse.spark import create_spark
from src.utils.logging_config import configure_logging
from src.utils.paths import project_root

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the muon_db bronze, silver, and gold Parquet lakehouse from converted NanoAOD Parquet."
    )
    parser.add_argument(
        "--source-parquet",
        default=str(project_root() / "data" / "parquet"),
        help="Input directory containing Parquet files produced from ROOT conversion.",
    )
    parser.add_argument(
        "--output-root",
        default=str(project_root() / "data" / "muon_db"),
        help="Lakehouse output root. Tables are written under bronze/, silver/, and gold/.",
    )
    parser.add_argument("--dataset", default="SingleMuon", help="Dataset partition value.")
    parser.add_argument("--year", type=int, default=2016, help="Year partition value.")
    parser.add_argument("--run-period", default="RunH", help="Run-period partition value.")
    parser.add_argument("--write-mode", default="overwrite", choices=["overwrite", "append", "error", "ignore"])
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    spark = create_spark()
    try:
        config = MuonDbConfig(
            source_parquet=args.source_parquet,
            output_root=args.output_root,
            dataset=args.dataset,
            year=args.year,
            run_period=args.run_period,
            write_mode=args.write_mode,
        )
        counts = MuonDbPipeline(spark, config).run()
        for table, count in sorted(counts.items()):
            print(f"{table}: {count}")
    except Exception:
        LOGGER.exception("muon_db lakehouse ETL failed")
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()

