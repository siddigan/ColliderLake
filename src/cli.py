from __future__ import annotations

import argparse

from src.acquire.clam import diagnose_file, download_file, write_diagnosis
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
    clam = sub.add_parser("clam", help="ColliderLake Acquisition Manager")
    clam_sub = clam.add_subparsers(dest="clam_command", required=True)
    diagnose = clam_sub.add_parser("diagnose", help="Diagnose headers for a registered file")
    diagnose.add_argument("filename")
    diagnose.add_argument("--dataset", default="run2012bc_doublemuparked")
    diagnose.add_argument("--write", action="store_true", help="Write diagnosis JSON beside raw file")
    download = clam_sub.add_parser("download", help="Resume-safe download for a registered file")
    download.add_argument("filename")
    download.add_argument("--dataset", default="run2012bc_doublemuparked")
    download.add_argument("--tool", choices=["auto", "aria2c", "xrdcp", "native"], default="auto")
    download.add_argument("--max-tries", type=int, default=0)
    download.add_argument("--retry-wait", type=float, default=10.0)
    download.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "run":
        run_pipeline(args.dataset, args.stage, args.max_batches)
    elif args.command == "clam":
        run_clam(args)


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

def run_clam(args: argparse.Namespace) -> None:
    if args.clam_command == "diagnose":
        diagnosis = diagnose_file(args.dataset, args.filename)
        print(f"final_url={diagnosis.final_url}")
        print(f"accept_ranges={diagnosis.accept_ranges}")
        print(f"content_length={diagnosis.content_length}")
        print(f"location={diagnosis.location}")
        if args.write:
            print(write_diagnosis(args.dataset, args.filename))
    elif args.clam_command == "download":
        print(
            download_file(
                dataset_id=args.dataset,
                filename=args.filename,
                tool=args.tool,
                max_tries=args.max_tries,
                retry_wait=args.retry_wait,
                dry_run=args.dry_run,
            )
        )


if __name__ == "__main__":
    main()
