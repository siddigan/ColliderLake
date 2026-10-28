from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


def _read_summary(path: Path) -> tuple[dict[str, tuple[float, float]], float]:
    text = path.read_text(encoding="utf-8")
    stages: dict[str, tuple[float, float]] = {}
    duration_pattern = r"(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s"
    for line in text.splitlines():
        match = re.match(
            rf"^(\w+)\s+\|\s+(SUCCESS|FAILED|PARTIAL)\s+\|\s+({duration_pattern})\s+\|\s+([\d,]+)\s+\|\s+([\d.]+)",
            line,
        )
        if not match:
            continue
        name, _status, _duration, hours, minutes, seconds, _rows, rows_per_second = match.groups()
        stages[name] = (_duration_seconds(hours, minutes, seconds), float(rows_per_second))
    match = re.search(rf"^total_wall_time:\s*{duration_pattern}", text, re.MULTILINE)
    if not match:
        raise ValueError(f"No total_wall_time in {path}")
    hours, minutes, seconds = match.groups()
    return stages, _duration_seconds(hours, minutes, seconds)


def _duration_seconds(hours: str | None, minutes: str | None, seconds: str | None) -> float:
    return float(hours or 0) * 3600 + float(minutes or 0) * 60 + float(seconds or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two measured ColliderLake run summaries")
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    args = parser.parse_args()
    old_path = args.old.expanduser().resolve()
    new_path = args.new.expanduser().resolve()
    if old_path == new_path:
        parser.error("refusing to compare a run summary with itself (same path)")
    if _sha256(old_path) == _sha256(new_path):
        parser.error("refusing to compare run summaries with identical content")
    for label, path in (("old", old_path), ("new", new_path)):
        for note in _notes(path):
            print(f"# {label} {note}")
    old, old_total = _read_summary(args.old)
    new, new_total = _read_summary(args.new)
    print("stage | old (s) | new (s) | speedup | old rows/s | new rows/s")
    print("---|---:|---:|---:|---:|---:")
    for stage in sorted(old.keys() | new.keys()):
        old_seconds, old_rate = old.get(stage, (float("nan"), float("nan")))
        new_seconds, new_rate = new.get(stage, (float("nan"), float("nan")))
        speedup = old_seconds / new_seconds if new_seconds > 0 else float("nan")
        print(
            f"{stage} | {old_seconds:.3f} | {new_seconds:.3f} | {speedup:.3f}x | {old_rate:.2f} | {new_rate:.2f}"
        )
    print(f"end-to-end | {old_total:.3f} | {new_total:.3f} | {old_total / new_total:.3f}x | - | -")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _notes(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().lower().startswith("note:")
    ]


if __name__ == "__main__":
    main()
