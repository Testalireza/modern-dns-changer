"""Tests for the built-in DNS presets and close-behaviour migration rules."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from presets import (
    DEFAULT_PRESET_NAMES,
    DEFAULT_PRESETS,
    is_builtin_name,
    merge_user_presets,
)
from storage import (
    load_presets,
    load_settings,
    load_user_presets,
    save_presets,
)
from validators import is_valid_dns


def test_all_default_presets_exist_in_expected_order() -> None:
    expected = [
        "Anti EA Sanction", "Cloudflare", "Google", "OpenDNS", "Quad9",
        "Level3 DNS", "DNSPod", "Begzar", "Jetping",
    ]
    assert list(DEFAULT_PRESETS.keys()) == expected
    print("test_all_default_presets_exist_in_expected_order OK")


def test_default_preset_addresses() -> None:
    expected = {
        "Anti EA Sanction": ("94.183.166.199", "94.183.166.195"),
        "Cloudflare": ("1.1.1.1", "1.0.0.1"),
        "Google": ("8.8.8.8", "8.8.4.4"),
        "OpenDNS": ("208.67.222.222", "208.67.220.220"),
        "Quad9": ("9.9.9.9", "149.112.112.112"),
        "Level3 DNS": ("4.2.2.1", "4.2.2.2"),
        "DNSPod": ("119.29.29.29", "182.254.116.116"),
        "Begzar": ("185.55.226.26", "185.55.225.25"),
        "Jetping": ("78.47.226.179", "188.245.125.175"),
    }
    for name, (primary, secondary) in expected.items():
        assert DEFAULT_PRESETS[name]["primary"] == primary
        assert DEFAULT_PRESETS[name]["secondary"] == secondary
    print("test_default_preset_addresses OK")


def test_default_presets_pass_validation() -> None:
    for name, dns in DEFAULT_PRESETS.items():
        assert is_valid_dns(dns["primary"]), f"{name} primary invalid"
        assert is_valid_dns(dns["secondary"]), f"{name} secondary invalid"
    print("test_default_presets_pass_validation OK")


def test_merge_preserves_existing_user_presets() -> None:
    user = {
        "My Home DNS": {"primary": "10.0.0.1", "secondary": ""},
        "Gaming DNS": {"primary": "1.1.1.1", "secondary": "8.8.8.8"},
        "Work DNS": {"primary": "9.9.9.9", "secondary": ""},
    }
    merged = merge_user_presets(user)
    # Built-ins are first.
    first_n = list(merged.keys())[:len(DEFAULT_PRESET_NAMES)]
    assert first_n == list(DEFAULT_PRESET_NAMES)
    # User presets exist and are untouched.
    for name, dns in user.items():
        assert merged[name] == dns, f"user preset {name} was changed"
    print("test_merge_preserves_existing_user_presets OK")


def test_merge_user_override_does_not_duplicate() -> None:
    # A legacy user Cloudflare preset wins over the built-in one, and stays at
    # the built-in list position without creating a second "Cloudflare".
    user = {"Cloudflare": {"primary": "1.2.3.4", "secondary": "5.6.7.8"}}
    merged = merge_user_presets(user)
    assert list(merged.keys()).count("Cloudflare") == 1
    assert merged["Cloudflare"] == {"primary": "1.2.3.4", "secondary": "5.6.7.8"}
    print("test_merge_user_override_does_not_duplicate OK")


def test_is_builtin_name() -> None:
    assert is_builtin_name("Cloudflare")
    assert is_builtin_name("Begzar")
    assert not is_builtin_name("My Home DNS")
    print("test_is_builtin_name OK")


def test_save_presets_preserves_builtin_named_user_preset() -> None:
    """A legacy user preset named ``Cloudflare`` must survive a save."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "presets.json"
        user = {
            "Custom": {"primary": "8.8.8.8", "secondary": ""},
            "Cloudflare": {"primary": "1.2.3.4", "secondary": "5.6.7.8"},
        }
        assert save_presets(p, user)
        user_loaded = load_user_presets(p)
        assert user_loaded == user
        # On load, the user override keeps the built-in position and no
        # duplicate "Cloudflare" is created.
        loaded = load_presets(p)
        assert list(loaded.keys()).count("Cloudflare") == 1
        assert loaded["Cloudflare"] == {"primary": "1.2.3.4", "secondary": "5.6.7.8"}
        print("test_save_presets_preserves_builtin_named_user_preset OK")


def test_close_behavior_default_is_tray() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "settings.json"
        settings = load_settings(p)
        assert settings["close_behavior"] == "tray"
        assert settings["minimize_to_tray"] is True
    print("test_close_behavior_default_is_tray OK")


def test_close_behavior_migrates_old_settings() -> None:
    import json
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "settings.json"
        # Old file with only minimize_to_tray (no close_behavior).
        p.write_text(json.dumps({"theme": "dark", "language": "en",
                                 "minimize_to_tray": False}), encoding="utf-8")
        settings = load_settings(p)
        assert settings["close_behavior"] == "exit"
        assert settings["minimize_to_tray"] is False
        assert settings["theme"] == "dark"
        assert settings["language"] == "en"
    print("test_close_behavior_migrates_old_settings OK")


def test_close_behavior_new_key_wins() -> None:
    import json
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "settings.json"
        p.write_text(json.dumps({"close_behavior": "exit",
                                 "minimize_to_tray": True}), encoding="utf-8")
        settings = load_settings(p)
        assert settings["close_behavior"] == "exit"
        assert settings["minimize_to_tray"] is False
    print("test_close_behavior_new_key_wins OK")


if __name__ == "__main__":
    test_all_default_presets_exist_in_expected_order()
    test_default_preset_addresses()
    test_default_presets_pass_validation()
    test_merge_preserves_existing_user_presets()
    test_merge_user_override_does_not_duplicate()
    test_is_builtin_name()
    test_save_presets_preserves_builtin_named_user_preset()
    test_close_behavior_default_is_tray()
    test_close_behavior_migrates_old_settings()
    test_close_behavior_new_key_wins()
    print("\nAll preset/close-behavior tests passed.")
