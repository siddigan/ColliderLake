from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    configured = os.environ.get("COLLIDERLAKE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    configured = os.environ.get("COLLIDERLAKE_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / "data"


def config_path(*parts: str) -> Path:
    return project_root() / "configs" / Path(*parts)


def data_path(*parts: str) -> Path:
    path = data_root() / Path(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def configured_data_path(value: str | Path, *parts: str) -> Path:
    relative = Path(value)
    if not relative.is_absolute():
        path_parts = relative.parts
        if path_parts and path_parts[0].lower() == "data":
            path_parts = path_parts[1:]
        return data_path(*path_parts, *parts)
    return relative.joinpath(*parts)


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
