"""
JSON storage with atomic writes and schema migration.
"""
from __future__ import annotations

import ipaddress
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from logger import get_logger
from validators import is_valid_dns, normalize_dns, sanitize_preset_name

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


def _coerce_bool(value: Any, default: bool = True) -> bool:
    """Coerce common JSON/bool/string representations into a real ``bool``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "off", "no", "")
    return default


def _coerce_int(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def sanitize_settings(raw: Any) -> dict:
    """Return a clean settings dict with defaults for every key/value.

    This is the single point that protects the UI from malformed, missing or
    invalid persisted settings (``null`` theme, a boolean stored as a string,
    an accidental non-dict settings file, etc.).
    """
    if not isinstance(raw, dict):
        raw = {}

    merged = dict(DEFAULT_SETTINGS)
    merged.update(raw)

    theme = merged.get("theme")
    if theme not in ("dark", "light"):
        theme = DEFAULT_SETTINGS["theme"]
    language = merged.get("language")
    if language not in ("en", "fa"):
        language = DEFAULT_SETTINGS["language"]

    def _text(key: str) -> str:
        val = merged.get(key, DEFAULT_SETTINGS.get(key, ""))
        return val if isinstance(val, str) else ""

    hotkey = _text("hotkey").strip() or DEFAULT_SETTINGS["hotkey"]
    window_geometry = _text("window_geometry").strip() or DEFAULT_SETTINGS["window_geometry"]

    return {
        "theme": theme,
        "language": language,
        "hotkey": hotkey,
        "preset_a": _text("preset_a"),
        "preset_b": _text("preset_b"),
        "minimize_to_tray": _coerce_bool(merged.get("minimize_to_tray"), True),
        "last_adapter": _text("last_adapter"),
        "window_geometry": window_geometry,
        "schema_version": _coerce_int(merged.get("schema_version"), 1),
    }


def sanitize_presets(raw: Any) -> dict:
    """Return a clean presets dict.

    Invalid entries are dropped instead of being passed to the UI, which would
    otherwise crash on ``entry.get(...)`` or send invalid DNS values to
    ``netsh``.
    """
    if not isinstance(raw, dict):
        return {}
    clean: dict = {}
    for name, value in raw.items():
        try:
            clean_name = sanitize_preset_name(str(name))
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        primary = (value.get("primary") or "").strip()
        secondary = (value.get("secondary") or "").strip()
        if not primary or not is_valid_dns(primary):
            continue
        try:
            primary = normalize_dns(primary)
        except ValueError:
            continue
        if secondary and is_valid_dns(secondary):
            try:
                secondary = normalize_dns(secondary)
            except ValueError:
                secondary = ""
        else:
            secondary = ""
        if primary.lower() == secondary.lower():
            secondary = ""
        if secondary:
            try:
                if ipaddress.ip_address(primary).version != ipaddress.ip_address(secondary).version:
                    continue  # mixed IPv4/IPv6 presets are not supported
            except (ipaddress.AddressValueError, ValueError):
                continue
        clean[clean_name] = {"primary": primary, "secondary": secondary}
    return clean


def load_presets(path: Path) -> dict:
    return sanitize_presets(load_json(path, DEFAULT_PRESETS))


def save_presets(path: Path, presets: dict) -> bool:
    return save_json(path, sanitize_presets(presets))


def load_settings(path: Path) -> dict:
    raw = load_json(path, dict(DEFAULT_SETTINGS))
    return sanitize_settings(raw)


def save_settings(path: Path, settings: dict) -> bool:
    return save_json(path, sanitize_settings(settings))
