from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.m1c_closeout import (
    ensure_performance_pointer,
    render_engine_table,
    sync_engine_tags,
    validate_performance_doc,
    write_engine_benchmark,
)


@pytest.fixture
def mini_registry(tmp_path, monkeypatch):
    root = tmp_path / "registry"
    runs = root / "runs"
    runs.mkdir(parents=True)
    ids = {engine: tuple(f"synthetic-{engine}-{index}" for index in range(1, 4))
           for engine in ("vectorized", "duckdb")}
    for engine, engine_ids in ids.items():
        for index, run_id in enumerate(engine_ids, start=1):
            context = {
                "dataset_id": "fixture_dataset",
                "data_root": str(tmp_path / "data"),
                "fixture_size": "30 silver rows",
                "gold_max_parts": "3",
                "selection_id": "sel-fixture",
                "fit_config_id": "fit-fixture",
                "gold_config_sha256": "a" * 64,
                "io_config_sha256": "b" * 64,
                "engine": engine,
                "duckdb_threads": 2,
                "duckdb_memory_limit": "300MB",
            }
            parts = [
                {"part": f"part-{part}.parquet", "rows": 10,
                 "query_seconds": 1.0 + part, "steady_state_query_seconds": 1.0 + part}
                for part in range(3)
            ]
            metrics = {"parts": parts, "peak_rss_bytes": (index + 1) * 1024 * 1024}
            if engine == "duckdb":
                metrics["cold_start_seconds"] = 0.2 + index / 100
            record = {
                "run_id": run_id,
                "state": "succeeded",
                "context": {"colliderlake_inputs": context},
                "context_hashes": {"colliderlake_inputs": hashlib.sha256(engine.encode()).hexdigest()},
                "stages": [{
                    "name": "gold", "status": "succeeded", "duration_s": 10.0 * index,
                    "rows_per_s": 1000.0 / index, "metrics": metrics,
                }],
            }
            run_dir = runs / run_id
            run_dir.mkdir()
            (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    # The pre-existing tags model an already-adjudicated registry. Recovery
    # should be a no-op for those tags and add only the dated aliases once.
    initial = {"engine-bench-vectorized": ids["vectorized"][1],
               "engine-bench-duckdb": ids["duckdb"][1]}
    (root / "tags.json").write_text(json.dumps(initial), encoding="utf-8")
    monkeypatch.setenv("HODOSCOPE_ROOT", str(root))
    return root, ids


def test_m1c_recovery_is_idempotent(mini_registry, tmp_path):
    _, ids = mini_registry
    registry = Path(os.environ["HODOSCOPE_ROOT"])
    run_ids = (*ids["vectorized"], *ids["duckdb"])
    benchmark = tmp_path / "published" / "engine_benchmark.json"
    tags = registry / "tags.json"
    m1_doc = tmp_path / "M1_RESONANCE_LADDER.md"
    m1_doc.write_text("## 3. Performance baseline\n\nContent\n\n## 4. Next\n", encoding="utf-8")

    assert write_engine_benchmark(registry, benchmark, run_ids)
    assert sync_engine_tags(registry, run_ids, previous_vectorized_id=None) == 2
    first_benchmark = hashlib.sha256(benchmark.read_bytes()).hexdigest()
    first_tags = hashlib.sha256(tags.read_bytes()).hexdigest()
    first_mtime = tags.stat().st_mtime_ns
    assert not write_engine_benchmark(registry, benchmark, run_ids)
    assert sync_engine_tags(registry, run_ids, previous_vectorized_id=None) == 0
    assert hashlib.sha256(benchmark.read_bytes()).hexdigest() == first_benchmark
    assert hashlib.sha256(tags.read_bytes()).hexdigest() == first_tags
    assert tags.stat().st_mtime_ns == first_mtime
    assert ensure_performance_pointer(m1_doc)
    first_doc = m1_doc.read_bytes()
    assert not ensure_performance_pointer(m1_doc)
    assert m1_doc.read_bytes() == first_doc


def test_parse_compare_and_corruption_rejection(mini_registry, tmp_path):
    _, ids = mini_registry
    registry = Path(os.environ["HODOSCOPE_ROOT"])
    run_ids = (*ids["vectorized"], *ids["duckdb"])
    benchmark = tmp_path / "engine_benchmark.json"
    write_engine_benchmark(registry, benchmark, run_ids)
    document = tmp_path / "performance.md"
    run_list = "\n".join(f"- `{run_id}`" for run_id in run_ids)
    document.write_text(render_engine_table(json.loads(benchmark.read_text())) + "\n" + run_list + "\n",
                         encoding="utf-8")
    validate_performance_doc(document, benchmark, registry, ledger_run_ids=())
    corrupted = document.read_text(encoding="utf-8").replace("20.000", "20.001", 1)
    document.write_text(corrupted, encoding="utf-8")
    with pytest.raises(ValueError, match="differ from benchmark JSON"):
        validate_performance_doc(document, benchmark, registry, ledger_run_ids=())


@pytest.mark.realdata
def test_m1c_real_artifacts_validate():
    registry = Path("data/results")
    document = Path("docs/results/M1C_PERFORMANCE.md")
    snapshot = Path("docs/results/engine_benchmark.json")
    required = [document, snapshot, *(registry / "runs" / run_id / "run.json"
                                      for run_id in (
        "20261102T212222.616810Z-81e86a", "20261102T212222.888504Z-ea3c43",
        "20261110T080408.893920Z-e75d65", "20261110T082043.046113Z-e9f922",
        "20261110T084009.385033Z-88b429", "20261110T084042.916422Z-1e921b",
        "20261110T084118.746168Z-fb8cb4", "20261110T084155.199631Z-a027f9",
        "20261110T084244.373337Z-ec287e", "20261110T084332.907829Z-90ca89",
    ))]
    if not all(path.is_file() for path in required):
        pytest.skip("realdata closeout artifacts are absent; synthetic coverage remains active")
    snapshot_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert f"SHA-256 `{snapshot_hash}`" in document.read_text(encoding="utf-8")
    validate_performance_doc(document, snapshot, registry)
