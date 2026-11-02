from __future__ import annotations

import argparse
import hashlib
import os
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
    from src.utils.paths import data_path

    registry_root = Path(os.environ.get("HODOSCOPE_ROOT", str(data_path("results"))))
    old_path = args.old.expanduser().resolve()
    new_path = args.new.expanduser().resolve()
    if _looks_like_hodoscope_record(args.old) and _looks_like_hodoscope_record(args.new):
        from src.hodoscope.cli import _diff

        if "HODOSCOPE_ROOT" not in os.environ:
            record_roots = [_record_root(args.old), _record_root(args.new)]
            if record_roots[0] is not None and record_roots[0] == record_roots[1]:
                registry_root = record_roots[0]

        old_id = _record_identifier(args.old)
        new_id = _record_identifier(args.new)
        raise SystemExit(_diff(old_id, new_id, registry_root))
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


def _looks_like_hodoscope_record(value: Path) -> bool:
    if value.is_dir() and (value / "run.json").is_file():
        return True
    if value.name == "run.json" and value.is_file():
        return True
    if not value.exists():
        from src.hodoscope.registry import resolve_id
        from src.utils.paths import data_path

        try:
            root = Path(os.environ.get("HODOSCOPE_ROOT", str(data_path("results"))))
            resolve_id(value.name, root)
            return True
        except (KeyError, OSError, ValueError):
            return False
    return False


def _record_identifier(value: Path) -> str:
    path = value.expanduser()
    if path.is_file() and path.name == "run.json":
        return path.parent.name
    if path.is_dir() and (path / "run.json").is_file():
        return path.name
    return str(value)


def _record_root(value: Path) -> Path | None:
    path = value.expanduser()
    if path.is_file() and path.name == "run.json":
        return path.parent.parent.parent
    if path.is_dir() and (path / "run.json").is_file():
        return path.parent.parent
    return None


if __name__ == "__main__":
    main()
