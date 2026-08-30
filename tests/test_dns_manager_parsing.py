"""Tests for the pure parsing helpers in dns_manager.

These tests do not invoke any Windows commands — they just verify the
text-parsing logic that is used for the verify-after-apply step.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dns_manager import (
    _dedup,
    _parse_dns_block,
    _parse_dns_servers,
    validate_preset,
)


def test_dedup_basic() -> None:
    assert _dedup(["1.1.1.1", "8.8.8.8"]) == ["1.1.1.1", "8.8.8.8"]
    assert _dedup(["1.1.1.1", "1.1.1.1", "8.8.8.8"]) == ["1.1.1.1", "8.8.8.8"]
    assert _dedup(["", "  ", "8.8.8.8"]) == ["8.8.8.8"]
    assert _dedup([]) == []
    print("test_dedup_basic OK")


def test_parse_dns_block_static() -> None:
    text = """\
Configuration for interface "Wi-Fi"
    DHCP enabled:                         Yes
    IP Address:                           192.168.1.50
    Subnet Prefix:                        192.168.1.0/24 (mask 255.255.255.0)
    Default Gateway:                      192.168.1.1
    Gateway Metric:                       0
    InterfaceMetric:                      35
    Statically Configured DNS Servers:    8.8.8.8
                                        8.8.4.4
    Register with which suffix:           Primary only
"""
    servers, is_dhcp = _parse_dns_block(text)
    assert "8.8.8.8" in servers
    assert "8.8.4.4" in servers
    assert is_dhcp is False
    print("test_parse_dns_block_static OK")


def test_parse_dns_block_inline() -> None:
    text = "Statically Configured DNS Servers:    1.1.1.1"
    servers, is_dhcp = _parse_dns_block(text)
    assert servers == ["1.1.1.1"]
    assert is_dhcp is False
    print("test_parse_dns_block_inline OK")


def test_parse_dns_block_dhcp() -> None:
    text = "DNS Servers configured through DHCP:    192.168.1.1"
    servers, is_dhcp = _parse_dns_block(text)
    assert is_dhcp is True
    print("test_parse_dns_block_dhcp OK")


def test_parse_dns_servers_ipv6() -> None:
    text = """\
Configuration for interface "Wi-Fi"

Configured DNS Servers:    2001:4860:4860::8888
                          2001:4860:4860::8844
Register with which suffix: Primary only
"""
    servers = _parse_dns_servers(text)
    assert "2001:4860:4860::8888" in servers
    assert "2001:4860:4860::8844" in servers
    print("test_parse_dns_servers_ipv6 OK")


def test_parse_dns_servers_inline() -> None:
    text = "Configured DNS Servers: 2001:4860:4860::8888"
    servers = _parse_dns_servers(text)
    assert "2001:4860:4860::8888" in servers
    print("test_parse_dns_servers_inline OK")


def test_parse_dns_block_ipv6_letter_hextet() -> None:
    # IPv6 addresses whose first hextet starts with a letter used to be
    # mis-parsed as a "label: value" line.
    text = (
        "Statically Configured DNS Servers:    fe80::1\n"
        "                                       fd00::2\n"
        "Register with which suffix:            Primary only\n"
    )
    servers, is_dhcp = _parse_dns_block(text)
    assert servers == ["fe80::1", "fd00::2"]
    assert is_dhcp is False
    print("test_parse_dns_block_ipv6_letter_hextet OK")


def test_parse_dns_servers_ipv6_letter_hextet() -> None:
    text = (
        "Configured DNS Servers:                2606:4700:4700::1111\n"
        "                                       fd00::2\n"
        "Register with which suffix:            Primary only\n"
    )
    servers = _parse_dns_servers(text)
    assert "2606:4700:4700::1111" in servers
    assert "fd00::2" in servers
    print("test_parse_dns_servers_ipv6_letter_hextet OK")


def test_parse_dns_servers_inline_first_hextet_not_lost() -> None:
    # The old code split a full IPv6 address on the first ':' and lost the
    # first hextet.
    text = "DNS servers configured for this interface:  2001:4860:4860::8888"
    servers = _parse_dns_servers(text)
    assert "2001:4860:4860::8888" in servers
    print("test_parse_dns_servers_inline_first_hextet_not_lost OK")


def test_validate_preset_happy() -> None:
    name, p, s, errs = validate_preset("Google", "8.8.8.8", "8.8.4.4")
    assert name == "Google"
    assert p == "8.8.8.8"
    assert s == "8.8.4.4"
    assert errs == []
    print("test_validate_preset_happy OK")


def test_validate_preset_ipv6() -> None:
    name, p, s, errs = validate_preset("Cloudflare6", "2606:4700:4700::1111", "")
    assert errs == []
    assert p == "2606:4700:4700::1111"
    assert s == ""
    print("test_validate_preset_ipv6 OK")


def test_validate_preset_missing_primary() -> None:
    name, p, s, errs = validate_preset("X", "", "")
    assert any("primary" in e.lower() for e in errs)
    print("test_validate_preset_missing_primary OK")


def test_validate_preset_invalid_primary() -> None:
    name, p, s, errs = validate_preset("X", "not an ip", "")
    assert errs
    assert p == ""
    print("test_validate_preset_invalid_primary OK")


def test_validate_preset_duplicate() -> None:
    name, p, s, errs = validate_preset("X", "8.8.8.8", "8.8.8.8")
    assert any("different" in e.lower() or "duplicate" in e.lower() for e in errs)
    print("test_validate_preset_duplicate OK")


def test_validate_preset_empty_name() -> None:
    name, p, s, errs = validate_preset("", "8.8.8.8", "")
    assert any("name" in e.lower() for e in errs)
    print("test_validate_preset_empty_name OK")


if __name__ == "__main__":
    test_dedup_basic()
    test_parse_dns_block_static()
    test_parse_dns_block_inline()
    test_parse_dns_block_dhcp()
    test_parse_dns_servers_ipv6()
    test_parse_dns_block_ipv6_letter_hextet()
    test_parse_dns_servers_ipv6_letter_hextet()
    test_parse_dns_servers_inline_first_hextet_not_lost()
    test_validate_preset_happy()
    test_validate_preset_ipv6()
    test_validate_preset_missing_primary()
    test_validate_preset_invalid_primary()
    test_validate_preset_duplicate()
    test_validate_preset_empty_name()
    print("\nAll dns_manager parsing tests passed.")
