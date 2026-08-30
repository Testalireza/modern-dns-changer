"""
Lightweight, thread-safe logging for Modern DNS Changer.

* Writes to a rotating file (1 MB, 3 backups).
* Also writes to stderr when running from source.
* Does not log sensitive user data (preset names + DNS IPs only at INFO).
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_LOGGER: logging.Logger | None = None


def setup_logging(file_path: Path, level: int = logging.INFO) -> logging.Logger:
    """Initialise the global logger. Safe to call multiple times."""
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("modern_dns_changer")
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] %(threadName)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler with rotation
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            file_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except (OSError, PermissionError) as exc:
        # If we cannot log to file, fall back to stderr only.
        sys.stderr.write(f"[logger] Cannot open log file {file_path}: {exc}\n")

    # Stderr handler — only if not frozen (in EXE mode there's no console)
    if not getattr(sys, "frozen", False):
        sh = logging.StreamHandler(stream=sys.stderr)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    _LOGGER = logger
    return logger


def get_logger() -> logging.Logger:
    """Return the global logger, initialising with defaults if needed."""
    if _LOGGER is None:
        # Lazy default — caller probably forgot to set up; that's fine.
        return setup_logging(Path("modern_dns_changer.log"))
    return _LOGGER
