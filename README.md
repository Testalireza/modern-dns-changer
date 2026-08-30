# Modern DNS Changer v4.1

A modern Windows 11 DNS changer with dark/light mode, English & Persian
translations, system tray, in-app "Download Updated Repository" button, and
robust IPv4 + IPv6 handling.

![Release](https://img.shields.io/github/v/release/Testalireza/modern-dns-changer)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## Features

- **One-click DNS switching** for any physical network adapter
- **IPv4 or IPv6** — each preset always applies to a single IP family, which
  is what Windows actually permits per stack
- **Built-in DNS presets** — Anti EA Sanction, Cloudflare, Google, OpenDNS,
  Quad9, Level3 DNS, DNSPod, Begzar and Jetping (read-only, shown first)
- **Custom DNS presets** — saved to `presets.json` (name + primary + secondary)
- **Backup & verification** — the previous DNS configuration is backed up
  before changes are applied, and the new state is re-read from Windows
  before reporting success
- **Hotkey toggle** — switch between Preset A and B with a key combination
  while the app is focused
- **Settings panel** — hotkey, A/B presets, theme, language, close behavior
- **System tray** — minimize to tray, restore, toggle DNS, quit
- **Configurable close behavior** — Close (X) either minimizes to tray or
  fully exits; tray → Quit always fully exits
- **Dark & Light** — auto-detects the Windows app theme on first launch
- **English & Persian** — full UI translation with RTL support
- **Windows 11 native styling** — Mica backdrop, dark title bar, rounded corners
- **Auto-elevate to Admin** — required for DNS changes; requested via UAC
- **Download Updated Repository** — in-app button that fetches the latest
  source ZIP from GitHub so you can sync your local copy of the project
- **Structured logging** — to `modern_dns_changer.log` (rotated, thread-safe)
- **Operation serialization** — a second DNS change is rejected instead of
  two `netsh` commands racing each other

## Download

The latest standalone `.exe` is published on the
[Releases page](https://github.com/Testalireza/modern-dns-changer/releases):

- **`ModernDNSChanger.exe`** — fully self-contained, ~20 MB
- Double-click to run (UAC prompt will appear for admin elevation)
- No Python install required

### Windows Defender False Positive

Some Windows Defender builds flag the EXE as `Wacatac.B!ml` — a generic
machine-learning detection, not a real malware signature. PyInstaller
EXEs commonly trigger this because they invoke `netsh`, request admin
elevation, and hook keyboard events — all legitimate for a DNS changer.

**To resolve:** add an exclusion in *Windows Security → Virus & threat
protection → Manage settings → Add or remove exclusions*, or run from
source (instructions below).

## Quick Start (Python)

1. Install Python 3.10 or newer.
2. From the project directory:
   ```bash
   pip install -r requirements.txt
   python main.py
   ```
   The app will auto-elevate to Administrator via UAC.
3. Or right-click `run.ps1` → "Run with PowerShell" (auto-elevates).

## Building the EXE (Windows)

You have three options. All of them produce
`dist\ModernDNSChanger.exe`.

### Option A — one-liner

```bat
build.bat --install --clean
```

### Option B — PowerShell

```powershell
.\build.ps1 -Install -Clean
```

### Option C — manual PyInstaller

```powershell
pip install -r requirements.txt
pip install pyinstaller
python generate_icon.py
pyinstaller build.spec --clean --noconfirm
```

The result is `dist\ModernDNSChanger.exe`. Copy it anywhere — the app is
fully portable. `presets.json`, `settings.json`, and the log file are
created next to the EXE.

## Project Structure

```
modern-dns-changer/
├── main.py              # Entry point: logging, elevation, app boot
├── ui.py                # Main window, settings window, all widgets
├── dns_manager.py       # netsh wrapper, IPv4+IPv6, backup & verify
├── platform_utils.py    # Admin check, Win11 effects, DPI awareness
├── validators.py        # IP/DNS validation
├── presets.py           # Built-in DNS presets (single source of truth)
├── storage.py           # Atomic JSON read/write
├── hotkeys.py           # Shared hotkey parser (UI + tests)
├── tray.py              # System-tray controller
├── widgets.py           # SmoothScrollFrame
├── logger.py            # Rotating log handler
├── app_paths.py         # PyInstaller-aware path resolution
├── translations.py      # English & Persian
├── generate_icon.py     # icon.ico / icon.png generator
├── build.spec           # PyInstaller spec
├── build.bat            # Windows batch build script
├── build.ps1            # PowerShell build script
├── run.ps1              # Run-as-admin script
├── requirements.txt     # Python dependencies
├── icon.ico             # App icon (regenerable)
└── icon.png             # PNG version of the icon
```

## How "Download Updated Repository" Works

The button in the main window fetches the GitHub repository as a ZIP
archive and saves it next to the application (typically
`modern-dns-changer-main.zip`). You can then:

1. Extract the ZIP.
2. Replace the files in your local clone.
3. `git add -A && git commit -m "sync v4.1" && git push`.

The URL used is a fixed, hardcoded pointer to the
[GitHub repository archive](https://codeload.github.com/),
so the EXE does not embed any third-party download links or controlled
binaries. The download is performed by Python's standard
`urllib.request` — no extra dependency required.

> **Note:** The ZIP is fetched over HTTPS directly from `codeload.github.com`,
> the same infrastructure used by GitHub's own "Download ZIP" button.
> The application does not execute anything from the downloaded archive.

## DNS Functionality

| Capability              | Status                                    |
|-------------------------|-------------------------------------------|
| IPv4 manual             | ✅                                         |
| IPv4 automatic (DHCP)   | ✅                                         |
| IPv6 manual             | ✅ (best-effort, when adapter has IPv6)   |
| IPv6 automatic (DHCP)   | ✅ (best-effort)                          |
| IPv4+IPv6 in one preset | ⚠️ Not supported — presets are single-family |
| Multiple adapters       | ✅ — pick from a sorted list              |
| Wi-Fi                   | ✅                                         |
| Ethernet                | ✅                                         |
| Virtual adapters        | ⚠️ Filtered out by `Get-NetAdapter -Physical` |
| Pre-change backup       | ✅ — in-memory snapshot                   |
| Post-change verification| ✅ — re-reads the adapter state           |
| Timeouts on every netsh | ✅ — 8 s per command                      |
| DNS server validation   | ✅ — rejects invalid/non-unicast IPs       |
| Concurrent-op protection| ✅ — a second DNS change is rejected       |

> Because Windows keeps the IPv4 and IPv6 DNS stacks separate, each preset
> stores one **primary** and one **secondary** server of the **same** IP family
> (either both IPv4 or both IPv6). To configure the other family, create a
> second preset and apply it separately.

## Built-in DNS Presets

The application ships the following presets (shown as read-only **Built-in**
entries at the top of the preset list).  They are not affiliated with or
endorsed by this application and are provided only as convenient presets.

| Name             | Primary DNS   | Secondary DNS    |
|------------------|---------------|------------------|
| Anti EA Sanction | 94.183.166.199| 94.183.166.195   |
| Cloudflare       | 1.1.1.1       | 1.0.0.1          |
| Google           | 8.8.8.8       | 8.8.4.4          |
| OpenDNS          | 208.67.222.222| 208.67.220.220   |
| Quad9            | 9.9.9.9       | 149.112.112.112  |
| Level3 DNS       | 4.2.2.1       | 4.2.2.2          |
| DNSPod           | 119.29.29.29  | 182.254.116.116  |
| Begzar           | 185.55.226.26 | 185.55.225.25    |
| Jetping          | 78.47.226.179 | 188.245.125.175  |

Built-in presets are read-only in the UI so they cannot be accidentally
deleted or duplicated.  A custom preset with the same name as a built-in
(e.g. an existing user `Cloudflare`) is treated as user data and is preserved
at that name instead of duplicating the built-in entry.

## Close Behavior

The **Close Behavior** setting in *Settings → Close Behavior* controls what
happens when you press the normal window Close (X) button:

- **Minimize to Tray** (default) — the window hides to the system tray and the
  application keeps running.  Use the tray icon to restore, toggle DNS, or quit.
- **Exit Application** — the window closes and the application fully exits,
  cleaning up the tray icon, hotkeys and background workers.

> **Tray → Quit always fully exits the application**, regardless of the Close
> Behavior setting.  The close-behavior setting never turns the tray's explicit
> Quit into a hide.

The choice is persisted in `settings.json` (`close_behavior`).  Older settings
files that only contain `minimize_to_tray` are migrated automatically; the
historical default (minimize to tray) is used when neither key is meaningful.

## Requirements

- **OS:** Windows 10 / 11 (uses `netsh` and PowerShell `Get-NetAdapter`)
- **Privileges:** Administrator (auto-requested at launch)
- **Python** (only for running from source): 3.10 or newer
- **Disk:** ~50 MB while building, ~20 MB for the final EXE

## Troubleshooting

| Problem                                              | Fix                                                                                  |
|------------------------------------------------------|--------------------------------------------------------------------------------------|
| `Failed to apply DNS`                                | Run as Administrator; the app already shows a banner asking you to restart elevated |
| Adapter is "Wi-Fi 2" / "Local Area Connection"       | The dropdown lists every physical adapter; pick the connected one                    |
| Windows Defender flagged the EXE                     | Add an exclusion (see above) — false positive                                       |
| Hotkey does nothing                                  | The app must be focused. Click on the window first, then press the key              |
| `python` is not found                                | Install Python 3.10+ and tick *Add to PATH* during install                          |
| `pyinstaller` is not found                           | `pip install pyinstaller`                                                            |
| The app is in the wrong language                     | Settings → Language                                                                  |
| I see only "(no presets)"                            | Add a preset using the form at the bottom of the main window                        |
| The app cannot restart as Admin                      | UAC was cancelled. Right-click the `.exe`/`main.py` → *Run as administrator*        |
| I get "Another DNS operation is already running"     | Wait a moment; DNS changes are deliberately serialized so two `netsh` commands cannot race |

## Automated Testing

Run the unit tests from the repository root:

```bash
python -m tests
```

The suite covers DNS validation, the built-in preset list and merge
behaviour, close-behaviour migration, tray lifecycle, `netsh` output parsing
(including IPv6), `apply_static` / `apply_dhcp` with mocked subprocesses,
configuration sanitisation, hotkey parsing, translations and path resolution.
The tests never change the machine's real DNS settings.

CI (`.github/workflows/ci.yml`) runs the suite on Windows and Ubuntu for
Python 3.10/3.12, and builds the Windows `.exe` with PyInstaller on every PR.

## Known Limitations

- **IPv4 + IPv6 in one preset is not supported.**  Windows keeps the DNS
  configuration for each stack separate, so a preset is either IPv4 or IPv6.
- **`netsh` output is localised on non-English Windows.**  The app uses
  PowerShell `Get-DnsClientServerAddress` as a locale-independent fallback for
  *verification*, while continuing to use `netsh` (which is parser-based) to
  detect DHCP vs static.  On heavily-localised systems, a static preset that
  Windows refuses to set could occasionally be reported more conservatively.
- **Not tested on a real Windows machine in this environment.**  DNS changes,
  UAC, tray notifications and the packaged `.exe` require a Windows 10/11
  machine and cannot be exercised from the sandbox that produced this PR.  The
  Windows build is validated in CI where a Windows runner is available.
- **Portable data location.**  `presets.json`, `settings.json` and the log file
  are stored next to the application, which keeps the `.exe` portable.  If you
  put the `.exe` in a read-only directory such as `C:\Program Files`, settings
  will not persist unless the app has write access there.

## License

MIT — see [LICENSE](LICENSE) if present, otherwise the standard MIT terms
apply.

---

Modern DNS Changer v4.1 — © 2026 Testalireza
