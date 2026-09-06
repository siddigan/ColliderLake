from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    configured = os.environ.get("COLLIDERLAKE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def config_path(*parts: str) -> Path:
    return project_root() / "configs" / Path(*parts)


def data_path(*parts: str) -> Path:
    path = project_root() / "data" / Path(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
