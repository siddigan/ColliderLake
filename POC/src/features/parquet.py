from __future__ import annotations

import logging
from pathlib import Path

import awkward as ak

from src.ingestion.root_io import iter_event_batches

LOGGER = logging.getLogger(__name__)


def convert_root_to_parquet(
    source: str,
    branches: list[str],
    output_dir: str | Path,
    step_size: int | str = 10_000,
    max_batches: int | None = None,
) -> list[Path]:
    """Write selected NanoAOD branches as chunked Parquet parts."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for index, arrays in enumerate(
        iter_event_batches(source, branches, step_size=step_size, max_batches=max_batches)
    ):
        output_path = destination / f"events_part_{index:04d}.parquet"
        ak.to_parquet(arrays, output_path)
        LOGGER.info("Wrote %s", output_path)
        written.append(output_path)
    return written
