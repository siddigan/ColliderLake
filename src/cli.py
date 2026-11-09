from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.acquire.clam import diagnose_file, download_file, write_diagnosis
from src.acquire.local import acquire_dataset
from src.bronze.convert import build_bronze
from src.dq.checks import run_dq
from src.gold.dimuon import build_gold
from src.hodoscope.registry import run as hodo_run
from src.physics.fitting import fit_resonance
from src.silver.build import build_silver
from src.utils.config import dataset_config, fit_config_id, load_yaml
from src.utils.hodo_adapter import context_provider, preflight_values
from src.utils.memory import PeakProcessTreeRSS
from src.utils.paths import config_path, configured_data_path, data_path, data_root
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


def main() -> int:
    parser = argparse.ArgumentParser(description="ColliderLake 2.0 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run a pipeline stage")
    run.add_argument("--dataset", required=True)
    run.add_argument("--stage", choices=STAGES, default="all")
    run.add_argument("--max-batches", type=int)
    run.add_argument("--verbose", action="store_true")
    run.add_argument("--quiet", action="store_true")
    run.add_argument("--expect-fit-config")
    run.add_argument("--expect-selection")
    run.add_argument("--engine", choices=["vectorized", "duckdb"])
    run.add_argument(
        "--analysis", help="Selection analysis name when a dataset has multiple selections"
    )
    run.add_argument("--strict", action="store_true")
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
        return run_pipeline(
            args.dataset,
            args.stage,
            args.max_batches,
            verbose=args.verbose,
            quiet=args.quiet,
            expect_fit_config=args.expect_fit_config,
            expect_selection=args.expect_selection,
            strict=args.strict,
            engine=args.engine,
            analysis=args.analysis,
        )
    elif args.command == "clam":
        configure_logging(
            quiet=getattr(args, "quiet", False), verbose=getattr(args, "verbose", False)
        )
        run_clam(args)
    return 0


def run_pipeline(
    dataset_id: str,
    stage: str,
    max_batches: int | None = None,
    *,
    verbose: bool = False,
    quiet: bool = False,
    expect_fit_config: str | None = None,
    expect_selection: str | None = None,
    strict: bool = False,
    engine: str | None = None,
    analysis: str | None = None,
) -> int:
    configure_logging(quiet=quiet, verbose=verbose)
    from src.utils.paths import data_root

    record = hodo_run(
        f"colliderlake:{dataset_id}:{stage}",
        context_providers=[context_provider(dataset_id, engine, analysis)],
        env_prefixes=("HODO", "COLLIDERLAKE_"),
        root=os.environ.get("HODOSCOPE_ROOT", str(data_root() / "results")),
    )
    failure = None
    traceback = None
    guard_aborted = False
    try:
        with record:
            recorded_inputs = record.data["context"]["colliderlake_inputs"]
            inputs = {
                **recorded_inputs,
                "fit_windows": {
                    key.removeprefix("fit_window_"): value
                    for key, value in recorded_inputs.items()
                    if key.startswith("fit_window_")
                },
            }
            preflight = preflight_values(record.run_id, inputs, record.data["git"])
            record.preflight(preflight)
            _print_preflight(preflight, quiet=quiet)
            reason = None
            if expect_fit_config and expect_fit_config != inputs["fit_config_id"]:
                reason = f"--expect-fit-config guard: expected {expect_fit_config}, actual {inputs['fit_config_id']}"
            elif expect_selection and expect_selection != inputs["selection_id"]:
                reason = f"--expect-selection guard: expected {expect_selection}, actual {inputs['selection_id']}"
            elif strict and record.data["git"].get("dirty"):
                reason = "--strict guard: dirty working tree at commit " + str(
                    record.data["git"].get("commit")
                )
            if reason:
                record.abort(reason)
                print(f"Hodoscope preflight ABORTED: {reason}", file=sys.stderr)
                guard_aborted = True
            else:
                _execute_pipeline(
                    dataset_id, stage, max_batches, verbose, quiet, record, engine, analysis
                )
    except BaseException as exc:  # noqa: BLE001 - persist summary before propagating interrupts unchanged
        failure, traceback = exc, exc.__traceback__
    _write_compatibility_outputs(record, archive=(stage == "all"))
    if guard_aborted:
        return 2
    if failure is not None:
        raise failure.with_traceback(traceback)
    return 0


def _print_preflight(values: dict[str, object], *, quiet: bool) -> None:
    summary = (
        f"preflight run_id={values['run_id']} commit={values['commit']} "
        f"selection_id={values['selection_id']} fit_config_id={values['fit_config_id']} "
        f"workers={values['workers']} data_root={values['data_root']}"
    )
    if values.get("dirty"):
        summary += " DIRTY=" + ",".join(values.get("dirty_files", []))
    print(summary, file=sys.stderr if values.get("dirty") else sys.stdout)
    for resonance, window in values["fit_windows"].items():
        print(f"preflight fit_window {resonance}={window}")


def _execute_pipeline(
    dataset_id: str,
    stage: str,
    max_batches: int | None,
    verbose: bool,
    quiet: bool,
    recorder,
    engine: str | None = None,
    analysis: str | None = None,
) -> None:
    configure_logging(quiet=quiet, verbose=verbose)
    stages = ["acquire", "bronze", "silver", "gold", "fit"] if stage == "all" else [stage]
    results: dict[str, StageResult] = {}
    run_started = time.monotonic()
    try:
        for item in stages:
            hstage = recorder.stage(item)
            hstage.__enter__()
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
            rss_monitor = PeakProcessTreeRSS().start()
            try:
                output = _run_stage(
                    item, dataset_id, max_batches, recorder.run_id, engine, analysis
                )
                elapsed = time.monotonic() - stage_started
                hstage.metric("peak_rss_bytes", rss_monitor.stop())
                stats = stage_stats(item)
                results[item] = StageResult("SUCCESS", elapsed, stats.rows_out, stats.batches)
                hstage.rows_out = stats.rows_out
                hstage.metric("batches", stats.batches)
                if item == "gold" and output is not None:
                    metrics_path = Path(output) / "engine_metrics.json"
                    if metrics_path.is_file():
                        engine_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                        for key, value in engine_metrics.items():
                            hstage.metric(key, value)
                hstage.__exit__(None, None, None)
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
            except BaseException as exc:
                hstage.metric("peak_rss_bytes", rss_monitor.stop())
                elapsed = time.monotonic() - stage_started
                stats = stage_stats(item)
                results[item] = StageResult("FAILED", elapsed, stats.rows_out, stats.batches)
                safe_log(logger, logging.ERROR, "stage %s FAILED", item)
                hstage.__exit__(type(exc), exc, exc.__traceback__)
                raise
    finally:
        summary = _run_summary(dataset_id, results, time.monotonic() - run_started, analysis)
        recorder.data["summary"] = summary


def _write_compatibility_outputs(record, *, archive: bool) -> None:
    summary = record.data.get("summary")
    if not summary:
        return
    results = data_path("results")
    canonical_ref = _canonical_run_ref(record)
    run_header = f"run_id: {record.run_id} \u2014 canonical: {canonical_ref}/\n"
    displayed = run_header + summary
    print(displayed, end="")
    canonical_summary = record.run_dir / "run_summary.txt"
    _atomic_text(canonical_summary, displayed)
    record.artifact(canonical_summary)

    fit_source = (
        results
        / "analysis=resonance"
        / f"dataset={record.data['context']['colliderlake_inputs']['dataset_id']}"
        / "fits.json"
    )
    fit_succeeded = any(
        item.get("name") == "fit" and item.get("status") == "succeeded"
        for item in record.data.get("stages", [])
    )
    if fit_succeeded and fit_source.is_file():
        canonical_fits = record.run_dir / "fits.json"
        shutil.copyfile(fit_source, canonical_fits)
        record.artifact(canonical_fits)
        parquet_source = fit_source.with_suffix(".parquet")
        if parquet_source.is_file():
            canonical_parquet = record.run_dir / "fits.parquet"
            shutil.copyfile(parquet_source, canonical_parquet)
            record.artifact(canonical_parquet)
        fits_payload = json.loads(fit_source.read_text(encoding="utf-8"))
        _atomic_text(
            fit_source,
            json.dumps(
                {
                    "_hodoscope": {
                        "run_id": record.run_id,
                        "canonical": f"{canonical_ref}/fits.json",
                    },
                    "fits": fits_payload,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    _atomic_text(results / "run_summary.txt", displayed)
    if archive:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        _atomic_text(results / "benchmarks" / f"run_summary_{stamp}.txt", displayed)


def _atomic_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _canonical_run_ref(record) -> str:
    try:
        return record.run_dir.relative_to(data_root()).as_posix()
    except ValueError:
        return str(record.run_dir.resolve())


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


def _run_stage(
    item: str,
    dataset_id: str,
    max_batches: int | None,
    run_id: str | None = None,
    engine: str | None = None,
    analysis: str | None = None,
) -> Path | None:
    if item == "acquire":
        return acquire_dataset(dataset_id)
    if item == "bronze":
        path = build_bronze(dataset_id, max_batches=max_batches)
        run_dq(dataset_id, "bronze", path, run_id=run_id, analysis=analysis)
        return path
    if item == "silver":
        path = build_silver(dataset_id)
        run_dq(dataset_id, "silver", path, run_id=run_id, analysis=analysis)
        return path
    if item == "gold":
        path = build_gold(dataset_id, engine=engine, analysis=analysis)
        run_dq(dataset_id, "gold", path, run_id=run_id, analysis=analysis)
        return path
    if item == "fit":
        if analysis is not None and analysis != "resonance":
            raise ValueError("fit stage currently supports only analysis='resonance'")
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


def _run_summary(
    dataset_id: str, results: dict[str, StageResult], total: float, analysis: str | None = None
) -> str:
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
            f"analysis: {analysis or _resolved_analysis(dataset_id)}",
            f"selection_id: {_selection_id(dataset_id, analysis)}",
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


def _resolved_analysis(dataset_id: str, analysis: str | None = None) -> str:
    from src.utils.config import selection_for_dataset

    return str(selection_for_dataset(dataset_id, analysis)[1]["analysis"])


def _selection_id(dataset_id: str, analysis: str | None = None) -> str:
    try:
        from src.utils.config import selection_for_dataset

        return selection_for_dataset(dataset_id, analysis)[2]
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    main()
