"""Unit tests for the storage module (atomic JSON, schema migration)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from presets import DEFAULT_PRESET_NAMES
from storage import (
    DEFAULT_SETTINGS,
    load_json,
    load_presets,
    load_settings,
    load_user_presets,
    sanitize_presets,
    sanitize_settings,
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
            "My DNS": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
            "Backup DNS": {"primary": "1.1.1.1", "secondary": "1.0.0.1"},
        }
        save_presets(p, data)
        user_loaded = load_user_presets(p)
        assert user_loaded == data
        # The display list also contains the built-in defaults, without
        # overwriting the user's data.
        merged = load_presets(p)
        for name in DEFAULT_PRESET_NAMES:
            assert name in merged
        for k, v in data.items():
            assert merged[k] == v
        print("test_presets_roundtrip OK")


def test_sanitize_settings_coerces_values() -> None:
    raw = {
        "theme": "purple",
        "language": "zz",
        "hotkey": "   ",
        "minimize_to_tray": "false",
        "preset_a": 123,
        "schema_version": "abc",
    }
    out = sanitize_settings(raw)
    assert out["theme"] == "dark"
    assert out["language"] == "en"
    assert out["hotkey"] == "F9"
    assert out["minimize_to_tray"] is False
    assert out["preset_a"] == ""
    assert out["schema_version"] == 1
    print("test_sanitize_settings_coerces_values OK")


def test_sanitize_settings_non_dict_defaults() -> None:
    out = sanitize_settings(["not", "a", "dict"])
    assert out["theme"] == "dark"
    assert out["minimize_to_tray"] is True
    print("test_sanitize_settings_non_dict_defaults OK")


def test_sanitize_presets_drops_invalid_entries() -> None:
    raw = {
        "Good": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
        "Bad dns": {"primary": "not-an-ip", "secondary": ""},
        "Bad type": "8.8.8.8",
        "Mixed families": {"primary": "8.8.8.8", "secondary": "::1"},
        "Duplicate": {"primary": "1.1.1.1", "secondary": "1.1.1.1"},
    }
    out = sanitize_presets(raw)
    assert "Good" in out
    assert out["Good"]["secondary"] == "8.8.4.4"
    assert "Bad dns" not in out
    assert "Bad type" not in out
    assert "Mixed families" not in out
    assert "Duplicate" in out
    assert out["Duplicate"]["secondary"] == ""
    print("test_sanitize_presets_drops_invalid_entries OK")


def test_load_presets_sanitizes_corrupt_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "presets.json"
        p.write_text(json.dumps({"Good": {"primary": "8.8.8.8"}, "X": "bad"}),
                     encoding="utf-8")
        user_loaded = load_user_presets(p)
        assert user_loaded == {"Good": {"primary": "8.8.8.8", "secondary": ""}}
        loaded = load_presets(p)
        assert loaded["Good"] == {"primary": "8.8.8.8", "secondary": ""}
        assert "X" not in loaded
        print("test_load_presets_sanitizes_corrupt_file OK")


if __name__ == "__main__":
    test_save_and_load_json()
    test_load_json_returns_default_when_missing()
    test_load_json_returns_default_on_corrupt_file()
    test_load_json_type_mismatch_returns_default()
    test_save_json_atomic_no_partial_file_on_dirty_close()
    test_settings_migrates_missing_keys()
    test_presets_roundtrip()
    test_sanitize_settings_coerces_values()
    test_sanitize_settings_non_dict_defaults()
    test_sanitize_presets_drops_invalid_entries()
    test_load_presets_sanitizes_corrupt_file()
    print("\nAll storage tests passed.")
