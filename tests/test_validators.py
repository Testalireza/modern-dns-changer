"""Unit tests for the validator module.

These tests do not require tkinter or customtkinter and can run in any
Python environment. Run with:

    python -m tests.test_validators
or
    python tests/test_validators.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validators import (
    has_duplicates,
    is_valid_dns,
    is_valid_ip,
    is_valid_ipv4,
    is_valid_ipv6,
    normalize_dns,
    normalize_ip,
    sanitize_preset_name,
)


def test_ipv4() -> None:
    assert is_valid_ipv4("8.8.8.8")
    assert is_valid_ipv4("1.1.1.1")
    assert is_valid_ipv4("192.168.1.1")
    assert is_valid_ipv4("  8.8.8.8  ")  # whitespace tolerated
    assert not is_valid_ipv4("256.1.1.1")
    assert not is_valid_ipv4("8.8.8")
    assert not is_valid_ipv4("8.8.8.8.8")
    assert not is_valid_ipv4("")
    assert not is_valid_ipv4("not an ip")
    assert not is_valid_ipv4("::1")
    print("test_ipv4 OK")


def test_ipv6() -> None:
    assert is_valid_ipv6("::1")
    assert is_valid_ipv6("2001:4860:4860::8888")
    assert is_valid_ipv6("fe80::1")
    assert is_valid_ipv6("2606:4700:4700::1111")
    assert not is_valid_ipv6("8.8.8.8")
    assert not is_valid_ipv6("not::ipv6")
    assert not is_valid_ipv6("")
    print("test_ipv6 OK")


def test_is_valid_ip() -> None:
    assert is_valid_ip("8.8.8.8")
    assert is_valid_ip("::1")
    assert is_valid_ip("2001:4860:4860::8888")
    assert not is_valid_ip("")
    assert not is_valid_ip("hello")
    print("test_is_valid_ip OK")


def test_is_valid_dns() -> None:
    assert is_valid_dns("8.8.8.8")
    assert is_valid_dns("  1.1.1.1  ")
    assert is_valid_dns("2606:4700:4700::1111")
    assert not is_valid_dns("")
    assert not is_valid_dns("not an ip")
    assert not is_valid_dns("999.999.999.999")
    print("test_is_valid_dns OK")


def test_normalize_ip() -> None:
    assert normalize_ip("8.8.8.8") == "8.8.8.8"
    assert normalize_ip("  8.8.8.8  ") == "8.8.8.8"
    assert normalize_ip("0:0:0:0:0:0:0:1") == "::1"
    assert normalize_ip("2001:4860:4860:0000:0000:0000:0000:8888") == "2001:4860:4860::8888"
    # Zone IDs are stripped
    assert normalize_ip("fe80::1%12") == "fe80::1"
    try:
        normalize_ip("not an ip")
    except ValueError:
        pass
    else:
        raise AssertionError("normalize_ip should reject invalid input")
    try:
        normalize_ip("")
    except ValueError:
        pass
    else:
        raise AssertionError("normalize_ip should reject empty input")
    print("test_normalize_ip OK")


def test_normalize_dns() -> None:
    assert normalize_dns("8.8.8.8") == "8.8.8.8"
    assert normalize_dns("::1") == "::1"
    print("test_normalize_dns OK")


def test_has_duplicates() -> None:
    assert not has_duplicates(["8.8.8.8", "1.1.1.1"])
    assert not has_duplicates(["8.8.8.8", ""])
    assert not has_duplicates([])
    assert has_duplicates(["8.8.8.8", "8.8.4.4", "8.8.8.8"])
    assert has_duplicates(["8.8.8.8", "  8.8.8.8  "])  # whitespace-insensitive
    print("test_has_duplicates OK")


def test_sanitize_preset_name() -> None:
    assert sanitize_preset_name("Google DNS") == "Google DNS"
    assert sanitize_preset_name("  Cloudflare  ") == "Cloudflare"
    try:
        sanitize_preset_name("")
    except ValueError:
        pass
    else:
        raise AssertionError("should reject empty name")
    try:
        sanitize_preset_name("name\nwith\nnewlines")
    except ValueError:
        pass
    else:
        raise AssertionError("should reject control chars")
    try:
        sanitize_preset_name("x" * 100)
    except ValueError:
        pass
    else:
        raise AssertionError("should reject too-long name")
    print("test_sanitize_preset_name OK")


def test_is_valid_dns_rejects_invalid_address_categories() -> None:
    # Broadcast / multicast / unspecified are never valid DNS server targets.
    assert not is_valid_dns("0.0.0.0")
    assert not is_valid_dns("255.255.255.255")
    assert not is_valid_dns("224.0.0.1")
    assert not is_valid_dns("ff02::1")
    assert not is_valid_dns("::")
    # Loopback is a legitimate local resolver.
    assert is_valid_dns("127.0.0.1")
    assert is_valid_dns("::1")
    print("test_is_valid_dns_rejects_invalid_address_categories OK")


def test_is_valid_dns_leading_zero_v4_rejected() -> None:
    # Python's ipaddress rejects an IPv4 address with leading zeros since 3.9.5.
    assert not is_valid_dns("01.1.1.1")
    print("test_is_valid_dns_leading_zero_v4_rejected OK")


if __name__ == "__main__":
    test_ipv4()
    test_ipv6()
    test_is_valid_ip()
    test_is_valid_dns()
    test_is_valid_dns_rejects_invalid_address_categories()
    test_is_valid_dns_leading_zero_v4_rejected()
    test_normalize_ip()
    test_normalize_dns()
    test_has_duplicates()
    test_sanitize_preset_name()
    print("\nAll validator tests passed.")
