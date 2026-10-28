from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from src import cli
from src.bronze.convert import _root_to_parquet
from src.utils.config import dataset_config
from src.utils.paths import data_path, ensure_parent
from src.utils.runlog import configure_logging, get_logger


def test_get_logger_is_idempotent_and_does_not_duplicate_records(caplog):
    configure_logging()
    first = get_logger("test")
    second = get_logger("test")
    handlers = [handler for handler in logging.getLogger("colliderlake").handlers if handler.__class__.__name__ == "_FlushingStreamHandler"]
    with caplog.at_level(logging.INFO, logger="colliderlake"):
        first.info("one record")
    assert second.extra["stage"] == "TEST"
    assert len(handlers) == 1
    assert [record.message for record in caplog.records].count("one record") == 1


def test_logging_level_precedence(monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_LOG", "DEBUG")
    configure_logging(quiet=False, verbose=False)
    assert logging.getLogger("colliderlake").level == logging.DEBUG
    configure_logging(quiet=False, verbose=True)
    assert logging.getLogger("colliderlake").level == logging.DEBUG
    configure_logging(quiet=True, verbose=True)
    assert logging.getLogger("colliderlake").level == logging.WARNING


def test_bronze_emits_heartbeat_for_each_batch(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    import uproot

    arrays = [_batch_arrays(2), _batch_arrays(2)]

    class Tree:
        num_entries = 4

        def keys(self):
            return list(arrays[0])

        def iterate(self, *_args, **_kwargs):
            yield from arrays

    class RootFile:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __getitem__(self, key):
            assert key == "Events"
            return Tree()

    monkeypatch.setattr(uproot, "open", lambda _path: RootFile())
    configure_logging(quiet=False, verbose=False)
    with caplog.at_level(logging.INFO, logger="colliderlake"):
        _root_to_parquet(
            tmp_path / "sample.root",
            {"sha256": "abc"},
            dataset_config("run2012bc_doublemuparked"),
            max_batches=2,
        )
    heartbeats = [record.message for record in caplog.records if record.message.startswith("batch ")]
    assert len(heartbeats) == 2
    assert all("ETA ~" in message and "elapsed" in message for message in heartbeats)


def test_dq_failure_logs_partial_and_reraises_original(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(cli, "acquire_dataset", lambda _dataset: tmp_path / "manifest.json")
    monkeypatch.setattr(cli, "build_bronze", lambda *_args, **_kwargs: tmp_path)

    def fail_dq(*_args, **_kwargs):
        raise KeyError("sentinel-dq-failure")

    monkeypatch.setattr(cli, "run_dq", fail_dq)
    configure_logging(quiet=False, verbose=False)
    with caplog.at_level(logging.INFO, logger="colliderlake"), pytest.raises(KeyError, match="sentinel-dq-failure"):
        cli.run_pipeline("run2012bc_doublemuparked", "all")
    messages = [record.message for record in caplog.records]
    assert any("DQ" in message and "halting" not in message for message in messages) is False
    assert any("stage bronze FAILED" in message for message in messages)
    assert not any("STAGE silver START" in message for message in messages)
    summary = (tmp_path / "artifacts" / "results" / "run_summary.txt").read_text(encoding="utf-8")
    assert "bronze   | FAILED" in summary
    assert "silver" not in summary


def test_summary_file_matches_terminal_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(cli, "_run_stage", lambda *_args: None)
    configure_logging(quiet=True, verbose=False)
    cli.run_pipeline("run2012bc_doublemuparked", "fit", quiet=True)
    terminal = capsys.readouterr().out
    written = (tmp_path / "artifacts" / "results" / "run_summary.txt").read_text(encoding="utf-8")
    assert written == terminal
    assert "fit_config_id:" in written


def test_full_run_archives_timestamped_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(cli, "_run_stage", lambda *_args: None)
    cli.run_pipeline("run2012bc_doublemuparked", "all", quiet=True)
    capsys.readouterr()
    archived = list((tmp_path / "artifacts" / "results" / "benchmarks").glob("run_summary_*.txt"))
    assert len(archived) == 1
    assert archived[0].read_text(encoding="utf-8").startswith("ColliderLake run summary\n")


def test_logging_does_not_add_parquet_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    import shutil

    shutil.copytree("configs", tmp_path / "configs")
    events = ensure_parent(data_path("bronze", "dataset=run2012bc_doublemuparked", "events", "part.parquet"))
    muons = ensure_parent(data_path("bronze", "dataset=run2012bc_doublemuparked", "muons", "part.parquet"))
    pd.DataFrame({"dataset_id": ["run2012bc_doublemuparked"], "run": [1], "luminosityBlock": [1], "event": [1]}).to_parquet(events, index=False)
    pd.DataFrame({"dataset_id": ["run2012bc_doublemuparked"], "run": [1], "luminosityBlock": [1], "event": [1], "muon_idx": [0], "pt": [4.0], "eta": [0.0], "phi": [0.0], "mass": [0.1056583755], "charge": [1]}).to_parquet(muons, index=False)
    original = pd.read_parquet
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", counted)
    configure_logging(quiet=True, verbose=False)
    from src.silver.build import build_silver

    build_silver("run2012bc_doublemuparked")
    quiet_calls = len(calls)
    calls.clear()
    configure_logging(quiet=False, verbose=True)
    build_silver("run2012bc_doublemuparked")
    assert len(calls) == quiet_calls


def _batch_arrays(size: int) -> dict[str, np.ndarray]:
    return {
        "nMuon": np.asarray([2] * size),
        "Muon_pt": np.asarray([[4.0, 4.0]] * size, dtype=object),
        "Muon_eta": np.asarray([[0.0, 0.0]] * size, dtype=object),
        "Muon_phi": np.asarray([[0.0, 1.0]] * size, dtype=object),
        "Muon_mass": np.asarray([[0.1056583755, 0.1056583755]] * size, dtype=object),
        "Muon_charge": np.asarray([[1, -1]] * size, dtype=object),
    }
