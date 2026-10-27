from __future__ import annotations

from src.utils.paths import configured_data_path, data_dir, data_path, ensure_parent


def test_data_path_and_configured_data_path_are_pure(tmp_path, monkeypatch):
    root = tmp_path / "lake"
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(root))

    file_path = data_path("raw", "sample.root")
    relative = configured_data_path("raw/sample.root")
    absolute = configured_data_path(root / "raw" / "sample.root")

    assert file_path == relative == absolute
    assert not file_path.exists()
    assert not root.exists()

    ensure_parent(file_path)
    assert file_path.parent.exists()
    assert not file_path.exists()


def test_data_dir_creates_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLIDERLAKE_DATA_ROOT", str(tmp_path / "lake"))
    directory = data_dir("silver", "dataset=toy")
    assert directory.is_dir()
