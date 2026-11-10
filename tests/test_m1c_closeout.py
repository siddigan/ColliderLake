from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from scripts.m1c_closeout import (
    RUN_IDS,
    ensure_performance_pointer,
    sync_engine_tags,
    validate_performance_doc,
    write_engine_benchmark,
)


def test_m1c_recovery_is_idempotent(tmp_path):
    source = Path("data/results/runs")
    registry = tmp_path / "registry"
    runs = registry / "runs"
    runs.mkdir(parents=True)
    old_vectorized_id = "20261109T225720.033929Z-2d8f9b"
    for run_id in (*RUN_IDS, old_vectorized_id):
        shutil.copytree(source / run_id, runs / run_id)
    run_record_hashes = {
        run_id: hashlib.sha256((runs / run_id / "run.json").read_bytes()).hexdigest()
        for run_id in (*RUN_IDS, old_vectorized_id)
    }
    tags = {
        "engine-bench-vectorized": old_vectorized_id,
        "engine-bench-duckdb": RUN_IDS[-1],
    }
    tag_path = registry / "tags.json"
    tag_path.write_text(json.dumps(tags), encoding="utf-8")
    benchmark = tmp_path / "results" / "engine_benchmark.json"

    write_engine_benchmark(registry, benchmark)
    sync_engine_tags(registry)
    first_benchmark = hashlib.sha256(benchmark.read_bytes()).hexdigest()
    first_tag = hashlib.sha256(tag_path.read_bytes()).hexdigest()
    first_tag_mtime = tag_path.stat().st_mtime_ns
    assert write_engine_benchmark(registry, benchmark) is False
    assert sync_engine_tags(registry) == 0
    assert hashlib.sha256(benchmark.read_bytes()).hexdigest() == first_benchmark
    assert hashlib.sha256(tag_path.read_bytes()).hexdigest() == first_tag
    assert tag_path.stat().st_mtime_ns == first_tag_mtime
    assert run_record_hashes == {
        run_id: hashlib.sha256((runs / run_id / "run.json").read_bytes()).hexdigest()
        for run_id in (*RUN_IDS, old_vectorized_id)
    }
    final_tags = json.loads(tag_path.read_text(encoding="utf-8"))
    assert final_tags["engine-bench-vectorized"] == RUN_IDS[1]
    assert final_tags["engine-bench-duckdb"] == RUN_IDS[-1]


def test_performance_pointer_is_added_once_in_section_three(tmp_path):
    doc = tmp_path / "M1_RESONANCE_LADDER.md"
    doc.write_text("## 3. Performance baseline\n\nTable\n\n## 4. Next\n", encoding="utf-8")
    assert ensure_performance_pointer(doc)
    first = doc.read_bytes()
    assert not ensure_performance_pointer(doc)
    assert doc.read_bytes() == first
    assert first.count(b"Performance study:") == 1
    assert first.index(b"Performance study:") < first.index(b"## 4.")


def test_performance_table_matches_registry_and_rejects_corruption(tmp_path):
    source = Path("docs/results/M1C_PERFORMANCE.md")
    corrupted = tmp_path / source.name
    text = source.read_text(encoding="utf-8")
    corrupted.write_text(text, encoding="utf-8")
    validate_performance_doc(
        corrupted, "data/results/engine_benchmark.json", "data/results"
    )
    corrupted.write_text(text.replace("35.715", "35.716", 1), encoding="utf-8")
    try:
        validate_performance_doc(
            corrupted, "data/results/engine_benchmark.json", "data/results"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("validator accepted a corrupted benchmark figure")
