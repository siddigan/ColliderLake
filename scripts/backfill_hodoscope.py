"""One-off, provenance-first registration of the CL2.0.6/CL2.1.0 evidence."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from src.hodoscope.registry import _atomic_json, add_tag, all_records
from src.utils.paths import data_path, project_root

_DURATION = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s")
_SUMMARY_STAGE = re.compile(
    r"^(\w+)\s+\|\s+(SUCCESS|FAILED|PARTIAL)\s+\|\s+(\S+)\s+\|\s+([\d,]+)(?:\s+\|\s+([\d.]+))?",
    re.MULTILINE,
)
_DONE_STAGE = re.compile(
    r"=== STAGE (\w+) DONE in (\S+) \| batches=(\d+) \| rows_out=([\d,]+) ==="
)


def _seconds(value: str) -> float | None:
    match = _DURATION.fullmatch(value)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return float(hours or 0) * 3600 + float(minutes or 0) * 60 + float(seconds or 0)


def _read_text(path: Path) -> str:
    payload = path.read_bytes()
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        return payload.decode("utf-16")
    return payload.decode("utf-8-sig", errors="replace")


def _tracked(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(project_root()).as_posix()
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative], cwd=project_root(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
        return True
    except (ValueError, OSError, subprocess.CalledProcessError):
        return False


def _source(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    encoding = "utf-16" if payload.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    tracked = _tracked(path)
    ignore_rule = None
    if not tracked:
        try:
            relative = path.resolve().relative_to(project_root()).as_posix()
            ignored = subprocess.run(
                ["git", "check-ignore", "-v", "--", relative],
                cwd=project_root(), capture_output=True, text=True, check=False,
            )
            if ignored.returncode == 0:
                ignore_rule = ignored.stdout.strip()
        except (ValueError, OSError):
            pass
    return {
        "path": str(path), "bytes": path.stat().st_size, "sha256": digest,
        "tracked": tracked, "ignore_rule": ignore_rule, "encoding": encoding,
    }


def _parse(path: Path) -> tuple[list[dict[str, object]], dict[str, str]]:
    text = _read_text(path)
    stages: list[dict[str, object]] = []
    for match in _SUMMARY_STAGE.finditer(text):
        name, status, duration_text, rows_text, _rate = match.groups()
        duration = _seconds(duration_text)
        rows = int(rows_text.replace(",", ""))
        stages.append({
            "name": name,
            "status": "succeeded" if status == "SUCCESS" else "failed",
            "duration_s": duration,
            "rows_out": rows,
            "rows_per_s": rows / duration if duration else None,
            "metrics": {},
            "evidence": {"source": str(path), "rows_per_s_formula": "rows_out / duration_s"},
        })
    if not stages:
        for name, duration_text, batches, rows_text in _DONE_STAGE.findall(text):
            duration = _seconds(duration_text)
            rows = int(rows_text.replace(",", ""))
            stages.append({
                "name": name.lower(), "status": "succeeded", "duration_s": duration,
                "rows_out": rows, "rows_per_s": rows / duration if duration else None,
                "metrics": {"batches": int(batches)},
                "evidence": {"source": str(path), "rows_per_s_formula": "rows_out / duration_s"},
            })
    values: dict[str, str] = {}
    for key in ("dataset_id", "selection_id", "fit_config_id", "workers", "total_wall_time"):
        match = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
        if match:
            values[key] = match.group(1).strip()
    return stages, values


def _register(path: Path, root: Path, label: str) -> str:
    source = _source(path)
    existing_id = None
    for prior in all_records(root):
        evidence = prior.get("evidence", {}).get("source_file", {}).get("value", {})
        if prior.get("backfilled") and evidence.get("path") == str(path):
            if (
                prior.get("evidence", {}).get("stages", {}).get("status") == "sourced"
                and evidence.get("sha256") == source.get("sha256")
                and evidence.get("tracked") == source.get("tracked")
                and evidence.get("ignore_rule") == source.get("ignore_rule")
                and prior.get("evidence", {}).get("commit_tracking", {}).get("status") == "sourced"
            ):
                return str(prior["run_id"])
            existing_id = str(prior["run_id"])
            break
    stages, values = _parse(path)
    now = datetime.now(UTC)
    run_id = existing_id or f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:6]}"
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=bool(existing_id))
    context: dict[str, object] = {key: values[key] for key in values if key in {"dataset_id", "selection_id", "fit_config_id", "workers"}}
    context_bytes = json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
    state = (
        "failed" if any(item["status"] == "failed" for item in stages)
        else "succeeded" if stages
        else "unresolved"
    )
    evidence: dict[str, object] = {
        "source_file": {"status": "sourced", "value": source},
        "stages": {"status": "sourced" if stages else "unresolved", "value": stages or "UNRESOLVED - no stage summary or DONE banner in source"},
        "original_started_at": {"status": "unresolved", "value": "UNRESOLVED - source has no calendar timestamp"},
        "original_commit": {"status": "unresolved", "value": "UNRESOLVED - source does not identify the producing commit"},
        "commit_tracking": {
            "status": "sourced",
            "value": (
                "tracked in Git at backfill time"
                if source["tracked"]
                else f"not tracked by Git; ignore rule evidence: {source['ignore_rule'] or 'no matching ignore rule'}"
            ),
            "source": "git ls-files and git check-ignore -v",
        },
        "run_id": {"status": "derived", "value": run_id, "formula": "UTC backfill timestamp + random six-hex collision suffix"},
        "state": (
            {"status": "derived", "value": state, "formula": "failed if any sourced stage failed; otherwise succeeded"}
            if stages
            else {"status": "unresolved", "value": "UNRESOLVED - no stage statuses available"}
        ),
        "started_at": {"status": "unresolved", "value": "UNRESOLVED - original run timestamp unavailable"},
        "ended_at": {"status": "unresolved", "value": "UNRESOLVED - original run timestamp unavailable"},
        "git": {"status": "unresolved", "value": "UNRESOLVED - historical commit not identified by the source"},
        "environment": {"status": "unresolved", "value": "UNRESOLVED - historical environment not recorded by source"},
        "context_sha256": {"status": "derived", "value": hashlib.sha256(context_bytes).hexdigest(), "formula": "SHA-256 of canonical JSON context"},
    }
    for key in ("dataset_id", "selection_id", "fit_config_id", "workers", "total_wall_time"):
        evidence[key] = (
            {"status": "sourced", "value": values[key], "source": str(path)}
            if key in values
            else {"status": "unresolved", "value": f"UNRESOLVED - {key} absent from {path}"}
        )
    record = {
        "run_id": run_id, "name": label, "state": state,
        "started_at": None, "ended_at": None,
        "failed_stage": next((item["name"] for item in stages if item["status"] == "failed"), None),
        "failure_scope": "stage" if any(item["status"] == "failed" for item in stages) else None,
        "abort_reason": None, "exit_code": None,
        "git": {"commit": None, "branch": None, "dirty": None, "dirty_files": []},
        "context": context, "context_hashes": {},
        "context_sha256": hashlib.sha256(context_bytes).hexdigest(),
        "env": {"python": None, "platform": None, "cpu_count": None, "vars": {}, "free_disk_gb": None, "total_ram_gb": None},
        "preflight": None, "stages": stages, "backfilled": True,
        "backfilled_at_utc": now.isoformat(), "evidence": evidence,
    }
    _atomic_json(run_dir / "run.json", record)
    _atomic_json(run_dir / "artifacts.json", [source])
    (run_dir / "log.txt").write_text(
        f"BACKFILLED from {path}\n" + _read_text(path),
        encoding="utf-8",
    )
    return run_id


def main() -> None:
    root = Path(os.environ.get("HODOSCOPE_ROOT", str(data_path("results"))))
    baseline = data_path("results", "benchmarks", "run_summary_baseline_cl206_backfilled.txt")
    sources = [
        (baseline, "historical:CL2.0.6-baseline"),
        (project_root() / "run_full.log", "historical:full-campaign-log"),
        (project_root() / "run_gold.log", "historical:gold-stage-log"),
        (project_root() / "run_fit.log", "historical:fit-stage-log"),
        (data_path("results", "benchmarks", "run_summary_20261028T100037.714950Z.txt"), "historical:CL2.1.0-benchmark"),
    ]
    registered: dict[str, str] = {}
    for path, label in sources:
        if path.is_file():
            registered[label] = _register(path, root, label)
        else:
            print(f"UNRESOLVED - source absent: {path}")
    baseline_id = registered.get("historical:CL2.0.6-baseline")
    if baseline_id:
        try:
            add_tag(baseline_id, "baseline-cl206", root)
        except ValueError as exc:
            if "already points" not in str(exc):
                raise
    print(json.dumps(registered, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
