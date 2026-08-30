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
- **IPv4 + IPv6** — configures both address families
- **Custom DNS presets** — saved to `presets.json` (name + primary + secondary)
- **Backup & verification** — the previous DNS configuration is backed up
  before changes are applied, and the new state is re-read from Windows
  before reporting success
- **Hotkey toggle** — switch between Preset A and B with a key combination
  while the app is focused
- **Settings panel** — hotkey, A/B presets, theme, language, system tray
- **System tray** — minimize to tray, restore, toggle DNS, quit
- **Dark & Light** — auto-detects the Windows app theme on first launch
- **English & Persian** — full UI translation with RTL support
- **Windows 11 native styling** — Mica backdrop, dark title bar, rounded corners
- **Auto-elevate to Admin** — required for DNS changes; requested via UAC
- **Download Updated Repository** — in-app button that fetches the latest
  source ZIP from GitHub so you can sync your local copy of the project
- **Structured logging** — to `modern_dns_changer.log` (rotated, thread-safe)

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
├── storage.py           # Atomic JSON read/write
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
| Multiple adapters       | ✅ — pick from a sorted list              |
| Wi-Fi                   | ✅                                         |
| Ethernet                | ✅                                         |
| Virtual adapters        | ⚠️ Filtered out by `Get-NetAdapter -Physical` |
| Pre-change backup       | ✅ — `presets.json` & in-memory snapshot  |
| Post-change verification| ✅ — re-reads the adapter state           |
| Timeouts on every netsh | ✅ — 6–8 s per command                    |
| DNS server validation   | ✅ — rejects invalid IPs before applying  |

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

## License

MIT — see [LICENSE](LICENSE) if present, otherwise the standard MIT terms
apply.

---

Modern DNS Changer v4.1 — © 2026 Testalireza
