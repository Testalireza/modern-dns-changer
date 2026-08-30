"""
JSON storage with atomic writes and schema migration.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from logger import get_logger

# Thread-safe storage
_LOCKS: dict[str, threading.Lock] = {}
_GLOBAL_LOCK = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _GLOBAL_LOCK:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def load_json(path: Path, default: Any) -> Any:
    """Load a JSON file. Returns ``default`` if the file does not exist or
    cannot be parsed."""
    log = get_logger()
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, type(default)):
            log.warning("load_json: type mismatch for %s (got %s, expected %s); using default",
                        path, type(data).__name__, type(default).__name__)
            return default
        return data
    except (OSError, json.JSONDecodeError) as exc:
        log.error("load_json: failed to read %s: %s", path, exc)
        return default


def save_json(path: Path, data: Any) -> bool:
    """Atomically write ``data`` to ``path`` as JSON. Returns True on success."""
    log = get_logger()
    lock = _lock_for(path)
    with lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write to a temp file in the same directory, then atomically replace
            fd, tmp_path = tempfile.mkstemp(
                prefix=path.name + ".",
                suffix=".tmp",
                dir=str(path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                os.replace(tmp_path, path)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return True
        except (OSError, TypeError, ValueError) as exc:
            log.error("save_json: failed to write %s: %s", path, exc)
            return False


# Defaults ----------------------------------------------------------------

DEFAULT_PRESETS: dict = {}

DEFAULT_SETTINGS: dict = {
    "theme": "dark",
    "language": "en",
    "hotkey": "F9",
    "preset_a": "",
    "preset_b": "",
    "minimize_to_tray": True,
    "last_adapter": "",
    "window_geometry": "800x580",
    "schema_version": 1,
}


def load_presets(path: Path) -> dict:
    return load_json(path, DEFAULT_PRESETS)


def save_presets(path: Path, presets: dict) -> bool:
    return save_json(path, presets)


def load_settings(path: Path) -> dict:
    raw = load_json(path, dict(DEFAULT_SETTINGS))
    if not isinstance(raw, dict):
        raw = dict(DEFAULT_SETTINGS)
    # Backwards compatibility / key defaults
    merged = dict(DEFAULT_SETTINGS)
    merged.update(raw)
    return merged


def save_settings(path: Path, settings: dict) -> bool:
    return save_json(path, settings)
