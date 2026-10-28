from __future__ import annotations

import logging
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.physics.muons import delta_r, pair_kinematics
from src.physics.pdg import MUON_MASS_GEV
from src.utils.config import selection_for_dataset
from src.utils.paths import data_dir, data_path, ensure_parent
from src.utils.runlog import add_stage_stats, get_logger, safe_log

EVENT_KEYS = ["dataset_id", "run", "luminosityBlock", "event"]
LOGGER = get_logger("gold")
_LOGGED_GLOBAL_MUON_NOOP = False


def build_gold(dataset_id: str) -> Path:
    logger = get_logger("gold")
    _, selection, sel_id = selection_for_dataset(dataset_id)
    safe_log(logger, logging.INFO, "selection_id=%s max_muons_per_event=%s", sel_id, selection.get("max_muons_per_event", 128))
    output_dir = data_dir("gold", "analysis=resonance", f"dataset={dataset_id}", "dimuon")
    silver_events_dir = data_path("silver", f"dataset={dataset_id}", "events")
    silver_muons_dir = data_path("silver", f"dataset={dataset_id}", "muons")
    written = 0
    for event_file in sorted(silver_events_dir.glob("*.parquet")):
        muon_file = silver_muons_dir / event_file.name
        if not muon_file.exists():
            continue
        events = pd.read_parquet(event_file)
        muons = pd.read_parquet(muon_file)
        rows = _build_pairs_for_part(events, muons, selection, sel_id, event_file.name)
        output = pd.DataFrame(rows)
        if not output.empty:
            output["pair_idx"] = output["pair_idx"].astype("int32")
        output.to_parquet(ensure_parent(output_dir / event_file.name), index=False)
        events_with_pairs = len(output[EVENT_KEYS].drop_duplicates()) if not output.empty else 0
        if output.empty:
            mass_range = "n/a"
        else:
            mass_range = f"{output['mass'].min():.6g}–{output['mass'].max():.6g}"
        safe_log(
            logger,
            logging.INFO,
            "part %s | events with >=2 OS muons %s | pairs built %s | mass %s",
            event_file.name,
            f"{events_with_pairs:,}",
            f"{len(output):,}",
            mass_range,
        )
        add_stage_stats("gold", batches=1, rows_out=len(output), events=events_with_pairs)
        written += 1
    if written == 0:
        raise FileNotFoundError(f"No silver event/muon file pairs found for {dataset_id}")
    return output_dir


def _build_pairs_for_part(
    events: pd.DataFrame,
    muons: pd.DataFrame,
    selection: dict[str, Any],
    sel_id: str,
    part_name: str | None = None,
) -> list[dict[str, Any]]:
    """Build all pairs for one silver part without per-event Python loops."""
    if events.empty or muons.empty:
        return []

    paths = selection.get("trigger", {}).get("paths", [])
    event_frame = events.copy()
    event_frame["_event_order"] = np.arange(len(event_frame), dtype=np.int64)
    event_frame["trigger_path"] = _trigger_paths(event_frame, paths)
    event_frame = event_frame[event_frame["trigger_path"].notna()].copy()
    if event_frame.empty:
        return []
    if "identity_mode" not in event_frame.columns:
        event_frame["identity_mode"] = "native"

    selected = _select_muons(muons, selection.get("muon", {}))
    if selected.empty:
        return []
    counts = selected.groupby(EVENT_KEYS, sort=False).size()
    max_muons = int(selection.get("max_muons_per_event", 128))
    above_half = counts[counts > max_muons / 2]
    if not above_half.empty:
        safe_log(
            LOGGER,
            logging.WARNING,
            "muon multiplicity warning | part %s | events_above_half_max=%d | max_muons_per_event_seen=%d | configured_max=%d",
            part_name or "<in-memory>",
            len(above_half),
            int(counts.max()),
            max_muons,
        )
    too_many = counts[counts > max_muons]
    if not too_many.empty:
        key = tuple(value.item() if isinstance(value, np.generic) else value for value in too_many.index[0])
        raise ValueError(
            f"Too many selected muons for event key {key}: {int(too_many.iloc[0])} > "
            f"selection config max_muons_per_event={max_muons}"
        )

    muon_columns = ["muon_idx", "pt", "eta", "phi", "mass", "charge", "iso"]
    selected = selected[EVENT_KEYS + muon_columns]
    left = selected.rename(columns={column: f"{column}_1" for column in muon_columns})
    right = selected.rename(columns={column: f"{column}_2" for column in muon_columns})
    pairs = left.merge(right, on=EVENT_KEYS, how="inner", sort=False)
    pairs = pairs[pairs["muon_idx_1"] < pairs["muon_idx_2"]].copy()
    if pairs.empty:
        return []
    if selection.get("pair", {}).get("opposite_charge", True):
        pairs = pairs[(pairs["charge_1"] * pairs["charge_2"]) < 0].copy()
    if pairs.empty:
        return []

    admitted = event_frame[EVENT_KEYS + ["trigger_path", "identity_mode", "_event_order"]]
    pairs = pairs.merge(admitted, on=EVENT_KEYS, how="inner", sort=False)
    if pairs.empty:
        return []

    pt1 = pairs["pt_1"].to_numpy(dtype=np.float64)
    eta1 = pairs["eta_1"].to_numpy(dtype=np.float64)
    phi1 = pairs["phi_1"].to_numpy(dtype=np.float64)
    pt2 = pairs["pt_2"].to_numpy(dtype=np.float64)
    eta2 = pairs["eta_2"].to_numpy(dtype=np.float64)
    phi2 = pairs["phi_2"].to_numpy(dtype=np.float64)
    mass1 = pairs["mass_1"].to_numpy(dtype=np.float64)
    mass2 = pairs["mass_2"].to_numpy(dtype=np.float64)
    energy1 = np.sqrt((pt1 * np.cosh(eta1)) ** 2 + mass1**2)
    energy2 = np.sqrt((pt2 * np.cosh(eta2)) ** 2 + mass2**2)
    px = pt1 * np.cos(phi1) + pt2 * np.cos(phi2)
    py = pt1 * np.sin(phi1) + pt2 * np.sin(phi2)
    pz = pt1 * np.sinh(eta1) + pt2 * np.sinh(eta2)
    energy = energy1 + energy2
    mass = np.sqrt(np.maximum(energy**2 - px**2 - py**2 - pz**2, 0.0))
    denominator = energy - pz
    rapidity = np.where(denominator <= 0.0, 0.0, 0.5 * np.log((energy + pz) / denominator))
    pair_pt = np.sqrt(px**2 + py**2)
    raw_delta_phi = np.abs(phi1 - phi2)
    delta_phi_value = np.where(raw_delta_phi > np.pi, 2.0 * np.pi - raw_delta_phi, raw_delta_phi)
    delta_r_value = np.sqrt((eta1 - eta2) ** 2 + delta_phi_value**2)

    low, high = selection.get("mass_window", [0.0, float("inf")])
    keep = (mass >= float(low)) & (mass <= float(high))
    pairs = pairs.loc[keep].copy()
    if pairs.empty:
        return []
    pairs["mass"] = mass[keep]
    pairs["pt_pair"] = pair_pt[keep]
    pairs["rapidity"] = rapidity[keep]
    pairs["delta_r"] = delta_r_value[keep]
    pairs["_pair_pt_sum"] = pairs["pt_1"] + pairs["pt_2"]
    pairs = pairs.sort_values(
        ["_event_order", "_pair_pt_sum", "muon_idx_1", "muon_idx_2"],
        ascending=[True, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    pairs["pair_idx"] = pairs.groupby(EVENT_KEYS, sort=False).cumcount().astype("int32")

    output = pd.DataFrame(
        {
            "dataset_id": pairs["dataset_id"],
            "run": pairs["run"].astype("int64"),
            "luminosityBlock": pairs["luminosityBlock"].astype("int64"),
            "event": pairs["event"].astype("int64"),
            "mu1_idx": pairs["muon_idx_1"].astype("int64"),
            "mu2_idx": pairs["muon_idx_2"].astype("int64"),
            "mass": pairs["mass"].astype("float64"),
            "pt_pair": pairs["pt_pair"].astype("float64"),
            "rapidity": pairs["rapidity"].astype("float64"),
            "delta_r": pairs["delta_r"].astype("float64"),
            "mu1_pt": pairs["pt_1"].astype("float64"),
            "mu1_eta": pairs["eta_1"].astype("float64"),
            "mu1_phi": pairs["phi_1"].astype("float64"),
            "mu1_iso": pairs["iso_1"].astype("object").where(pairs["iso_1"].notna(), None),
            "mu1_charge": pairs["charge_1"].astype("int64"),
            "mu2_pt": pairs["pt_2"].astype("float64"),
            "mu2_eta": pairs["eta_2"].astype("float64"),
            "mu2_phi": pairs["phi_2"].astype("float64"),
            "mu2_iso": pairs["iso_2"].astype("object").where(pairs["iso_2"].notna(), None),
            "mu2_charge": pairs["charge_2"].astype("int64"),
            "trigger_path": pairs["trigger_path"].astype("object"),
            "selection_id": sel_id,
            "identity_mode": pairs["identity_mode"].astype("object"),
            "pair_idx": pairs["pair_idx"],
        }
    )
    output["is_leading_pair"] = output["pair_idx"] == 0
    return output.to_dict("records")


def _build_pairs_reference(
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


def _select_muons(muons: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    frame = muons.copy()
    if "mass" not in frame.columns:
        frame["mass"] = MUON_MASS_GEV
    if "iso" not in frame.columns:
        frame["iso"] = np.nan
    mask = ~(frame["pt"].astype(float) < float(config.get("pt_min", 0.0)))
    mask &= ~(frame["eta"].abs().astype(float) > float(config.get("abs_eta_max", 999.0)))
    if "iso_max" in config:
        iso = frame["iso"].astype(float)
        mask &= iso.notna() & ~(iso >= float(config["iso_max"]))
    if config.get("quality") == "tight_id":
        if "tight_id" not in frame.columns:
            return frame.iloc[0:0].copy()
        mask &= frame["tight_id"].map(bool)
    return frame.loc[mask].copy()


def _trigger_paths(events: pd.DataFrame, paths: list[str]) -> pd.Series:
    if not paths:
        return pd.Series("none", index=events.index, dtype="object")
    labels = np.full(len(events), None, dtype=object)
    admitted = np.zeros(len(events), dtype=bool)
    for path in paths:
        if path in events.columns:
            values = events[path].fillna(False).astype(bool).to_numpy()
        else:
            values = np.zeros(len(events), dtype=bool)
        take = (~admitted) & values
        labels[take] = path
        admitted |= values
    return pd.Series(labels, index=events.index, dtype="object")


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
    selected.sort(key=lambda item: int(item.get("muon_idx", 0)))
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
                "mu1_idx": int(first.get("muon_idx", 0)),
                "mu2_idx": int(second.get("muon_idx", 0)),
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
    rows.sort(
        key=lambda item: (
            -(item["mu1_pt"] + item["mu2_pt"]),
            item["mu1_idx"],
            item["mu2_idx"],
        )
    )
    for index, row in enumerate(rows):
        row["pair_idx"] = index
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
            safe_log(LOGGER, logging.INFO, "quality=global_muon: no-op for reduced 2012 format")
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
