from __future__ import annotations

import logging
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from src.physics.muons import delta_r, pair_kinematics
from src.physics.pdg import MUON_MASS_GEV
from src.utils.config import selection_for_dataset
from src.utils.paths import data_path, ensure_parent

EVENT_KEYS = ["dataset_id", "run", "luminosityBlock", "event"]
LOGGER = logging.getLogger(__name__)
_LOGGED_GLOBAL_MUON_NOOP = False


def build_gold(dataset_id: str) -> Path:
    _, selection, sel_id = selection_for_dataset(dataset_id)
    output_dir = data_path("gold", "analysis=resonance", f"dataset={dataset_id}", "dimuon")
    silver_events_dir = data_path("silver", f"dataset={dataset_id}", "events")
    silver_muons_dir = data_path("silver", f"dataset={dataset_id}", "muons")
    written = 0
    for event_file in sorted(silver_events_dir.glob("*.parquet")):
        muon_file = silver_muons_dir / event_file.name
        if not muon_file.exists():
            continue
        events = pd.read_parquet(event_file)
        muons = pd.read_parquet(muon_file)
        rows = _build_pairs_for_part(events, muons, selection, sel_id)
        output = pd.DataFrame(rows)
        # TODO(awkward vectorization, Phase 1): replace pandas grouping for full-stat runs.
        output.to_parquet(ensure_parent(output_dir / event_file.name), index=False)
        written += 1
    if written == 0:
        raise FileNotFoundError(f"No silver event/muon file pairs found for {dataset_id}")
    return output_dir


def _build_pairs_for_part(
    events: pd.DataFrame,
    muons: pd.DataFrame,
    selection: dict[str, Any],
    sel_id: str,
) -> list[dict[str, Any]]:
    if events.empty or muons.empty:
        return []
    rows: list[dict[str, Any]] = []
    grouped = {key: group for key, group in muons.groupby(EVENT_KEYS, sort=False)}
    for _, event in events.iterrows():
        key = tuple(event[column] for column in EVENT_KEYS)
        event_muons = grouped.get(key)
        if event_muons is None:
            continue
        rows.extend(_event_pairs(event, event_muons.to_dict("records"), selection, sel_id))
    return rows


def _event_pairs(
    event: pd.Series,
    muons: list[dict[str, Any]],
    selection: dict[str, Any],
    sel_id: str,
) -> list[dict[str, Any]]:
    admitted_by = _trigger_path(event, selection.get("trigger", {}).get("paths", []))
    if admitted_by is None:
        return []
    selected = [_muon for _muon in muons if _passes_muon(_muon, selection.get("muon", {}))]
    rows: list[dict[str, Any]] = []
    for first, second in combinations(selected, 2):
        if selection.get("pair", {}).get("opposite_charge", True) and first["charge"] * second["charge"] >= 0:
            continue
        pair = pair_kinematics(
            first["pt"],
            first["eta"],
            first["phi"],
            second["pt"],
            second["eta"],
            second["phi"],
            first.get("mass", MUON_MASS_GEV) or MUON_MASS_GEV,
            second.get("mass", MUON_MASS_GEV) or MUON_MASS_GEV,
        )
        low, high = selection.get("mass_window", [0.0, float("inf")])
        if not (low <= pair["mass"] <= high):
            continue
        rows.append(
            {
                "dataset_id": event["dataset_id"],
                "run": int(event["run"]),
                "luminosityBlock": int(event["luminosityBlock"]),
                "event": int(event["event"]),
                "mass": float(pair["mass"]),
                "pt_pair": float(pair["pt_pair"]),
                "rapidity": float(pair["rapidity"]),
                "delta_r": float(delta_r(first["eta"], first["phi"], second["eta"], second["phi"])),
                "mu1_pt": float(first["pt"]),
                "mu1_eta": float(first["eta"]),
                "mu1_phi": float(first["phi"]),
                "mu1_iso": _nullable_float(first.get("iso")),
                "mu1_charge": int(first["charge"]),
                "mu2_pt": float(second["pt"]),
                "mu2_eta": float(second["eta"]),
                "mu2_phi": float(second["phi"]),
                "mu2_iso": _nullable_float(second.get("iso")),
                "mu2_charge": int(second["charge"]),
                "trigger_path": admitted_by,
                "selection_id": sel_id,
                "identity_mode": event.get("identity_mode", "native"),
            }
        )
    rows.sort(key=lambda item: item["pt_pair"], reverse=True)
    for index, row in enumerate(rows):
        row["is_leading_pair"] = index == 0
    return rows


def _passes_muon(muon: dict[str, Any], config: dict[str, Any]) -> bool:
    global _LOGGED_GLOBAL_MUON_NOOP
    if float(muon["pt"]) < float(config.get("pt_min", 0.0)):
        return False
    if abs(float(muon["eta"])) > float(config.get("abs_eta_max", 999.0)):
        return False
    if "iso_max" in config:
        iso = muon.get("iso")
        if pd.isna(iso) or float(iso) >= float(config["iso_max"]):
            return False
    quality = config.get("quality")
    if quality == "tight_id" and not bool(muon.get("tight_id", False)):
        return False
    if quality == "global_muon":
        if not _LOGGED_GLOBAL_MUON_NOOP:
            LOGGER.info("quality=global_muon: no-op for reduced 2012 format")
            _LOGGED_GLOBAL_MUON_NOOP = True
        return True
    return True


def _trigger_path(event: pd.Series, paths: list[str]) -> str | None:
    if not paths:
        return "none"
    for path in paths:
        if bool(event.get(path, False)):
            return path
    return None


def _nullable_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
