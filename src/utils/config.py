from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from src.utils.paths import config_path, project_root


def load_yaml(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = project_root() / resolved
    with resolved.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected mapping in {resolved}")
    return data


def load_datasets(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    data = load_yaml(path or config_path("datasets.yaml"))
    datasets = data.get("datasets", {})
    if not isinstance(datasets, dict):
        raise TypeError("configs/datasets.yaml must contain a datasets mapping")
    return datasets


def dataset_config(dataset_id: str) -> dict[str, Any]:
    datasets = load_datasets()
    try:
        config = dict(datasets[dataset_id])
    except KeyError as exc:
        raise KeyError(f"Unknown dataset {dataset_id!r}; expected one of {sorted(datasets)}") from exc
    config["dataset_id"] = dataset_id
    return config


def selection_files() -> list[Path]:
    return sorted(config_path("selections").glob("*.yaml"))


def selection_for_dataset(dataset_id: str) -> tuple[Path, dict[str, Any], str]:
    matches: list[tuple[Path, dict[str, Any], str]] = []
    for path in selection_files():
        config = load_yaml(path)
        if config.get("dataset") == dataset_id:
            matches.append((path, config, selection_id(config)))
    if not matches:
        raise KeyError(f"No selection config found for dataset {dataset_id!r}")
    return matches[0]


def selection_id(selection: dict[str, Any]) -> str:
    payload = json.dumps(selection, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
