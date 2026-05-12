from __future__ import annotations

import argparse
import logging
import ssl
import urllib.request
from pathlib import Path

from tqdm import tqdm

from _bootstrap import add_workspace_to_path

add_workspace_to_path()

from src.ingestion.samples import SINGLE_MUON_RUN2016H_SAMPLE
from src.utils.logging_config import configure_logging
from src.utils.paths import data_dir

LOGGER = logging.getLogger(__name__)


class DownloadProgress(tqdm):
    def update_to(self, blocks: int = 1, block_size: int = 1, total_size: int | None = None) -> None:
        if total_size is not None:
            self.total = total_size
        self.update(blocks * block_size - self.n)


def download_file(url: str, destination: Path, overwrite: bool = False, insecure_ssl: bool = False) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        LOGGER.info("File already exists: %s", destination)
        return destination

    LOGGER.info("Downloading %s", url)
    try:
        context = ssl._create_unverified_context() if insecure_ssl else None
        with DownloadProgress(unit="B", unit_scale=True, miniters=1, desc=destination.name) as progress:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(url, destination, reporthook=progress.update_to)
    except Exception as exc:
        if destination.exists():
            destination.unlink()
        raise RuntimeError(f"Download failed for {url}") from exc
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a small CMS SingleMuon NanoAOD sample file.")
    parser.add_argument("--url", default=SINGLE_MUON_RUN2016H_SAMPLE.http_url, help="HTTP URL to download.")
    parser.add_argument("--output-dir", type=Path, default=data_dir("raw"), help="Destination directory.")
    parser.add_argument("--filename", default=None, help="Output filename. Defaults to the URL basename.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing local file.")
    parser.add_argument("--insecure-ssl", action="store_true", help="Disable HTTPS certificate verification.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    filename = args.filename or args.url.rstrip("/").split("/")[-1]
    output = download_file(
        args.url,
        args.output_dir / filename,
        overwrite=args.overwrite,
        insecure_ssl=args.insecure_ssl,
    )
    LOGGER.info("Sample available at %s", output)


if __name__ == "__main__":
    main()
