import hashlib
import json
import shutil

from src.acquire.local import manifest_entries
from src.silver.build import _write_lumi_manifest
from src.utils.paths import data_path


def test_local_manifest_fills_missing_sha256(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")
    raw = data_path("raw", "run2012bc_doublemuparked")
    raw.mkdir(parents=True)
    source = raw / "sample.root"
    source.write_bytes(b"root fixture bytes")
    manifest = {
        "dataset_id": "run2012bc_doublemuparked",
        "local_path": "raw/run2012bc_doublemuparked",
        "files": [{"name": source.name, "size_bytes": source.stat().st_size, "sha256": None}],
    }
    manifest_file = raw / "MANIFEST.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    entries = manifest_entries("run2012bc_doublemuparked")

    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert entries[0][1]["sha256"] == expected
    assert json.loads(manifest_file.read_text(encoding="utf-8"))["files"][0]["sha256"] == expected


def test_lumi_manifest_records_native_lists_and_synthetic_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "artifacts"))
    shutil.copytree("configs", tmp_path / "configs")

    _write_lumi_manifest(
        "native",
        {"event_identity": "native"},
        {(2, 9), (2, 3)},
        {(2, 3)},
    )
    native = json.loads(data_path("silver", "dataset=native", "lumi_processed.json").read_text())
    assert native["processed_lumis"] == [[2, 3], [2, 9]]
    assert native["processed_lumi_count"] == 2
    assert native["certified_intersection_lumis"] == [[2, 3]]
    assert native["certified_intersection_count"] == 1

    _write_lumi_manifest("synthetic", {"event_identity": "synthetic"}, set(), set())
    synthetic = json.loads(
        data_path("silver", "dataset=synthetic", "lumi_processed.json").read_text()
    )
    assert synthetic["status"] == "not applicable: synthetic identity"
