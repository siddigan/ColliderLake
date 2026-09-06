from __future__ import annotations

import argparse
import logging

import awkward as ak
import numpy as np

from _bootstrap import add_workspace_to_path

add_workspace_to_path()

from src.ingestion.root_io import iter_event_batches
from src.ingestion.samples import DEFAULT_BRANCHES, SINGLE_MUON_RUN2016H_SAMPLE
from src.physics.muons import batch_summary, flatten_muon_pt
from src.utils.logging_config import configure_logging
from src.utils.paths import outputs_dir
from src.visualization.histograms import save_muon_pt_histogram

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract muon variables and plot muon pT.")
    parser.add_argument("--input", default=SINGLE_MUON_RUN2016H_SAMPLE.http_url, help="Local ROOT file or remote URL.")
    parser.add_argument("--step-size", default="25 MB", help="uproot batch size, e.g. 10000 or '25 MB'.")
    parser.add_argument("--max-batches", type=int, default=2, help="Stop after this many batches.")
    parser.add_argument("--output", default=outputs_dir() / "muon_pt.png", help="Output plot path.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    muon_pts: list[np.ndarray] = []
    try:
        for arrays in iter_event_batches(
            args.input,
            DEFAULT_BRANCHES,
            step_size=args.step_size,
            max_batches=args.max_batches,
        ):
            summary = batch_summary(arrays)
            LOGGER.info("Batch summary: %s", summary)
            muon_pts.append(flatten_muon_pt(arrays))

            if "MET_pt" in arrays.fields:
                LOGGER.info("MET_pt mean: %.3f GeV", float(ak.mean(arrays["MET_pt"])))
            if "Jet_pt" in arrays.fields:
                LOGGER.info("Jets in batch: %s", int(ak.sum(ak.num(arrays["Jet_pt"]))))

        if not muon_pts:
            raise RuntimeError("No event batches were read")

        all_pt = np.concatenate(muon_pts)
        output_path = save_muon_pt_histogram(all_pt, args.output)
        LOGGER.info("Saved muon pT histogram to %s", output_path)
    except Exception:
        LOGGER.exception("Muon extraction failed")
        raise


if __name__ == "__main__":
    main()
