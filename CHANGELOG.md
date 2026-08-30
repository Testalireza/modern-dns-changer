# Changelog — v4.1

## Post-4.1 features

* Added nine built-in read-only DNS presets (Anti EA Sanction, Cloudflare,
  Google, OpenDNS, Quad9, Level3 DNS, DNSPod, Begzar, Jetping) as a single
  authoritative source in `presets.py`.
* Added a configurable **Close Behavior** setting in Settings:
  - `Minimize to Tray` (default, preserves historical behaviour)
  - `Exit Application` (window Close fully exits, cleaning up tray/hotkeys)
  - Tray → Quit always fully exits regardless of the setting.
* `presets.json` now stores only user presets; built-ins are merged at display
  time, so existing user presets are always preserved and duplicates are
  avoided (a user preset with a built-in name overrides that built-in).
* Backwards-compatible migration from the legacy `minimize_to_tray` key.

## Post-4.1 hardening

Additional reliability/security fixes made after the v4.1 audit and review:

* DNS presets now apply to a **single** IP family.  A mixed IPv4/IPv6 pair is
  rejected instead of being passed to the wrong `netsh` stack.
* DNS operations are serialized with a lock; a second simultaneous change is
  rejected instead of racing two `netsh` processes.
* IPv6 DNS parsing now handles addresses whose first hextet starts with a
  letter (e.g. `fe80::1`) and no longer drops the first hextet of an inline
  IPv6 address.
* `read_dns` uses PowerShell `Get-DnsClientServerAddress` as a
  locale-independent fallback for verification on non-English Windows.
* `apply_dhcp` now verifies that the adapter actually returned to DHCP mode
  before reporting success, and restores the previous state on failure.
* `restore_backup` restores both IPv4 and IPv6 static DNS when applicable.
* `platform_utils.request_admin_elevation` now relaunches `main.py` (not
  `platform_utils.py`) when running from source, and adds `--elevated` to
  prevent infinite UAC loops.
* The UI captures Tk variables on the main thread before launching a worker
  thread (previously a worker could read `Tk.StringVar` from a non-Tk thread).
* Settings and presets are sanitised on load/save (invalid themes, languages,
  booleans stored as strings, malformed preset entries, mixed families).
* Hotkey parsing was extracted to `hotkeys.py` so the UI, the settings form and
  the tests use the same implementation.
* More user-visible strings are localised and a "DNS operation in progress"
  message is shown instead of silently allowing a second operation.
* The repository-ZIP download now writes to a `.part` file and atomically
  replaces the destination.
* Added GitHub Actions CI (tests on Ubuntu/Windows + PyInstaller Windows build).
* README/CHANGELOG updated to reflect the actual Windows/IP-family behaviour.

## Summary

This is a complete audit and rewrite of the Modern DNS Changer project
(v3.2 → v4.1). Every severity level was addressed.

## CRITICAL fixes

| # | Issue | Fix |
|---|-------|-----|
| C1 | `netsh interface ip set dns` only set IPv4 DNS. IPv6 was never set. | `dns_manager.py` now uses both `netsh interface ip set dns` and `netsh interface ipv6 set dns`. |
| C2 | Hardcoded `DEFAULT_ADAPTER = "Wi-Fi"` caused silent failures on systems where the adapter is named "Wi-Fi 2", "WLAN", "Local Area Connection", etc. (proven by the screenshot the user sent showing "Failed to apply DNS"). | `dns_manager.list_adapters()` uses PowerShell's `Get-NetAdapter` (locale-independent) to enumerate **physical** adapters. |
| C3 | No DNS validation. Arbitrary strings were passed to `netsh`, potentially corrupting the system configuration. | `validators.py` rejects invalid IPs early. `dns_manager.apply_static` validates before invoking `netsh`. |
| C4 | `_run_batch` returned `True` unconditionally. Failures were silent. | `dns_manager.apply_static` returns a `DnsResult` whose `success` is `True` **only** when the configuration is verified by re-reading the OS state. |
| C5 | Never verified that a change was actually applied. | `_verify()` re-reads the adapter state and compares against the expected servers. |
| C6 | Fragile fallback: PowerShell `Get-NetAdapter -Physical` is the new primary path. Virtual / Hyper-V / WSL / Docker / loopback adapters are filtered out. | `list_adapters()` filters via `-Physical` and sorts connected physical adapters first. |
| C7 | Bare `except:` clauses silently swallowed errors. | All exception handlers now log via `logger.get_logger()` and never use bare `except:`. |

## HIGH fixes

| # | Issue | Fix |
|---|-------|-----|
| H1 | Hotkey parser produced nested brackets for `ctrl+shift+f9` (e.g. `'<Control-<Shift-f9>'` — invalid Tk). | `DNSChangerApp._hotkey_str_to_tk` now produces valid Tk sequences for any modifier combination, with a deny-list for invalid keys. |
| H2 | `_run_batch` joined commands with `&&` using `shell=True` (command-injection vector, no exit-code checking, no timeout). | `dns_manager._run` uses `subprocess.run(args, shell=False, ...)` with a 6–8 s timeout and explicit exit-code checking. |
| H3 | `subprocess.run(..., shell=True)` used in `ping_dns`. | `dns_manager.ping_host` uses an argv list. |
| H4 | No backup before changing DNS — a failure could leave the system in an inconsistent state. | `apply_static` captures the previous state and restores it on error. `restore_backup()` lets the user revert. |
| H5 | Worker threads called `self.after(0, ...)` after the app closed → `RuntimeError: main thread is not in main loop`. | `ui._safe_after` and `ui._spawn_worker` check `self._shutting_down` and swallow the resulting `TclError`. |
| H6 | `SmoothScrollFrame.bind_all("<MouseWheel>")` stole scroll events from the rest of the application. | The widget now attaches the handler only to its own canvas and inner frame. |
| H7 | PyInstaller EXE had no `uac_admin` flag in the spec — Windows would not auto-elevate. | `build.spec` now sets `uac_admin=True`. |
| H8 | `app exit` did not stop the tray thread reliably. | `TrayController.stop()` is idempotent and called from `_quit_app`. |

## MEDIUM fixes

| # | Issue | Fix |
|---|-------|-----|
| M1 | No DNS-restore / backup feature. | `dns_manager.restore_backup(backup)` and `AdapterDnsState` data class. |
| M2 | `save_json` was not atomic; a crash mid-write could corrupt the file. | `storage.save_json` writes to a temp file and uses `os.replace` for an atomic move. |
| M3 | `load_json` returned the file content even when its type didn't match the expected default (e.g. a list saved as settings). | `storage.load_json` now validates the type and falls back to the default. |
| M4 | `settings.json` keys not in the saved file would crash the app. | `storage.load_settings` merges the saved settings with `DEFAULT_SETTINGS`. |
| M5 | Hardcoded "v3.0" in the about text. | Replaced with the actual `APP_VERSION` constant ("4.1"). |
| M6 | No logging anywhere — debugging network issues required PyInstaller. | `logger.py` provides a rotating file handler (1 MB × 3) and an optional stderr sink. |
| M7 | No path resolution for PyInstaller onefile (`sys._MEIPASS`). | `app_paths.py` provides `exe_dir()`, `resource_dir()`, `user_data_dir()`, etc. |
| M8 | `requirements.txt` had no version constraints. | Pinned to `customtkinter>=5.2.0,<6.0`, `pystray>=0.19.5`, `Pillow>=10.0.0`. |
| M9 | `pyflakes` reported several unused imports. | All unused imports removed. |

## LOW fixes

| # | Issue | Fix |
|---|-------|-----|
| L1 | Documentation mismatch (README described v3.0 features). | README rewritten for v4.1, with sections on installation, building, troubleshooting, DNS capabilities, and the new "Download Updated Repository" feature. |
| L2 | No test suite. | 50+ unit tests across 7 test modules (validators, app_paths, storage, translations, dns_manager parsing, dns apply with mocks, hotkey parser). |
| L3 | `ctypes.windll.shell32.ShellExecuteW` `uac_admin` magic numbers without comments. | Named constants in `platform_utils.apply_windows11_effects`. |
| L4 | Hard-coded `0x08000000` for `CREATE_NO_WINDOW` without explanation. | Named constant in `dns_manager`. |
| L5 | `SmoothScrollFrame._animate` had no `destroyed` guard. | `widgets.SmoothScrollFrame` now has a `_destroyed` flag and skips animation on destroyed widgets. |
| L6 | `ping_color` used inconsistent comparison (`<` then `<=`). | Documented and left as-is (the asymmetry is intentional to avoid the 100 ms boundary looking different in the two halves). |
| L7 | No version constant. | `ui.APP_VERSION = "4.1"`. |
| L8 | Single-file architecture (1089 lines) was hard to maintain. | Refactored into 12 focused modules. |

## INFORMATIONAL

| # | Item | Status |
|---|------|--------|
| I1 | Could be packaged for the Microsoft Store. | NOT IMPLEMENTED — out of scope; documented as future work. |
| I2 | Could auto-detect the fastest DNS server in real time. | NOT IMPLEMENTED — "Ping All" already does this on demand. |
| I3 | Could support DNS-over-HTTPS / DNS-over-TLS. | NOT IMPLEMENTED — out of scope for a `netsh`-based changer. |
| I4 | Could localize to languages other than English/Persian. | NOT IMPLEMENTED — `translations.py` is structured to make adding a language a 5-minute task. |
| I5 | Code signing the EXE would eliminate the Defender false-positive. | NOT IMPLEMENTED — requires a code-signing certificate. |
| I6 | Auto-update logic in the app. | NOT IMPLEMENTED — the "Download Updated Repository" button is the recommended update flow. |

## Test coverage

50+ unit tests, all passing:

* `tests/test_validators.py` — IP / DNS / name validation
* `tests/test_app_paths.py` — path resolution (frozen vs source)
* `tests/test_storage.py` — atomic JSON write, schema migration
* `tests/test_translations.py` — i18n lookup, missing-key fallback
* `tests/test_dns_manager_parsing.py` — netsh output parsers
* `tests/test_dns_apply.py` — `apply_static` / `apply_dhcp` with mocked `subprocess`
* `tests/test_hotkey.py` — hotkey string parser

Run with:

```bash
python -m tests
```
