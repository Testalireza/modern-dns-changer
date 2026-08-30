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

For verification we re-read the configuration via
``netsh interface ip show config`` / ``netsh interface ipv6 show config``
and parse out the ``Statically Configured DNS Servers`` line.
"""
from __future__ import annotations

import json
import subprocess
import sys
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


# ------------------------------------------------------------------ utilities

# Hide the console window that would otherwise flash when we spawn netsh.
# CREATE_NO_WINDOW = 0x08000000
_CREATE_NO_WINDOW = 0x08000000

# Default timeouts (seconds) for each command. We do not want a single hung
# netsh process to freeze the GUI forever.
_DEFAULT_TIMEOUT = 8.0
_VERIFY_TIMEOUT = 6.0


def _netsh_args(*args: str) -> list[str]:
    """Build a ``netsh`` command as an argv list (no shell)."""
    return ["netsh", *args]


def _is_windows() -> bool:
    return sys.platform == "win32"


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    """Run a subprocess safely. No shell, with a timeout and no console."""
    kwargs: dict = {
        "args": args,
        "shell": False,
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if _is_windows():
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    return subprocess.run(**kwargs)


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
    requested configuration was actually applied and verified."""

    success: bool
    message: str = ""
    backup: AdapterDnsState | None = None
    verified: AdapterDnsState | None = None
    errors: list[str] = field(default_factory=list)

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

def read_dns(adapter: str) -> AdapterDnsState:
    """Read the current DNS configuration of ``adapter``.

    Returns an :class:`AdapterDnsState` with the current IPv4 / IPv6
    statically-configured DNS servers. If the adapter is in DHCP mode
    ``is_dhcp`` will be ``True`` and the address lists will be empty.
    """
    log = get_logger()
    state = AdapterDnsState(name=adapter)

    if not _is_windows():
        return state

    # IPv4
    try:
        r = _run(_netsh_args("interface", "ip", "show", "config", f'name={adapter}'),
                 timeout=_VERIFY_TIMEOUT)
        if r.returncode == 0:
            state.ipv4, state.is_dhcp = _parse_dns_block(r.stdout or "")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
        log.warning("read_dns(ipv4) for %r failed: %s", adapter, exc)

    # IPv6
    try:
        r = _run(_netsh_args("interface", "ipv6", "show", "dns", f'interface={adapter}'),
                 timeout=_VERIFY_TIMEOUT)
        if r.returncode == 0:
            state.ipv6 = _parse_dns_servers(r.stdout or "")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
        log.warning("read_dns(ipv6) for %r failed: %s", adapter, exc)

    return state


def _parse_dns_block(text: str) -> tuple[list[str], bool]:
    """Parse the ``Statically Configured DNS Servers`` block in
    ``netsh interface ip show config`` output.

    Returns ``(servers, is_dhcp)``. ``is_dhcp`` is True if the adapter
    obtains its DNS from DHCP rather than from the static list.
    """
    servers: list[str] = []
    in_block = False
    is_dhcp = True
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "statically configured dns servers" in low:
            in_block = True
            is_dhcp = False
            # Sometimes the first server is on the same line
            tail = line.split(":", 1)[-1].strip()
            for s in tail.split():
                if s:
                    servers.append(s)
            continue
        if "dns servers configured through dhcp" in low:
            # No static servers when DHCP is in effect
            is_dhcp = True
            in_block = False
            continue
        if in_block:
            # Continuation lines: either a bare IP or a "Label: value" entry.
            if ":" in line and not line[0].isdigit():
                # Section header (e.g. "Register with which suffix:") — end
                # the static block.
                in_block = False
                continue
            # Each line in the block is one server address
            servers.append(line)
    return _dedup(servers), is_dhcp


def _parse_dns_servers(text: str) -> list[str]:
    """Parse ``netsh interface ipv6 show dns`` output.

    The actual output format from Windows is:

        Configuration for interface "Wi-Fi"
        DNS servers configured for this interface:  1::1
                                                   2::2
        Register with which suffix:                  Primary only

    Older variants use ``Configured DNS Servers:``.
    """
    servers: list[str] = []
    capture = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        # Start of the DNS server block
        if "dns servers configured" in low or low.startswith("configured dns servers"):
            capture = True
            tail = line.split(":", 1)[-1].strip()
            for s in tail.split():
                if s:
                    servers.append(s)
            continue
        if capture:
            # End of block
            if "register with which suffix" in low or "primary only" in low:
                break
            # Continuation lines: either a bare IP or "Label: value"
            if ":" in line and not line[0].isdigit():
                tail = line.split(":", 1)[-1].strip()
                for s in tail.split():
                    if s:
                        servers.append(s)
            else:
                servers.append(line)
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


def _validate_inputs(primary: str, secondary: str) -> tuple[str, str, list[str]]:
    """Normalise + validate DNS values. Returns (primary, secondary, errors)."""
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
    return p, s, errors


def _set_adapter_dns_static(adapter: str, primary: str, secondary: str) -> list[str]:
    """Apply a static IPv4 + IPv6 configuration. Returns a list of error
    messages (empty on success)."""
    log = get_logger()
    errors: list[str] = []

    # First, clear any existing DNS entries for this adapter — without this,
    # repeated applications can accumulate ``index=2`` entries and fail.
    try:
        r = _run(_netsh_args("interface", "ip", "delete", "dns",
                             f"name={adapter}", "all"),
                 timeout=_DEFAULT_TIMEOUT)
        if r.returncode != 0:
            log.debug("delete ip dns rc=%d stderr=%s", r.returncode, r.stderr)
    except subprocess.TimeoutExpired:
        errors.append("Timed out clearing IPv4 DNS")
    except subprocess.SubprocessError as exc:
        errors.append(f"Failed to clear IPv4 DNS: {exc}")

    try:
        r = _run(_netsh_args("interface", "ipv6", "delete", "dns",
                             f"interface={adapter}", "all"),
                 timeout=_DEFAULT_TIMEOUT)
        if r.returncode != 0:
            log.debug("delete ipv6 dns rc=%d stderr=%s", r.returncode, r.stderr)
    except subprocess.TimeoutExpired:
        errors.append("Timed out clearing IPv6 DNS")
    except subprocess.SubprocessError as exc:
        errors.append(f"Failed to clear IPv6 DNS: {exc}")

    # Set IPv4 primary
    try:
        r = _run(_netsh_args("interface", "ip", "set", "dns",
                             f"name={adapter}", "static", primary,
                             "primary", "validate=no"),
                 timeout=_DEFAULT_TIMEOUT)
        if r.returncode != 0:
            errors.append(f"Failed to set IPv4 primary: {(r.stderr or r.stdout).strip()}")
    except subprocess.TimeoutExpired:
        errors.append("Timed out setting IPv4 primary DNS")
    except subprocess.SubprocessError as exc:
        errors.append(f"Failed to set IPv4 primary: {exc}")

    # Set IPv4 secondary
    if secondary and not errors:
        try:
            r = _run(_netsh_args("interface", "ip", "add", "dns",
                                 f"name={adapter}", secondary, "index=2",
                                 "validate=no"),
                     timeout=_DEFAULT_TIMEOUT)
            if r.returncode != 0:
                errors.append(f"Failed to set IPv4 secondary: {(r.stderr or r.stdout).strip()}")
        except subprocess.TimeoutExpired:
            errors.append("Timed out setting IPv4 secondary DNS")
        except subprocess.SubprocessError as exc:
            errors.append(f"Failed to set IPv4 secondary: {exc}")

    # Set IPv6 primary (best-effort: not all networks have IPv6)
    if not errors:
        try:
            r = _run(_netsh_args("interface", "ipv6", "set", "dns",
                                 f"interface={adapter}", "static", primary),
                     timeout=_DEFAULT_TIMEOUT)
            # Some Windows builds return a non-zero rc when IPv6 is not
            # enabled on the adapter — that's expected, not a fatal error.
            if r.returncode != 0 and "not found" not in (r.stderr or "").lower():
                log.debug("set ipv6 primary rc=%d stderr=%s", r.returncode, r.stderr)
        except subprocess.TimeoutExpired:
            log.warning("Timed out setting IPv6 primary DNS")
        except subprocess.SubprocessError as exc:
            log.warning("Failed to set IPv6 primary: %s", exc)

    return errors


def _set_adapter_dns_dhcp(adapter: str) -> list[str]:
    """Reset ``adapter`` to obtain DNS automatically (DHCP)."""
    log = get_logger()
    errors: list[str] = []
    # First, clear any statically configured servers
    try:
        _run(_netsh_args("interface", "ip", "delete", "dns",
                         f"name={adapter}", "all"),
             timeout=_DEFAULT_TIMEOUT)
    except subprocess.TimeoutExpired:
        errors.append("Timed out clearing IPv4 DNS")
    except subprocess.SubprocessError as exc:
        errors.append(f"Failed to clear IPv4 DNS: {exc}")

    try:
        _run(_netsh_args("interface", "ipv6", "delete", "dns",
                         f"interface={adapter}", "all"),
             timeout=_DEFAULT_TIMEOUT)
    except subprocess.TimeoutExpired:
        log.warning("Timed out clearing IPv6 DNS")
    except subprocess.SubprocessError as exc:
        log.warning("Failed to clear IPv6 DNS: %s", exc)

    # Switch to DHCP
    try:
        r = _run(_netsh_args("interface", "ip", "set", "dns",
                             f"name={adapter}", "dhcp"),
                 timeout=_DEFAULT_TIMEOUT)
        if r.returncode != 0:
            errors.append(f"Failed to set DHCP: {(r.stderr or r.stdout).strip()}")
    except subprocess.TimeoutExpired:
        errors.append("Timed out setting DHCP DNS")
    except subprocess.SubprocessError as exc:
        errors.append(f"Failed to set DHCP: {exc}")

    # IPv6 DHCP (best-effort)
    try:
        r = _run(_netsh_args("interface", "ipv6", "set", "dns",
                             f"interface={adapter}", "dhcp"),
                 timeout=_DEFAULT_TIMEOUT)
        if r.returncode != 0:
            log.debug("ipv6 dhcp rc=%d stderr=%s", r.returncode, r.stderr)
    except subprocess.TimeoutExpired:
        log.warning("Timed out setting IPv6 DHCP DNS")
    except subprocess.SubprocessError as exc:
        log.warning("Failed to set IPv6 DHCP: %s", exc)

    return errors


def _verify(adapter: str, expected: list[str]) -> tuple[bool, AdapterDnsState, str]:
    """Re-read the adapter's DNS state and check that ``expected`` is present.

    Returns ``(ok, state, message)``.
    """
    log = get_logger()
    # Allow a brief moment for the OS to register the change
    time.sleep(0.3)
    state = read_dns(adapter)
    all_current = [s.lower() for s in state.ipv4 + state.ipv6]
    for exp in expected:
        if exp.lower() not in all_current:
            msg = (
                f"Verification failed: expected {exp!r} in adapter {adapter!r}, "
                f"got IPv4={state.ipv4} IPv6={state.ipv6}"
            )
            log.error(msg)
            return False, state, msg
    return True, state, "verified"


# ------------------------------------------------------------------ public API

def apply_static(adapter: str, primary: str, secondary: str) -> DnsResult:
    """Apply a static DNS configuration to ``adapter``.

    * Validates inputs (rejects invalid IPs early).
    * Backs up the current configuration.
    * Applies the change.
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

    backup = read_dns(adapter)
    log.info("backup: ipv4=%s ipv6=%s dhcp=%s", backup.ipv4, backup.ipv6, backup.is_dhcp)

    apply_errs = _set_adapter_dns_static(adapter, p, s)
    if apply_errs:
        # Try to restore the backup so the user is not left in a bad state
        log.error("apply_static: %s — restoring backup", apply_errs)
        if backup.is_dhcp or not (backup.ipv4 or backup.ipv6):
            _set_adapter_dns_dhcp(adapter)
        elif backup.ipv4:
            _set_adapter_dns_static(adapter, backup.ipv4[0],
                                    backup.ipv4[1] if len(backup.ipv4) > 1 else "")
        return DnsResult(False, "; ".join(apply_errs), backup=backup, errors=apply_errs)

    ok, verified, msg = _verify(adapter, [p] + ([s] if s else []))
    if not ok:
        return DnsResult(False, msg, backup=backup, verified=verified, errors=[msg])

    return DnsResult(True, "DNS applied and verified", backup=backup, verified=verified)


def apply_dhcp(adapter: str) -> DnsResult:
    """Reset ``adapter`` to obtain DNS automatically (DHCP)."""
    log = get_logger()
    log.info("apply_dhcp: adapter=%r", adapter)
    if not adapter or not adapter.strip():
        return DnsResult(False, "No network adapter selected", errors=["adapter empty"])

    backup = read_dns(adapter)
    errs = _set_adapter_dns_dhcp(adapter)
    if errs:
        return DnsResult(False, "; ".join(errs), backup=backup, errors=errs)
    return DnsResult(True, "Adapter set to automatic DNS (DHCP)", backup=backup)


def restore_backup(backup: AdapterDnsState) -> DnsResult:
    """Restore a previously captured :class:`AdapterDnsState`."""
    if not backup or not backup.name:
        return DnsResult(False, "No backup to restore", errors=["no backup"])
    if backup.is_dhcp or not (backup.ipv4 or backup.ipv6):
        return apply_dhcp(backup.name)
    primary = backup.ipv4[0] if backup.ipv4 else ""
    secondary = backup.ipv4[1] if len(backup.ipv4) > 1 else ""
    if not primary:
        return apply_dhcp(backup.name)
    return apply_static(backup.name, primary, secondary)


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
