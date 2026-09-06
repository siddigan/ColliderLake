from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.acquire.local import manifest_entries
from src.utils.config import dataset_config
from src.utils.paths import data_path, ensure_parent

EVENT_KEYS = ["dataset_id", "run", "luminosityBlock", "event"]
NATIVE_KEYS = ["run", "luminosityBlock", "event"]
MUON_BRANCHES = {
    "Muon_pt": "pt",
    "Muon_eta": "eta",
    "Muon_phi": "phi",
    "Muon_mass": "mass",
    "Muon_charge": "charge",
    "Muon_tightId": "tight_id",
    "Muon_mediumId": "medium_id",
    "Muon_pfRelIso04_all": "iso",
}


def build_bronze(dataset_id: str, max_batches: int | None = None) -> Path:
    config = dataset_config(dataset_id)
    written = 0
    for source, manifest in manifest_entries(dataset_id):
        if source.suffix.lower() == ".root":
            written += _root_to_parquet(source, manifest, config, max_batches)
        elif source.suffix.lower() == ".parquet":
            written += _tabular_to_parquet(pd.read_parquet(source), source, manifest, config)
        elif source.suffix.lower() == ".csv":
            written += _tabular_to_parquet(pd.read_csv(source), source, manifest, config)
    if written == 0:
        raise RuntimeError(f"No bronze files written for {dataset_id}")
    return data_path("bronze", f"dataset={dataset_id}")


def _root_to_parquet(
    source: Path,
    manifest: dict[str, Any],
    config: dict[str, Any],
    max_batches: int | None,
) -> int:
    try:
        import uproot
    except ImportError as exc:
        raise RuntimeError("ROOT conversion requires uproot") from exc

    requested = list(config.get("branches", []))
    identity_mode = config.get("event_identity", "native")
    written = 0
    event_offset = 0
    with uproot.open(source) as root_file:
        tree = root_file["Events"]
        available = set(tree.keys())
        branches = [branch for branch in requested if branch in available]
        if identity_mode == "native":
            missing_keys = [branch for branch in NATIVE_KEYS if branch not in branches]
            if missing_keys:
                raise KeyError(f"{source} is missing required event branches: {missing_keys}")
        for batch_index, arrays in enumerate(tree.iterate(branches, library="np", step_size="25 MB")):
            if max_batches is not None and batch_index >= max_batches:
                break
            batch_size = _batch_size(arrays)
            base = _base_columns(
                dataset_id=config["dataset_id"],
                source=source,
                manifest=manifest,
                batch_size=batch_size,
                identity_mode=identity_mode,
                arrays=arrays,
                event_offset=event_offset,
            )
            part = f"{source.stem}_part_{batch_index:04d}.parquet"
            _write_events(base, arrays, config["dataset_id"], part)
            _write_muons(base, arrays, config["dataset_id"], part)
            event_offset += batch_size
            written += 1
    return written


def _tabular_to_parquet(
    frame: pd.DataFrame,
    source: Path,
    manifest: dict[str, Any],
    config: dict[str, Any],
) -> int:
    identity_mode = config.get("event_identity", "native")
    arrays = {column: frame[column].to_numpy() for column in frame.columns}
    base = _base_columns(
        dataset_id=config["dataset_id"],
        source=source,
        manifest=manifest,
        batch_size=len(frame),
        identity_mode=identity_mode,
        arrays=arrays,
        event_offset=0,
    )
    part = f"{source.stem}_part_0000.parquet"
    _write_events(base, arrays, config["dataset_id"], part)
    _write_muons(base, arrays, config["dataset_id"], part)
    return 1


def _base_columns(
    dataset_id: str,
    source: Path,
    manifest: dict[str, Any],
    batch_size: int,
    identity_mode: str,
    arrays: dict[str, Any],
    event_offset: int,
) -> pd.DataFrame:
    if identity_mode == "synthetic":
        event_index = range(event_offset, event_offset + batch_size)
        run = [1] * batch_size
        lumi = [1] * batch_size
        event = list(event_index)
    else:
        run = arrays["run"]
        lumi = arrays["luminosityBlock"]
        event = arrays["event"]
    return pd.DataFrame(
        {
            "dataset_id": dataset_id,
            "run": run,
            "luminosityBlock": lumi,
            "event": event,
            "identity_mode": identity_mode,
            "_source_file": source.name,
            "_source_sha256": manifest["sha256"],
            "_ingest_ts": datetime.now(UTC).isoformat(),
        }
    )


def _write_events(
    base: pd.DataFrame,
    arrays: dict[str, Any],
    dataset_id: str,
    part: str,
) -> None:
    events = base.copy()
    for name, values in arrays.items():
        if name in MUON_BRANCHES or name in NATIVE_KEYS or name == "nMuon":
            continue
        if _is_scalar_array(values):
            events[name] = values
    path = data_path("bronze", f"dataset={dataset_id}", "events") / part
    events.to_parquet(ensure_parent(path), index=False)


def _write_muons(
    base: pd.DataFrame,
    arrays: dict[str, Any],
    dataset_id: str,
    part: str,
) -> None:
    rows: list[dict[str, Any]] = []
    pts = _jagged(arrays.get("Muon_pt"), len(base))
    for event_idx, event_pts in enumerate(pts):
        for muon_idx, _ in enumerate(event_pts):
            row = {column: base.iloc[event_idx][column] for column in EVENT_KEYS}
            row.update(
                {
                    "muon_idx": muon_idx,
                    "identity_mode": base.iloc[event_idx]["identity_mode"],
                    "_source_file": base.iloc[event_idx]["_source_file"],
                    "_source_sha256": base.iloc[event_idx]["_source_sha256"],
                    "_ingest_ts": base.iloc[event_idx]["_ingest_ts"],
                }
            )
            for branch, column in MUON_BRANCHES.items():
                values = _jagged(arrays.get(branch), len(base))
                row[column] = values[event_idx][muon_idx] if muon_idx < len(values[event_idx]) else None
            rows.append(row)
    muons = pd.DataFrame(rows)
    path = data_path("bronze", f"dataset={dataset_id}", "muons") / part
    muons.to_parquet(ensure_parent(path), index=False)


def _batch_size(arrays: dict[str, Any]) -> int:
    if not arrays:
        return 0
    return len(next(iter(arrays.values())))


def _is_scalar_array(values: Any) -> bool:
    return not any(isinstance(item, (list, tuple)) for item in values[: min(len(values), 5)])


def _jagged(values: Any, batch_size: int) -> list[list[Any]]:
    if values is None:
        return [[] for _ in range(batch_size)]
    output: list[list[Any]] = []
    for item in values:
        if hasattr(item, "tolist"):
            item = item.tolist()
        if isinstance(item, tuple):
            item = list(item)
        if isinstance(item, list):
            output.append(item)
        else:
            output.append([item])
    return output
