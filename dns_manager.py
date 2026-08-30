"""
DNS management — Windows-only.

Design goals
============
* Apply IPv4 and IPv6 DNS in a single coordinated transaction.
* **Backup** the previous configuration so the user can restore it later.
* **Verify** after applying: do not declare success without reading the
  resulting state from the OS.
* Surface real errors (exit codes, stderr, timeout) instead of swallowing
  them.
* Use ``subprocess.run`` with a list of arguments (no ``shell=True``) to
  avoid command-injection from adapter names or DNS values.
* Every command runs with a timeout so the GUI can never hang forever.

Important ``netsh`` notes
-------------------------
* ``netsh interface ip set dns`` only manages **IPv4** (the *interface ip*
  context is the legacy IPv4 stack).
* ``netsh interface ipv6 set dns`` is the equivalent for IPv6.
* Both commands require the interface **name**, not the interface index,
  so we always quote the name and fall back to the interface alias when
  the canonical name fails.

For verification we re-read the configuration after applying, using both
``netsh interface ip show config`` / ``netsh interface ipv6 show dnsservers``
(parsed text) and the locale-independent PowerShell cmdlet
``Get-DnsClientServerAddress`` (JSON).  Verification never trusts the write
command alone: the expected servers are compared, per IP family, against the
freshly-read state, using :mod:`ipaddress` for normalisation, with a short
bounded retry/backoff to absorb the small delay Windows may need before the
new configuration becomes visible.
"""
from __future__ import annotations

import ipaddress
import json
import locale
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Iterable

from logger import get_logger
from validators import (
    has_duplicates,
    is_valid_dns,
    normalize_dns,
    sanitize_preset_name,
)

# Serializes DNS-changing operations so two clicks / hotkeys / tray events can
# never run two ``netsh`` commands against the same adapter concurrently.
_DNS_LOCK = threading.Lock()


# ------------------------------------------------------------------ utilities

# Hide the console window that would otherwise flash when we spawn netsh.
# CREATE_NO_WINDOW = 0x08000000
_CREATE_NO_WINDOW = 0x08000000

# Default timeouts (seconds) for each command. We do not want a single hung
# netsh process to freeze the GUI forever.
_DEFAULT_TIMEOUT = 8.0
_VERIFY_TIMEOUT = 6.0

# Bounded verify-after-apply timing.  Windows occasionally needs a moment
# before a fresh DNS configuration is reported back (the DNS Client service
# re-reads the store asynchronously).  We therefore re-check a few times with
# a growing backoff instead of one fixed sleep — but stay strictly bounded so
# a genuine failure is reported quickly (never an infinite loop, never a
# multi-second freeze on top of the time the read commands themselves take).
_VERIFY_INITIAL_DELAY = 0.2
_VERIFY_RETRY_DELAYS: tuple[float, ...] = (0.3, 0.6, 1.1)


def _netsh_args(*args: str) -> list[str]:
    """Build a ``netsh`` command as an argv list (no shell)."""
    return ["netsh", *args]


def _is_windows() -> bool:
    return sys.platform == "win32"


def _decode_output(data: bytes | str | None) -> str:
    """Decode subprocess output without ever raising.

    ``netsh`` writes in the console's OEM code page, PowerShell (roughly) in
    the ANSI code page, and neither necessarily matches Python's default
    encoding.  Treating the output as text with ``text=True`` alone can raise
    an uncaught :class:`UnicodeDecodeError` on localised Windows builds (e.g.
    Persian/Arabic code pages), which would kill the worker thread instead of
    reporting a DNS error.  We capture bytes and try, in order: UTF-8, the
    system-preferred encoding, and UTF-8 with replacement — IPv4/IPv6
    literals are pure ASCII, so the data verification cares about always
    survives.
    """
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    for encoding in ("utf-8", locale.getpreferredencoding(False) or "cp1252"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    """Run a subprocess safely. No shell, with a timeout and no console.

    ``OSError`` (for example ``netsh`` missing on a non-Windows dev box) is
    converted to :class:`subprocess.SubprocessError` so every caller that
    already guards against subprocess failures also handles it correctly.

    Output is captured as bytes and decoded defensively (see
    :func:`_decode_output`), so localised Windows output can never crash the
    DNS pipeline.
    """
    kwargs: dict = {
        "args": args,
        "shell": False,
        "capture_output": True,
        "text": False,
        "timeout": timeout,
    }
    if _is_windows():
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    try:
        raw = subprocess.run(**kwargs)
    except OSError as exc:
        raise subprocess.SubprocessError(f"failed to run {args[0]}: {exc}") from exc
    return subprocess.CompletedProcess(
        raw.args, raw.returncode,
        _decode_output(raw.stdout), _decode_output(raw.stderr),
    )


# ------------------------------------------------------------------ data model

@dataclass
class AdapterDnsState:
    """Snapshot of the DNS configuration for a single adapter."""

    name: str
    ipv4: list[str] = field(default_factory=list)
    ipv6: list[str] = field(default_factory=list)
    is_dhcp: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AdapterDnsState":
        return cls(
            name=str(data.get("name", "")),
            ipv4=list(data.get("ipv4") or []),
            ipv6=list(data.get("ipv6") or []),
            is_dhcp=bool(data.get("is_dhcp", True)),
        )


@dataclass
class DnsResult:
    """Outcome of a DNS operation. ``success`` is True only if the
    requested configuration was actually applied and verified.

    ``details`` carries structured, UI-friendly diagnostic information.
    When ``details["code"] == "verification_failed"`` it also contains the
    adapter name plus the expected/detected IPv4/IPv6 server lists, so the
    caller can render a proper localised explanation instead of a raw
    one-line string.
    """

    success: bool
    message: str = ""
    backup: AdapterDnsState | None = None
    verified: AdapterDnsState | None = None
    errors: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def __bool__(self) -> bool:  # convenience
        return self.success


# ------------------------------------------------------------------ detection

def list_adapters() -> list[dict]:
    """Return a list of physical network adapters via PowerShell.

    Each entry is a dict with keys: ``name``, ``alias`` (friendly name),
    ``description``, ``status`` (Up/Down/Disconnected), ``if_index``,
    ``interface_type`` (Ethernet / Wireless / etc.), ``virtual`` (bool).

    We use PowerShell's ``Get-NetAdapter`` because it gives us **stable,
    locale-independent** field names and works on Windows 8+ / Server 2012+
    (which covers every supported Windows 11 / Windows 10 installation).

    If PowerShell is unavailable for any reason, we fall back to parsing
    ``netsh interface show interface``.
    """
    log = get_logger()
    if not _is_windows():
        return [{"name": "Wi-Fi", "alias": "Wi-Fi", "description": "",
                 "status": "Up", "if_index": 0, "interface_type": "",
                 "virtual": False}]

    try:
        ps_cmd = (
            "$ErrorActionPreference='Stop'; "
            "Get-NetAdapter -Physical | "
            "Select-Object Name, InterfaceDescription, Status, ifIndex, "
            "InterfaceType, Virtual | "
            "ConvertTo-Json -Compress"
        )
        r = _run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            timeout=15.0,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            if isinstance(data, dict):
                data = [data]
            adapters = []
            for item in data:
                # ``InterfaceType`` is e.g. 6 for Ethernet, 71 for Wireless
                adapters.append({
                    "name": str(item.get("Name") or "").strip(),
                    "alias": str(item.get("Name") or "").strip(),
                    "description": str(item.get("InterfaceDescription") or ""),
                    "status": str(item.get("Status") or ""),
                    "if_index": int(item.get("ifIndex") or 0),
                    "interface_type": str(item.get("InterfaceType") or ""),
                    "virtual": bool(item.get("Virtual")),
                })
            if adapters:
                # Sort: connected first, then Wi-Fi/Ethernet first
                def _sort_key(a: dict) -> tuple:
                    up = 0 if a["status"].lower() == "up" else 1
                    wireless = 0 if "wireless" in a["interface_type"].lower() or "wi-fi" in (a["name"] + a["description"]).lower() else 1
                    return (up, wireless, a["name"].lower())
                adapters.sort(key=_sort_key)
                log.debug("list_adapters: found %d adapters via PowerShell", len(adapters))
                return adapters
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        log.warning("list_adapters: PowerShell failed (%s) — falling back to netsh", exc)

    # Fallback: parse ``netsh interface show interface``
    return _list_adapters_netsh_fallback()


def _list_adapters_netsh_fallback() -> list[dict]:
    log = get_logger()
    try:
        r = _run(_netsh_args("interface", "show", "interface"),
                 timeout=_DEFAULT_TIMEOUT)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
        log.error("netsh interface show interface failed: %s", exc)
        return []
    adapters: list[dict] = []
    for raw in (r.stdout or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("---") or line.lower().startswith("admin state"):
            continue
        # Tokens: Admin State, State, Type, Interface Name
        parts = line.split()
        if len(parts) < 4:
            continue
        # Skip the header row
        if parts[0].lower() in ("admin", "state"):
            continue
        name = " ".join(parts[3:]).strip()
        if not name:
            continue
        adapters.append({
            "name": name,
            "alias": name,
            "description": "",
            "status": parts[1] if len(parts) > 1 else "",
            "if_index": 0,
            "interface_type": "",
            "virtual": False,
        })
    return adapters


# ------------------------------------------------------------------ state read

class _NetshRead:
    """Internal result of the ``netsh``-based read.

    Besides the parsed address lists we record whether the command actually
    ran and which (English) section markers were seen, because the markers
    are the only signal distinguishing static DNS from DHCP-provided DNS in
    ``netsh`` output.  On localised Windows the markers will simply be absent
    and the callers fall back to the PowerShell-derived addresses plus a
    content-comparison cross-check.
    """

    __slots__ = ("state", "ok", "v4_static", "v4_dhcp")

    def __init__(self, state: AdapterDnsState, ok: bool,
                 v4_static: bool, v4_dhcp: bool) -> None:
        self.state = state
        self.ok = ok
        self.v4_static = v4_static
        self.v4_dhcp = v4_dhcp


def _read_dns_netsh(adapter: str) -> AdapterDnsState:
    """Read DNS using ``netsh``.  Returns the parsed adapter state."""
    return _read_dns_netsh_full(adapter).state


def _read_dns_netsh_full(adapter: str) -> _NetshRead:
    """Read DNS using ``netsh`` and report *how reliable* the read was."""
    log = get_logger()
    state = AdapterDnsState(name=adapter)
    ok = False
    v4_static = False
    v4_dhcp = False

    # IPv4
    try:
        r = _run(_netsh_args("interface", "ip", "show", "config", f'name={adapter}'),
                 timeout=_VERIFY_TIMEOUT)
        if r.returncode == 0 and (r.stdout or "").strip():
            ok = True
            servers, block = _parse_dns_block_detailed(r.stdout or "")
            state.ipv4 = servers
            state.is_dhcp = block != "static"
            v4_static = block == "static"
            v4_dhcp = block == "dhcp"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
        log.warning("read_dns(ipv4) for %r failed: %s", adapter, exc)

    # IPv6 — use the unambiguous full command name (``show dns`` relies on
    # netsh's abbreviation resolution, which has changed between releases).
    try:
        r = _run(_netsh_args("interface", "ipv6", "show", "dnsservers",
                             f'interface={adapter}'),
                 timeout=_VERIFY_TIMEOUT)
        if r.returncode == 0:
            ok = True
            state.ipv6 = _parse_dns_servers(r.stdout or "")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
        log.warning("read_dns(ipv6) for %r failed: %s", adapter, exc)

    return _NetshRead(state, ok, v4_static, v4_dhcp)


def _read_dns_powershell(adapter: str) -> AdapterDnsState | None:
    """Read the *effective* DNS server addresses using PowerShell.

    ``Get-DnsClientServerAddress`` returns structured, locale-independent data
    on Windows 8+, which makes DNS verification work even on non-English
    Windows installations where ``netsh`` output is localised.  The command is
    written without script blocks (e.g. ``@{n=...;e={...}}``) so it also runs
    under PowerShell ConstrainedLanguage mode.

    Returns ``None`` when PowerShell is unavailable, errors out, or reports
    nothing at all for the adapter.  When the adapter reports rows whose
    server lists are simply empty (e.g. DHCP with nothing leased yet), a
    state with empty lists is returned — the read itself worked.
    """
    log = get_logger()
    try:
        safe = adapter.replace("'", "''")
        ps_cmd = (
            "$ErrorActionPreference='SilentlyContinue'; "
            f"Get-DnsClientServerAddress -InterfaceAlias '{safe}' | "
            "Select-Object AddressFamily, ServerAddresses | "
            "ConvertTo-Json -Compress"
        )
        r = _run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            timeout=10.0,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        payload = json.loads(r.stdout)
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list) or not payload:
            return None
        if not any(isinstance(row, dict) for row in payload):
            return None
        state = AdapterDnsState(name=adapter)
        for row in payload or []:
            if not isinstance(row, dict):
                continue
            raw_family = row.get("AddressFamily") or 0
            # Accept both the direct property name and the legacy computed
            # ``Servers`` alias used by earlier versions of this function.
            raw_servers = row.get("ServerAddresses")
            if raw_servers is None:
                raw_servers = row.get("Servers")
            if raw_servers is None:
                raw_servers = []
            if isinstance(raw_servers, str):
                raw_servers = [raw_servers]
            elif not isinstance(raw_servers, (list, tuple)):
                raw_servers = []
            servers = [str(s) for s in raw_servers if s]
            try:
                family_int = int(raw_family)
            except (TypeError, ValueError):
                family_int = 0
            family_text = str(raw_family).lower()
            if family_int == 2 or family_text == "ipv4":
                state.ipv4 = _dedup([normalize_dns(s) for s in servers])
            elif family_int == 23 or family_text == "ipv6":
                state.ipv6 = _dedup([normalize_dns(s) for s in servers])
        # PowerShell reports the DNS servers currently in effect (static or
        # DHCP).  We cannot authoritatively tell the difference from this
        # cmdlet, so the caller keeps the ``netsh``-derived ``is_dhcp`` flag
        # when the two sources are combined.  When only this source is used,
        # the addresses are still useful for verification.
        log.debug("read_dns(powershell) for %r: ipv4=%s ipv6=%s",
                  adapter, state.ipv4, state.ipv6)
        return state
    except (subprocess.TimeoutExpired, subprocess.SubprocessError,
            json.JSONDecodeError, ValueError) as exc:
        log.debug("read_dns(powershell) for %r failed: %s", adapter, exc)
        return None


class _FullRead:
    """Combined result of every read channel for one adapter."""

    __slots__ = ("state", "reliable", "v4_static_marker", "v4_dhcp_marker",
                 "ps_worked")

    def __init__(self, state: AdapterDnsState, reliable: bool,
                 v4_static_marker: bool, v4_dhcp_marker: bool,
                 ps_worked: bool) -> None:
        self.state = state
        self.reliable = reliable
        self.v4_static_marker = v4_static_marker
        self.v4_dhcp_marker = v4_dhcp_marker
        self.ps_worked = ps_worked


def read_dns(adapter: str) -> AdapterDnsState:
    """Read the current DNS configuration of ``adapter``.

    Returns an :class:`AdapterDnsState` with the current IPv4 / IPv6 DNS
    servers.  On Windows the source of truth is ``netsh`` (to distinguish
    static from DHCP), with PowerShell used as a locale-independent fallback
    when ``netsh`` output cannot be parsed (e.g. localised output).
    """
    return _read_dns_full(adapter).state


def _read_dns_full(adapter: str) -> _FullRead:
    """Merge every available read channel for ``adapter``.

    Address lists come from ``netsh`` when parseable, filled in from
    PowerShell otherwise.  The result is considered *reliable* when at least
    one channel returned data — an unreadable adapter must be reported to the
    user as a real failure, never silently accepted.
    """
    log = get_logger()
    if not _is_windows():
        return _FullRead(AdapterDnsState(name=adapter), reliable=True,
                         v4_static_marker=False, v4_dhcp_marker=False,
                         ps_worked=False)

    netsh = _read_dns_netsh_full(adapter)
    state = netsh.state

    ps_state = _read_dns_powershell(adapter)
    if ps_state is not None:
        # If netsh could not read a static block for either family, the
        # PowerShell effective addresses still let verification succeed and
        # give the caller accurate server lists for the status/backup UI.
        if not state.ipv4:
            state.ipv4 = ps_state.ipv4
        if not state.ipv6:
            state.ipv6 = ps_state.ipv6
        log.debug("read_dns: merged PowerShell addresses for %r", adapter)

    if not netsh.v4_static and not netsh.v4_dhcp and (state.ipv4 or state.ipv6):
        # The netsh markers could not be parsed (typical on localised
        # Windows) yet the adapter clearly has DNS servers configured.  Treat
        # the configuration as *not-plain-DHCP* so a backup restore re-applies
        # those servers instead of silently dropping a static configuration
        # by switching the adapter to DHCP.  (An explicit "configured through
        # DHCP" marker always wins → English systems keep exact behaviour.)
        state.is_dhcp = False

    reliable = netsh.ok or ps_state is not None
    return _FullRead(
        state,
        reliable=reliable,
        v4_static_marker=netsh.v4_static,
        v4_dhcp_marker=netsh.v4_dhcp,
        ps_worked=ps_state is not None,
    )


def _extract_ip_tokens(text: str) -> list[str]:
    """Extract valid IP-address tokens from ``text``.

    This is deliberately generous about surrounding punctuation (Windows
    ``netsh`` output sometimes adds colons after labels) but strict about the
    address itself: every token is validated through :func:`ipaddress`.

    The function is what makes the fallback parsers tolerate both IPv4 and
    IPv6 addresses, including addresses whose first hextet starts with a letter
    (e.g. ``fe80::1`` or ``2606:4700:4700::1111``).
    """
    out: list[str] = []
    if not text:
        return out
    for raw in text.replace(",", " ").split():
        token = raw.strip(" \t:;()[]\"'")
        # A trailing colon that belongs to Windows output, not to the address.
        if token.endswith(":"):
            token = token[:-1]
        if not token:
            continue
        try:
            out.append(normalize_dns(token))
        except ValueError:
            continue
    return out


def _parse_dns_block_detailed(text: str) -> tuple[list[str], str | None]:
    """Parse the DNS block in ``netsh interface ip show config`` output.

    Returns ``(servers, marker)`` where ``marker`` is:

    * ``"static"`` — an explicit static DNS section was seen;
    * ``"dhcp"`` — an explicit "configured through DHCP" section was seen;
    * ``None`` — neither marker was found (typical for localised Windows
      output; the caller must not invent a DHCP/static verdict and should
      rely on the locale-independent PowerShell channel instead).

    The parser recognises the English headers used by ``netsh``; any line
    containing a label (``something:``) followed by no valid IP address ends
    the static block, so stray addresses later in the output (gateways etc.)
    are never misread as DNS servers.
    """
    servers: list[str] = []
    in_block = False
    marker: str | None = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "statically configured dns servers" in low:
            in_block = True
            marker = "static"
            servers.extend(_extract_ip_tokens(line))
            continue
        if "dns servers configured through dhcp" in low:
            if marker != "static":
                marker = "dhcp"
            in_block = False
            continue
        if "register with which suffix" in low or "primary only" in low:
            in_block = False
            continue
        if in_block:
            tokens = _extract_ip_tokens(line)
            if tokens:
                servers.extend(tokens)
            else:
                # A non-IP line (usually a ``label: value`` section header)
                # ends the static server block.
                in_block = False
    return _dedup(servers), marker


def _parse_dns_block(text: str) -> tuple[list[str], bool]:
    """Parse the DNS block in ``netsh interface ip show config`` output.

    Returns ``(servers, is_dhcp)``. ``is_dhcp`` is True unless an explicit
    static DNS section was detected.
    """
    servers, marker = _parse_dns_block_detailed(text)
    return servers, marker != "static"


def _parse_dns_servers(text: str) -> list[str]:
    """Parse ``netsh interface ipv6 show dns`` output.

    The typical output format is::

        Configuration for interface "Wi-Fi"
        DNS servers configured for this interface:  1::1
                                                   2::2
        Register with which suffix:                  Primary only

    Older variants use ``Configured DNS Servers:``.  The parser stops when it
    reaches a label line that contains no IP address, which also tolerates
    localised output around the DNS block.
    """
    servers: list[str] = []
    capture = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "dns servers configured" in low or low.startswith("configured dns servers"):
            capture = True
            servers.extend(_extract_ip_tokens(line))
            continue
        if "register with which suffix" in low or "primary only" in low:
            capture = False
            continue
        if capture:
            tokens = _extract_ip_tokens(line)
            if tokens:
                servers.extend(tokens)
            else:
                capture = False
    return _dedup(servers)


def _dedup(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = (v or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


# ------------------------------------------------------------------ write


def _family_of(ip: str) -> str:
    """Return ``"ipv4"`` or ``"ipv6"`` for a valid normalised IP address."""
    try:
        ipaddress.IPv4Address(ip)
        return "ipv4"
    except (ipaddress.AddressValueError, ValueError):
        pass
    try:
        ipaddress.IPv6Address(ip)
        return "ipv6"
    except (ipaddress.AddressValueError, ValueError):
        pass
    raise ValueError(f"not a valid IP address: {ip!r}")


def _validate_inputs(primary: str, secondary: str) -> tuple[str, str, list[str]]:
    """Normalise + validate DNS values. Returns (primary, secondary, errors).

    A primary/secondary pair must be the same IP family: Windows treats the
    IPv4 stack and IPv6 stack separately, and mixing e.g. an IPv4 primary with
    an IPv6 secondary would silently apply the wrong family to both stacks.
    """
    errors: list[str] = []
    p = (primary or "").strip()
    s = (secondary or "").strip()
    try:
        p = normalize_dns(p) if p else ""
    except ValueError:
        errors.append(f"Invalid primary DNS: {primary!r}")
        p = ""
    try:
        s = normalize_dns(s) if s else ""
    except ValueError:
        errors.append(f"Invalid secondary DNS: {secondary!r}")
        s = ""
    if p and not is_valid_dns(p):
        errors.append(f"Invalid primary DNS: {primary!r}")
    if s and not is_valid_dns(s):
        errors.append(f"Invalid secondary DNS: {secondary!r}")
    if p and s and p.lower() == s.lower():
        errors.append("Primary and secondary DNS must be different")
    if p and s:
        try:
            if _family_of(p) != _family_of(s):
                errors.append("Primary and secondary DNS must be the same IP family")
        except ValueError:
            pass
    return p, s, errors


def _set_adapter_dns_static_family(
    adapter: str, family: str, primary: str, secondary: str,
) -> list[str]:
    """Apply a static DNS configuration for one IP family only.

    This is the correct Windows behaviour: ``netsh interface ip`` only manages
    IPv4 while ``netsh interface ipv6`` only manages IPv6.  Applying an IPv4
    address to the IPv6 stack (or vice versa) is rejected by Windows and can
    leave the adapter in an inconsistent state.
    """
    log = get_logger()
    if family == "ipv4":
        context = "ip"
        addr_arg = "name"
    elif family == "ipv6":
        context = "ipv6"
        addr_arg = "interface"
    else:
        raise ValueError(f"unknown family {family!r}")

    errors: list[str] = []

    # Clear any existing DNS entries for this family first — without this,
    # repeated applications can accumulate ``index=2`` entries and fail.
    try:
        r = _run(_netsh_args("interface", context, "delete", "dns",
                             f"{addr_arg}={adapter}", "all"),
                 timeout=_DEFAULT_TIMEOUT)
        if r.returncode != 0:
            log.debug("%s delete dns rc=%d stderr=%s", family, r.returncode, r.stderr)
    except subprocess.TimeoutExpired:
        errors.append(f"Timed out clearing {family} DNS")
    except subprocess.SubprocessError as exc:
        errors.append(f"Failed to clear {family} DNS: {exc}")

    # Set primary.  Every parameter is passed in ``name=value`` form so the
    # meaning never depends on positional matching in netsh (positional
    # tokens are bound left-to-right, and their interpretation differs
    # slightly between Windows releases).
    try:
        args = _netsh_args(
            "interface", context, "set", "dns", f"{addr_arg}={adapter}", "static",
            primary, "validate=no",
        )
        if family == "ipv4":
            args.append("register=primary")
        r = _run(args, timeout=_DEFAULT_TIMEOUT)
        if r.returncode != 0:
            errors.append(f"Failed to set {family} primary DNS: {(r.stderr or r.stdout).strip()}")
    except subprocess.TimeoutExpired:
        errors.append(f"Timed out setting {family} primary DNS")
    except subprocess.SubprocessError as exc:
        errors.append(f"Failed to set {family} primary DNS: {exc}")

    # Set secondary
    if secondary and not errors:
        try:
            args = _netsh_args(
                "interface", context, "add", "dns", f"{addr_arg}={adapter}",
                secondary, "index=2", "validate=no",
            )
            r = _run(args, timeout=_DEFAULT_TIMEOUT)
            if r.returncode != 0:
                errors.append(
                    f"Failed to set {family} secondary DNS: {(r.stderr or r.stdout).strip()}"
                )
        except subprocess.TimeoutExpired:
            errors.append(f"Timed out setting {family} secondary DNS")
        except subprocess.SubprocessError as exc:
            errors.append(f"Failed to set {family} secondary DNS: {exc}")

    return errors


def _set_adapter_dns_static(adapter: str, primary: str, secondary: str) -> list[str]:
    """Apply a static DNS configuration (family inferred from ``primary``)."""
    family = _family_of(primary)
    return _set_adapter_dns_static_family(adapter, family, primary, secondary)


def _set_adapter_dns_dhcp(adapter: str) -> list[str]:
    """Reset ``adapter`` to obtain DNS automatically (DHCP) for both families."""
    log = get_logger()
    errors: list[str] = []

    for family in ("ipv4", "ipv6"):
        context = "ip" if family == "ipv4" else "ipv6"
        addr_arg = "name" if family == "ipv4" else "interface"
        try:
            _run(_netsh_args("interface", context, "delete", "dns",
                             f"{addr_arg}={adapter}", "all"),
                 timeout=_DEFAULT_TIMEOUT)
        except subprocess.TimeoutExpired:
            errors.append(f"Timed out clearing {family} DNS")
        except subprocess.SubprocessError as exc:
            errors.append(f"Failed to clear {family} DNS: {exc}")

        try:
            r = _run(_netsh_args("interface", context, "set", "dns",
                                 f"{addr_arg}={adapter}", "dhcp"),
                     timeout=_DEFAULT_TIMEOUT)
            if r.returncode != 0:
                # IPv6 is best-effort on adapters without IPv6.  IPv4 DHCP is
                # required for the "Auto (DHCP)" action to be considered done.
                if family == "ipv4":
                    errors.append(f"Failed to set {family} DHCP: {(r.stderr or r.stdout).strip()}")
                else:
                    log.debug("%s dhcp rc=%d stderr=%s", family, r.returncode, r.stderr)
        except subprocess.TimeoutExpired:
            if family == "ipv4":
                errors.append(f"Timed out setting {family} DHCP DNS")
            else:
                log.warning("Timed out setting IPv6 DHCP DNS")
        except subprocess.SubprocessError as exc:
            if family == "ipv4":
                errors.append(f"Failed to set {family} DHCP: {exc}")
            else:
                log.warning("Failed to set IPv6 DHCP: %s", exc)

    return errors


def _ip_key(value: str) -> "ipaddress.IPv4Address | ipaddress.IPv6Address | None":
    """Return the parsed IP object for comparison, or ``None`` if invalid.

    Using :mod:`ipaddress` means different textual representations of the
    same address (case, IPv6 zero-compression, leading zeros) compare equal,
    as they must.
    """
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _missing_expected(
    state: AdapterDnsState, expected: Iterable[str],
) -> tuple[list[str], list[str]]:
    """Family-aware comparison between the expected and the detected DNS.

    IPv4 expectations are matched *only* against the IPv4 list and IPv6
    expectations *only* against the IPv6 list.  In particular an empty IPv6
    configuration can never make an IPv4 verification fail, and vice versa.
    Order and textual representation are irrelevant.
    """
    cur4 = {k for k in (_ip_key(x) for x in state.ipv4) if k is not None}
    cur6 = {k for k in (_ip_key(x) for x in state.ipv6) if k is not None}
    missing4: list[str] = []
    missing6: list[str] = []
    for raw in expected:
        key = _ip_key(raw)
        if key is None:
            continue
        if key.version == 4:
            if key not in cur4:
                missing4.append(str(key))
        else:
            if key not in cur6:
                missing6.append(str(key))
    return missing4, missing6


def _format_servers(values: Iterable[str]) -> str:
    """Human-readable server list for log/status messages."""
    items = [v for v in values if v]
    return ", ".join(items) if items else "none"


def _verify(
    adapter: str, expected: list[str], sleep=time.sleep,
) -> tuple[bool, AdapterDnsState, str, dict]:
    """Re-read the adapter's DNS state and check that ``expected`` is present.

    Windows sometimes needs a moment before the freshly applied DNS
    configuration is reflected in read APIs, so this performs a short,
    strictly bounded series of read attempts (initial delay, then a growing
    backoff).  It never loops forever and never succeeds without the OS
    actually reporting the expected values.

    Returns ``(ok, state, message, details)``.  On failure ``details``
    contains a ``verification_failed`` code plus the adapter name and the
    expected/detected IPv4/IPv6 lists so the UI can show a clean, localised
    diagnostic instead of a raw string dump.
    """
    log = get_logger()
    expected_norm = [str(k) for k in (_ip_key(e) for e in expected) if k is not None]
    if not expected_norm:
        # Nothing to prove (shouldn't happen for a static apply, but never
        # manufacture a failure out of thin air).
        return True, read_dns(adapter), "verified", {}
    exp4 = [e for e in expected_norm if ":" not in e]
    exp6 = [e for e in expected_norm if ":" in e]

    state = AdapterDnsState(name=adapter)
    reliable = False
    delays = (_VERIFY_INITIAL_DELAY, *_VERIFY_RETRY_DELAYS)
    for attempt, delay in enumerate(delays):
        if delay > 0:
            sleep(delay)
        full = _read_dns_full(adapter)
        state = full.state
        reliable = full.reliable
        missing4, missing6 = _missing_expected(state, expected_norm)
        if not missing4 and not missing6:
            log.info(
                "verify: %r confirmed on attempt %d: ipv4=%s ipv6=%s",
                adapter, attempt + 1, state.ipv4, state.ipv6,
            )
            return True, state, "verified", {}
        log.debug(
            "verify attempt %d for %r: still missing ipv4=%s ipv6=%s (read_ok=%s)",
            attempt + 1, adapter, missing4, missing6, reliable,
        )

    details = {
        "code": "verification_failed",
        "adapter": adapter,
        "expected_ipv4": exp4,
        "expected_ipv6": exp6,
        "detected_ipv4": list(state.ipv4),
        "detected_ipv6": list(state.ipv6),
        "read_ok": reliable,
    }
    if not reliable:
        msg = (
            f"DNS verification failed for adapter {adapter!r}: unable to read "
            f"the adapter's DNS configuration back from Windows."
        )
    else:
        msg = (
            f"DNS verification failed for adapter {adapter!r}: Windows reports "
            f"IPv4 DNS ({_format_servers(state.ipv4)}) / IPv6 DNS "
            f"({_format_servers(state.ipv6)}), but IPv4 ({_format_servers(exp4)})"
            f" / IPv6 ({_format_servers(exp6)}) was requested."
        )
    log.error(msg)
    return False, state, msg, details


def _restore_backup_state(backup: AdapterDnsState | None) -> DnsResult:
    """Restore ``backup`` without acquiring the DNS lock (called internally)."""
    if not backup or not backup.name:
        return DnsResult(False, "No backup to restore", errors=["no backup"])

    if backup.is_dhcp or not (backup.ipv4 or backup.ipv6):
        errs = _set_adapter_dns_dhcp(backup.name)
    else:
        errs: list[str] = []
        if backup.ipv4:
            errs += _set_adapter_dns_static_family(
                backup.name, "ipv4", backup.ipv4[0],
                backup.ipv4[1] if len(backup.ipv4) > 1 else "",
            )
        if backup.ipv6:
            errs += _set_adapter_dns_static_family(
                backup.name, "ipv6", backup.ipv6[0],
                backup.ipv6[1] if len(backup.ipv6) > 1 else "",
            )
    if errs:
        return DnsResult(False, "; ".join(errs), backup=backup, errors=errs)
    return DnsResult(True, "Previous DNS configuration restored", backup=backup)


# ------------------------------------------------------------------ public API

def apply_static(adapter: str, primary: str, secondary: str) -> DnsResult:
    """Apply a static DNS configuration to ``adapter``.

    * Validates inputs (rejects invalid IPs early).
    * Backs up the current configuration.
    * Applies the change for the correct IP family only.
    * Verifies the result by re-reading the adapter state.
    * Returns a :class:`DnsResult` describing what happened.
    """
    log = get_logger()
    log.info("apply_static: adapter=%r primary=%r secondary=%r", adapter, primary, secondary)

    if not adapter or not adapter.strip():
        return DnsResult(False, "No network adapter selected", errors=["adapter empty"])

    p, s, errs = _validate_inputs(primary, secondary)
    if errs:
        log.error("apply_static: invalid input: %s", errs)
        return DnsResult(False, "Invalid DNS address", errors=errs)
    if not p:
        return DnsResult(False, "Primary DNS is required", errors=["no primary"])

    if not _DNS_LOCK.acquire(blocking=False):
        return DnsResult(
            False, "Another DNS operation is already running",
            errors=["DNS operation already running"],
        )

    try:
        backup = read_dns(adapter)
        log.info("backup: ipv4=%s ipv6=%s dhcp=%s", backup.ipv4, backup.ipv6, backup.is_dhcp)

        apply_errs = _set_adapter_dns_static(adapter, p, s)
        if apply_errs:
            log.error("apply_static: %s — restoring backup", apply_errs)
            restore_result = _restore_backup_state(backup)
            if not restore_result.success:
                log.error("restore after apply failure also failed: %s", restore_result.message)
            return DnsResult(
                False, "; ".join(apply_errs), backup=backup, errors=apply_errs,
            )

        ok, verified, msg, verify_details = _verify(adapter, [p] + ([s] if s else []))
        if not ok:
            log.error("apply_static: verification failed — restoring backup")
            _restore_backup_state(backup)
            return DnsResult(
                False, msg, backup=backup, verified=verified,
                errors=[msg], details=verify_details,
            )

        return DnsResult(True, "DNS applied and verified", backup=backup, verified=verified)
    finally:
        _DNS_LOCK.release()


def _verify_dhcp(
    adapter: str, backup: AdapterDnsState, sleep=time.sleep,
) -> tuple[bool, AdapterDnsState, str, dict]:
    """Verify that ``adapter`` really returned to automatic (DHCP) DNS.

    Unlike static verification we must not look for a specific address.
    Instead, this accepts the configuration when either:

    * ``netsh`` explicitly reports the "configured through DHCP" section, or
    * no *static* DNS section was detected **and** the adapter no longer
      holds exactly the static configuration it had before the change
      (a locale-independent cross-check — if the DHCP reset silently failed,
      the old static servers would still be there, and that is reported as
      a real failure).

    Uses the same bounded retry/backoff as :func:`_verify`.
    """
    log = get_logger()
    known_static = {
        k for k in (_ip_key(x) for x in (backup.ipv4 + backup.ipv6)) if k is not None
    }
    state = backup
    reliable = False
    delays = (_VERIFY_INITIAL_DELAY, *_VERIFY_RETRY_DELAYS)
    for attempt, delay in enumerate(delays):
        if delay > 0:
            sleep(delay)
        full = _read_dns_full(adapter)
        state = full.state
        reliable = full.reliable
        if full.v4_dhcp_marker:
            log.info("verify_dhcp: %r reports DHCP on attempt %d", adapter, attempt + 1)
            return True, state, "verified", {}
        if full.v4_static_marker:
            log.debug("verify_dhcp attempt %d for %r: still static", attempt + 1)
            continue
        current = {
            k for k in (_ip_key(x) for x in (state.ipv4 + state.ipv6)) if k is not None
        }
        if full.reliable and not (known_static and known_static == current):
            log.info(
                "verify_dhcp: %r has no static DNS after attempt %d (localized check)",
                adapter, attempt + 1,
            )
            return True, state, "verified", {}
        log.debug(
            "verify_dhcp attempt %d for %r: cannot confirm DHCP yet (read_ok=%s)",
            attempt + 1, adapter, full.reliable,
        )

    details = {
        "code": "dhcp_verification_failed",
        "adapter": adapter,
        "expected_ipv4": [],
        "expected_ipv6": [],
        "detected_ipv4": list(state.ipv4),
        "detected_ipv6": list(state.ipv6),
        "read_ok": reliable,
    }
    msg = (
        f"DHCP verification failed for adapter {adapter!r}: the adapter did "
        f"not switch back to automatic DNS (it still reports IPv4 "
        f"({_format_servers(state.ipv4)}) / IPv6 ({_format_servers(state.ipv6)}))."
    )
    log.error(msg)
    return False, state, msg, details


def apply_dhcp(adapter: str) -> DnsResult:
    """Reset ``adapter`` to obtain DNS automatically (DHCP).

    The operation is verified by re-reading the adapter state and only reports
    success when the adapter is actually back in DHCP mode (see
    :func:`_verify_dhcp`).
    """
    log = get_logger()
    log.info("apply_dhcp: adapter=%r", adapter)
    if not adapter or not adapter.strip():
        return DnsResult(False, "No network adapter selected", errors=["adapter empty"])

    if not _DNS_LOCK.acquire(blocking=False):
        return DnsResult(
            False, "Another DNS operation is already running",
            errors=["DNS operation already running"],
        )

    try:
        backup = read_dns(adapter)
        errs = _set_adapter_dns_dhcp(adapter)
        if errs:
            log.error("apply_dhcp: %s — restoring backup", errs)
            _restore_backup_state(backup)
            return DnsResult(False, "; ".join(errs), backup=backup, errors=errs)

        ok, state, msg, verify_details = _verify_dhcp(adapter, backup)
        if ok:
            return DnsResult(True, "Adapter set to automatic DNS (DHCP)",
                             backup=backup, verified=state)
        log.error(msg)
        _restore_backup_state(backup)
        return DnsResult(
            False, msg, backup=backup, verified=state,
            errors=[msg], details=verify_details,
        )
    finally:
        _DNS_LOCK.release()


def restore_backup(backup: AdapterDnsState) -> DnsResult:
    """Restore a previously captured :class:`AdapterDnsState`."""
    if not backup or not backup.name:
        return DnsResult(False, "No backup to restore", errors=["no backup"])

    if not _DNS_LOCK.acquire(blocking=False):
        return DnsResult(
            False, "Another DNS operation is already running",
            errors=["DNS operation already running"],
        )

    try:
        return _restore_backup_state(backup)
    finally:
        _DNS_LOCK.release()


# ------------------------------------------------------------------ ping (DNS test)

def ping_host(ip: str, count: int = 3, timeout_ms: int = 2000) -> int:
    """Return the average ICMP round-trip in milliseconds, or ``-1`` on failure.

    This is a *connectivity* test, **not** a *DNS resolution* test. A
    responsive IP address tells us the server is reachable; it does not
    prove that DNS queries will succeed.
    """
    log = get_logger()
    if not ip or not ip.strip():
        return -1
    try:
        # Use argument list (no shell)
        args = ["ping", "-n", str(count), "-w", str(timeout_ms), ip.strip()]
        timeout = max(15, count * timeout_ms / 1000 + 3)
        kwargs: dict = {
            "args": args, "shell": False,
            "capture_output": True, "text": True, "timeout": timeout,
        }
        if _is_windows():
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        r = subprocess.run(**kwargs)
        times: list[int] = []
        for line in (r.stdout or "").splitlines():
            l = line.strip().lower()
            for part in l.split():
                if part.startswith("time=") or part.startswith("time<"):
                    raw = part.replace("time=", "").replace("time<", "").replace("ms", "")
                    try:
                        times.append(int(float(raw)))
                    except ValueError:
                        pass
        if not times:
            return -1
        return sum(times) // len(times)
    except subprocess.TimeoutExpired:
        log.warning("ping_host: timeout pinging %s", ip)
        return -1
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("ping_host: error pinging %s: %s", ip, exc)
        return -1


def ping_color(ms: int) -> str:
    """Return a color name for the given latency, or ``"red"`` on timeout."""
    if ms < 0:
        return "red"
    if ms < 100:
        return "green"
    if ms <= 200:
        return "orange"
    return "red"


def ping_text(ms: int) -> str:
    if ms < 0:
        return "Timeout"
    return f"{ms}ms"


# ------------------------------------------------------------------ presets

def validate_preset(name: str, primary: str, secondary: str) -> tuple[str, str, str, list[str]]:
    """Validate a new preset. Returns ``(name, primary, secondary, errors)``."""
    errors: list[str] = []
    try:
        clean_name = sanitize_preset_name(name)
    except ValueError as exc:
        clean_name = ""
        errors.append(f"Invalid name: {exc}")
    p = ""
    s = ""
    if not primary or not primary.strip():
        errors.append("Primary DNS is required")
    elif not is_valid_dns(primary):
        errors.append("Primary DNS is not a valid IP address")
    else:
        try:
            p = normalize_dns(primary)
        except ValueError as exc:
            errors.append(f"Primary DNS: {exc}")
    if secondary and secondary.strip():
        if not is_valid_dns(secondary):
            errors.append("Secondary DNS is not a valid IP address")
        else:
            try:
                s = normalize_dns(secondary)
            except ValueError as exc:
                errors.append(f"Secondary DNS: {exc}")
    if p and s and p.lower() == s.lower():
        errors.append("Primary and secondary DNS must be different")
    if has_duplicates([p, s]):
        errors.append("Duplicate DNS entries")
    return clean_name, p, s, errors
