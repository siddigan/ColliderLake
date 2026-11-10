from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .log import configure_logging, get_logger
from .registry import add_tag, all_records, load_record, move_tag, resolve_id, run, runs_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hodo", description="Hodoscope run recorder")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="List recorded runs")
    listing.add_argument("--limit", type=int, default=50)

    show = commands.add_parser("show", help="Show a run or tag")
    show.add_argument("identifier")

    tag = commands.add_parser("tag", help="Assign a unique label to a run")
    tag.add_argument("identifier")
    tag.add_argument("label")
    tag.add_argument("--move", action="store_true", help="move an existing tag with a guard")
    tag.add_argument("--expected-current", help="required current run ID when moving a tag")

    diff = commands.add_parser("diff", help="Compare two run records")
    diff.add_argument("old")
    diff.add_argument("new")

    sql = commands.add_parser("sql", help="Query recorded run JSON with DuckDB")
    sql.add_argument("query")

    wrap = commands.add_parser("wrap", help="Record an arbitrary command")
    wrap.add_argument("--name", default="wrapped-command")
    wrap.add_argument("command_line", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if args.command == "list":
        _list_runs(args.limit)
    elif args.command == "show":
        _show_run(args.identifier)
    elif args.command == "tag":
        run_id = resolve_id(args.identifier)
        if args.move:
            if not args.expected_current:
                raise SystemExit("hodo tag --move requires --expected-current RUN_ID")
            move_tag(run_id, args.label, args.expected_current)
        else:
            if args.expected_current:
                raise SystemExit("--expected-current is only valid with --move")
            add_tag(run_id, args.label)
    elif args.command == "diff":
        return _diff(args.old, args.new)
    elif args.command == "sql":
        _sql(args.query)
    elif args.command == "wrap":
        return _wrap(args.name, args.command_line)
    return 0


def _record_duration(record: dict[str, Any]) -> float | None:
    values = [s.get("duration_s") for s in record.get("stages", [])]
    valid = [v for v in values if isinstance(v, (int, float))]
    return float(sum(valid)) if valid else None


def _display_state(record: dict[str, Any]) -> str:
    state = record.get("state", "unknown")
    if state in (None, "unknown", "unresolved"):
        return "UNKNOWN"
    return "INTERRUPTED" if state in ("started", "running") else str(state).upper()


def _list_runs(limit: int) -> None:
    registry = Path(os.environ.get("HODOSCOPE_ROOT", "hodoscope_data"))
    tag_path = registry / "tags.json"
    tags = json.loads(tag_path.read_text(encoding="utf-8")) if tag_path.is_file() else {}
    tags_by_run: dict[str, list[str]] = {}
    for label, run_id in tags.items():
        tags_by_run.setdefault(run_id, []).append(label)
    records = sorted(all_records(), key=lambda x: x.get("run_id", ""), reverse=True)[:limit]
    print("run_id | date | state | total_time_s | commit | context | backfilled | tags")
    print("---|---|---|---:|---|---|---|---")
    for item in records:
        commit = (item.get("git", {}).get("commit") or "unknown")[:8]
        context_hash = (item.get("context_sha256") or "")[:12]
        display = f"BACKFILLED/{_display_state(item)}" if item.get("backfilled") else _display_state(item)
        print(
            f"{item.get('run_id')} | {item.get('started_at') or 'date unresolved'} | {display} | "
            f"{_record_duration(item)} | {commit} | {context_hash} | "
            f"{item.get('backfilled', False)} | {', '.join(tags_by_run.get(item.get('run_id'), []))}"
        )


def _show_run(identifier: str) -> None:
    run_id = resolve_id(identifier)
    record = load_record(run_id)
    record["display_state"] = _display_state(record)
    if record.get("backfilled"):
        print("BACKFILLED HISTORICAL RECORD — source evidence and unresolved fields follow")
    if record["display_state"] == "INTERRUPTED":
        print("INTERRUPTED (derived from persisted state=running; record was not rewritten)")
    print(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False))
    artifacts_path = runs_root() / run_id / "artifacts.json"
    if artifacts_path.is_file():
        print("artifacts:")
        print(artifacts_path.read_text(encoding="utf-8"), end="")


def _code(record: dict[str, Any]) -> dict[str, Any]:
    git = record.get("git", {})
    return {key: git.get(key) for key in ("commit", "branch", "dirty", "dirty_files")}


def _diff(old_id: str, new_id: str, root: str | Path | None = None) -> int:
    old_record = load_record(resolve_id(old_id, root), root)
    new_record = load_record(resolve_id(new_id, root), root)
    old_code, new_code = _code(old_record), _code(new_record)
    old_context, new_context = old_record.get("context", {}), new_record.get("context", {})
    inputs_identical = old_code == new_code and old_context == new_context
    records_identical = old_record == new_record
    print("CODE DELTAS")
    print(f"code: {'identical' if old_code == new_code else 'CHANGED'}")
    if old_code != new_code:
        _print_mapping_diff(old_code, new_code)
    print("CONTEXT DELTAS")
    print(f"context: {'identical' if old_context == new_context else 'CHANGED'}")
    if old_context != new_context:
        _print_mapping_diff(old_context, new_context)
        print("*** ANALYSIS INPUT CONTEXT DELTA above; inspect before interpreting timings. ***")
    if old_record.get("context_hashes") != new_record.get("context_hashes"):
        print("*** CONTEXT HASHES DIFFER. ***")
        print("context hashes: " + repr((old_record.get("context_hashes"), new_record.get("context_hashes"))))
    old_dirty, new_dirty = old_code.get("dirty"), new_code.get("dirty")
    if old_dirty != new_dirty or old_code.get("dirty_files") != new_code.get("dirty_files"):
        print("*** DIRTY-TREE STATE OR FILES DIFFER. ***")

    print("ENVIRONMENT DELTAS")
    old_env, new_env = old_record.get("env", {}), new_record.get("env", {})
    _print_mapping_diff(old_env, new_env)
    env_identical = old_env == new_env

    if records_identical:
        print("records are identical")
    elif inputs_identical:
        print("analysis inputs are identical; records differ")
    else:
        print("neither inputs nor records are identical")
    if records_identical:
        print("Refusing timing comparison: records are identical.", file=sys.stderr)
        return 2
    if inputs_identical and env_identical:
        print("Refusing timing comparison: recorded code and context inputs are identical.", file=sys.stderr)
        return 2

    print("STAGE TIMINGS")
    old_stages = {s["name"]: s for s in old_record.get("stages", [])}
    new_stages = {s["name"]: s for s in new_record.get("stages", [])}
    print("stage | old (s) | new (s) | speedup")
    print("---|---:|---:|---:")
    for name in sorted(old_stages.keys() | new_stages.keys()):
        old_stage, new_stage = old_stages.get(name, {}), new_stages.get(name, {})
        old_s, new_s = old_stage.get("duration_s"), new_stage.get("duration_s")
        valid = (
            old_stage.get("status") == "succeeded"
            and new_stage.get("status") == "succeeded"
            and isinstance(old_s, (int, float)) and old_s > 0
            and isinstance(new_s, (int, float)) and new_s > 0
        )
        speedup = f"{old_s / new_s:.3f}x" if valid else "n/a"
        print(f"{name} | {old_s if old_s is not None else 'n/a'} | {new_s if new_s is not None else 'n/a'} | {speedup}")
    return 0


def _print_mapping_diff(old: dict[str, Any], new: dict[str, Any]) -> None:
    for key in sorted(old.keys() | new.keys()):
        if old.get(key) != new.get(key):
            print(f"{key}: {old.get(key)!r} -> {new.get(key)!r}")


def _sql(query: str) -> None:
    try:
        import duckdb
    except ImportError:
        print("DuckDB is not installed; Hodoscope non-SQL commands remain available.")
        return
    paths = [str(p).replace("\\", "/") for p in runs_root().glob("*/run.json")]
    if not paths:
        print("no run records")
        return
    con = duckdb.connect()
    try:
        escaped = [p.replace("'", "''") for p in paths]
        con.execute(
            "CREATE VIEW runs AS SELECT * FROM read_json_auto(["
            + ",".join(f"'{p}'" for p in escaped)
            + "])"
        )
        result = con.execute(query)
        print(" | ".join(item[0] for item in (result.description or [])))
        for row in result.fetchall():
            print(" | ".join(str(value) for value in row))
    finally:
        con.close()


def _wrap(name: str, command_line: list[str]) -> int:
    command = command_line[1:] if command_line[:1] == ["--"] else command_line
    if not command:
        raise SystemExit("wrap requires -- <command...>")
    logger = get_logger("wrap")
    configure_logging()
    process_lock = threading.Lock()
    try:
        with run(name, env_prefixes=("HODO", "COLLIDERLAKE_")) as record:
            log_path = record.run_dir / "log.txt"
            with record.stage("command"):
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )

                def tee(stream, target) -> None:
                    for line in iter(stream.readline, ""):
                        target.write(line)
                        target.flush()
                        with process_lock, log_path.open("a", encoding="utf-8", newline="\n") as handle:
                            handle.write(line if line.endswith("\n") else line + "\n")
                    stream.close()

                threads = [
                    threading.Thread(target=tee, args=(process.stdout, sys.stdout), daemon=False),
                    threading.Thread(target=tee, args=(process.stderr, sys.stderr), daemon=False),
                ]
                for thread in threads:
                    thread.start()
                code = process.wait()
                for thread in threads:
                    thread.join()
                record.set_exit_code(code)
                logger.info("wrapped command exited with %d", code)
                if code:
                    raise subprocess.CalledProcessError(code, command)
    except subprocess.CalledProcessError as exc:
        return int(exc.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
