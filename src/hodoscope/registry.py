from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from .log import ensure_logging, run_log

ContextProvider = Callable[[], dict[str, Any]]
_registry_lock = threading.RLock()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_value(value: Any) -> Any:
    try:
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): _json_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_value(v) for v in value]
        return {"__type__": type(value).__qualname__, "repr": repr(value)}
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, set):
        return sorted((_json_value(v) for v in value), key=lambda v: _canonical_json(v))
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _git_value(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _git_context() -> dict[str, Any]:
    commit = _git_value("rev-parse", "HEAD")
    branch = _git_value("branch", "--show-current")
    dirty = bool(_git_value("status", "--porcelain"))
    changed = _git_value("status", "--porcelain") or ""
    files = sorted({line[3:].strip() for line in changed.splitlines() if len(line) > 3})
    return {"commit": commit, "branch": branch, "dirty": dirty, "dirty_files": files}


def _environment(prefixes: Iterable[str]) -> dict[str, Any]:
    disk = shutil.disk_usage(Path.cwd())
    env_prefixes = tuple(prefixes)
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "vars": {k: v for k, v in sorted(os.environ.items()) if k.startswith(env_prefixes)},
        "free_disk_gb": disk.free / (1024**3),
        "total_ram_gb": _total_ram_gb(),
    }


def _total_ram_gb() -> float | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total_phys / (1024**3)
        return None
    try:
        return float(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024**3))
    except (AttributeError, OSError, ValueError):
        return None


def run(
    name: str,
    *,
    context_providers: Iterable[ContextProvider] = (),
    env_prefixes: Iterable[str] = (),
    root: str | Path | None = None,
) -> RunContext:
    return RunContext(name, context_providers, env_prefixes, root)


class RunStage(AbstractContextManager):
    def __init__(self, record: RunContext, name: str):
        self.record = record
        self.name = name
        self.rows_out: int | None = None
        self.metrics: dict[str, Any] = {}
        self.started_at = ""
        self._started = 0.0

    def metric(self, name: str, value: Any) -> None:
        self.metrics[name] = _json_value(value)

    def __enter__(self) -> Self:
        if self.record._active_stage is not None:
            raise RuntimeError("a run cannot have nested stages")
        self._started = time.perf_counter()
        self.started_at = _utc_now()
        self.record._active_stage = self
        self.record.data["state"] = "running"
        self.record.data["stages"].append(
            {
                "name": self.name,
                "status": "running",
                "started_at": self.started_at,
                "ended_at": None,
                "duration_s": None,
                "rows_out": None,
                "rows_per_s": None,
                "metrics": {},
            }
        )
        self.record._persist()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        duration = time.perf_counter() - self._started
        item = self.record.data["stages"][-1]
        item.update(
            {
                "status": "failed" if exc_type else "succeeded",
                "ended_at": _utc_now(),
                "duration_s": duration,
                "rows_out": self.rows_out,
                "rows_per_s": (
                    self.rows_out / duration
                    if self.rows_out is not None and duration > 0
                    else None
                ),
                "metrics": _json_value(self.metrics),
            }
        )
        self.record._active_stage = None
        if exc_type:
            self.record.data["state"] = "failed"
            self.record.data["failed_stage"] = self.name
            self.record.data["failure_scope"] = "stage"
            self.record.data["error"] = {"type": exc_type.__qualname__, "message": str(exc)}
        self.record._persist()
        return False


class RunContext(AbstractContextManager):
    def __init__(
        self,
        name: str,
        context_providers: Iterable[ContextProvider],
        env_prefixes: Iterable[str],
        root: str | Path | None,
    ) -> None:
        self.name = name
        self.providers = tuple(context_providers)
        self.env_prefixes = tuple(env_prefixes)
        self.root = Path(root or os.environ.get("HODOSCOPE_ROOT", "hodoscope_data")).expanduser()
        self.run_id = ""
        self.run_dir = Path()
        self.data: dict[str, Any] = {}
        self.artifacts: list[dict[str, Any]] = []
        self._active_stage: RunStage | None = None
        self._log_context = None
        self._abort_reason: str | None = None
        self._closed = False
        self.exit_code: int | None = None

    def __enter__(self) -> Self:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        while True:
            self.run_id = f"{stamp}-{uuid.uuid4().hex[:6]}"
            self.run_dir = self.root / "runs" / self.run_id
            try:
                self.run_dir.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                continue
        self.data = {
            "run_id": self.run_id,
            "name": self.name,
            "state": "started",
            "started_at": _utc_now(),
            "ended_at": None,
            "failed_stage": None,
            "failure_scope": None,
            "abort_reason": None,
            "exit_code": None,
            "git": _git_context(),
            "context": {},
            "context_hashes": {},
            "context_sha256": _sha256_bytes(b"{}"),
            "env": _environment(self.env_prefixes),
            "preflight": None,
            "stages": [],
            "backfilled": False,
        }
        _atomic_json(self.run_dir / "run.json", self.data)
        _atomic_json(self.run_dir / "artifacts.json", self.artifacts)
        (self.run_dir / "log.txt").touch()
        ensure_logging()
        self._log_context = run_log(self.run_dir / "log.txt")
        self._log_context.__enter__()
        self.data["state"] = "running"
        self._persist()
        try:
            contexts: dict[str, Any] = {}
            hashes: dict[str, str] = {}
            for provider in self.providers:
                value = _json_value(provider())
                key = getattr(provider, "__name__", f"provider_{len(contexts)}")
                contexts[key] = value
                hashes[key] = _sha256_bytes(_canonical_json(value).encode("utf-8"))
            canonical_context = _canonical_json(contexts).encode("utf-8")
            self.data["context"] = contexts
            self.data["context_hashes"] = hashes
            self.data["context_sha256"] = _sha256_bytes(canonical_context)
            self._persist()
        except BaseException as exc:
            self.data["state"] = "failed"
            self.data["failure_scope"] = "run"
            self.data["error"] = {"type": type(exc).__qualname__, "message": str(exc)}
            self.data["ended_at"] = _utc_now()
            self._persist()
            self._log_context.__exit__(type(exc), exc, exc.__traceback__)
            self._closed = True
            raise
        return self

    def stage(self, name: str) -> RunStage:
        if self._closed:
            raise RuntimeError("run is already closed")
        return RunStage(self, name)

    def preflight(self, values: dict[str, Any]) -> None:
        self.data["preflight"] = _json_value(values)
        self._persist()

    def abort(self, reason: str) -> None:
        self._abort_reason = reason
        self.data["state"] = "aborted"
        self.data["abort_reason"] = reason
        self.data["ended_at"] = _utc_now()
        self._persist()

    def artifact(self, path: str | Path) -> dict[str, Any]:
        given = Path(path)
        if given.is_dir():
            raise ValueError("artifact() accepts files only; use external() for directories")
        absolute = given.expanduser().resolve()
        item = {
            "path": str(path),
            "absolute_path": str(absolute),
            "cwd": str(Path.cwd()),
            "kind": "file",
            "bytes": absolute.stat().st_size,
            "sha256": _sha256_file(absolute),
        }
        self.artifacts.append(item)
        _atomic_json(self.run_dir / "artifacts.json", self.artifacts)
        return item

    def external(self, path: str | Path, **meta: Any) -> dict[str, Any]:
        given = Path(path)
        absolute = given.expanduser().resolve()
        if not absolute.exists():
            raise FileNotFoundError(absolute)
        item: dict[str, Any] = {
            "path": str(path),
            "absolute_path": str(absolute),
            "cwd": str(Path.cwd()),
            "kind": "directory" if absolute.is_dir() else "file",
            "metadata": _json_value(meta),
        }
        if absolute.is_dir():
            inventory = []
            for child in sorted(p for p in absolute.rglob("*") if p.is_file()):
                inventory.append(
                    {
                        "relpath": child.relative_to(absolute).as_posix(),
                        "bytes": child.stat().st_size,
                        "sha256": _sha256_file(child),
                    }
                )
            item["inventory"] = inventory
        self.artifacts.append(item)
        _atomic_json(self.run_dir / "artifacts.json", self.artifacts)
        return item

    def set_exit_code(self, code: int) -> None:
        self.exit_code = code
        self.data["exit_code"] = code
        self._persist()

    def _persist(self) -> None:
        _atomic_json(self.run_dir / "run.json", self.data)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._closed:
            return False
        self._closed = True
        if self._abort_reason is None:
            if exc_type is not None:
                self.data["state"] = "failed"
                if self.data.get("failure_scope") != "stage":
                    self.data["failure_scope"] = "run"
                    self.data["error"] = {"type": exc_type.__qualname__, "message": str(exc)}
            elif self.exit_code not in (None, 0):
                self.data["state"] = "failed"
                self.data["failure_scope"] = "run"
                self.data["error"] = {"type": "ProcessExit", "message": f"exit code {self.exit_code}"}
            else:
                self.data["state"] = "succeeded"
            self.data["ended_at"] = _utc_now()
            self._persist()
        if self._log_context is not None:
            self._log_context.__exit__(exc_type, exc, tb)
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runs_root(root: str | Path | None = None) -> Path:
    base = Path(root or os.environ.get("HODOSCOPE_ROOT", "hodoscope_data")).expanduser()
    return base / "runs"


def load_record(run_id: str, root: str | Path | None = None) -> dict[str, Any]:
    path = runs_root(root) / run_id / "run.json"
    return json.loads(path.read_text(encoding="utf-8"))


def all_records(root: str | Path | None = None) -> list[dict[str, Any]]:
    records = []
    for path in sorted(runs_root(root).glob("*/run.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return records


def resolve_id(identifier: str, root: str | Path | None = None) -> str:
    record_path = runs_root(root) / identifier / "run.json"
    if record_path.is_file():
        return identifier
    index = (Path(root or os.environ.get("HODOSCOPE_ROOT", "hodoscope_data")) / "tags.json")
    tags = json.loads(index.read_text(encoding="utf-8")) if index.is_file() else {}
    if identifier not in tags:
        raise KeyError(f"no run or tag named {identifier!r}")
    return str(tags[identifier])


def _cross_process_lock(path: Path):
    class Lock:
        def __enter__(self):
            self.handle = path.open("a+b")
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0, os.SEEK_END)
                if self.handle.tell() == 0:
                    self.handle.write(b"\0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
            return self

        def __exit__(self, *_args):
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()

    return Lock()


def add_tag(run_id: str, label: str, root: str | Path | None = None) -> None:
    if not label or any(c.isspace() for c in label):
        raise ValueError("tag must be non-empty and contain no whitespace")
    record = load_record(run_id, root)
    registry_root = Path(root or os.environ.get("HODOSCOPE_ROOT", "hodoscope_data"))
    registry_root.mkdir(parents=True, exist_ok=True)
    index_path = registry_root / "tags.json"
    lock_path = registry_root / ".tags.lock"
    with _registry_lock, _cross_process_lock(lock_path):
        tags = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        if label in tags:
            raise ValueError(f"tag {label!r} already points to run {tags[label]!r}")
        tags[label] = record["run_id"]
        _atomic_json(index_path, tags)
