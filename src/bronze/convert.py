from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.acquire.local import manifest_files
from src.utils.config import dataset_config
from src.utils.paths import data_path


def build_bronze(dataset_id: str, max_batches: int | None = None) -> Path:
    config = dataset_config(dataset_id)
    output_dir = data_path("bronze", f"dataset={dataset_id}", "events")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = manifest_files(dataset_id)
    written: list[Path] = []
    for source in files:
        if source.suffix.lower() == ".root":
            written.extend(_root_to_parquet(source, output_dir, config, max_batches))
        elif source.suffix.lower() == ".parquet":
            frame = pd.read_parquet(source)
            written.append(_write_frame(frame, output_dir, dataset_id, source, len(written)))
        elif source.suffix.lower() == ".csv":
            frame = pd.read_csv(source)
            written.append(_write_frame(frame, output_dir, dataset_id, source, len(written)))
    if not written:
        raise RuntimeError(f"No bronze files written for {dataset_id}")
    return output_dir


def _root_to_parquet(
    source: Path,
    output_dir: Path,
    config: dict,
    max_batches: int | None,
) -> list[Path]:
    try:
        import awkward as ak
        import uproot
    except ImportError as exc:
        raise RuntimeError("ROOT conversion requires uproot and awkward") from exc

    requested = list(config.get("branches", []))
    written: list[Path] = []
    with uproot.open(source) as root_file:
        tree = root_file["Events"]
        available = set(tree.keys())
        branches = [branch for branch in requested if branch in available]
        missing_keys = [branch for branch in ("run", "luminosityBlock", "event") if branch not in branches]
        if missing_keys:
            raise KeyError(f"{source} is missing required event branches: {missing_keys}")
        for index, arrays in enumerate(tree.iterate(branches, library="ak", step_size="25 MB")):
            if max_batches is not None and index >= max_batches:
                break
            arrays = ak.with_field(arrays, dataset_id, "dataset_id")
            arrays = ak.with_field(arrays, source.name, "_source_file")
            arrays = ak.with_field(arrays, datetime.now(timezone.utc).isoformat(), "_ingest_ts")
            output = output_dir / f"{source.stem}_part_{index:04d}.parquet"
            ak.to_parquet(arrays, output)
            written.append(output)
    return written


def _write_frame(frame: pd.DataFrame, output_dir: Path, dataset_id: str, source: Path, index: int) -> Path:
    data = frame.copy()
    data["dataset_id"] = dataset_id
    data["_source_file"] = source.name
    data["_ingest_ts"] = datetime.now(timezone.utc).isoformat()
    output = output_dir / f"{source.stem}_part_{index:04d}.parquet"
    data.to_parquet(output, index=False)
    return output
