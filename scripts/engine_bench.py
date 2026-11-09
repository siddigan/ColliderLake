from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from src.cli import run_pipeline
from src.hodoscope.registry import add_tag, all_records, resolve_id
from src.utils.config import fit_config_id, load_yaml, selection_for_dataset
from src.utils.paths import config_path, data_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Hodoscope-recorded gold engine benchmark")
    parser.add_argument("--dataset", default="run2012bc_doublemuparked")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--parts",
        type=int,
        default=20,
        help="leading silver Parquet parts in the benchmark fixture",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 3:
        parser.error("--runs must be at least 3 to support the required median and range")
    if args.parts < 1:
        parser.error("--parts must be positive")

    data_root = Path(os.environ.get("COLLIDERLAKE_DATA_ROOT", "data")).resolve()
    hodo_root = Path(os.environ.get("HODOSCOPE_ROOT", str(data_root / "results")))
    event_parts = sorted(data_path("silver", f"dataset={args.dataset}", "events").glob("*.parquet"))
    matched = [
        event for event in event_parts if (event.parent.parent / "muons" / event.name).is_file()
    ][: args.parts]
    if not matched:
        parser.error(f"no matching silver Parquet parts found for {args.dataset}")
    fixture_rows = sum(_rows(path) for path in matched)
    _, _, selected_id = selection_for_dataset(args.dataset)
    fit_id = fit_config_id(load_yaml(config_path("fits", "resonance_ladder.yaml")))
    os.environ["COLLIDERLAKE_BENCH_FIXTURE_SIZE"] = str(
        f"{fixture_rows} event rows across {len(matched)} parts"
    )
    os.environ["COLLIDERLAKE_GOLD_MAX_PARTS"] = str(len(matched))
    os.environ.setdefault("COLLIDERLAKE_DUCKDB_THREADS", "2")
    os.environ.setdefault("COLLIDERLAKE_DQ_MEM", "2GB")

    groups: dict[str, list[dict[str, Any]]] = {}
    for engine in ("vectorized", "duckdb"):
        records_before = {record["run_id"] for record in all_records(hodo_root)}
        for _ in range(args.runs):
            started = time.perf_counter()
            code = run_pipeline(args.dataset, "gold", quiet=True, engine=engine)
            if code:
                raise RuntimeError(f"Hodoscope-recorded {engine} gold stage exited {code}")
            latest = [
                record
                for record in all_records(hodo_root)
                if record["run_id"] not in records_before
            ]
            if not latest:
                raise RuntimeError(f"no Hodoscope run record created for {engine}")
            record = latest[-1]
            records_before.add(record["run_id"])
            stage = next(item for item in record["stages"] if item["name"] == "gold")
            context = record["context"]["colliderlake_inputs"]
            if (
                context["engine"] != engine
                or context["selection_id"] != selected_id
                or context["fit_config_id"] != fit_id
            ):
                raise RuntimeError("benchmark context changed between engine runs")
            metrics = stage.get("metrics", {})
            part_metrics = metrics.get("parts", [])
            cold_start = metrics.get("cold_start_seconds")
            if engine == "vectorized":
                cold_start = part_metrics[0].get("query_seconds") if part_metrics else None
            groups.setdefault(engine, []).append(
                {
                    "run_id": record["run_id"],
                    "duration_seconds": stage["duration_s"],
                    "wall_seconds": time.perf_counter() - started,
                    "rows_out": stage["rows_out"],
                    "pairs_per_second": stage["rows_per_s"],
                    "peak_rss_bytes": metrics.get("peak_rss_bytes", 0),
                    "output_bytes": sum(p.get("output_bytes", 0) for p in part_metrics),
                    "cold_start_seconds": cold_start,
                    "steady_state_query_seconds": [
                        p.get("steady_state_query_seconds", p.get("query_seconds"))
                        for p in part_metrics[1:]
                    ],
                }
            )

    summaries = {}
    for engine, items in groups.items():
        durations = [item["duration_seconds"] for item in items]
        med = statistics.median(durations)
        median_run = min(items, key=lambda item: abs(item["duration_seconds"] - med))
        label = f"engine-bench-{engine}"
        try:
            existing = resolve_id(label, hodo_root)
        except KeyError:
            add_tag(median_run["run_id"], label, hodo_root)
        else:
            if existing != median_run["run_id"]:
                raise RuntimeError(f"Hodoscope tag {label} already points to {existing}")
        summaries[engine] = {
            "median_seconds": med,
            "range_seconds": [min(durations), max(durations)],
            "median_run_id": median_run["run_id"],
            "contributing_run_ids": [item["run_id"] for item in items],
            "runs": items,
            "cold_start_seconds": [item["cold_start_seconds"] for item in items],
            "steady_state_query_seconds": {
                item["run_id"]: item["steady_state_query_seconds"] for item in items
            },
        }

    result = {
        "dataset_id": args.dataset,
        "fixture": {"event_rows": fixture_rows, "parts": len(matched)},
        "selection_id": selected_id,
        "fit_config_id": fit_id,
        "duckdb": {
            "threads": int(os.environ["COLLIDERLAKE_DUCKDB_THREADS"]),
            "memory_limit": os.environ["COLLIDERLAKE_DQ_MEM"],
        },
        "statistics_source": "Hodoscope run records; per-engine median and range derive from gold stage duration_s",
        "engines": summaries,
    }
    output_path = args.output or data_root / "results" / "engine_benchmark.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output_path)
    return 0


def _rows(path: Path) -> int:
    from pyarrow import parquet

    return parquet.ParquetFile(path).metadata.num_rows


if __name__ == "__main__":
    raise SystemExit(main())
