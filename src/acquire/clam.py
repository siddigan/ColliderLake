from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.acquire.local import acquire_dataset
from src.utils.config import dataset_config
from src.utils.paths import project_root


@dataclass(frozen=True)
class HeaderDiagnosis:
    url: str
    final_url: str
    accept_ranges: bool
    content_length: int | None
    location: str | None


@dataclass(frozen=True)
class DownloadTarget:
    dataset_id: str
    name: str
    url: str
    output_path: Path
    expected_size: int | None = None
    expected_sha256: str | None = None
    xrootd_url: str | None = None


def diagnose_file(dataset_id: str, filename: str) -> HeaderDiagnosis:
    target = resolve_target(dataset_id, filename)
    return diagnose_url(target.url)


def download_file(
    dataset_id: str,
    filename: str,
    tool: str = "auto",
    max_tries: int = 0,
    retry_wait: float = 10.0,
    dry_run: bool = False,
) -> Path:
    target = resolve_target(dataset_id, filename)
    if tool == "auto":
        diagnosis = diagnose_url(target.url)
        tool = "aria2c" if shutil.which("aria2c") and diagnosis.accept_ranges else "native"
    if tool == "aria2c":
        _run_or_print(_aria2c_command(target), dry_run)
    elif tool == "xrdcp":
        _run_or_print(_xrdcp_command(target, max_tries), dry_run)
    elif tool == "native":
        if dry_run:
            print(" ".join(_native_command_text(target)))
        else:
            native_download(target, max_tries=max_tries, retry_wait=retry_wait)
    else:
        raise ValueError(f"Unknown CLAM tool {tool!r}; expected auto, aria2c, xrdcp, native")
    if not dry_run:
        verify_target(target)
        acquire_dataset(dataset_id)
    return target.output_path


def resolve_target(dataset_id: str, filename: str) -> DownloadTarget:
    config = dataset_config(dataset_id)
    raw_dir = project_root() / config.get("local_path", f"data/raw/{dataset_id}")
    for item in config.get("files", []):
        if item.get("name") == filename:
            return DownloadTarget(
                dataset_id=dataset_id,
                name=filename,
                url=item["url"],
                output_path=raw_dir / filename,
                expected_size=item.get("size_bytes"),
                expected_sha256=item.get("sha256"),
                xrootd_url=item.get("xrootd_url"),
            )
    if "://" in filename:
        name = filename.rstrip("/").rsplit("/", 1)[-1]
        return DownloadTarget(dataset_id, name, filename, raw_dir / name)
    raise KeyError(f"{filename!r} is not registered for dataset {dataset_id!r}")


def diagnose_url(url: str, timeout: float = 30.0) -> HeaderDiagnosis:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        length = response.getheader("Content-Length")
        return HeaderDiagnosis(
            url=url,
            final_url=response.url,
            accept_ranges=(response.getheader("Accept-Ranges") or "").lower() == "bytes",
            content_length=int(length) if length else None,
            location=response.getheader("Location"),
        )


def native_download(
    target: DownloadTarget,
    max_tries: int = 0,
    retry_wait: float = 10.0,
    chunk_size: int = 1024 * 1024,
) -> None:
    target.output_path.parent.mkdir(parents=True, exist_ok=True)
    part = target.output_path.with_suffix(target.output_path.suffix + ".part")
    tries = 0
    while True:
        try:
            start = part.stat().st_size if part.exists() else 0
            request = urllib.request.Request(target.url)
            if start:
                request.add_header("Range", f"bytes={start}-")
            with urllib.request.urlopen(request, timeout=60) as response:
                mode = "ab" if start else "wb"
                with part.open(mode) as handle:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        handle.write(chunk)
            if target.expected_size is None or part.stat().st_size >= target.expected_size:
                part.replace(target.output_path)
                return
        except (OSError, urllib.error.URLError):
            tries += 1
            if max_tries and tries >= max_tries:
                raise
            time.sleep(retry_wait)


def verify_target(target: DownloadTarget) -> None:
    if not target.output_path.exists():
        raise FileNotFoundError(target.output_path)
    if target.expected_size is not None and target.output_path.stat().st_size != target.expected_size:
        raise RuntimeError(
            f"Size mismatch for {target.output_path}: "
            f"{target.output_path.stat().st_size} != {target.expected_size}"
        )
    if target.expected_sha256:
        actual = _sha256(target.output_path)
        if actual.lower() != target.expected_sha256.lower():
            raise RuntimeError(f"SHA-256 mismatch for {target.output_path}: {actual}")


def target_metadata(dataset_id: str, filename: str) -> dict[str, Any]:
    target = resolve_target(dataset_id, filename)
    diagnosis = diagnose_url(target.url)
    return {
        "dataset_id": dataset_id,
        "filename": target.name,
        "url": target.url,
        "xrootd_url": target.xrootd_url,
        "output_path": str(target.output_path),
        "diagnosed_at_utc": datetime.now(UTC).isoformat(),
        "headers": diagnosis.__dict__,
    }


def _aria2c_command(target: DownloadTarget) -> list[str]:
    return [
        "aria2c",
        "-c",
        "-x",
        "4",
        "-s",
        "4",
        "-k",
        "20M",
        "--retry-wait=10",
        "--max-tries=0",
        "--file-allocation=none",
        "-d",
        str(target.output_path.parent),
        "-o",
        target.output_path.name,
        target.url,
    ]


def _xrdcp_command(target: DownloadTarget, max_tries: int) -> list[str]:
    if not target.xrootd_url:
        raise ValueError(f"No XRootD URL registered for {target.name}")
    tries = str(max_tries if max_tries else 10)
    return ["xrdcp", "--retry", tries, target.xrootd_url, str(target.output_path)]


def _native_command_text(target: DownloadTarget) -> list[str]:
    return [
        "python",
        "-m",
        "src.cli",
        "clam",
        "download",
        target.name,
        "--dataset",
        target.dataset_id,
        "--tool",
        "native",
    ]


def _run_or_print(command: list[str], dry_run: bool) -> None:
    if dry_run:
        print(" ".join(command))
        return
    subprocess.run(command, check=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_diagnosis(dataset_id: str, filename: str) -> Path:
    metadata = target_metadata(dataset_id, filename)
    output = resolve_target(dataset_id, filename).output_path.parent / f"{filename}.diagnosis.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return output
