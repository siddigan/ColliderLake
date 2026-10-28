from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.acquire.clam import diagnose_file, download_file, write_diagnosis
from src.acquire.local import acquire_dataset
from src.bronze.convert import build_bronze
from src.dq.checks import run_dq
from src.gold.dimuon import build_gold
from src.physics.fitting import fit_resonance
from src.silver.build import build_silver
from src.utils.config import dataset_config, fit_config_id, load_yaml
from src.utils.paths import config_path, configured_data_path, data_path, ensure_parent
from src.utils.runlog import (
    begin_stage,
    configure_logging,
    format_duration,
    format_size,
    get_logger,
    safe_log,
    stage_stats,
)

STAGES = ("acquire", "bronze", "silver", "gold", "fit", "all")


@dataclass
class StageResult:
    status: str
    duration: float
    rows_out: int
    batches: int


def main() -> None:
    parser = argparse.ArgumentParser(description="ColliderLake 2.0 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run a pipeline stage")
    run.add_argument("--dataset", required=True)
    run.add_argument("--stage", choices=STAGES, default="all")
    run.add_argument("--max-batches", type=int)
    run.add_argument("--verbose", action="store_true")
    run.add_argument("--quiet", action="store_true")
    clam = sub.add_parser("clam", help="ColliderLake Acquisition Manager")
    clam.add_argument("--verbose", action="store_true")
    clam.add_argument("--quiet", action="store_true")
    clam_sub = clam.add_subparsers(dest="clam_command", required=True)
    diagnose = clam_sub.add_parser("diagnose", help="Diagnose headers for a registered file")
    diagnose.add_argument("filename")
    diagnose.add_argument("--dataset", default="run2012bc_doublemuparked")
    diagnose.add_argument(
        "--write", action="store_true", help="Write diagnosis JSON beside raw file"
    )
    download = clam_sub.add_parser("download", help="Resume-safe download for a registered file")
    download.add_argument("filename")
    download.add_argument("--dataset", default="run2012bc_doublemuparked")
    download.add_argument("--tool", choices=["auto", "aria2c", "xrdcp", "native"], default="auto")
    download.add_argument("--max-tries", type=int, default=0)
    download.add_argument("--retry-wait", type=float, default=10.0)
    download.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "run":
        run_pipeline(
            args.dataset,
            args.stage,
            args.max_batches,
            verbose=args.verbose,
            quiet=args.quiet,
        )
    elif args.command == "clam":
        configure_logging(
            quiet=getattr(args, "quiet", False), verbose=getattr(args, "verbose", False)
        )
        run_clam(args)


def run_pipeline(
    dataset_id: str,
    stage: str,
    max_batches: int | None = None,
    *,
    verbose: bool = False,
    quiet: bool = False,
) -> None:
    configure_logging(quiet=quiet, verbose=verbose)
    stages = ["acquire", "bronze", "silver", "gold", "fit"] if stage == "all" else [stage]
    results: dict[str, StageResult] = {}
    run_started = time.monotonic()
    try:
        for item in stages:
            begin_stage(item)
            logger = get_logger(item)
            safe_log(
                logger,
                logging.INFO,
                "=== STAGE %s START | dataset=%s | input=%s ===",
                item,
                dataset_id,
                _input_description(dataset_id),
            )
            stage_started = time.monotonic()
            try:
                output = _run_stage(item, dataset_id, max_batches)
                elapsed = time.monotonic() - stage_started
                stats = stage_stats(item)
                results[item] = StageResult("SUCCESS", elapsed, stats.rows_out, stats.batches)
                safe_log(
                    logger,
                    logging.INFO,
                    "=== STAGE %s DONE in %s | batches=%d | rows_out=%s ===",
                    item,
                    format_duration(elapsed),
                    stats.batches,
                    f"{stats.rows_out:,}",
                )
                if output is not None:
                    print(output)
            except BaseException:
                elapsed = time.monotonic() - stage_started
                stats = stage_stats(item)
                results[item] = StageResult("FAILED", elapsed, stats.rows_out, stats.batches)
                safe_log(logger, logging.ERROR, "stage %s FAILED", item)
                raise
    finally:
        summary = _run_summary(dataset_id, results, time.monotonic() - run_started)
        _emit_summary(
            summary,
            archive=(stage == "all"),
        )


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


def _run_stage(item: str, dataset_id: str, max_batches: int | None) -> Path | None:
    if item == "acquire":
        return acquire_dataset(dataset_id)
    if item == "bronze":
        path = build_bronze(dataset_id, max_batches=max_batches)
        run_dq(dataset_id, "bronze", path)
        return path
    if item == "silver":
        path = build_silver(dataset_id)
        run_dq(dataset_id, "silver", path)
        return path
    if item == "gold":
        path = build_gold(dataset_id)
        run_dq(dataset_id, "gold", path)
        return path
    if item == "fit":
        return fit_resonance(dataset_id)
    raise ValueError(f"Unknown stage {item!r}")


def _input_description(dataset_id: str) -> str:
    config = dataset_config(dataset_id)
    files = config.get("files", [])
    if not files:
        return f"dataset={dataset_id} (unknown size)"
    item = files[0]
    filename = str(item.get("name", "unknown"))
    raw_dir = configured_data_path(config.get("local_path", f"raw/{dataset_id}"))
    path = raw_dir / filename
    size = path.stat().st_size if path.exists() else item.get("size_bytes")
    return f"{filename} ({format_size(size)})"


def _run_summary(dataset_id: str, results: dict[str, StageResult], total: float) -> str:
    workers = os.environ.get("COLLIDERLAKE_WORKERS", "auto")
    lines = [
        "ColliderLake run summary",
        "stage    | status  | duration | rows_out | rows_per_second",
        "---------|---------|----------|----------|----------------",
    ]
    for stage, result in results.items():
        lines.append(
            f"{stage:<8} | {result.status:<7} | {format_duration(result.duration):<8} | {result.rows_out:,} | {result.rows_out / result.duration if result.duration else 0:.2f}"
        )
    overall = (
        "SUCCESS" if all(result.status == "SUCCESS" for result in results.values()) else "PARTIAL"
    )
    lines.extend(
        [
            "",
            f"dataset_id: {dataset_id}",
            f"overall_status: {overall}",
            f"total_wall_time: {format_duration(total)}",
            f"workers: {workers}",
            "stage_speedup: measured by scripts/bench_compare.py against a prior run summary",
            "pipeline_speedup: measured by scripts/bench_compare.py against a prior run summary",
            f"selection_id: {_selection_id(dataset_id)}",
            f"fit_config_id: {_fit_config_id()}",
            f"results: {data_path('results')}",
            f"dq_report: {data_path('results') / 'dq_report.json'}",
        ]
    )
    return "\n".join(lines) + "\n"


def _fit_config_id() -> str:
    try:
        return fit_config_id(load_yaml(config_path("fits", "resonance_ladder.yaml")))
    except Exception:  # noqa: BLE001
        return "unknown"


def _selection_id(dataset_id: str) -> str:
    try:
        from src.utils.config import selection_for_dataset

        return selection_for_dataset(dataset_id)[2]
    except Exception:  # noqa: BLE001
        return "unknown"


def _emit_summary(summary: str, *, archive: bool = False) -> None:
    _try_print_summary(summary)
    try:
        output = ensure_parent(data_path("results", "run_summary.txt"))
        output.write_text(summary, encoding="utf-8")
        if archive:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
            archived = ensure_parent(data_path("results", "benchmarks", f"run_summary_{stamp}.txt"))
            archived.write_text(summary, encoding="utf-8")
    except Exception:  # noqa: BLE001
        return


def _try_print_summary(summary: str) -> None:
    try:
        print(summary, end="")
    except Exception:  # noqa: BLE001
        return


if __name__ == "__main__":
    main()
