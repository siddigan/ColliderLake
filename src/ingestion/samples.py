from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NanoAODSample:
    name: str
    record_url: str
    doi: str
    root_url: str
    http_url: str


SINGLE_MUON_RUN2016H_SAMPLE = NanoAODSample(
    name="SingleMuon Run2016H NanoAOD v9 sample",
    record_url="https://opendata.cern.ch/record/30563",
    doi="10.7483/OPENDATA.CMS.4BUS.64MV",
    root_url=(
        "root://eospublic.cern.ch//eos/opendata/cms/Run2016H/SingleMuon/"
        "NANOAOD/UL2016_MiniAODv2_NanoAODv9-v1/120000/"
        "61FC1E38-F75C-6B44-AD19-A9894155874E.root"
    ),
    http_url=(
        "https://eospublic.cern.ch/eos/opendata/cms/Run2016H/SingleMuon/"
        "NANOAOD/UL2016_MiniAODv2_NanoAODv9-v1/120000/"
        "61FC1E38-F75C-6B44-AD19-A9894155874E.root"
    ),
)


DEFAULT_TREE_NAME = "Events"
DEFAULT_BRANCHES = [
    "Muon_pt",
    "Muon_eta",
    "Muon_phi",
    "Muon_mass",
    "MET_pt",
    "Jet_pt",
]
