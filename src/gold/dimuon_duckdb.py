from __future__ import annotations

import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from src.physics.pdg import MUON_MASS_GEV
from src.utils.paths import data_root

EVENT_KEYS = ["dataset_id", "run", "luminosityBlock", "event"]
BASE_COLUMNS = [
    "dataset_id",
    "run",
    "luminosityBlock",
    "event",
    "mu1_idx",
    "mu2_idx",
    "mass",
    "pt_pair",
    "rapidity",
    "delta_r",
    "mu1_pt",
    "mu1_eta",
    "mu1_phi",
    "mu1_iso",
    "mu1_charge",
    "mu2_pt",
    "mu2_eta",
    "mu2_phi",
    "mu2_iso",
    "mu2_charge",
    "trigger_path",
    "selection_id",
    "identity_mode",
    "pair_idx",
    "is_leading_pair",
]


@contextmanager
def duckdb_session():
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="gold-duckdb-spill-", dir=root) as spill,
        duckdb.connect() as con,
    ):
        con.execute("SET memory_limit = ?", [os.environ.get("COLLIDERLAKE_DQ_MEM", "2GB")])
        con.execute("SET temp_directory = ?", [spill])
        con.execute("SET preserve_insertion_order = false")
        con.execute("SET threads = ?", [int(os.environ.get("COLLIDERLAKE_DUCKDB_THREADS", "2"))])
        yield con


def build_part(
    event_path: Path,
    muon_path: Path,
    events: pd.DataFrame,
    selection: dict[str, Any],
    selection_id: str,
    *,
    profile: str = "reduced",
    required_columns: list[str] | None = None,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> tuple[pd.DataFrame, float]:
    """Build one gold part with a DuckDB Parquet self-join and return its cold query time."""
    muon_names = set(pq.read_schema(muon_path).names)
    required_columns = required_columns or []
    source_aliases = {"Muon_pfRelIso04_all": "iso"}
    missing = [
        name for name in required_columns if source_aliases.get(name, name) not in muon_names
    ]
    if missing:
        raise ValueError(f"contract violation: {missing[0]} required by profile {profile}")

    from src.gold.dimuon import _trigger_paths

    trigger_paths = list(selection.get("trigger", {}).get("paths", []))
    event_frame = events.copy()
    event_frame["trigger_path"] = _trigger_paths(event_frame, trigger_paths)
    event_frame = event_frame[event_frame["trigger_path"].notna()].copy()
    if "identity_mode" not in event_frame:
        event_frame["identity_mode"] = "native"
    if event_frame.empty or "muon_idx" not in muon_names:
        return pd.DataFrame(columns=BASE_COLUMNS), 0.0

    muon_projection = [
        name
        for name in EVENT_KEYS
        + ["muon_idx", "pt", "eta", "phi", "mass", "charge", "iso", "tight_id", "medium_id"]
        if name in muon_names
    ]
    if "mass" not in muon_names:
        muon_projection.append("mass")
    if "iso" not in muon_names:
        muon_projection.append("iso")
    extras = [(name, source_aliases.get(name, name)) for name in required_columns]
    muon_projection.extend(
        source for _, source in extras if source in muon_names and source not in muon_projection
    )
    select_muons = [
        f'coalesce(CAST("mass" AS DOUBLE), {MUON_MASS_GEV!r}) AS "mass"'
        if name == "mass" and name in muon_names
        else f'{MUON_MASS_GEV!r}::DOUBLE AS "mass"'
        if name == "mass"
        else 'NULL::DOUBLE AS "iso"'
        if name == "iso" and name not in muon_names
        else f'"{name}"'
        for name in muon_projection
    ]
    mu_config = selection.get("muon", {})
    filters = [
        f'CAST("pt" AS DOUBLE) >= {float(mu_config.get("pt_min", 0.0))!r}',
        f'abs(CAST("eta" AS DOUBLE)) <= {float(mu_config.get("abs_eta_max", 999.0))!r}',
    ]
    if "iso_max" in mu_config:
        filters += ['"iso" IS NOT NULL', f'CAST("iso" AS DOUBLE) < {float(mu_config["iso_max"])!r}']
    if mu_config.get("quality") == "tight_id":
        filters.append('coalesce("tight_id", false)')
    low, high = selection.get("mass_window", [0.0, float("inf")])
    if selection.get("pair", {}).get("opposite_charge", True):
        charge_filter = "a.charge * b.charge < 0"
    else:
        charge_filter = "true"
    phi_delta = "abs(a.phi - b.phi)"
    dphi = f"CASE WHEN {phi_delta} > pi() THEN 2 * pi() - {phi_delta} ELSE {phi_delta} END"
    e1 = "sqrt(pow(a.pt * cosh(a.eta), 2) + pow(a.mass, 2))"
    e2 = "sqrt(pow(b.pt * cosh(b.eta), 2) + pow(b.mass, 2))"
    px = "a.pt * cos(a.phi) + b.pt * cos(b.phi)"
    py = "a.pt * sin(a.phi) + b.pt * sin(b.phi)"
    pz = "a.pt * sinh(a.eta) + b.pt * sinh(b.eta)"
    energy = f"({e1} + {e2})"
    mass_expr = (
        f"sqrt(greatest(pow({energy}, 2) - pow({px}, 2) - pow({py}, 2) - pow({pz}, 2), 0.0))"
    )
    pair_pt_expr = f"sqrt(pow({px}, 2) + pow({py}, 2))"
    rapidity_expr = f"CASE WHEN {energy} - ({pz}) <= 0 THEN 0.0 ELSE 0.5 * ln(({energy} + ({pz})) / ({energy} - ({pz}))) END"
    extra_select = []
    for required, source in extras:
        extra_select += [f'a."{source}" AS "mu1_{required}"', f'b."{source}" AS "mu2_{required}"']
    sql = f"""
        WITH muons AS (
            SELECT {", ".join(select_muons)}
            FROM read_parquet('{str(muon_path).replace("'", "''")}')
            WHERE {" AND ".join(filters)}
        ), pairs AS (
            SELECT e.dataset_id, e.run, e.luminosityBlock, e.event,
                   a.muon_idx AS mu1_idx, b.muon_idx AS mu2_idx,
                   {mass_expr} AS mass, {pair_pt_expr} AS pt_pair,
                   {rapidity_expr} AS rapidity,
                   sqrt(pow(a.eta - b.eta, 2) + pow({dphi}, 2)) AS delta_r,
                   a.pt AS mu1_pt, a.eta AS mu1_eta, a.phi AS mu1_phi, a.iso AS mu1_iso,
                   a.charge AS mu1_charge, b.pt AS mu2_pt, b.eta AS mu2_eta,
                   b.phi AS mu2_phi, b.iso AS mu2_iso, b.charge AS mu2_charge,
                   e.trigger_path, e.identity_mode, a.pt + b.pt AS _pt_sum
                   {"," if extra_select else ""}{", ".join(extra_select)}
            FROM muons a JOIN muons b
              ON {" AND ".join(f'a."{k}" = b."{k}"' for k in EVENT_KEYS)}
             AND a.muon_idx < b.muon_idx
            JOIN events e ON {" AND ".join(f'a."{k}" = e."{k}"' for k in EVENT_KEYS)}
            WHERE {charge_filter}
        ), accepted AS (
            SELECT *, CAST(row_number() OVER (
                PARTITION BY dataset_id, run, luminosityBlock, event
                ORDER BY _pt_sum DESC, mu1_idx ASC, mu2_idx ASC
            ) - 1 AS INTEGER) AS pair_idx
            FROM pairs WHERE mass >= {float(low)!r} AND mass <= {float(high)!r}
        )
        SELECT dataset_id, CAST(run AS BIGINT) AS run,
               CAST(luminosityBlock AS BIGINT) AS luminosityBlock,
               CAST(event AS BIGINT) AS event,
               CAST(mu1_idx AS BIGINT) AS mu1_idx, CAST(mu2_idx AS BIGINT) AS mu2_idx,
               CAST(mass AS DOUBLE) AS mass, CAST(pt_pair AS DOUBLE) AS pt_pair,
               CAST(rapidity AS DOUBLE) AS rapidity, CAST(delta_r AS DOUBLE) AS delta_r,
               CAST(mu1_pt AS DOUBLE) AS mu1_pt, CAST(mu1_eta AS DOUBLE) AS mu1_eta,
               CAST(mu1_phi AS DOUBLE) AS mu1_phi, mu1_iso,
               CAST(mu1_charge AS BIGINT) AS mu1_charge, CAST(mu2_pt AS DOUBLE) AS mu2_pt,
               CAST(mu2_eta AS DOUBLE) AS mu2_eta, CAST(mu2_phi AS DOUBLE) AS mu2_phi,
               mu2_iso, CAST(mu2_charge AS BIGINT) AS mu2_charge,
               trigger_path, '{selection_id}' AS selection_id, identity_mode,
               pair_idx, pair_idx = 0 AS is_leading_pair
               {"," if extra_select else ""}{", ".join(f'"mu1_{name}", "mu2_{name}"' for name, _ in extras)}
        FROM accepted ORDER BY dataset_id, run, luminosityBlock, event, pair_idx
    """
    started = time.perf_counter()
    if connection is None:
        with duckdb_session() as owned:
            owned.register("events", event_frame[EVENT_KEYS + ["trigger_path", "identity_mode"]])
            output = owned.execute(sql).fetchdf()
            owned.unregister("events")
    else:
        connection.register("events", event_frame[EVENT_KEYS + ["trigger_path", "identity_mode"]])
        output = connection.execute(sql).fetchdf()
        connection.unregister("events")
    elapsed = time.perf_counter() - started
    if "pair_idx" in output:
        output["pair_idx"] = output["pair_idx"].astype("int32")
    ordered = BASE_COLUMNS + [f"mu{i}_{name}" for name, _ in extras for i in (1, 2)]
    return output.reindex(columns=ordered), elapsed
