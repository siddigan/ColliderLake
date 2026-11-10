from __future__ import annotations

import json
import os
import time

from src.acquire.local import acquire_dataset


def test_repeated_acquire_preserves_identical_manifest(tmp_path, monkeypatch):
    raw = tmp_path / "raw" / "sample"
    raw.mkdir(parents=True)
    (raw / "sample.root").write_bytes(b"small fixture")
    config = {
        "local_path": "raw/sample",
        "portal_record": "record-1",
        "doi": "10.0000/example",
    }
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("src.acquire.local.dataset_config", lambda _dataset: config)

    manifest = acquire_dataset("sample")
    before = manifest.read_bytes()
    original_mtime = manifest.stat().st_mtime_ns
    time.sleep(0.01)
    acquire_dataset("sample")

    assert manifest.read_bytes() == before
    assert manifest.stat().st_mtime_ns == original_mtime
    data = json.loads(before)
    assert data["files"][0]["sha256"]
    assert not os.path.exists(tmp_path / ".git")
