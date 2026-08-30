"""Tests for dns_manager.apply_static / apply_dhcp that mock subprocess."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dns_manager
from dns_manager import apply_dhcp, apply_static, AdapterDnsState, restore_backup


def _ok(stdout: str = "", stderr: str = "") -> MagicMock:
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = 0
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def _fail(stderr: str = "some error", stdout: str = "") -> MagicMock:
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = 1
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def _is_show_config(args) -> bool:
    """Return True if args is a ``show config`` netsh command."""
    return (
        len(args) >= 4
        and "netsh" in args[0]
        and "show" in args
        and "config" in args
    )


def _is_show_dns(args) -> bool:
    return (
        len(args) >= 4
        and "netsh" in args[0]
        and "show" in args
        and ("dns" in args or "dnsservers" in args)
    )


def test_apply_static_happy_path() -> None:
    """Static apply succeeds and verifies."""
    sample_static = (
        "Statically Configured DNS Servers:    8.8.8.8\n"
        "                                      8.8.4.4\n"
    )
    sample_dhcp = "DNS Servers configured through DHCP:    192.168.1.1\n"
    show_n = [0]

    def fake_run(args, **kwargs):
        if _is_show_config(args):
            show_n[0] += 1
            cp = _ok()
            cp.stdout = sample_dhcp if show_n[0] == 1 else sample_static
            return cp
        return _ok()

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        result = apply_static("Wi-Fi", "8.8.8.8", "8.8.4.4")

    assert result.success, f"apply_static should succeed, got {result.message}"
    assert result.backup is not None
    assert result.verified is not None
    assert "8.8.8.8" in result.verified.ipv4
    assert "8.8.4.4" in result.verified.ipv4
    print("test_apply_static_happy_path OK")


def test_apply_static_invalid_primary() -> None:
    with patch.object(dns_manager, "_is_windows", return_value=True):
        result = apply_static("Wi-Fi", "not an ip", "")
    assert not result.success
    assert any("invalid" in e.lower() for e in result.errors)
    print("test_apply_static_invalid_primary OK")


def test_apply_static_duplicate_primary_secondary() -> None:
    with patch.object(dns_manager, "_is_windows", return_value=True):
        result = apply_static("Wi-Fi", "8.8.8.8", "8.8.8.8")
    assert not result.success
    print("test_apply_static_duplicate_primary_secondary OK")


def test_apply_static_empty_adapter() -> None:
    result = apply_static("", "8.8.8.8", "")
    assert not result.success
    print("test_apply_static_empty_adapter OK")


def test_apply_static_netsh_failure_rolls_back() -> None:
    """If netsh fails partway, the previous state is restored."""
    sample_dhcp = "DNS Servers configured through DHCP:    192.168.1.1\n"
    show_n = [0]
    set_calls = [0]

    def fake_run(args, **kwargs):
        if _is_show_config(args):
            show_n[0] += 1
            return _ok(stdout=sample_dhcp)
        if "set" in args and "static" in args:
            set_calls[0] += 1
            return _fail("adapter not found")
        return _ok()

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        result = apply_static("Wi-Fi", "8.8.8.8", "8.8.4.4")

    assert not result.success
    assert result.backup is not None
    # The "set static" call should have been attempted at least once
    assert set_calls[0] >= 1
    print("test_apply_static_netsh_failure_rolls_back OK")


def test_apply_dhcp_happy() -> None:
    def fake_run(args, **kwargs):
        if _is_show_config(args):
            cp = _ok()
            cp.stdout = "DNS Servers configured through DHCP:    192.168.1.1\n"
            return cp
        return _ok()

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        result = apply_dhcp("Wi-Fi")

    assert result.success
    assert result.backup is not None
    assert result.backup.is_dhcp is True
    print("test_apply_dhcp_happy OK")


def test_apply_dhcp_empty_adapter() -> None:
    result = apply_dhcp("")
    assert not result.success
    print("test_apply_dhcp_empty_adapter OK")


def test_restore_backup_to_dhcp() -> None:
    """If backup was DHCP, restore_backup should set DHCP again."""
    backup = AdapterDnsState(name="Wi-Fi", ipv4=[], ipv6=[], is_dhcp=True)
    sample_static = "Statically Configured DNS Servers:    8.8.8.8\n"

    def fake_run(args, **kwargs):
        if _is_show_config(args):
            return _ok(stdout=sample_static)
        return _ok()

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        result = restore_backup(backup)
    assert result.success
    print("test_restore_backup_to_dhcp OK")


def test_restore_backup_to_static() -> None:
    """If backup was static, restore_backup should re-apply those servers."""
    backup = AdapterDnsState(
        name="Wi-Fi", ipv4=["1.0.0.1", "1.0.0.2"], ipv6=[], is_dhcp=False,
    )
    sample_dhcp = "DNS Servers configured through DHCP:    192.168.1.1\n"
    show_n = [0]

    def fake_run(args, **kwargs):
        if _is_show_config(args):
            show_n[0] += 1
            cp = _ok()
            if show_n[0] == 1:
                cp.stdout = sample_dhcp
            else:
                cp.stdout = (
                    "Statically Configured DNS Servers:    1.0.0.1\n"
                    "                                      1.0.0.2\n"
                )
            return cp
        return _ok()

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        result = restore_backup(backup)
    assert result.success
    print("test_restore_backup_to_static OK")


def test_ping_host_success() -> None:
    fake = MagicMock(spec=subprocess.CompletedProcess)
    fake.returncode = 0
    fake.stdout = "Reply from 8.8.8.8: bytes=32 time=12ms TTL=117\n" * 3
    fake.stderr = ""
    with patch.object(dns_manager.subprocess, "run", return_value=fake):
        ms = dns_manager.ping_host("8.8.8.8", count=3, timeout_ms=2000)
    assert ms == 12, f"expected 12ms, got {ms}"
    print("test_ping_host_success OK")


def test_ping_host_timeout() -> None:
    fake = MagicMock(spec=subprocess.CompletedProcess)
    fake.returncode = 0
    fake.stdout = ""  # no time= lines
    fake.stderr = ""
    with patch.object(dns_manager.subprocess, "run", return_value=fake):
        ms = dns_manager.ping_host("8.8.8.8")
    assert ms == -1
    print("test_ping_host_timeout OK")


def test_ping_host_raises() -> None:
    with patch.object(
        dns_manager.subprocess, "run",
        side_effect=subprocess.TimeoutExpired(cmd="ping", timeout=15),
    ):
        ms = dns_manager.ping_host("8.8.8.8")
    assert ms == -1
    print("test_ping_host_raises OK")


def test_apply_static_ipv6_does_not_touch_ipv4() -> None:
    """An IPv6 preset must only write to the IPv6 stack."""
    ipv4_dhcp = "DNS Servers configured through DHCP:    192.168.1.1\n"
    ipv6_static = (
        "Configured DNS Servers:                2606:4700:4700::1111\n"
        "                                       fd00::2\n"
        "Register with which suffix:            Primary only\n"
    )
    show_dns_n = [0]
    calls: list[list] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if _is_show_config(args):
            return _ok(stdout=ipv4_dhcp)
        if _is_show_dns(args):
            show_dns_n[0] += 1
            return _ok(stdout=ipv6_static if show_dns_n[0] == 2 else "")
        return _ok()

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        result = apply_static("Wi-Fi", "2606:4700:4700::1111", "fd00::2")

    assert result.success, result.message
    # No IPv4 write commands should have been issued.
    ipv4_writes = [
        c for c in calls
        if any(x == "ip" for x in c)
        and any(x in ("set", "add", "delete") for x in c)
    ]
    assert ipv4_writes == [], f"IPv4 stack was touched: {ipv4_writes}"
    print("test_apply_static_ipv6_does_not_touch_ipv4 OK")


def test_apply_static_mixed_family_rejected() -> None:
    with patch.object(dns_manager, "_is_windows", return_value=True):
        result = apply_static("Wi-Fi", "8.8.8.8", "::1")
    assert not result.success
    assert any("family" in e.lower() for e in result.errors)
    print("test_apply_static_mixed_family_rejected OK")


def test_apply_static_locked_busy() -> None:
    """A second operation while one is running is rejected immediately."""
    assert dns_manager._DNS_LOCK.acquire(blocking=False)
    try:
        with patch.object(dns_manager, "_is_windows", return_value=True):
            result = apply_static("Wi-Fi", "8.8.8.8", "")
        assert not result.success
        assert any("running" in e.lower() for e in result.errors)
    finally:
        dns_manager._DNS_LOCK.release()
    print("test_apply_static_locked_busy OK")


def test_read_dns_powershell_scalar_servers() -> None:
    """PowerShell may report a single server as a scalar instead of a list."""
    payload = json.dumps({"AddressFamily": 2, "Servers": "8.8.8.8"})

    def fake_run(args, **kwargs):
        return _ok(stdout=payload)

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        state = dns_manager._read_dns_powershell("Wi-Fi")

    assert state is not None
    assert state.ipv4 == ["8.8.8.8"]
    print("test_read_dns_powershell_scalar_servers OK")


def test_read_dns_powershell_string_family() -> None:
    """Some PowerShell versions return AddressFamily as a string."""
    payload = json.dumps({
        "AddressFamily": "IPv6",
        "Servers": ["2001:4860:4860::8888"],
    })

    def fake_run(args, **kwargs):
        return _ok(stdout=payload)

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        state = dns_manager._read_dns_powershell("Wi-Fi")

    assert state is not None
    assert state.ipv6 == ["2001:4860:4860::8888"]
    print("test_read_dns_powershell_string_family OK")


def test_apply_dhcp_verify_fails_when_static_remains() -> None:
    """If the adapter still reports static DNS after reset, DHCP fails."""
    static = (
        "Statically Configured DNS Servers:    8.8.8.8\n"
        "                                      8.8.4.4\n"
    )

    def fake_run(args, **kwargs):
        if _is_show_config(args):
            return _ok(stdout=static)
        return _ok()

    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=fake_run):
        result = apply_dhcp("Wi-Fi")
    assert not result.success
    assert any("dhcp" in result.message.lower() or "verification" in result.message.lower()
               for e in [result.message])
    print("test_apply_dhcp_verify_fails_when_static_remains OK")


if __name__ == "__main__":
    test_apply_static_happy_path()
    test_apply_static_invalid_primary()
    test_apply_static_duplicate_primary_secondary()
    test_apply_static_empty_adapter()
    test_apply_static_netsh_failure_rolls_back()
    test_apply_dhcp_happy()
    test_apply_dhcp_empty_adapter()
    test_restore_backup_to_dhcp()
    test_restore_backup_to_static()
    test_ping_host_success()
    test_ping_host_timeout()
    test_ping_host_raises()
    test_apply_static_ipv6_does_not_touch_ipv4()
    test_apply_static_mixed_family_rejected()
    test_apply_static_locked_busy()
    test_read_dns_powershell_scalar_servers()
    test_read_dns_powershell_string_family()
    test_apply_dhcp_verify_fails_when_static_remains()
    print("\nAll dns apply tests passed.")
