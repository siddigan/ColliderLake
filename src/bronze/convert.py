from __future__ import annotations

import json
import logging
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.acquire.local import manifest_entries
from src.utils.config import bronze_contract, dataset_config, load_yaml, parquet_write_options
from src.utils.paths import data_dir, data_path, ensure_parent
from src.utils.runlog import add_stage_stats, format_duration, get_logger, safe_log

EVENT_KEYS = ["dataset_id", "run", "luminosityBlock", "event"]
NATIVE_KEYS = ["run", "luminosityBlock", "event"]


def build_bronze(dataset_id: str, max_batches: int | None = None) -> Path:
    config = dataset_config(dataset_id)
    contract = bronze_contract(config)
    branch_audit: dict[str, Any] = {
        "profile": contract["name"],
        "sources": [],
    }
    written = 0
    for source, manifest in manifest_entries(dataset_id):
        if source.suffix.lower() == ".root":
            written += _root_to_parquet(
                source, manifest, config, max_batches, contract=contract, audit=branch_audit
            )
        elif source.suffix.lower() == ".parquet":
            written += _tabular_to_parquet(
                pd.read_parquet(source), source, manifest, config, contract["muon_branch_columns"]
            )
        elif source.suffix.lower() == ".csv":
            written += _tabular_to_parquet(
                pd.read_csv(source), source, manifest, config, contract["muon_branch_columns"]
            )
    if written == 0:
        raise RuntimeError(f"No bronze files written for {dataset_id}")
    missing_optional = sorted(
        {
            branch
            for item in branch_audit["sources"]
            for branch in item["missing_configured_branches"]
        }
    )
    missing_required = sorted(
        {branch for item in branch_audit["sources"] for branch in item["missing_required_branches"]}
    )
    branch_audit["missing_configured_branches"] = missing_optional
    branch_audit["missing_required_branches"] = missing_required
    output = data_dir("bronze", f"dataset={dataset_id}") / "branch_audit.json"
    ensure_parent(output).write_text(
        json.dumps(branch_audit, indent=2, sort_keys=True), encoding="utf-8"
    )
    return data_dir("bronze", f"dataset={dataset_id}")


def _root_to_parquet(
    source: Path,
    manifest: dict[str, Any],
    config: dict[str, Any],
    max_batches: int | None,
    *,
    contract: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
) -> int:
    try:
        import uproot
    except ImportError as exc:
        raise RuntimeError("ROOT conversion requires uproot") from exc

    contract = contract or bronze_contract(config)
    muon_branch_columns = contract["muon_branch_columns"]
    configured = list(config.get("branches", []))
    candidates = list(contract.get("candidate_branches", []))
    required = set(contract.get("required_branches", []))
    requested = list(dict.fromkeys(configured + sorted(required) + candidates))
    identity_mode = config.get("event_identity", "native")
    written = 0
    event_offset = 0
    estimated_batch_size = 0
    logger = get_logger("bronze")
    started = time.monotonic()
    with uproot.open(source) as root_file:
        tree = root_file["Events"]
        total_entries = int(tree.num_entries)
        available = set(tree.keys())
        missing = [branch for branch in requested if branch not in available]
        missing_required = sorted(required.intersection(missing))
        missing_optional = sorted(set(missing) - required)
        if missing_optional:
            safe_log(
                logger,
                logging.WARNING,
                "configured ROOT branches absent; skipping optional branches | source=%s | branches=%s",
                source.name,
                ", ".join(missing_optional),
            )
        if missing_required:
            safe_log(
                logger,
                logging.ERROR,
                "contract-required ROOT branches absent | source=%s | branches=%s",
                source.name,
                ", ".join(missing_required),
            )
        if audit is not None:
            audit["sources"].append(
                {
                    "source": source.name,
                    "configured_branches": requested,
                    "present_branches": [branch for branch in requested if branch in available],
                    "missing_configured_branches": missing_optional,
                    "missing_required_branches": missing_required,
                }
            )
        branches = [branch for branch in requested if branch in available]
        if identity_mode == "native":
            missing_keys = [branch for branch in NATIVE_KEYS if branch not in branches]
            if missing_keys:
                raise KeyError(f"{source} is missing required event branches: {missing_keys}")
        for batch_index, arrays in enumerate(
            tree.iterate(branches, library="np", step_size="25 MB")
        ):
            if max_batches is not None and batch_index >= max_batches:
                break
            batch_size = _batch_size(arrays)
            if estimated_batch_size == 0:
                estimated_batch_size = batch_size
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
            event_rows = _write_events(
                base, arrays, config["dataset_id"], part, set(muon_branch_columns)
            )
            muon_rows = _write_muons(base, arrays, config["dataset_id"], part, muon_branch_columns)
            event_offset += batch_size
            written += 1
            add_stage_stats(
                "bronze",
                batches=1,
                rows_out=event_rows + muon_rows,
                events=event_rows,
                muons=muon_rows,
            )
            elapsed = time.monotonic() - started
            throughput = event_offset / elapsed if elapsed > 0.0 else 0.0
            eta = (total_entries - event_offset) / throughput if throughput > 0.0 else 0.0
            total_batches = math.ceil(total_entries / max(estimated_batch_size, 1))
            safe_log(
                logger,
                logging.INFO,
                "batch %d/~%d | events %s/%s (%.1f%%) | %.0f ev/s | elapsed %s | ETA ~%s",
                batch_index + 1,
                total_batches,
                f"{event_offset:,}",
                f"{total_entries:,}",
                100.0 * event_offset / total_entries if total_entries else 0.0,
                throughput,
                format_duration(elapsed),
                format_duration(eta),
            )
    return written


def _tabular_to_parquet(
    frame: pd.DataFrame,
    source: Path,
    manifest: dict[str, Any],
    config: dict[str, Any],
    muon_branch_columns: dict[str, str] | None = None,
) -> int:
    logger = get_logger("bronze")
    started = time.monotonic()
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
    branch_columns = muon_branch_columns or _all_muon_branch_columns()
    event_rows = _write_events(base, arrays, config["dataset_id"], part, set(branch_columns))
    muon_rows = _write_muons(base, arrays, config["dataset_id"], part, branch_columns)
    add_stage_stats(
        "bronze",
        batches=1,
        rows_out=event_rows + muon_rows,
        events=event_rows,
        muons=muon_rows,
    )
    elapsed = time.monotonic() - started
    throughput = event_rows / elapsed if elapsed > 0.0 else 0.0
    safe_log(
        logger,
        logging.INFO,
        "batch 1/~1 | events %s/%s (100.0%%) | %.0f ev/s | elapsed %s | ETA ~0.0s",
        f"{event_rows:,}",
        f"{event_rows:,}",
        throughput,
        format_duration(elapsed),
    )
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
    muon_branches: set[str] | None = None,
) -> int:
    events = base.copy()
    muon_branches = muon_branches or _all_muon_branch_columns().keys()
    for name, values in arrays.items():
        if name in muon_branches or name in NATIVE_KEYS or name == "nMuon":
            continue
        if _is_scalar_array(values):
            events[name] = values
    path = data_path("bronze", f"dataset={dataset_id}", "events") / part
    events.to_parquet(ensure_parent(path), index=False, **parquet_write_options("bronze"))
    return len(events)


def _write_muons(
    base: pd.DataFrame,
    arrays: dict[str, Any],
    dataset_id: str,
    part: str,
    muon_branch_columns: dict[str, str] | None = None,
) -> int:
    muon_branch_columns = muon_branch_columns or _all_muon_branch_columns()
    rows: list[dict[str, Any]] = []
    batch_size = len(base)
    jagged = {branch: _jagged(arrays.get(branch), batch_size) for branch in muon_branch_columns}
    pts = jagged["Muon_pt"]
    base_columns = {
        column: base[column].to_numpy(copy=False)
        for column in [
            *EVENT_KEYS,
            "identity_mode",
            "_source_file",
            "_source_sha256",
            "_ingest_ts",
        ]
    }
    for event_idx, event_pts in enumerate(pts):
        for muon_idx, _ in enumerate(event_pts):
            row = {column: base_columns[column][event_idx] for column in EVENT_KEYS}
            row.update(
                {
                    "muon_idx": muon_idx,
                    "identity_mode": base_columns["identity_mode"][event_idx],
                    "_source_file": base_columns["_source_file"][event_idx],
                    "_source_sha256": base_columns["_source_sha256"][event_idx],
                    "_ingest_ts": base_columns["_ingest_ts"][event_idx],
                }
            )
            for branch, column in muon_branch_columns.items():
                if branch not in arrays:
                    continue
                values = jagged[branch]
                row[column] = (
                    values[event_idx][muon_idx] if muon_idx < len(values[event_idx]) else None
                )
            rows.append(row)
    muons = pd.DataFrame(rows)
    path = data_path("bronze", f"dataset={dataset_id}", "muons") / part
    muons.to_parquet(ensure_parent(path), index=False, **parquet_write_options("bronze"))
    return len(muons)


def _all_muon_branch_columns() -> dict[str, str]:
    contract = load_yaml("configs/contracts/bronze.yaml")
    return dict(contract.get("muon_branch_columns", {}))


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
