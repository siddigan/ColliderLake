from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the workspace root, overridable with CERN_WORKSPACE_ROOT."""
    configured = os.environ.get("CERN_WORKSPACE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def data_dir(kind: str) -> Path:
    allowed = {"adoc", "raw", "processed", "parquet", "muon_db"}
    if kind not in allowed:
        raise ValueError(f"Unknown data directory {kind!r}; expected one of {sorted(allowed)}")
    path = project_root() / "data" / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def outputs_dir() -> Path:
    path = project_root() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_input(source: str | Path) -> str:
    """Resolve local paths while leaving remote URLs untouched."""
    text = str(source)
    if "://" in text:
        return text
    return str(Path(text).expanduser().resolve())
