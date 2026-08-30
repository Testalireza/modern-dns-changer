"""
Input validation utilities — IPv4, IPv6, DNS-specific helpers.

We deliberately reject anything that is not a syntactically valid IP address
or a recognised special token (e.g. ``dhcp``, ``automatic``). Strings that
look like IPs but have extra whitespace, leading zeros, or non-canonical
forms are normalised to the canonical string form before being passed to
``netsh``.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Iterable

# A trivial "looks like an IP" sniff for early rejection. We always defer to
# ``ipaddress`` for the authoritative check.
_IPV4_LIKE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def is_valid_ipv4(text: str) -> bool:
    """Return True if ``text`` is a syntactically valid IPv4 address."""
    if not text:
        return False
    try:
        ipaddress.IPv4Address(text.strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_valid_ipv6(text: str) -> bool:
    """Return True if ``text`` is a syntactically valid IPv6 address."""
    if not text:
        return False
    try:
        ipaddress.IPv6Address(text.strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_valid_ip(text: str) -> bool:
    """Return True if ``text`` is a valid IPv4 or IPv6 address."""
    if not text:
        return False
    s = text.strip()
    if not s:
        return False
    # ``ipaddress.ip_address`` auto-detects family but we want to avoid
    # Windows-style "::1" being misparsed, so we try the explicit forms.
    return is_valid_ipv4(s) or is_valid_ipv6(s)


def normalize_ip(text: str) -> str:
    """Return the canonical textual form of an IP, or raise ``ValueError``."""
    s = (text or "").strip()
    if not s:
        raise ValueError("empty IP")
    # Strip zone IDs (e.g. fe80::1%12) — netsh can't handle them
    s = s.split("%", 1)[0]
    if is_valid_ipv4(s):
        return str(ipaddress.IPv4Address(s))
    if is_valid_ipv6(s):
        return str(ipaddress.IPv6Address(s))
    raise ValueError(f"not a valid IP address: {text!r}")


def is_valid_dns(value: str) -> bool:
    """Return True if ``value`` is an acceptable DNS server string.

    The string is whitespace-trimmed; an empty string is rejected.
    """
    if value is None:
        return False
    s = value.strip()
    if not s:
        return False
    if _IPV4_LIKE.match(s):
        return is_valid_ipv4(s)
    # Generic check (handles IPv6 too)
    return is_valid_ip(s)


def normalize_dns(value: str) -> str:
    """Return the canonical form of a DNS server string. Raises on invalid."""
    return normalize_ip(value)


def has_duplicates(values: Iterable[str]) -> bool:
    """Return True if any non-empty entries in ``values`` are duplicates."""
    seen: set[str] = set()
    for v in values:
        s = (v or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            return True
        seen.add(key)
    return False


def sanitize_preset_name(name: str) -> str:
    """Trim and validate a preset name.

    Names are allowed to contain most printable characters except characters
    that would corrupt the JSON storage or the on-disk file name. We are
    generous here because the name is never used as a shell argument.
    """
    if name is None:
        raise ValueError("empty name")
    s = name.strip()
    if not s:
        raise ValueError("empty name")
    if len(s) > 64:
        raise ValueError("name too long (max 64 chars)")
    if any(c in s for c in ("\n", "\r", "\t", "\x00")):
        raise ValueError("name contains control characters")
    return s
