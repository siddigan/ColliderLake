from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.utils.config import dataset_config
from src.utils.paths import configured_data_path, data_root, ensure_parent

DATA_EXTENSIONS = {".root", ".parquet", ".csv"}


def acquire_dataset(dataset_id: str) -> Path:
    config = dataset_config(dataset_id)
    raw_dir = configured_data_path(config.get("local_path", f"raw/{dataset_id}"))
    raw_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in raw_dir.iterdir() if path.suffix.lower() in DATA_EXTENSIONS)
    if not files:
        raise FileNotFoundError(
            f"No local data files found for {dataset_id}. Place ROOT files in {raw_dir}."
        )

    manifest = {
        "dataset_id": dataset_id,
        "portal_record": config.get("portal_record"),
        "doi": config.get("doi"),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "local_path": raw_dir.relative_to(data_root()).as_posix(),
        "files": [_file_entry(path) for path in files],
    }
    output = ensure_parent(raw_dir / "MANIFEST.json")
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return output


def manifest_path(dataset_id: str) -> Path:
    config = dataset_config(dataset_id)
    return configured_data_path(config.get("local_path", f"raw/{dataset_id}")) / "MANIFEST.json"


def manifest_files(dataset_id: str) -> list[Path]:
    return [path for path, _ in manifest_entries(dataset_id)]


def manifest_entries(dataset_id: str) -> list[tuple[Path, dict[str, Any]]]:
    path = manifest_path(dataset_id)
    if not path.exists():
        path = acquire_dataset(dataset_id)
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    raw_dir = configured_data_path(data["local_path"])
    return [(raw_dir / item["name"], item) for item in data["files"]]


def _file_entry(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
