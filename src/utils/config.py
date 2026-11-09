from __future__ import annotations

import hashlib
import json
from functools import lru_cache
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
        raise KeyError(
            f"Unknown dataset {dataset_id!r}; expected one of {sorted(datasets)}"
        ) from exc
    config["dataset_id"] = dataset_id
    return config


def selection_files() -> list[Path]:
    return sorted(config_path("selections").glob("*.yaml"))


_SELECTION_KEYS = {
    "selection_name",
    "dataset",
    "analysis",
    "muon",
    "pair",
    "trigger",
    "max_muons_per_event",
    "mass_window",
}
_SELECTION_NESTED_KEYS = {
    "muon": {"pt_min", "abs_eta_max", "iso_max", "quality"},
    "pair": {"opposite_charge"},
    "trigger": {"paths"},
}


def selection_for_dataset(
    dataset_id: str, analysis: str | None = None
) -> tuple[Path, dict[str, Any], str]:
    matches: list[tuple[Path, dict[str, Any], str]] = []
    for path in selection_files():
        config = load_yaml(path)
        validate_selection(config, path)
        if config.get("dataset") == dataset_id and (
            analysis is None or config["analysis"] == analysis
        ):
            matches.append((path, config, selection_id(config, path)))
    if not matches:
        suffix = f" and analysis {analysis!r}" if analysis is not None else ""
        raise KeyError(f"No selection config found for dataset {dataset_id!r}{suffix}")
    if len(matches) > 1:
        candidates = ", ".join(f"{config['analysis']} ({path.name})" for path, config, _ in matches)
        raise ValueError(
            f"Ambiguous selections for dataset {dataset_id!r}; pass analysis to choose one: {candidates}"
        )
    return matches[0]


def validate_selection(selection: dict[str, Any], source_path: str | Path = "<selection>") -> None:
    source = str(source_path)
    unknown = sorted(set(selection) - _SELECTION_KEYS)
    if unknown:
        raise ValueError(f"Unknown selection key {unknown[0]!r} in {source}")
    required = _SELECTION_KEYS - {"max_muons_per_event"}
    missing = sorted(required - set(selection))
    if missing:
        raise ValueError(f"Missing selection key {missing[0]!r} in {source}")
    for parent, allowed in _SELECTION_NESTED_KEYS.items():
        value = selection[parent]
        if not isinstance(value, dict):
            raise TypeError(f"Selection key {parent!r} must be a mapping in {source}")
        unknown_nested = sorted(set(value) - allowed)
        if unknown_nested:
            raise ValueError(
                f"Unknown selection key {unknown_nested[0]!r} under {parent!r} in {source}"
            )
    for parent in _SELECTION_NESTED_KEYS:
        required_nested = {
            "muon": {"pt_min", "abs_eta_max"},
            "pair": {"opposite_charge"},
            "trigger": {"paths"},
        }[parent]
        missing_nested = sorted(required_nested - set(selection[parent]))
        if missing_nested:
            raise ValueError(
                f"Missing selection key {missing_nested[0]!r} under {parent!r} in {source}"
            )
    window = selection["mass_window"]
    if not isinstance(window, (list, tuple)) or len(window) != 2:
        raise ValueError(f"Selection key 'mass_window' must have two entries in {source}")
    if "max_muons_per_event" in selection and (
        isinstance(selection["max_muons_per_event"], bool)
        or not isinstance(selection["max_muons_per_event"], int)
        or selection["max_muons_per_event"] < 1
    ):
        raise ValueError(
            f"Selection key 'max_muons_per_event' must be a positive integer in {source}"
        )


def selection_id(selection: dict[str, Any], source_path: str | Path = "<selection>") -> str:
    validate_selection(selection, source_path)
    payload = json.dumps(selection, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def fit_config_id(fit_config: dict[str, Any]) -> str:
    """Return the stable short hash for a resolved fit configuration."""
    payload = json.dumps(fit_config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


@lru_cache(maxsize=8)
def _io_config(path: str) -> dict[str, Any]:
    return load_yaml(path)


def parquet_write_options(layer: str) -> dict[str, Any]:
    """Return configured PyArrow/Pandas compression options for a layer."""
    io_config = _io_config(str(config_path("io.yaml")))
    try:
        setting = io_config["parquet"][layer]
    except KeyError as exc:
        raise KeyError(f"No Parquet codec configured for layer {layer!r}") from exc
    options: dict[str, Any] = {"compression": str(setting["codec"])}
    if "compression_level" in setting:
        options["compression_level"] = int(setting["compression_level"])
    return options


def gold_engine(override: str | None = None) -> str:
    configured = load_yaml(config_path("gold.yaml")).get("engine", "vectorized")
    engine = override or configured
    if engine not in {"vectorized", "duckdb"}:
        raise ValueError("gold engine must be 'vectorized' or 'duckdb'")
    return str(engine)


def bronze_contract(dataset: dict[str, Any]) -> dict[str, Any]:
    contract = load_yaml(config_path("contracts", "bronze.yaml"))
    profile_name = str(dataset.get("bronze_profile", "reduced"))
    profiles = contract.get("profiles", {})
    if profile_name not in profiles:
        raise ValueError(f"unknown bronze contract profile {profile_name!r}")
    profile = dict(profiles[profile_name])
    profile["name"] = profile_name
    profile["muon_branch_columns"] = dict(contract.get("muon_branch_columns", {}))
    return profile
