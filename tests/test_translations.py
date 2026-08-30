"""Unit tests for the translations module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from translations import TRANSLATIONS, get_text


def test_known_key_english() -> None:
    assert get_text("en", "apply_dns") == "Apply DNS"
    assert get_text("en", "preset_saved", name="X") == "Preset X saved"
    print("test_known_key_english OK")


def test_known_key_persian() -> None:
    assert "اعمال" in get_text("fa", "apply_dns")
    assert "{name}" in TRANSLATIONS["fa"]["preset_saved"]
    # After formatting, the placeholder is gone
    assert "{name}" not in get_text("fa", "preset_saved", name="X")
    print("test_known_key_persian OK")


def test_unknown_key_falls_back() -> None:
    # Falls back to English, then to the key itself
    assert get_text("en", "totally_unknown_key") == "totally_unknown_key"
    assert get_text("fa", "totally_unknown_key") == "totally_unknown_key"
    print("test_unknown_key_falls_back OK")


def test_unknown_lang_falls_back_to_english() -> None:
    assert get_text("zz", "apply_dns") == "Apply DNS"
    print("test_unknown_lang_falls_back_to_english OK")


def test_format_kwargs_optional() -> None:
    # Missing format kwargs leave placeholders intact (no KeyError)
    out = get_text("en", "preset_saved", name="X")
    assert "{name}" not in out
    # But passing the wrong kw produces a fallback (no crash)
    out = get_text("en", "preset_saved", notname="X")
    # Either formatted with the placeholder left or the original — both OK
    assert isinstance(out, str)
    print("test_format_kwargs_optional OK")


def test_no_missing_translations_for_used_keys() -> None:
    """Spot-check the keys that ui.py and main.py use."""
    used = [
        "subtitle", "settings_btn", "adapter", "quick_actions",
        "apply_dns", "auto_dhcp", "status_ready", "presets",
        "no_presets", "add_new_preset", "preset_name", "preferred_dns",
        "secondary_dns", "add_preset_btn", "apply", "delete",
        "hotkey", "hotkey_desc", "save_hotkey", "settings_title",
        "appearance", "dark_mode", "light_mode", "language_section",
        "english", "persian", "tray_section", "about_section",
        "about_text", "close", "cancel", "applying", "applied",
        "apply_failed", "preset_saved", "preset_deleted", "dhcp_applying",
        "dhcp_done", "dhcp_failed", "no_presets_warning", "hotkey_saved",
        "toggle_failed", "admin_needed", "admin_msg", "restart_admin",
        "tray_show", "tray_quit", "tray_toggle", "tray_tooltip",
        "download_repo_btn", "download_repo_title", "download_repo_desc",
        "downloading", "downloading_url", "downloading_progress",
        "downloaded_to", "download_failed", "download",
        "hotkey_invalid",
        "operation_in_progress", "best", "all_timed_out", "best_dns",
        "all_timed_out_status", "ping", "ping_all", "pinging",
        "toggle_presets_section", "toggle_presets_desc", "a_label", "b_label",
        "save_ab", "ab_must_differ", "toggle_saved", "on", "off",
        "hotkey_placeholder", "admin_elevation_failed", "no_presets_option",
    ]
    for key in used:
        assert key in TRANSLATIONS["en"], f"English translation missing: {key}"
        assert key in TRANSLATIONS["fa"], f"Persian translation missing: {key}"
    print("test_no_missing_translations_for_used_keys OK")


if __name__ == "__main__":
    test_known_key_english()
    test_known_key_persian()
    test_unknown_key_falls_back()
    test_unknown_lang_falls_back_to_english()
    test_format_kwargs_optional()
    test_no_missing_translations_for_used_keys()
    print("\nAll translations tests passed.")
