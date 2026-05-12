from __future__ import annotations

import sys
from pathlib import Path


def add_workspace_to_path() -> None:
    workspace = Path(__file__).resolve().parents[1]
    if str(workspace) not in sys.path:
        sys.path.insert(0, str(workspace))
