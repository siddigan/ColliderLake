from __future__ import annotations

import awkward as ak
import numpy as np


def flatten_muon_pt(events: ak.Array) -> np.ndarray:
    """Return a dense NumPy array of all muon pT values in the event batch."""
    if "Muon_pt" not in events.fields:
        raise KeyError("Muon_pt branch is required")
    return ak.to_numpy(ak.flatten(events["Muon_pt"], axis=None))


def batch_summary(events: ak.Array) -> dict[str, float]:
    muon_pt = flatten_muon_pt(events)
    summary = {
        "events": float(len(events)),
        "muons": float(len(muon_pt)),
    }
    if len(muon_pt):
        summary["muon_pt_mean"] = float(np.mean(muon_pt))
        summary["muon_pt_max"] = float(np.max(muon_pt))
    return summary
