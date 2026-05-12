from __future__ import annotations

from dataclasses import dataclass


DATASET_NAME = "SingleMuon"
DATASET_PATH = "/SingleMuon/Run2016H-UL2016_MiniAODv2_NanoAODv9-v1/NANOAOD"
YEAR = 2016
RUN_PERIOD = "RunH"
NANOAOD_VERSION = "NanoAODv9"

EVENT_COLUMNS = ["run", "luminosityBlock", "event"]
MUON_COLUMNS = [
    "Muon_pt",
    "Muon_eta",
    "Muon_phi",
    "Muon_mass",
    "Muon_charge",
    "Muon_tightId",
    "Muon_pfRelIso04_all",
]
JET_COLUMNS = ["Jet_pt", "Jet_eta", "Jet_phi", "Jet_mass", "Jet_btagDeepB"]
MET_COLUMNS = ["MET_pt", "MET_phi", "PuppiMET_pt"]
TRIGGER_COLUMNS = ["HLT_IsoMu24", "HLT_Mu50"]
QUALITY_COLUMNS = ["Flag_goodVertices", "Flag_METFilters"]

BRONZE_COLUMNS = EVENT_COLUMNS + MUON_COLUMNS + JET_COLUMNS + MET_COLUMNS + TRIGGER_COLUMNS + QUALITY_COLUMNS


@dataclass(frozen=True)
class MuonDbConfig:
    """Runtime settings for the muon_db Spark ETL."""

    source_parquet: str
    output_root: str
    dataset: str = DATASET_NAME
    dataset_path: str = DATASET_PATH
    year: int = YEAR
    run_period: str = RUN_PERIOD
    nanoaod_version: str = NANOAOD_VERSION
    write_mode: str = "overwrite"

