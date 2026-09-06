from __future__ import annotations

import argparse

from src.acquire.local import acquire_dataset
from src.bronze.convert import build_bronze
from src.dq.checks import run_dq
from src.gold.dimuon import build_gold
from src.physics.fitting import fit_resonance
from src.silver.build import build_silver
from src.utils.paths import data_path

STAGES = ("acquire", "bronze", "silver", "gold", "fit", "all")


def main() -> None:
    parser = argparse.ArgumentParser(description="ColliderLake 2.0 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run a pipeline stage")
    run.add_argument("--dataset", required=True)
    run.add_argument("--stage", choices=STAGES, default="all")
    run.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    if args.command == "run":
        run_pipeline(args.dataset, args.stage, args.max_batches)


def run_pipeline(dataset_id: str, stage: str, max_batches: int | None = None) -> None:
    stages = ["acquire", "bronze", "silver", "gold", "fit"] if stage == "all" else [stage]
    for item in stages:
        if item == "acquire":
            print(acquire_dataset(dataset_id))
        elif item == "bronze":
            path = build_bronze(dataset_id, max_batches=max_batches)
            run_dq(dataset_id, "bronze", path)
            print(path)
        elif item == "silver":
            path = build_silver(dataset_id)
            run_dq(dataset_id, "silver", path)
            print(path)
        elif item == "gold":
            path = build_gold(dataset_id)
            run_dq(dataset_id, "gold", path)
            print(path)
        elif item == "fit":
            print(fit_resonance(dataset_id))
    print(data_path("results") / "dq_report.json")


if __name__ == "__main__":
    main()
