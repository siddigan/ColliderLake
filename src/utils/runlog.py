from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

LOGGER_NAME = "colliderlake"
_logger = logging.getLogger(LOGGER_NAME)
_configured = False


class _FlushingStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
            self.flush()
        except Exception:  # noqa: BLE001
            # Logging must never change the pipeline's control flow.
            return


@dataclass
class StageCounters:
    batches: int = 0
    rows_out: int = 0
    events: int = 0
    muons: int = 0
    files: int = 0


_stage_counters: dict[str, StageCounters] = {}


def configure_logging(*, quiet: bool = False, verbose: bool = False) -> None:
    """Configure the ColliderLake logger once, while allowing level updates."""
    global _configured
    if not _configured:
        _logger.setLevel(logging.INFO)
        _logger.propagate = True
        handler = next((item for item in _logger.handlers if isinstance(item, _FlushingStreamHandler)), None)
        if handler is None:
            handler = _FlushingStreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)s | %(stage)s | %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            _logger.addHandler(handler)
        _configured = True

    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        configured = os.environ.get("COLLIDERLAKE_LOG", "INFO").upper()
        level = getattr(logging, configured, logging.INFO)
        if not isinstance(level, int):
            level = logging.INFO
    _logger.setLevel(level)


def get_logger(stage: str) -> logging.LoggerAdapter:
    if not _configured:
        configure_logging()
    return logging.LoggerAdapter(_logger, {"stage": stage.upper()})


def safe_log(logger: logging.LoggerAdapter, level: int, message: str, *args: Any) -> None:
    try:
        logger.log(level, message, *args)
    except Exception:  # noqa: BLE001
        return


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
    counters = _stage_counters.setdefault(stage, StageCounters())
    counters.batches += batches
    counters.rows_out += rows_out
    counters.events += events
    counters.muons += muons
    counters.files += files


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
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return "unknown size"
