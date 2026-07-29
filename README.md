# Modern DNS Changer

A modern Windows 11 DNS changer desktop app with dark/light mode, English/Persian language support, and a system tray icon.

![Release](https://img.shields.io/github/v/release/Testalireza/modern-dns-changer)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **One-click DNS switching** — Change DNS for your WiFi adapter instantly using silent `netsh` commands
- **Custom DNS presets** — Save preferred + secondary DNS combos with custom names
- **Hotkey toggle** — Switch between two selected presets with a keyboard shortcut (works when app is focused)
- **Settings panel** — Configure hotkey, select Preset A/B for toggle, theme, language, and tray
- **System tray icon** — Minimize to tray, toggle DNS from the tray menu
- **Dark & Light mode** — Auto-detects Windows theme on first launch, switchable in Settings
- **English & Persian** — Full UI translation with RTL support for Persian
- **Windows 11 styling** — Mica backdrop, dark title bar, rounded corners
- **Auto-elevate** — Requests admin privileges automatically (required for DNS changes)
- **Compact layout** — Everything fits in the window without scrolling

## Download

Download the latest `.exe` from [Releases](https://github.com/Testalireza/modern-dns-changer/releases):

- **ModernDNSChanger.exe** — standalone executable, no Python needed
- Double-click to run (will prompt for admin access via UAC)
- ~19 MB

### Windows Defender False Positive

Windows Defender may flag the `.exe` as `Trojan:Win32/Wacatac.B!ml`. This is a **false positive** — the `!ml` suffix means it was flagged by a machine-learning heuristic, not by finding actual malware. PyInstaller-built apps commonly trigger this because they run `netsh` commands, request admin elevation, and hook keyboard events — all legitimate for a DNS changer but suspicious to an AI.

**To resolve:** Add an exclusion in Windows Security → Virus & threat protection → Manage settings → Add or remove exclusions. Or run from source (see below).

## Quick Start (Python)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run as Administrator:
   ```bash
   python main.py
   ```

Or right-click `run.ps1` → "Run with PowerShell" (auto-elevates to Admin).

## Building the .exe (Windows)

```powershell
pip install -r requirements.txt
pip install pyinstaller
python generate_icon.py
pyinstaller build.spec --clean --noconfirm
```

Your standalone `.exe` will be in `dist\ModernDNSChanger.exe`.

The .exe:
- Runs with **no console window** (GUI only)
- **Auto-requests admin elevation** on launch (UAC prompt)
- Includes the app icon
- Supports system tray, dark/light mode, and English/Persian

## Hotkey Setup

The hotkey works **when the app window is focused** (not globally).

1. Open **Settings** (gear icon in the header)
2. In the **Toggle Hotkey** section:
   - Type a key combo in the text field (e.g. `F9`, `ctrl+d`, `ctrl+shift+d`)
   - Or click a quick-pick button (F5–F10, ctrl+d, ctrl+shift+d)
   - Click **Save**
3. In the **Toggle Presets (A/B)** section:
   - Select **Preset A** from the dropdown
   - Select **Preset B** from the dropdown
   - Click **Save A/B**
4. Now pressing the hotkey while the app is focused toggles between A and B

## System Tray

- Closing the window sends it to the system tray (can be disabled in Settings)
- Right-click the tray icon to: Show app, Toggle DNS, or Quit

## Settings

Open the Settings panel (gear button in the header) to configure:
- **Appearance** — Dark / Light mode
- **Language** — English / Persian (فارسی)
- **Toggle Hotkey** — Set the key combo + select Preset A and B
- **System Tray** — Enable/disable minimize-to-tray
- **About** — App info

## Project Structure

```
modern-dns-changer/
├── main.py              # Main application
├── translations.py      # English & Persian translations
├── build.spec           # PyInstaller build configuration
├── build.ps1            # Windows build script
├── run.ps1              # Run script (auto-elevates to admin)
├── generate_icon.py     # Generates the app .ico icon
├── requirements.txt     # Python dependencies
├── presets.json         # Saved DNS presets (auto-generated)
├── settings.json        # Settings (auto-generated)
└── icon.ico             # App icon (auto-generated)
```

## Requirements

- Windows 10/11 (uses `netsh` for DNS changes)
- Administrator privileges (auto-requested on launch)
- Python 3.8+ (or use the .exe build)

## License

MIT — do whatever you want with it.
