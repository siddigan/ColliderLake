from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
from hist import Hist


def save_muon_pt_histogram(
    muon_pt: np.ndarray,
    output_path: str | Path,
    bins: int = 80,
    pt_range: tuple[float, float] = (0.0, 200.0),
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    histogram = Hist.new.Reg(bins, pt_range[0], pt_range[1], name="pt", label="Muon pT [GeV]").Double()
    histogram.fill(muon_pt)

    plt.style.use(hep.style.CMS)
    fig, ax = plt.subplots(figsize=(8, 6))
    histogram.plot(ax=ax, histtype="fill", alpha=0.75)
    ax.set_xlabel("Muon pT [GeV]")
    ax.set_ylabel("Muon count")
    ax.set_title("CMS Open Data: SingleMuon Run2016H")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def save_histogram(
    values: np.ndarray,
    output_path: str | Path,
    bins: int,
    value_range: tuple[float, float],
    xlabel: str,
    ylabel: str,
    title: str,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    clean_values = np.asarray(values)
    clean_values = clean_values[np.isfinite(clean_values)]

    histogram = Hist.new.Reg(bins, value_range[0], value_range[1], name="value", label=xlabel).Double()
    histogram.fill(clean_values)

    plt.style.use(hep.style.CMS)
    fig, ax = plt.subplots(figsize=(8, 6))
    histogram.plot(ax=ax, histtype="fill", alpha=0.75)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output
