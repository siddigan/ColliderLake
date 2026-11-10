from __future__ import annotations

import hashlib
import json
import os
import statistics
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.hodoscope.registry import add_tag, load_record, move_tag

RUN_IDS = (
    "20261110T084009.385033Z-88b429",
    "20261110T084042.916422Z-1e921b",
    "20261110T084118.746168Z-fb8cb4",
    "20261110T084155.199631Z-a027f9",
    "20261110T084244.373337Z-ec287e",
    "20261110T084332.907829Z-90ca89",
)
EXPECTED_ENGINES = ("vectorized", "duckdb")
ALLOWED_ENGINE_CONTEXT_DELTAS = {
    "engine",
    "duckdb_threads",
    "duckdb_memory_limit",
}
BENCHMARK_RELATIVE_PATH = Path("data/results/engine_benchmark.json")


def _gold_stage(record: dict[str, Any]) -> dict[str, Any]:
    return next(stage for stage in record.get("stages", []) if stage.get("name") == "gold")


def _valid_context(record: dict[str, Any]) -> dict[str, Any]:
    contexts = record.get("context", {})
    if len(contexts) != 1:
        raise ValueError(f"{record.get('run_id')}: expected one Hodoscope input context")
    return next(iter(contexts.values()))


def _parts_signature(stage: dict[str, Any]) -> list[tuple[str, int]]:
    parts = stage.get("metrics", {}).get("parts", [])
    signature = []
    for part in parts:
        name = part.get("part") or part.get("part_name")
        rows = part.get("rows") or part.get("rows_out")
        if not isinstance(name, str) or not isinstance(rows, int):
            raise ValueError("gold metrics lack a complete ordered part list")
        signature.append((name, rows))
    return signature


def _cold_start(engine: str, stage: dict[str, Any]) -> float:
    metrics = stage.get("metrics", {})
    if engine == "duckdb":
        value = metrics.get("cold_start_seconds")
    else:
        parts = metrics.get("parts", [])
        value = parts[0].get("query_seconds") if parts else None
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{engine}: missing positive cold-start measurement")
    return float(value)


def _steady_state_median(stage: dict[str, Any]) -> float:
    parts = stage.get("metrics", {}).get("parts", [])[1:]
    values = [
        part.get("steady_state_query_seconds", part.get("query_seconds"))
        for part in parts
    ]
    values = [float(value) for value in values if isinstance(value, (int, float))]
    if not values:
        raise ValueError("gold metrics lack steady-state query measurements")
    return float(statistics.median(values))


def _input_identity(
    contexts: list[dict[str, Any]],
    hashes_by_engine: dict[str, set[str]],
    signatures: list[list[tuple[str, int]]],
) -> dict[str, Any]:
    if len({tuple(signature) for signature in signatures}) != 1:
        raise ValueError("contributing runs do not share the same ordered silver part list")
    reference = dict(contexts[0])
    normalized = [
        {key: value for key, value in context.items() if key not in ALLOWED_ENGINE_CONTEXT_DELTAS}
        for context in contexts
    ]
    if any(item != normalized[0] for item in normalized[1:]):
        raise ValueError("input-relevant context differs across contributing runs")
    for engine, hashes in hashes_by_engine.items():
        if len(hashes) != 1:
            raise ValueError(f"{engine} context hashes differ across its contributing runs")

    input_keys = (
        "dataset_id",
        "data_root",
        "fixture_size",
        "gold_max_parts",
        "selection_id",
        "fit_config_id",
        "gold_config_sha256",
        "io_config_sha256",
    )
    missing = [key for key in input_keys if key not in reference]
    if missing:
        raise ValueError(f"recorded input context is missing fields: {missing}")
    signature_bytes = json.dumps(
        {
            "data_root": reference["data_root"],
            "dataset_id": reference["dataset_id"],
            "fixture_size": reference["fixture_size"],
            "gold_max_parts": reference["gold_max_parts"],
            "parts": signatures[0],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "silver_part_list_fingerprint": hashlib.sha256(signature_bytes).hexdigest(),
        "selection_id": reference["selection_id"],
        "fit_config_id": reference["fit_config_id"],
        "gold_config_sha256": reference["gold_config_sha256"],
        "io_config_sha256": reference["io_config_sha256"],
        "data_root": reference["data_root"],
    }


def build_engine_benchmark(
    registry_root: str | Path,
    run_ids: tuple[str, ...] = RUN_IDS,
) -> dict[str, Any]:
    records = [load_record(run_id, registry_root) for run_id in run_ids]
    contexts: list[dict[str, Any]] = []
    signatures: list[list[tuple[str, int]]] = []
    hashes_by_engine: dict[str, set[str]] = {engine: set() for engine in EXPECTED_ENGINES}
    grouped: dict[str, list[dict[str, Any]]] = {engine: [] for engine in EXPECTED_ENGINES}

    for record in records:
        run_id = record.get("run_id")
        if record.get("state") != "succeeded":
            raise ValueError(f"{run_id}: run did not succeed")
        context = _valid_context(record)
        engine = context.get("engine")
        if engine not in grouped:
            raise ValueError(f"{run_id}: unsupported recorded engine {engine!r}")
        context_hash = record.get("context_hashes", {}).get("colliderlake_inputs")
        if not context_hash:
            raise ValueError(f"{run_id}: missing input context hash")
        hashes_by_engine[engine].add(context_hash)
        contexts.append(context)

        stage = _gold_stage(record)
        if stage.get("status") != "succeeded":
            raise ValueError(f"{run_id}: gold stage did not succeed")
        metrics = stage.get("metrics", {})
        values = {
            "run_id": run_id,
            "wall_s": float(stage["duration_s"]),
            "peak_rss_bytes": int(metrics["peak_rss_bytes"]),
            "pairs_per_s": float(stage["rows_per_s"]),
            "cold_start_s": _cold_start(engine, stage),
        }
        steady = _steady_state_median(stage)
        grouped[engine].append({"values": values, "steady_state_median_s": steady})
        signatures.append(_parts_signature(stage))

    for engine, runs in grouped.items():
        if len(runs) < 3:
            raise ValueError(f"{engine}: only {len(runs)} valid contributing runs")
        if len(runs) != 3:
            raise ValueError(f"{engine}: expected three recorded runs, found {len(runs)}")

    input_identity = _input_identity(contexts, hashes_by_engine, signatures)
    engines: dict[str, Any] = {}
    for engine, runs in grouped.items():
        per_run = [item["values"] for item in runs]
        fields = ("wall_s", "peak_rss_bytes", "pairs_per_s", "cold_start_s")
        median = {
            field: statistics.median(item[field] for item in per_run) for field in fields
        }
        steady_medians = [item["steady_state_median_s"] for item in runs]
        median["steady_state_median_s"] = statistics.median(steady_medians)
        ranges = {
            field: {
                "min": min(item[field] for item in per_run),
                "max": max(item[field] for item in per_run),
            }
            for field in fields
        }
        ranges["steady_state_median_s"] = {
            "min": min(steady_medians),
            "max": max(steady_medians),
        }
        sample_context = next(context for context in contexts if context["engine"] == engine)
        settings: dict[str, Any] = {"engine": engine}
        for key in ("duckdb_threads", "duckdb_memory_limit", "workers", "workers_requested"):
            if key in sample_context:
                settings[key] = sample_context[key]
        engines[engine] = {
            "contributing_run_ids": [item["run_id"] for item in per_run],
            "per_run": per_run,
            "median": median,
            "range": ranges,
            "engine_settings": settings,
        }

    first_context = contexts[0]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scale": f"fixture ({first_context['gold_max_parts']} parts, {first_context['fixture_size'].split()[0]} silver rows)",
        "protocol": {
            "runs_per_engine_min": 3,
            "median_method": "median of wall_s over contributing runs",
            "range_method": "min-max",
            "inputs_must_match": True,
            "permitted_deltas": ["engine", "duckdb_threads", "duckdb_memory_limit"],
        },
        "inputs": input_identity,
        "engines": engines,
        "excluded_runs": [],
        "units": {
            "wall_s": "seconds",
            "peak_rss_bytes": "bytes",
            "pairs_per_s": "pairs/second",
            "cold_start_s": "seconds",
        },
    }


def _without_generated_at(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "generated_at"}


def write_engine_benchmark(
    registry_root: str | Path,
    output_path: str | Path,
    run_ids: tuple[str, ...] = RUN_IDS,
) -> bool:
    output = Path(output_path)
    payload = build_engine_benchmark(registry_root, run_ids)
    if output.is_file():
        current = json.loads(output.read_text(encoding="utf-8"))
        if _without_generated_at(current) == _without_generated_at(payload):
            print("engine_benchmark.json already current")
            return False
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(output)
    return True


def validate_engine_benchmark(
    registry_root: str | Path,
    benchmark_path: str | Path,
    run_ids: tuple[str, ...] = RUN_IDS,
) -> None:
    path = Path(benchmark_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "generated_at", "scale", "protocol", "inputs", "engines", "excluded_runs", "units"
    }
    if set(payload) != required:
        raise ValueError(f"benchmark schema keys differ: {set(payload) ^ required}")
    datetime.fromisoformat(payload["generated_at"])
    expected = build_engine_benchmark(registry_root, run_ids)
    if _without_generated_at(payload) != _without_generated_at(expected):
        raise ValueError("benchmark JSON does not match values recomputed from the registry")
    for engine in EXPECTED_ENGINES:
        recorded_ids = payload["engines"][engine]["contributing_run_ids"]
        if len(recorded_ids) < 3 or recorded_ids != expected["engines"][engine]["contributing_run_ids"]:
            raise ValueError(f"{engine}: contributing run IDs do not validate")


def median_run_ids(registry_root: str | Path) -> dict[str, str]:
    payload = build_engine_benchmark(registry_root)
    result = {}
    for engine, item in payload["engines"].items():
        ordered = sorted(item["per_run"], key=lambda run: (run["wall_s"], run["run_id"]))
        result[engine] = ordered[len(ordered) // 2]["run_id"]
    return result


def sync_engine_tags(registry_root: str | Path) -> int:
    root = Path(registry_root)
    target_ids = median_run_ids(root)
    old_vectorized_id = "20261109T225720.033929Z-2d8f9b"
    operations = (
        ("engine-bench-vectorized", target_ids["vectorized"], old_vectorized_id, True),
        ("engine-bench-duckdb", target_ids["duckdb"], None, False),
        ("engine-bench-vectorized-20261110", target_ids["vectorized"], None, False),
        ("engine-bench-duckdb-20261110", target_ids["duckdb"], None, False),
    )
    writes = 0
    for label, target, expected_old, is_move in operations:
        # Re-read immediately before this individual mutation; registry APIs repeat the
        # expected-current check while holding the cross-process tag lock.
        index_path = root / "tags.json"
        tags = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
        current = tags.get(label)
        if current == target:
            print(f"tag {label} already points to {target}; no write")
            continue
        if is_move:
            if current != expected_old:
                raise RuntimeError(
                    f"STOP tag operation {label}: expected {expected_old}, found {current}"
                )
            writes += int(move_tag(target, label, expected_old or "", root))
        else:
            if current is not None:
                raise RuntimeError(f"STOP tag operation {label}: unexpected target {current}")
            add_tag(target, label, root)
            writes += 1
    return writes


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("write-benchmark", "validate-benchmark"))
    parser.add_argument("--registry", type=Path, default=Path("data/results"))
    parser.add_argument("--output", type=Path, default=BENCHMARK_RELATIVE_PATH)
    args = parser.parse_args()
    if args.action == "write-benchmark":
        write_engine_benchmark(args.registry, args.output)
    else:
        validate_engine_benchmark(args.registry, args.output)
        print("engine_benchmark.json validated against Hodoscope registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
