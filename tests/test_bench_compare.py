from __future__ import annotations

import sys

import pytest

from scripts import bench_compare


def _summary(note: str = "") -> str:
    prefix = f"note: {note}\n" if note else ""
    return (
        prefix
        + "stage | status | duration | rows_out | rows_per_second\n"
        + "bronze | SUCCESS | 10.0s | 100 | 10.00\n"
        + "total_wall_time: 10.0s\n"
    )


def test_compare_refuses_same_path(tmp_path, monkeypatch, capsys):
    path = tmp_path / "run.txt"
    path.write_text(_summary(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["bench_compare", str(path), str(path)])
    with pytest.raises(SystemExit, match="2"):
        bench_compare.main()
    assert "same path" in capsys.readouterr().err


def test_compare_refuses_identical_content_at_different_paths(tmp_path, monkeypatch, capsys):
    old, new = tmp_path / "old.txt", tmp_path / "new.txt"
    old.write_text(_summary(), encoding="utf-8")
    new.write_text(_summary(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["bench_compare", str(old), str(new)])
    with pytest.raises(SystemExit, match="2"):
        bench_compare.main()
    assert "identical content" in capsys.readouterr().err


def test_compare_echoes_backfilled_notes(tmp_path, monkeypatch, capsys):
    old, new = tmp_path / "old.txt", tmp_path / "new.txt"
    old.write_text(_summary("backfilled baseline: historical run"), encoding="utf-8")
    new.write_text(_summary("new measured run"), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["bench_compare", str(old), str(new)])
    bench_compare.main()
    output = capsys.readouterr().out
    assert "# old note: backfilled baseline: historical run" in output
    assert "# new note: new measured run" in output


def test_hodoscope_record_ids_delegate_to_hodo_diff(tmp_path, monkeypatch, capsys):
    from src.hodoscope.registry import run

    monkeypatch.setenv("HODOSCOPE_ROOT", str(tmp_path))
    with run("old", context_providers=[lambda: {"fit_window_z": [86, 96]}], root=tmp_path) as old, old.stage("fit") as stage:
        stage.rows_out = 1
    with run("new", context_providers=[lambda: {"fit_window_z": [70, 110]}], root=tmp_path) as new, new.stage("fit") as stage:
        stage.rows_out = 1
    monkeypatch.setattr(sys, "argv", ["bench_compare", old.run_id, new.run_id])
    with pytest.raises(SystemExit) as result:
        bench_compare.main()
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert "CONTEXT DELTAS" in output
    assert "fit_window_z" in output
    assert output.index("ANALYSIS INPUT CONTEXT DELTA") < output.index("STAGE TIMINGS")
