"""Regression tests for DNS verification after Apply DNS (v4.1.0 bug).

v4.1.0 could report::

    Failed to apply DNS: Verification failed: expected '94.183.166.199' in
    adapter 'Wi-Fi', got IPv4=[] IPv6=[]

even though Windows *had* accepted the configuration.  Root causes fixed:

* a single read-back 0.3s after applying lost the race against Windows'
  asynchronous DNS-store update;
* parsing depended on English-only ``netsh`` section headers (localised
  Windows produced no data at all);
* the PowerShell fallback used a script block (fails under
  ConstrainedLanguage) and was one-shot only;
* comparisons mixed IP families and compared raw-ish strings;
* the failure message leaked Python list representations into the UI.

The tests below simulate Windows with :class:`FakeWindows` — an in-memory
DNS store that answers ``netsh``/``powershell.exe`` the way real Windows
does, including English vs. localised output and delayed visibility of a
freshly applied configuration.
"""
from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dns_manager
from dns_manager import (
    AdapterDnsState,
    apply_dhcp,
    apply_static,
    restore_backup,
)


# ---------------------------------------------------------------- helpers

def _cp(stdout: str = "", stderr: str = "", rc: int = 0) -> MagicMock:
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = rc
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


class FakeWindows:
    """Simulates the Windows DNS store, ``netsh`` and PowerShell.

    * ``dns4`` / ``dns6``: the configured servers per family, or the string
      ``"dhcp"`` when the adapter obtains DNS automatically.
    * ``localized=True``: ``netsh`` answers with translated (here: German
      style) section headers, so English-marker parsers find nothing — the
      PowerShell JSON channel must then carry verification.
    * ``ps_stale_reads``: PowerShell reports the *previous* state for the
      first N reads after a change, mimicking Windows' asynchronous update
      of the effective DNS registration (the v4.1.0 timing race).
    * ``accept_writes=False``: ``netsh`` "succeeds" (rc 0) but the store
      silently does not change — the way a genuinely failed apply looks.
    """

    def __init__(self, adapter: str = "Wi-Fi", *, localized: bool = False) -> None:
        self.adapter = adapter
        self.localized = localized
        self.dns4: "str | list[str]" = "dhcp"
        self.dns6: "str | list[str]" = "dhcp"
        self.accept_writes = True
        self.ps_stale_reads = 0
        self.commands: list[list[str]] = []
        self.ps_json_reads = 0
        self._stale_left = 0
        self._stale: tuple = ("dhcp", "dhcp")

    # --------------------------------------------------------- fake _run

    def run(self, args, **_kwargs) -> MagicMock:
        args = [str(a) for a in args]
        self.commands.append(args)
        if args and "powershell.exe" in args[0]:
            return self._powershell(args)
        return self._netsh(args)

    # -------------------------------------------------------------- netsh

    def _netsh(self, args: list[str]) -> MagicMock:
        joined = " ".join(args)

        # adapter existence check (name=...) / interface=...
        for token in args:
            if token.startswith("name=") or token.startswith("interface="):
                if token.split("=", 1)[1] != self.adapter:
                    return _cp(stderr="The interface is not found.", rc=1)

        if "show" in args and "config" in args:
            return self._show_v4()
        if "show" in args and ("dnsservers" in args or "dns" in args) and "ipv6" in args:
            return self._show_v6()

        if "delete" in args and "dns" in args:
            self._mutate()
            if "ipv6" in args:
                if self.accept_writes:
                    self.dns6 = "dhcp"
            elif self.accept_writes:
                self.dns4 = "dhcp"
            return _cp()

        if "set" in args and "dns" in args:
            self._mutate()
            if "dhcp" in args:
                if "ipv6" in args:
                    if self.accept_writes:
                        self.dns6 = "dhcp"
                elif self.accept_writes:
                    self.dns4 = "dhcp"
                return _cp()
            if "static" in args:
                ip = self._positional_ip(args)
                if self.accept_writes and ip:
                    if "ipv6" in args:
                        self.dns6 = [ip]
                    else:
                        self.dns4 = [ip]
                return _cp()

        if "add" in args and "dns" in args:
            self._mutate()
            ip = self._positional_ip(args)
            if self.accept_writes and ip:
                if "ipv6" in args:
                    if isinstance(self.dns6, list):
                        self.dns6.append(ip)
                elif isinstance(self.dns4, list):
                    self.dns4.append(ip)
            return _cp()

        return _cp(stderr=f"unhandled: {joined}", rc=1)

    @staticmethod
    def _positional_ip(args: list[str]) -> "str | None":
        for token in args:
            if token.count(".") == 3 or ":" in token:
                try:
                    dns_manager._ip_key(token)
                    return token
                except Exception:
                    continue
        return None

    def _mutate(self) -> None:
        # A pending configuration change: the next ``ps_stale_reads`` PS
        # reads still report the state from *before* this change.  Snapshot
        # copies — the live lists are mutated in place by ``add``.
        snap4 = list(self.dns4) if isinstance(self.dns4, list) else self.dns4
        snap6 = list(self.dns6) if isinstance(self.dns6, list) else self.dns6
        self._stale = (snap4, snap6)
        self._stale_left = self.ps_stale_reads

    def _show_v4(self) -> MagicMock:
        dhcp_line = (
            "    Über DHCP konfigurierte DNS-Server:     192.168.1.1"
            if self.localized else
            "    DNS servers configured through DHCP:  192.168.1.1"
        )
        static_head = (
            "    Statisch konfigurierte DNS-Server:    "
            if self.localized else
            "    Statically Configured DNS Servers:    "
        )
        header = (
            f'Konfiguration der Schnittstelle "{self.adapter}"'
            if self.localized else
            f'Configuration for interface "{self.adapter}"'
        )
        lines = [
            header,
            "    DHCP enabled:                         Yes",
            "    IP Address:                           192.168.1.50",
            "    Subnet Prefix:                        192.168.1.0/24 (mask 255.255.255.0)",
            "    Default Gateway:                      192.168.1.1",
            "    Gateway Metric:                       0",
            "    InterfaceMetric:                      35",
        ]
        if self.dns4 == "dhcp":
            lines.append(dhcp_line)
        else:
            servers = list(self.dns4)
            lines.append(static_head + servers[0])
            for extra in servers[1:]:
                lines.append(" " * 42 + extra)
        lines.append("    Register with which suffix:           Primary only")
        return _cp(stdout="\n".join(lines) + "\n")

    def _show_v6(self) -> MagicMock:
        lines = [f'Configuration for interface "{self.adapter}"', ""]
        if self.dns6 == "dhcp":
            lines.append("Configured DNS Servers:                fec0:0:0:ffff::1%1")
            lines.append("                                       fec0:0:0:ffff::2%1")
        else:
            servers = list(self.dns6)
            lines.append("Configured DNS Servers:                " + servers[0])
            for extra in servers[1:]:
                lines.append(" " * 42 + extra)
        lines.append("Register with which suffix:            Primary only")
        return _cp(stdout="\n".join(lines) + "\n")

    # ---------------------------------------------------------- powershell

    def _powershell(self, args: list[str]) -> MagicMock:
        self.ps_json_reads += 1
        # Like the real cmdlet with -InterfaceAlias: nothing is reported for
        # an alias that does not exist.
        if f"'{self.adapter}'" not in " ".join(args):
            return _cp(stdout="")
        if self._stale_left > 0:
            self._stale_left -= 1
            dns4, dns6 = self._stale
        else:
            dns4, dns6 = self.dns4, self.dns6
        v4 = list(dns4) if dns4 != "dhcp" else ["192.168.1.1"]
        v6 = list(dns6) if dns6 != "dhcp" else []
        rows = [
            {"AddressFamily": 2, "ServerAddresses": v4},
            {"AddressFamily": 23, "ServerAddresses": v6},
        ]
        return _cp(stdout=json.dumps(rows))


# ------------------------------------------------------------- test setup

@contextlib.contextmanager
def _patched(os_env: FakeWindows):
    with patch.object(dns_manager, "_is_windows", return_value=True), \
         patch.object(dns_manager, "_run", side_effect=os_env.run):
        yield


def _quiet_timeouts():
    return (
        patch.object(dns_manager, "_VERIFY_INITIAL_DELAY", 0.0),
        patch.object(dns_manager, "_VERIFY_RETRY_DELAYS", (0.0, 0.0, 0.0)),
    )


# ---------------------------------------------------------- parser cases

def test_parse_realistic_static_output() -> None:
    """Case 1: realistic netsh output exposes both static IPv4 servers."""
    text = (
        'Configuration for interface "Wi-Fi"\n'
        '    DHCP enabled:                         Yes\n'
        '    IP Address:                           192.168.1.50\n'
        '    Subnet Prefix:                        192.168.1.0/24 (mask 255.255.255.0)\n'
        '    Default Gateway:                      192.168.1.1\n'
        '    Gateway Metric:                       0\n'
        '    InterfaceMetric:                      35\n'
        '    Statically Configured DNS Servers:    94.183.166.199\n'
        '                                          94.183.166.195\n'
        '    Register with which suffix:           Primary only\n'
    )
    servers, is_dhcp = dns_manager._parse_dns_block(text)
    assert servers == ["94.183.166.199", "94.183.166.195"], servers
    assert is_dhcp is False
    print("test_parse_realistic_static_output OK")


def test_parse_does_not_confuse_gateway_with_dns() -> None:
    """Gateway/subnet IPs must never be misread as DNS servers."""
    text = (
        'Configuration for interface "Ethernet 2"\n'
        '    IP Address:                           10.0.0.42\n'
        '    Default Gateway:                      10.0.0.1\n'
        '    DNS servers configured through DHCP:  10.0.0.1\n'
        '                                        10.0.0.2\n'
    )
    servers, is_dhcp = dns_manager._parse_dns_block(text)
    assert "10.0.0.42" not in servers
    assert "10.0.0.1" not in servers or is_dhcp  # DHCP-sourced DNS is allowed
    assert is_dhcp is True
    print("test_parse_does_not_confuse_gateway_with_dns OK")


def test_localized_output_has_no_marker_but_is_dhcp_safe() -> None:
    """Case 7: localized output yields an *unknown* marker, not a verdict."""
    text = (
        'Konfiguration der Schnittstelle "Wi-Fi"\n'
        '    Statisch konfigurierte DNS-Server:    94.183.166.199\n'
        '                                          94.183.166.195\n'
        '    Registrierungssuffix:                 Nur primär\n'
    )
    servers, marker = dns_manager._parse_dns_block_detailed(text)
    assert marker is None  # unknown — no false DHCP verdict, no false static
    print("test_localized_output_has_no_marker_but_is_dhcp_safe OK")


# ------------------------------------------------- _missing_expected cases

def test_missing_expected_ipv4_only_ipv6_empty() -> None:
    """Case 2: an empty IPv6 config must never fail IPv4 verification."""
    state = AdapterDnsState(
        name="Wi-Fi",
        ipv4=["94.183.166.199", "94.183.166.195"],
        ipv6=[],
    )
    missing4, missing6 = dns_manager._missing_expected(
        state, ["94.183.166.199", "94.183.166.195"],
    )
    assert not missing4 and not missing6
    print("test_missing_expected_ipv4_only_ipv6_empty OK")


def test_missing_expected_families_are_separate() -> None:
    """Case 3: an IPv4 expectation satisfied only in IPv6 must still fail."""
    state = AdapterDnsState(
        name="Wi-Fi", ipv4=[], ipv6=["2606:4700:4700::1111"],
    )
    missing4, missing6 = dns_manager._missing_expected(state, ["1.1.1.1"])
    assert missing4 == ["1.1.1.1"]
    missing4, missing6 = dns_manager._missing_expected(
        state, ["2606:4700:4700::1111"],
    )
    assert not missing4 and not missing6
    print("test_missing_expected_families_are_separate OK")


def test_missing_expected_normalises_representation() -> None:
    """Case 8: order and textual representation must not matter."""
    state = AdapterDnsState(
        name="Wi-Fi",
        ipv4=["94.183.166.195", "94.183.166.199"],  # reversed order
        ipv6=["2606:4700:4700:0:0:0:0:1111"],        # expanded form
    )
    missing4, missing6 = dns_manager._missing_expected(
        state,
        ["94.183.166.199", "94.183.166.195", "2606:4700:4700::1111"],
    )
    assert not missing4 and not missing6
    print("test_missing_expected_normalises_representation OK")


# ------------------------------------------------------- _verify behaviour

def test_verify_waits_for_delayed_visibility() -> None:
    """The read-back race must be absorbed by the bounded retry loop."""
    states = [
        (AdapterDnsState(name="Wi-Fi"), True),                      # stale #1
        (AdapterDnsState(name="Wi-Fi"), True),                      # stale #2
        (AdapterDnsState(name="Wi-Fi", ipv4=["94.183.166.199",
                                             "94.183.166.195"]), True),
    ]
    reads = {"n": 0}

    class _FakeFull:
        def __init__(self, state, reliable):
            self.state = state
            self.reliable = reliable

    def fake_read(_adapter):
        idx = min(reads["n"], len(states) - 1)
        reads["n"] += 1
        state, reliable = states[idx]
        return _FakeFull(state, reliable)

    with patch.object(dns_manager, "_read_dns_full", side_effect=fake_read):
        ok, state, msg, details = dns_manager._verify(
            "Wi-Fi", ["94.183.166.199", "94.183.166.195"], sleep=lambda _s: None,
        )
    assert ok, msg
    assert reads["n"] == 3  # bounded retries, not one shot
    assert state.ipv4 == ["94.183.166.199", "94.183.166.195"]
    print("test_verify_waits_for_delayed_visibility OK")


def test_verify_bounded_and_reports_real_mismatch() -> None:
    """Case 9: a genuine mismatch fails fast, bounded, with clean output."""
    state = AdapterDnsState(name="Wi-Fi", ipv4=["192.168.1.1"], ipv6=[])
    reads = {"n": 0}

    class _FakeFull:
        def __init__(self):
            self.state = state
            self.reliable = True

    def fake_read(_adapter):
        reads["n"] += 1
        return _FakeFull()

    with patch.object(dns_manager, "_read_dns_full", side_effect=fake_read):
        ok, _state, msg, details = dns_manager._verify(
            "Wi-Fi", ["94.183.166.199", "94.183.166.195"], sleep=lambda _s: None,
        )
    assert not ok
    # attempts == 1 + len(delays) — strictly bounded
    assert reads["n"] == 1 + len(dns_manager._VERIFY_RETRY_DELAYS)
    # No ugly Python representations leak into the message.
    assert "IPv4=[" not in msg and "IPv6=0" not in msg, msg
    assert "94.183.166.199" in msg and "192.168.1.1" in msg
    assert details["code"] == "verification_failed"
    assert details["expected_ipv4"] == ["94.183.166.199", "94.183.166.195"]
    assert details["detected_ipv4"] == ["192.168.1.1"]
    assert details["detected_ipv6"] == []
    assert details["read_ok"] is True
    print("test_verify_bounded_and_reports_real_mismatch OK")


def test_verify_unreadable_adapter_is_an_honest_failure() -> None:
    class _FakeFull:
        def __init__(self):
            self.state = AdapterDnsState(name="Wi-Fi")
            self.reliable = False

    with patch.object(dns_manager, "_read_dns_full",
                      side_effect=lambda _a: _FakeFull()):
        ok, _state, msg, details = dns_manager._verify(
            "Wi-Fi", ["8.8.8.8"], sleep=lambda _s: None,
        )
    assert not ok
    assert "unable to read" in msg
    assert details["read_ok"] is False
    print("test_verify_unreadable_adapter_is_an_honest_failure OK")


# ------------------------------------------- full end-to-end (FakeWindows)

def test_apply_anti_ea_sanction_end_to_end() -> None:
    """The exact reported scenario must succeed (Case 1 + Case 5)."""
    win = FakeWindows("Wi-Fi")
    with _patched(win):
        result = apply_static("Wi-Fi", "94.183.166.199", "94.183.166.195")
    assert result.success, result.message
    assert result.verified is not None
    assert result.verified.ipv4 == ["94.183.166.199", "94.183.166.195"]
    # The OS really holds the config, and only the IPv4 stack was written.
    assert win.dns4 == ["94.183.166.199", "94.183.166.195"]
    ipv6_writes = [
        c for c in win.commands
        if "ipv6" in c and any(x in ("set", "add", "delete") for x in c)
    ]
    assert ipv6_writes == [], ipv6_writes
    print("test_apply_anti_ea_sanction_end_to_end OK")


def test_apply_all_builtin_presets() -> None:
    """Every built-in preset must apply and verify generically."""
    from presets import DEFAULT_PRESETS

    for name, dns in DEFAULT_PRESETS.items():
        win = FakeWindows("Wi-Fi")
        with _patched(win):
            result = apply_static("Wi-Fi", dns["primary"], dns["secondary"])
        assert result.success, f"{name}: {result.message}"
        assert result.verified.ipv4 == [dns["primary"], dns["secondary"]], name
    print("test_apply_all_builtin_presets OK")


def test_apply_with_adapter_name_containing_spaces() -> None:
    """Case 6: adapter names with spaces match and verify correctly."""
    win = FakeWindows("Local Area Connection 2")
    with _patched(win):
        result = apply_static("Local Area Connection 2", "1.1.1.1", "1.0.0.1")
    assert result.success, result.message
    assert win.dns4 == ["1.1.1.1", "1.0.0.1"]
    assert any("name=Local Area Connection 2" in c for c in win.commands)
    print("test_apply_with_adapter_name_containing_spaces OK")


def test_apply_wrong_adapter_name_is_an_error_not_a_false_pass() -> None:
    """Case 4: only the requested adapter is read/applied."""
    win = FakeWindows("Wi-Fi")
    with _patched(win):
        result = apply_static("Ethernet", "1.1.1.1", "")
    assert not result.success
    # It must not be a *verification* false-failure either — the write
    # itself was rejected by netsh (adapter not found) and reported.
    assert result.details.get("code") != "verification_failed"
    print("test_apply_wrong_adapter_name_is_an_error_not_a_false_pass OK")


def test_apply_on_localized_windows_succeeds() -> None:
    """Case 7: localized netsh text must not break verification."""
    win = FakeWindows("Wi-Fi", localized=True)
    with _patched(win):
        result = apply_static("Wi-Fi", "94.183.166.199", "94.183.166.195")
    assert result.success, result.message
    assert win.dns4 == ["94.183.166.199", "94.183.166.195"]
    print("test_apply_on_localized_windows_succeeds OK")


def test_apply_with_delayed_powershell_visibility() -> None:
    """The timing race from the v4.1.0 report: first reads are stale."""
    win = FakeWindows("Wi-Fi", localized=True)
    win.ps_stale_reads = 2  # first two PS reads after a write show old state
    with _patched(win):
        result = apply_static("Wi-Fi", "94.183.166.199", "94.183.166.195")
    assert result.success, result.message
    # It took extra reads, but the bounded retry loop absorbed the race.
    assert win.ps_json_reads > 2
    print("test_apply_with_delayed_powershell_visibility OK")


def test_apply_genuine_failure_is_reported_cleanly() -> None:
    """Do not hide real failures: OS accepts the command but never applies.

    This is what a *true* failure looks like — the app must report it,
    restore the backup, and show structured, readable diagnostics.
    """
    win = FakeWindows("Wi-Fi")
    win.accept_writes = False
    with _patched(win):
        result = apply_static("Wi-Fi", "94.183.166.199", "94.183.166.195")
    assert not result.success
    assert result.details.get("code") == "verification_failed"
    assert result.details["expected_ipv4"] == ["94.183.166.199", "94.183.166.195"]
    assert "IPv4=[" not in result.message
    # The previous (DHCP) configuration was restored, not left half-applied.
    assert win.dns4 == "dhcp"
    print("test_apply_genuine_failure_is_reported_cleanly OK")


def test_apply_ipv6_preset_verifies_only_ipv6() -> None:
    """IPv4 leftovers must not interfere with IPv6 verification (Case 3)."""
    win = FakeWindows("Wi-Fi")
    win.dns4 = ["99.99.99.99"]  # pre-existing unrelated static IPv4 DNS
    win.dns6 = ["fec0:0:0:ffff::9"]
    with _patched(win):
        result = apply_static(
            "Wi-Fi", "2606:4700:4700::1111", "2606:4700:4700::1001",
        )
    assert result.success, result.message
    assert win.dns6 == ["2606:4700:4700::1111", "2606:4700:4700::1001"]
    assert win.dns4 == ["99.99.99.99"]  # untouched
    print("test_apply_ipv6_preset_verifies_only_ipv6 OK")


# --------------------------------------------------------------- DHCP mode

def test_dhcp_restore_verified_english() -> None:
    win = FakeWindows("Wi-Fi")
    win.dns4 = ["94.183.166.199", "94.183.166.195"]
    with _patched(win):
        result = apply_dhcp("Wi-Fi")
    assert result.success, result.message
    assert win.dns4 == "dhcp"
    print("test_dhcp_restore_verified_english OK")


def test_dhcp_restore_verified_localized() -> None:
    """Localized Windows: no markers — content comparison decides."""
    win = FakeWindows("Wi-Fi", localized=True)
    win.dns4 = ["94.183.166.199", "94.183.166.195"]
    with _patched(win):
        result = apply_dhcp("Wi-Fi")
    assert result.success, result.message
    assert win.dns4 == "dhcp"
    print("test_dhcp_restore_verified_localized OK")


def test_dhcp_restore_genuine_failure_localized() -> None:
    """If the DHCP reset silently fails, the old static servers remain —
    that must be detected *without* English markers."""
    win = FakeWindows("Wi-Fi", localized=True)
    win.dns4 = ["94.183.166.199", "94.183.166.195"]
    win.accept_writes = False
    with _patched(win):
        result = apply_dhcp("Wi-Fi")
    assert not result.success
    assert result.details.get("code") == "dhcp_verification_failed"
    assert win.dns4 == ["94.183.166.199", "94.183.166.195"]  # restored/unchanged
    print("test_dhcp_restore_genuine_failure_localized OK")


def test_restore_backup_on_localized_static_keeps_servers() -> None:
    """Backups built on localized Windows restore the static servers instead
    of resetting the adapter to DHCP and losing them."""
    win = FakeWindows("Wi-Fi", localized=True)
    win.dns4 = ["94.183.166.199", "94.183.166.195"]
    with _patched(win):
        backup = dns_manager.read_dns("Wi-Fi")
        win.dns4 = ["1.1.1.1", "1.0.0.1"]  # something else meanwhile
        result = restore_backup(backup)
    assert result.success, result.message
    assert win.dns4 == ["94.183.166.199", "94.183.166.195"], win.dns4
    print("test_restore_backup_on_localized_static_keeps_servers OK")


# ------------------------------------------------- powershell JSON channel

def test_powershell_serveraddresses_key_parsed() -> None:
    """The simplified (script-block-free) PowerShell command output."""
    payload = json.dumps([
        {"AddressFamily": 2, "ServerAddresses": ["94.183.166.199",
                                                 "94.183.166.195"]},
        {"AddressFamily": 23, "ServerAddresses": []},
    ])

    def fake_run(args, **kwargs):
        return _cp(stdout=payload)

    with patch.object(dns_manager, "_run", side_effect=fake_run):
        state = dns_manager._read_dns_powershell("Wi-Fi")
    assert state is not None
    assert state.ipv4 == ["94.183.166.199", "94.183.166.195"]
    assert state.ipv6 == []
    print("test_powershell_serveraddresses_key_parsed OK")


def test_powershell_empty_rows_mean_read_ok_not_failure() -> None:
    """A DHCP adapter with no leases yet: rows exist, servers are empty."""
    payload = json.dumps([
        {"AddressFamily": 2, "ServerAddresses": []},
        {"AddressFamily": 23, "ServerAddresses": []},
    ])

    def fake_run(args, **kwargs):
        return _cp(stdout=payload)

    with patch.object(dns_manager, "_run", side_effect=fake_run):
        state = dns_manager._read_dns_powershell("Wi-Fi")
    assert state is not None  # the read worked — it is not "None" (broken)
    assert state.ipv4 == [] and state.ipv6 == []
    print("test_powershell_empty_rows_mean_read_ok_not_failure OK")


def test_powershell_broken_returns_none() -> None:
    def fake_run(args, **kwargs):
        return _cp(stderr="not recognized", rc=1)

    with patch.object(dns_manager, "_run", side_effect=fake_run):
        assert dns_manager._read_dns_powershell("Wi-Fi") is None
    print("test_powershell_broken_returns_none OK")


# ------------------------------------------------------------- misc robust

def test_decode_output_never_raises() -> None:
    """Localized OEM output must decode losslessly-for-ASCII, never crash."""
    assert dns_manager._decode_output(b"8.8.8.8") == "8.8.8.8"
    assert dns_manager._decode_output("already text") == "already text"
    assert dns_manager._decode_output(None) == ""
    # Invalid UTF-8 (e.g. OEM code page) must not raise.
    out = dns_manager._decode_output(b"Prim\x84re DNS-Server: 94.183.166.199")
    assert "94.183.166.199" in out
    print("test_decode_output_never_raises OK")


def test_format_servers() -> None:
    assert dns_manager._format_servers([]) == "none"
    assert dns_manager._format_servers(["1.1.1.1"]) == "1.1.1.1"
    assert dns_manager._format_servers(["1.1.1.1", "1.0.0.1"]) == "1.1.1.1, 1.0.0.1"
    print("test_format_servers OK")


def test_details_are_ui_ready_for_all_failures() -> None:
    """Whichever way verification fails, details must be renderable."""
    win = FakeWindows("Wi-Fi", localized=True)
    win.accept_writes = False
    with _patched(win):
        result = apply_static("Wi-Fi", "94.183.166.199", "94.183.166.195")
    d = result.details
    for key in ("code", "adapter", "expected_ipv4", "expected_ipv6",
                "detected_ipv4", "detected_ipv6"):
        assert key in d, key
    # Exercise the same formatting the UI dialog uses.
    from translations import get_text
    for lang in ("en", "fa"):
        body = get_text(
            lang, "verify_failed_detail",
            adapter=d["adapter"],
            expected_v4="\n".join(d["expected_ipv4"]),
            expected_v6="\n".join(d["expected_ipv6"]) or "(none)",
            detected_v4="\n".join(d["detected_ipv4"]) or "(none)",
            detected_v6="\n".join(d["detected_ipv6"]) or "(none)",
        )
        assert "94.183.166.199" in body
        assert d["adapter"] in body
    print("test_details_are_ui_ready_for_all_failures OK")


if __name__ == "__main__":
    test_parse_realistic_static_output()
    test_parse_does_not_confuse_gateway_with_dns()
    test_localized_output_has_no_marker_but_is_dhcp_safe()
    test_missing_expected_ipv4_only_ipv6_empty()
    test_missing_expected_families_are_separate()
    test_missing_expected_normalises_representation()
    test_verify_waits_for_delayed_visibility()
    test_verify_bounded_and_reports_real_mismatch()
    test_verify_unreadable_adapter_is_an_honest_failure()
    test_apply_anti_ea_sanction_end_to_end()
    test_apply_all_builtin_presets()
    test_apply_with_adapter_name_containing_spaces()
    test_apply_wrong_adapter_name_is_an_error_not_a_false_pass()
    test_apply_on_localized_windows_succeeds()
    test_apply_with_delayed_powershell_visibility()
    test_apply_genuine_failure_is_reported_cleanly()
    test_apply_ipv6_preset_verifies_only_ipv6()
    test_dhcp_restore_verified_english()
    test_dhcp_restore_verified_localized()
    test_dhcp_restore_genuine_failure_localized()
    test_restore_backup_on_localized_static_keeps_servers()
    test_powershell_serveraddresses_key_parsed()
    test_powershell_empty_rows_mean_read_ok_not_failure()
    test_powershell_broken_returns_none()
    test_decode_output_never_raises()
    test_format_servers()
    test_details_are_ui_ready_for_all_failures()
    print("\nAll DNS verification tests passed.")
