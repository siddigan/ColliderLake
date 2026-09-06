from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Iterator

import awkward as ak
import uproot

from src.ingestion.samples import DEFAULT_TREE_NAME
from src.utils.paths import resolve_input

LOGGER = logging.getLogger(__name__)


def open_root_file(source: str):
    """Open a local or remote ROOT file without reading event data eagerly."""
    resolved = resolve_input(source)
    LOGGER.info("Opening ROOT file: %s", resolved)
    try:
        if resolved.startswith("https://") and os.environ.get("CERN_ALLOW_INSECURE_SSL") == "1":
            LOGGER.warning("Opening HTTPS ROOT file with SSL verification disabled")
            return uproot.open(resolved, ssl=False)
        return uproot.open(resolved)
    except Exception as exc:
        raise RuntimeError(f"Could not open ROOT file {resolved!r}") from exc


def get_tree(source: str, tree_name: str = DEFAULT_TREE_NAME):
    root_file = open_root_file(source)
    try:
        return root_file[tree_name]
    except KeyError as exc:
        available = ", ".join(root_file.keys())
        raise KeyError(f"Tree {tree_name!r} not found. Available top-level keys: {available}") from exc


def top_level_keys(source: str) -> dict[str, str]:
    root_file = open_root_file(source)
    return root_file.classnames()


def list_branches(source: str, tree_name: str = DEFAULT_TREE_NAME) -> list[str]:
    tree = get_tree(source, tree_name)
    return list(tree.keys())


def iter_event_batches(
    source: str,
    branches: Iterable[str],
    tree_name: str = DEFAULT_TREE_NAME,
    step_size: int | str = 10_000,
    max_batches: int | None = None,
) -> Iterator[ak.Array]:
    """Yield selected branches in chunks to keep memory bounded."""
    tree = get_tree(source, tree_name)
    branch_list = list(branches)
    if isinstance(step_size, str) and step_size.isdigit():
        step_size = int(step_size)
    missing = sorted(set(branch_list) - set(tree.keys()))
    if missing:
        raise KeyError(f"Missing branches in {tree_name!r}: {missing}")

    for batch_index, arrays in enumerate(
        tree.iterate(branch_list, step_size=step_size, library="ak")
    ):
        if max_batches is not None and batch_index >= max_batches:
            break
        LOGGER.info("Read batch %s with %s events", batch_index, len(arrays))
        yield arrays


def read_small_batch(
    source: str,
    branches: Iterable[str],
    tree_name: str = DEFAULT_TREE_NAME,
    entry_stop: int = 1_000,
) -> ak.Array:
    tree = get_tree(source, tree_name)
    branch_list = list(branches)
    return tree.arrays(branch_list, entry_stop=entry_stop, library="ak")
