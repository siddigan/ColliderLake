from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from src.physics.muons import delta_r, invariant_mass
from src.physics.pdg import MUON_MASS_GEV
from src.utils.config import selection_for_dataset
from src.utils.paths import data_path, ensure_parent


def build_gold(dataset_id: str) -> Path:
    _, selection, sel_id = selection_for_dataset(dataset_id)
    silver = _read_parquet_dir(data_path("silver", f"dataset={dataset_id}", "events"))
    rows = [_pair for _, event in silver.iterrows() for _pair in _event_pairs(event, selection, sel_id)]
    output = pd.DataFrame(rows)
    output_dir = data_path("gold", "analysis=resonance", f"dataset={dataset_id}", "dimuon")
    output_path = ensure_parent(output_dir / "part-0000.parquet")
    output.to_parquet(output_path, index=False)
    return output_dir


def _read_parquet_dir(path: Path) -> pd.DataFrame:
    files = sorted(path.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Parquet files found under {path}")
    return pd.concat((pd.read_parquet(file) for file in files), ignore_index=True)


def _event_pairs(event: pd.Series, selection: dict[str, Any], sel_id: str) -> list[dict[str, Any]]:
    muons = _muons(event)
    muon_cfg = selection.get("muon", {})
    trigger_cfg = selection.get("trigger", {})
    paths = trigger_cfg.get("paths", [])
    admitted_by = _trigger_path(event, paths)
    if admitted_by is None:
        return []
    selected = [_muon for _muon in muons if _passes_muon(_muon, muon_cfg)]
    rows: list[dict[str, Any]] = []
    for first, second in combinations(selected, 2):
        if selection.get("pair", {}).get("opposite_charge", True) and first["charge"] * second["charge"] >= 0:
            continue
        mass = invariant_mass(
            first["pt"], first["eta"], first["phi"], second["pt"], second["eta"], second["phi"],
            first.get("mass", MUON_MASS_GEV), second.get("mass", MUON_MASS_GEV)
        )
        low, high = selection.get("mass_window", [0.0, float("inf")])
        if not (low <= mass <= high):
            continue
        rows.append(
            {
                "dataset_id": event["dataset_id"],
                "run": int(event["run"]),
                "luminosityBlock": int(event["luminosityBlock"]),
                "event": int(event["event"]),
                "mass": float(mass),
                "pt_pair": float(first["pt"] + second["pt"]),
                "rapidity": 0.0,
                "delta_r": float(delta_r(first["eta"], first["phi"], second["eta"], second["phi"])),
                "mu1_pt": first["pt"],
                "mu1_eta": first["eta"],
                "mu1_phi": first["phi"],
                "mu1_iso": first.get("iso"),
                "mu1_charge": first["charge"],
                "mu2_pt": second["pt"],
                "mu2_eta": second["eta"],
                "mu2_phi": second["phi"],
                "mu2_iso": second.get("iso"),
                "mu2_charge": second["charge"],
                "trigger_path": admitted_by,
                "selection_id": sel_id,
            }
        )
    rows.sort(key=lambda item: item["pt_pair"], reverse=True)
    for index, row in enumerate(rows):
        row["is_leading_pair"] = index == 0
    return rows


def _muons(event: pd.Series) -> list[dict[str, Any]]:
    pts = _as_list(event.get("Muon_pt"))
    etas = _as_list(event.get("Muon_eta"))
    phis = _as_list(event.get("Muon_phi"))
    masses = _as_list(event.get("Muon_mass")) or [MUON_MASS_GEV] * len(pts)
    charges = _as_list(event.get("Muon_charge"))
    tight_ids = _as_list(event.get("Muon_tightId"))
    medium_ids = _as_list(event.get("Muon_mediumId"))
    isolations = _as_list(event.get("Muon_pfRelIso04_all"))
    muons: list[dict[str, Any]] = []
    for index, pt in enumerate(pts):
        muons.append(
            {
                "pt": float(pt),
                "eta": float(etas[index]),
                "phi": float(phis[index]),
                "mass": float(masses[index]) if index < len(masses) else MUON_MASS_GEV,
                "charge": int(charges[index]),
                "tight_id": bool(tight_ids[index]) if index < len(tight_ids) else False,
                "medium_id": bool(medium_ids[index]) if index < len(medium_ids) else False,
                "iso": float(isolations[index]) if index < len(isolations) else None,
            }
        )
    return muons


def _passes_muon(muon: dict[str, Any], config: dict[str, Any]) -> bool:
    if muon["pt"] < float(config.get("pt_min", 0.0)):
        return False
    if abs(muon["eta"]) > float(config.get("abs_eta_max", 999.0)):
        return False
    if "iso_max" in config and (muon.get("iso") is None or muon["iso"] >= float(config["iso_max"])):
        return False
    quality = config.get("quality")
    if quality == "tight_id" and not muon.get("tight_id", False):
        return False
    if quality == "global_muon":
        return True
    return True


def _trigger_path(event: pd.Series, paths: list[str]) -> str | None:
    if not paths:
        return "none"
    for path in paths:
        if bool(event.get(path, False)):
            return path
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return value
    return [value]
