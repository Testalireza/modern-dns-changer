"""Unit tests for the storage module (atomic JSON, schema migration)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage import (
    DEFAULT_SETTINGS,
    load_json,
    load_presets,
    load_settings,
    save_json,
    save_presets,
)


def test_save_and_load_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.json"
        data = {"a": 1, "b": [1, 2, 3], "c": "string"}
        assert save_json(p, data)
        loaded = load_json(p, {"default": True})
        assert loaded == data
        print("test_save_and_load_json OK")


def test_load_json_returns_default_when_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "missing.json"
        loaded = load_json(p, {"hello": "world"})
        assert loaded == {"hello": "world"}
        print("test_load_json_returns_default_when_missing OK")


def test_load_json_returns_default_on_corrupt_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.json"
        p.write_text("{this is not valid json", encoding="utf-8")
        loaded = load_json(p, {"hello": "world"})
        assert loaded == {"hello": "world"}
        print("test_load_json_returns_default_on_corrupt_file OK")


def test_load_json_type_mismatch_returns_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.json"
        p.write_text("[]", encoding="utf-8")  # JSON list, not dict
        loaded = load_json(p, {"hello": "world"})
        assert loaded == {"hello": "world"}
        print("test_load_json_type_mismatch_returns_default OK")


def test_save_json_atomic_no_partial_file_on_dirty_close() -> None:
    """If the temp file is not on the same filesystem, the replace should
    still work; we just check that save_json creates the file in a sane
    way."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.json"
        save_json(p, {"a": 1})
        assert p.exists()
        # Make sure there are no leftover .tmp files
        leftovers = list(Path(tmp).glob("x.json.*.tmp"))
        assert not leftovers, f"Leftover temp files: {leftovers}"
        print("test_save_json_atomic_no_partial_file_on_dirty_close OK")


def test_settings_migrates_missing_keys() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "settings.json"
        # Old settings file without "language" key
        p.write_text(json.dumps({"theme": "light", "hotkey": "F8"}), encoding="utf-8")
        loaded = load_settings(p)
        # Missing keys are filled with defaults
        for k, v in DEFAULT_SETTINGS.items():
            assert k in loaded, f"Missing key {k} after migration"
        assert loaded["theme"] == "light"
        assert loaded["hotkey"] == "F8"
        assert loaded["language"] == DEFAULT_SETTINGS["language"]
        print("test_settings_migrates_missing_keys OK")


def test_presets_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "presets.json"
        data = {
            "Google": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
            "Cloudflare": {"primary": "1.1.1.1", "secondary": "1.0.0.1"},
        }
        save_presets(p, data)
        loaded = load_presets(p)
        assert loaded == data
        print("test_presets_roundtrip OK")


if __name__ == "__main__":
    test_save_and_load_json()
    test_load_json_returns_default_when_missing()
    test_load_json_returns_default_on_corrupt_file()
    test_load_json_type_mismatch_returns_default()
    test_save_json_atomic_no_partial_file_on_dirty_close()
    test_settings_migrates_missing_keys()
    test_presets_roundtrip()
    print("\nAll storage tests passed.")
