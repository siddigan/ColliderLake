from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from src.hodoscope.cli import _diff
from src.hodoscope.log import configure_logging, get_logger
from src.hodoscope.registry import add_tag, all_records, load_record, run


def test_run_lifecycle_stage_failure_persists_and_propagates_original_exception(tmp_path):
    error = RuntimeError("injected stage error")
    record = run("failure-test", root=tmp_path)
    with pytest.raises(RuntimeError) as caught, record as current, current.stage("bronze") as stage:
        stage.rows_out = 12
        stage.metric("files", 2)
        raise error
    assert caught.value is error
    saved = load_record(record.run_id, tmp_path)
    assert saved["state"] == "failed"
    assert saved["failed_stage"] == "bronze"
    assert saved["stages"][0]["status"] == "failed"
    assert saved["stages"][0]["rows_per_s"] > 0
    assert json.loads((record.run_dir / "run.json").read_text(encoding="utf-8")) == saved


def test_exception_outside_stage_and_interrupted_display_are_honest(tmp_path, capsys, monkeypatch):
    failed = run("outside-stage", root=tmp_path)
    with pytest.raises(ValueError, match="outside"), failed:
        raise ValueError("outside")
    assert load_record(failed.run_id, tmp_path)["failure_scope"] == "run"

    interrupted = run("interrupted", root=tmp_path)
    interrupted.__enter__()
    # Simulate the logging context being detached while a process is killed.
    interrupted._log_context.__exit__(None, None, None)
    stored = json.loads((interrupted.run_dir / "run.json").read_text(encoding="utf-8"))
    assert stored["state"] == "running"
    from src.hodoscope.cli import _show_run

    monkeypatch.setenv("HODOSCOPE_ROOT", str(tmp_path))
    _show_run(interrupted.run_id)
    shown = capsys.readouterr().out
    assert "INTERRUPTED" in shown
    assert (
        json.loads((interrupted.run_dir / "run.json").read_text(encoding="utf-8"))["state"]
        == "running"
    )


def test_rows_per_second_null_and_atomic_stage_updates(tmp_path):
    with run("unknown-rows", root=tmp_path) as record, record.stage("no-count"):
        pass
    stage = load_record(record.run_id, tmp_path)["stages"][0]
    assert stage["rows_out"] is None
    assert stage["rows_per_s"] is None
    assert not list(record.run_dir.glob("*.tmp"))


def test_artifact_and_external_directory_have_distinct_integrity_semantics(tmp_path):
    file_path = tmp_path / "source.txt"
    file_path.write_text("artifact", encoding="utf-8")
    directory = tmp_path / "external"
    directory.mkdir()
    (directory / "a.txt").write_text("a", encoding="utf-8")
    (directory / "b.txt").write_text("b", encoding="utf-8")
    with run("artifact-test", root=tmp_path / "registry") as record:
        artifact = record.artifact(file_path)
        external = record.external(directory, rows=2)
        with pytest.raises(ValueError, match="files only"):
            record.artifact(directory)
    assert len(artifact["sha256"]) == 64
    assert external["kind"] == "directory"
    assert [entry["relpath"] for entry in external["inventory"]] == ["a.txt", "b.txt"]
    assert "sha256" not in external
    assert external["metadata"] == {"rows": 2}


def test_two_concurrent_runs_have_separate_ids_and_logs(tmp_path):
    configure_logging()
    barrier = threading.Barrier(2)
    results: list[tuple[str, Path]] = []

    def work(stage: str) -> None:
        with run(f"concurrent-{stage}", root=tmp_path) as record:
            barrier.wait(timeout=5)
            get_logger(stage).warning("message-%s", stage)
            with record.stage(stage) as item:
                item.rows_out = 1
            artifact_path = record.run_dir / "marker.txt"
            artifact_path.write_text(stage, encoding="utf-8")
            record.artifact(artifact_path)
            results.append((record.run_id, record.run_dir / "log.txt"))

    threads = [threading.Thread(target=work, args=(name,)) for name in ("alpha", "beta")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert len({item[0] for item in results}) == 2
    for run_id, log_path in results:
        text = log_path.read_text(encoding="utf-8")
        name = load_record(run_id, tmp_path)["name"]
        assert text
        assert f"message-{name.removeprefix('concurrent-')}" in text
        assert load_record(run_id, tmp_path)["state"] == "succeeded"
        artifacts = json.loads((log_path.parent / "artifacts.json").read_text(encoding="utf-8"))
        assert len(artifacts) == 1
        assert Path(artifacts[0]["absolute_path"]).read_text(encoding="utf-8") == name.removeprefix(
            "concurrent-"
        )


def test_tags_are_unique_and_resolve(tmp_path):
    with run("tagged", root=tmp_path) as record:
        pass
    add_tag(record.run_id, "baseline-cl206", tmp_path)
    assert all_records(tmp_path)[0]["run_id"] == record.run_id
    from src.hodoscope.registry import resolve_id

    assert resolve_id("baseline-cl206", tmp_path) == record.run_id
    with pytest.raises(ValueError, match="already points"):
        add_tag(record.run_id, "baseline-cl206", tmp_path)


def test_sql_exposes_run_json_records(tmp_path, monkeypatch, capsys):
    from src.hodoscope.cli import _sql

    monkeypatch.setenv("HODOSCOPE_ROOT", str(tmp_path))
    with run("sql-test", root=tmp_path):
        pass
    _sql("SELECT count(*) AS run_count FROM runs")
    assert "1" in capsys.readouterr().out


def test_diff_refuses_identical_recorded_inputs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HODOSCOPE_ROOT", str(tmp_path))

    def provider():
        return {"fit_config_id": "abc", "fit_windows": {"z": [70, 110]}}

    with (
        run("one", context_providers=[provider], root=tmp_path) as record_a,
        record_a.stage("fit") as stage,
    ):
        stage.rows_out = 4
    with (
        run("two", context_providers=[provider], root=tmp_path) as record_b,
        record_b.stage("fit") as stage,
    ):
        stage.rows_out = 4
    # Normalize runtime-only git/environment fields for this exact-input case.
    for record in (record_a, record_b):
        path = record.run_dir / "run.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["git"] = {"commit": "same", "branch": "main", "dirty": False, "dirty_files": []}
        data["env"] = {"python": "same"}
        path.write_text(json.dumps(data), encoding="utf-8")
    assert _diff(record_a.run_id, record_b.run_id) == 2
    out = capsys.readouterr()
    assert (
        out.out.index("CODE DELTAS")
        < out.out.index("CONTEXT DELTAS")
        < out.out.index("ENVIRONMENT")
    )
    assert "analysis inputs are identical" in out.out
    assert "Refusing timing comparison" in out.err


def test_diff_names_identical_records_before_refusing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HODOSCOPE_ROOT", str(tmp_path))
    with run("same-record", root=tmp_path) as record:
        pass
    clone = record.run_dir.parent / "identical-copy"
    clone.mkdir()
    (clone / "run.json").write_bytes((record.run_dir / "run.json").read_bytes())
    assert _diff(record.run_id, "identical-copy") == 2
    captured = capsys.readouterr()
    assert "records are identical" in captured.out
    assert captured.out.index("CODE DELTAS") < captured.out.index("ENVIRONMENT DELTAS")
    assert "Refusing timing comparison" in captured.err


def test_cli_module_help_and_wrap_capture(tmp_path):
    env = dict(os.environ, HODOSCOPE_ROOT=str(tmp_path / "records"))
    help_result = subprocess.run(
        [sys.executable, "-m", "hodoscope", "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert help_result.returncode == 0
    wrapped = subprocess.run(
        [
            sys.executable,
            "-m",
            "hodoscope",
            "wrap",
            "--name",
            "echo-test",
            "--",
            sys.executable,
            "-c",
            "print('wrap-ok')",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert wrapped.returncode == 0
    assert "wrap-ok" in wrapped.stdout
    record = all_records(tmp_path / "records")[0]
    assert record["state"] == "succeeded"
    assert "wrap-ok" in (tmp_path / "records" / "runs" / record["run_id"] / "log.txt").read_text(
        encoding="utf-8"
    )


def test_colliderlake_preflight_guard_aborts_before_stage_or_summary_write(tmp_path, monkeypatch):
    from src import cli as colliderlake_cli

    data_root = tmp_path / "data"
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(data_root))
    called = []
    monkeypatch.setattr(colliderlake_cli, "_run_stage", lambda *args, **kwargs: called.append(args))
    colliderlake_cli.run_pipeline(
        "run2012bc_doublemuparked", "fit", expect_fit_config="wrong-config", quiet=True
    )
    records = all_records(data_root / "results")
    assert len(records) == 1
    assert records[0]["state"] == "aborted"
    assert "--expect-fit-config" in records[0]["abort_reason"]
    assert records[0]["preflight"]["fit_config_id"] != "wrong-config"
    assert called == []
    assert not (data_root / "results" / "run_summary.txt").exists()


def test_compatibility_pointers_move_after_canonical_run_is_saved(tmp_path, monkeypatch, capsys):
    from src import cli as colliderlake_cli

    data_root = tmp_path / "data"
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(data_root))
    writes = []

    def fake_fit(_item, dataset_id, *_args):
        output = data_root / "results" / "analysis=resonance" / f"dataset={dataset_id}"
        output.mkdir(parents=True, exist_ok=True)
        payload = [{"run_number": len(writes) + 1}]
        fit_path = output / "fits.json"
        fit_path.write_text(json.dumps(payload), encoding="utf-8")
        writes.append(payload)
        return output

    monkeypatch.setattr(colliderlake_cli, "_run_stage", fake_fit)
    colliderlake_cli.run_pipeline("run2012bc_doublemuparked", "fit", quiet=True)
    first_summary = (data_root / "results" / "run_summary.txt").read_text(encoding="utf-8")
    first_id = first_summary.splitlines()[0].split()[1]
    first_canonical = data_root / "results" / "runs" / first_id
    assert (first_canonical / "run_summary.txt").is_file()
    assert json.loads((first_canonical / "fits.json").read_text(encoding="utf-8")) == writes[0]

    colliderlake_cli.run_pipeline("run2012bc_doublemuparked", "fit", quiet=True)
    second_summary = (data_root / "results" / "run_summary.txt").read_text(encoding="utf-8")
    second_id = second_summary.splitlines()[0].split()[1]
    pointer = json.loads(
        (
            data_root
            / "results"
            / "analysis=resonance"
            / "dataset=run2012bc_doublemuparked"
            / "fits.json"
        ).read_text(encoding="utf-8")
    )
    assert second_id != first_id
    assert pointer["_hodoscope"]["run_id"] == second_id
    assert json.loads((first_canonical / "fits.json").read_text(encoding="utf-8")) == writes[0]


def test_backfill_marks_unknown_provenance_and_is_idempotent(tmp_path):
    from scripts.backfill_hodoscope import _register

    source = tmp_path / "historical.txt"
    source.write_text(
        "ColliderLake run summary\n"
        "stage | status | duration | rows_out | rows_per_second\n"
        "fit | SUCCESS | 5.0s | 4 | 0.80\n"
        "fit_config_id: abc12345\n",
        encoding="utf-8",
    )
    registry = tmp_path / "registry"
    first_id = _register(source, registry, "historical:test")
    second_id = _register(source, registry, "historical:test")
    assert first_id == second_id
    record = load_record(first_id, registry)
    assert record["backfilled"] is True
    assert record["evidence"]["original_commit"]["status"] == "unresolved"
    assert record["evidence"]["fit_config_id"]["status"] == "sourced"
    assert record["evidence"]["stages"]["value"][0]["rows_per_s"] == 0.8


def test_strict_dirty_preflight_aborts_and_records_commit_and_files(tmp_path, monkeypatch, capsys):
    from src import cli as colliderlake_cli
    from src.hodoscope import registry

    root = tmp_path / "data"
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(root))
    monkeypatch.setattr(
        registry,
        "_git_context",
        lambda: {"commit": "abc123", "branch": "test", "dirty": True, "dirty_files": ["x.py"]},
    )
    monkeypatch.setattr(
        colliderlake_cli, "_run_stage", lambda *_args, **_kwargs: pytest.fail("stage ran")
    )
    colliderlake_cli.run_pipeline("run2012bc_doublemuparked", "fit", strict=True, quiet=True)
    capsys.readouterr()
    record = all_records(root / "results")[0]
    assert record["state"] == "aborted"
    assert record["preflight"]["commit"] == "abc123"
    assert record["preflight"]["dirty_files"] == ["x.py"]
    assert "--strict" in record["abort_reason"]


def test_git_dirty_paths_preserve_full_relative_path(monkeypatch):
    from src.hodoscope import registry

    def fake_run(command, **_kwargs):
        class Result:
            stdout = "commit\n"

        if command[1:3] == ["branch", "--show-current"]:
            Result.stdout = "main\n"
        elif command[1:3] == ["status", "--porcelain=v1"]:
            Result.stdout = " M configs/fits/resonance_ladder.yaml\n?? tests/test full path.py\n"
        return Result()

    monkeypatch.setattr(registry.subprocess, "run", fake_run)
    context = registry._git_context()
    assert context["dirty_files"] == [
        "configs/fits/resonance_ladder.yaml",
        "tests/test full path.py",
    ]


def test_diff_reports_environment_only_delta_without_refusing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HODOSCOPE_ROOT", str(tmp_path))

    def provider():
        return {"fit_config_id": "same"}

    with run("old-env", context_providers=[provider], root=tmp_path) as old, old.stage("fit"):
        pass
    with run("new-env", context_providers=[provider], root=tmp_path) as new, new.stage("fit"):
        pass
    for record, cpu_count in ((old, 4), (new, 8)):
        path = record.run_dir / "run.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["git"] = {"commit": "same", "branch": "main", "dirty": False, "dirty_files": []}
        payload["env"] = {"cpu_count": cpu_count}
        path.write_text(json.dumps(payload), encoding="utf-8")
    assert _diff(old.run_id, new.run_id) == 0
    captured = capsys.readouterr()
    assert "analysis inputs are identical; records differ" in captured.out
    assert "cpu_count: 4 -> 8" in captured.out
    assert "STAGE TIMINGS" in captured.out
    assert "Refusing timing comparison" not in captured.err


def test_hodoscope_import_boundary_and_module_invocation():
    package = Path("src/hodoscope")
    allowed_external = set(sys.stdlib_module_names) | {"duckdb"}
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # package-local Hodoscope modules only
                if node.module:
                    imported.append(node.module)
            for name in imported:
                assert name.partition(".")[0] in allowed_external, (path, imported)
    for args in (
        [sys.executable, "-m", "hodoscope", "--help"],
        [sys.executable, "-m", "src.hodoscope", "--help"],
    ):
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        assert result.returncode == 0
