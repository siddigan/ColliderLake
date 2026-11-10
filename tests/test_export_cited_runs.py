from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.export_cited_runs import DEFAULT_RUN_IDS, export_runs


def test_export_sanitizes_only_paths_and_is_idempotent(tmp_path):
    source = tmp_path / "registry" / "runs" / "fixture-run"
    source.mkdir(parents=True)
    record = {
        "run_id": "fixture-run",
        "context": {"inputs": {"data_root": r"C:\Users\private\ColliderLake\data",
                                "selection_id": "stable-id"}},
        "env": {"vars": {"HODOSCOPE_ROOT": r"C:\Users\private\ColliderLake\data\results",
                          "TMPDIR": r"C:\Users\private\AppData\Local\Temp\session"}},
        "preflight": {"data_root": r"C:\Users\private\ColliderLake\data"},
        "stages": [{"metrics": {"count": 9, "gold_path": r"C:\Users\private\ColliderLake\data\gold\x.parquet",
                                  "metric_hash": "f" * 64}}],
        "summary": "results: C:\\Users\\private\\ColliderLake\\data\\results\n"
                   "dq_report: C:\\Users\\private\\ColliderLake\\data\\results\\dq.json\n",
    }
    (source / "run.json").write_text(json.dumps(record), encoding="utf-8")
    (source / "run_summary.txt").write_text(record["summary"], encoding="utf-8")
    output = tmp_path / "export"
    assert len(export_runs(("fixture-run",), tmp_path / "registry", output)) == 2
    exported = output / "fixture-run" / "run.json"
    text = exported.read_text(encoding="utf-8")
    data = json.loads(text)
    assert "Users" not in text and "AppData" not in text
    assert data["run_id"] == record["run_id"]
    assert data["context"]["inputs"]["selection_id"] == "stable-id"
    assert data["stages"][0]["metrics"]["count"] == 9
    assert data["stages"][0]["metrics"]["metric_hash"] == "f" * 64
    before = exported.read_bytes()
    assert all(line.startswith("unchanged") for line in export_runs(("fixture-run",), tmp_path / "registry", output))
    assert exported.read_bytes() == before
    record["summary"] += "note: changed source record\n"
    (source / "run.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(RuntimeError, match="--refresh"):
        export_runs(("fixture-run",), tmp_path / "registry", output)
    refreshed = export_runs(("fixture-run",), tmp_path / "registry", output, refresh=True)
    assert any("refreshed" in line and " -> " in line for line in refreshed)


def test_committed_cited_run_exports_are_parseable_and_sanitized():
    for run_id in DEFAULT_RUN_IDS:
        directory = Path("docs/results/runs") / run_id
        record_path = directory / "run.json"
        summary_path = directory / "run_summary.txt"
        record_text = record_path.read_text(encoding="utf-8")
        json.loads(record_text)
        for text in (record_text, summary_path.read_text(encoding="utf-8")):
            assert "Users" not in text
            assert "AppData" not in text
            assert not re.search(r"(?i)[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]", text)
