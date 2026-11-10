"""Export cited Hodoscope run records with path-only privacy sanitization."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

DEFAULT_RUN_IDS = (
    "20261110T084009.385033Z-88b429",
    "20261110T084042.916422Z-1e921b",
    "20261110T084118.746168Z-fb8cb4",
    "20261110T084155.199631Z-a027f9",
    "20261110T084244.373337Z-ec287e",
    "20261110T084332.907829Z-90ca89",
    "20261110T082043.046113Z-e9f922",
    "20261110T080408.893920Z-e75d65",
    "20261110T000101.653408Z-eed7ca",
)
PATH_FIELDS = {
    "data_root", "path", "absolute_path", "cwd", "temp_directory", "temp_dir",
    "temp_path", "spill_dir", "spill_path", "artifact_path",
}
def _absolute_parts(value: str) -> tuple[str, ...] | None:
    win = PureWindowsPath(value)
    if win.is_absolute():
        return tuple(win.parts)
    posix = PurePosixPath(value)
    if posix.is_absolute():
        return tuple(posix.parts)
    return None


def _portable_path(value: str) -> str:
    parts = _absolute_parts(value)
    if parts is None:
        return value
    folded = [part.casefold().rstrip("\\/") for part in parts]
    for index in range(len(folded) - 1):
        if folded[index] == "colliderlake" and folded[index + 1] == "data":
            tail = [part for part in parts[index + 1:] if part not in ("\\", "/")]
            return "<data_root>" + ("/" + "/".join(tail[1:]) if len(tail) > 1 else "")
    for index, part in enumerate(folded):
        if part == "temp" or (part == "local" and "appdata" in folded[:index]):
            tail = [p for p in parts[index + 1:] if p not in ("\\", "/")]
            basename = tail[-1] if tail else ""
            return "<tmp>" + ("/" + basename if basename else "")
    # Remaining absolute machine paths are private machine-local locations.
    tail = [part for part in parts if part not in ("\\", "/")]
    basename = tail[-1] if tail else ""
    return "<tmp>" + ("/" + basename if basename else "")


def _sanitize_summary(value: str) -> str:
    output = []
    for line in value.splitlines():
        match = re.match(r"^(\s*(?:results|dq_report)\s*:\s*)(.*)$", line, re.IGNORECASE)
        output.append(match.group(1) + _portable_path(match.group(2)) if match else line)
    return "\n".join(output) + ("\n" if value.endswith("\n") else "")


def sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    def visit(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            if key == "vars":
                return {
                    name: _portable_path(item) if isinstance(item, str) and _absolute_parts(item) else item
                    for name, item in value.items()
                }
            return {name: visit(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [visit(item, key) for item in value]
        if isinstance(value, str):
            if key == "summary":
                return _sanitize_summary(value)
            if key.casefold() in PATH_FIELDS or key.casefold().endswith("_path"):
                return _portable_path(value)
        return value

    return visit(record)


def export_runs(
    run_ids: tuple[str, ...],
    registry_root: str | Path = "data/results",
    output_root: str | Path = "docs/results/runs",
    *,
    refresh: bool = False,
) -> list[str]:
    source_root, destination_root = Path(registry_root), Path(output_root)
    report: list[str] = []
    for run_id in run_ids:
        source = source_root / "runs" / run_id
        destination = destination_root / run_id
        outputs = {
            "run.json": json.dumps(
                sanitize_record(json.loads((source / "run.json").read_text(encoding="utf-8"))),
                indent=2, sort_keys=True, ensure_ascii=False,
            ) + "\n",
            "run_summary.txt": _sanitize_summary(
                (source / "run_summary.txt").read_text(encoding="utf-8")
            ),
        }
        for name, text in outputs.items():
            target = destination / name
            data = text.encode("utf-8")
            if target.is_file():
                old = target.read_bytes()
                if old == data:
                    report.append(f"unchanged {target}")
                    continue
                if not refresh:
                    raise RuntimeError(
                        f"{target} differs from source; rerun with --refresh to replace it"
                    )
                old_hash, new_hash = hashlib.sha256(old).hexdigest(), hashlib.sha256(data).hexdigest()
                report.append(f"refreshed {target}: {old_hash} -> {new_hash}")
            else:
                report.append(f"created {target} sha256={hashlib.sha256(data).hexdigest()}")
            destination.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_ids", nargs="*", default=list(DEFAULT_RUN_IDS))
    parser.add_argument("--registry", default="data/results")
    parser.add_argument("--output", default="docs/results/runs")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    for line in export_runs(tuple(args.run_ids), args.registry, args.output, refresh=args.refresh):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
