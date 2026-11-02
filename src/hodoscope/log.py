from __future__ import annotations

import contextvars
import logging
import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER_NAME = "colliderlake"
_logger = logging.getLogger(LOGGER_NAME)
_configured = False
_log_path: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "hodoscope_run_log_path", default=None
)
_file_lock = threading.RLock()


class _RunFileHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        path = _log_path.get()
        if path is None:
            return
        message = self.format(record)
        with _file_lock, path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(message + "\n")


class _FlushingStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def configure_logging(
    *, quiet: bool = False, verbose: bool = False, log_path: str | Path | None = None
) -> None:
    """Configure idempotent stderr and context-local per-run UTF-8 sinks."""
    global _configured
    if not _configured:
        _logger.setLevel(logging.INFO)
        _logger.propagate = False
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(stage)s | %(message)s", datefmt="%H:%M:%S"
        )
        stream = next(
            (h for h in _logger.handlers if isinstance(h, _FlushingStreamHandler)), None
        )
        if stream is None:
            stream = _FlushingStreamHandler(sys.stderr)
            _logger.addHandler(stream)
        stream.setFormatter(formatter)
        run_file = next((h for h in _logger.handlers if isinstance(h, _RunFileHandler)), None)
        if run_file is None:
            run_file = _RunFileHandler()
            _logger.addHandler(run_file)
        run_file.setFormatter(formatter)
        _configured = True

    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        configured = os.environ.get("HODOSCOPE_LOG", os.environ.get("COLLIDERLAKE_LOG", "INFO")).upper()
        level = getattr(logging, configured, logging.INFO)
        if not isinstance(level, int):
            level = logging.INFO
    _logger.setLevel(level)
    if log_path is not None:
        _log_path.set(Path(log_path))


def ensure_logging() -> None:
    if not _configured:
        configure_logging()


@contextmanager
def run_log(path: str | Path) -> Iterator[None]:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    token = _log_path.set(resolved)
    try:
        yield
    finally:
        _log_path.reset(token)


def get_logger(stage: str) -> logging.LoggerAdapter:
    if not _configured:
        configure_logging()
    return logging.LoggerAdapter(_logger, {"stage": stage.upper()})


def safe_log(logger: logging.LoggerAdapter, level: int, message: str, *args: Any) -> None:
    """Compatibility name; logging errors propagate instead of hiding failures."""
    logger.log(level, message, *args)


@dataclass
class StageCounters:
    batches: int = 0
    rows_out: int = 0
    events: int = 0
    muons: int = 0
    files: int = 0


_stage_counters: dict[str, StageCounters] = {}


def begin_stage(stage: str) -> None:
    _stage_counters[stage] = StageCounters()


def add_stage_stats(
    stage: str,
    *,
    batches: int = 0,
    rows_out: int = 0,
    events: int = 0,
    muons: int = 0,
    files: int = 0,
) -> None:
    current = _stage_counters.setdefault(stage, StageCounters())
    current.batches += batches
    current.rows_out += rows_out
    current.events += events
    current.muons += muons
    current.files += files


def stage_stats(stage: str) -> StageCounters:
    return _stage_counters.get(stage, StageCounters())


def reset_stage_stats() -> None:
    _stage_counters.clear()


def format_duration(seconds: float) -> str:
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    total = int(seconds)
    minutes, remaining = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{remaining:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown size"
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return "unknown size"
