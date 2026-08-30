"""Authoritative built-in DNS presets.

This module is the single source of truth for the presets shipped with the
application.  The UI and storage layer read from here so the values are never
duplicated in presentation or networking code.

Provider names are kept as proper nouns (``Cloudflare``, ``Google``, ...) in
every language.  This keeps the entries stable across translations and makes
hotkey A/B selection and duplicate detection unambiguous.
"""
from __future__ import annotations

from typing import Any

from validators import is_valid_dns, normalize_dns

# Ordered list of built-in presets.  The order here is also the display order
# for the default section of the preset list.
_DEFAULT_PRESET_ROWS: list[tuple[str, str, str]] = [
    ("Anti EA Sanction", "94.183.166.199", "94.183.166.195"),
    ("Cloudflare", "1.1.1.1", "1.0.0.1"),
    ("Google", "8.8.8.8", "8.8.4.4"),
    ("OpenDNS", "208.67.222.222", "208.67.220.220"),
    ("Quad9", "9.9.9.9", "149.112.112.112"),
    ("Level3 DNS", "4.2.2.1", "4.2.2.2"),
    ("DNSPod", "119.29.29.29", "182.254.116.116"),
    # Begzar (begzar.ir): 185.55.226.26 primary, 185.55.225.25 secondary.
    ("Begzar", "185.55.226.26", "185.55.225.25"),
    ("Jetping", "78.47.226.179", "188.245.125.175"),
]


def _build_default_presets() -> dict[str, dict[str, str]]:
    """Build and validate the built-in presets dict (preserving order)."""
    out: dict[str, dict[str, str]] = {}
    for name, primary, secondary in _DEFAULT_PRESET_ROWS:
        if not is_valid_dns(primary) or not is_valid_dns(secondary):
            raise ValueError(f"built-in preset {name!r} contains an invalid DNS address")
        out[name] = {
            "primary": normalize_dns(primary),
            "secondary": normalize_dns(secondary),
        }
    return out


#: Ordered ``{name: {"primary": ..., "secondary": ...}}`` of built-in presets.
DEFAULT_PRESETS: dict[str, dict[str, str]] = _build_default_presets()

#: Names of the built-in presets (used by the UI to distinguish read-only
#: entries and by storage when computing which entries are user-created).
DEFAULT_PRESET_NAMES: tuple[str, ...] = tuple(DEFAULT_PRESETS.keys())


def is_builtin_name(name: str) -> bool:
    """Return True if ``name`` is a built-in preset name."""
    return name in DEFAULT_PRESETS


def merge_user_presets(user_presets: dict[str, Any]) -> dict[str, Any]:
    """Return built-in presets merged with ``user_presets``, in display order.

    * Built-in presets are listed first, in the defined order.
    * A user preset whose name matches a built-in name *overrides* that
      built-in entry (existing user data is never destroyed) instead of being
      duplicated.
    * Remaining user presets are appended in their existing stored order.

    ``user_presets`` must already be sanitized by the storage layer.
    """
    merged: dict[str, Any] = dict(DEFAULT_PRESETS)
    for name, value in (user_presets or {}).items():
        if name in merged:
            # Keep the user's entry at the built-in position so ordering stays
            # stable, but never lose the user's saved values.
            merged[name] = value
        else:
            merged[name] = value
    return merged
