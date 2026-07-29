# Modern DNS Changer

A modern Windows 11 DNS changer desktop app with dark/light mode, English/Persian language support, and a system tray icon.

## ✨ Features

- **One-click DNS switching** — Change DNS for your WiFi adapter instantly (silent `netsh` commands)
- **Custom DNS presets** — Save preferred + secondary DNS combos with custom names
- **Global hotkey toggle** — Switch between two selected presets with a keyboard shortcut (default: `Ctrl+Shift+D`)
- **System tray icon** — Minimize to tray, toggle DNS from the tray menu, restore with one click
- **Dark & Light mode** — Switch between dark navy and light themes in Settings
- **English & Persian** — Full UI translation with RTL support for Persian (فارسی)
- **Settings panel** — Theme, language, tray, and hotkey all configurable in one place
- **Windows 11 native styling** — Mica backdrop, dark title bar, rounded corners
- **Auto-elevate** — Requests admin privileges automatically (required for DNS changes)
- **Auto-detects WiFi adapter** — Prioritizes wireless adapters

## 🚀 Quick Start (Python)

1. Install dependencies:
   ```bash
   pip install customtkinter keyboard pystray pillow
   ```

2. Run as Administrator:
   ```bash
   python main.py
   ```

Or right-click `run.ps1` → "Run with PowerShell" (auto-elevates to Admin).

## 📦 Build .exe (Windows 11)

1. Install build dependencies:
   ```powershell
   pip install customtkinter keyboard pyinstaller pillow pystray
   ```

2. Generate the app icon:
   ```powershell
   python generate_icon.py
   ```

3. Build the .exe:
   ```powershell
   ./build.ps1
   ```

4. Your standalone `.exe` will be in `dist\ModernDNSChanger.exe`

The .exe:
- Runs with **no console window** (GUI only)
- **Auto-requests admin elevation** on launch (UAC prompt)
- Includes the app icon
- Supports **system tray**, **dark/light mode**, and **English/Persian**
- Can be copied anywhere — no Python needed

## 📁 Project Structure

```
modern-dns-changer/
├── main.py              # Main application
├── translations.py      # English & Persian translations
├── build.spec           # PyInstaller build configuration
├── build.ps1            # Windows build script
├── run.ps1              # Run script (auto-elevates to admin)
├── generate_icon.py     # Generates the app .ico icon
├── requirements.txt     # Python dependencies
├── presets.json          # Saved DNS presets (auto-generated)
├── settings.json         # Settings: theme, language, hotkey (auto-generated)
└── icon.ico             # App icon (auto-generated)
```

## ⌨️ Hotkey Setup

1. Add at least 2 DNS presets
2. In the "Toggle Hotkey" section, select **Preset A** and **Preset B**
3. Set your hotkey (default: `ctrl+shift+d`)
4. Click "Save Hotkey"
5. Now pressing the hotkey anywhere on your PC toggles between the two presets

## 📱 System Tray

- Closing the window sends it to the system tray (can be disabled in Settings)
- Right-click the tray icon to: Show app, Toggle DNS, or Quit
- The hotkey works even when the app is in the tray

## 🎨 Settings

Open the Settings panel (⚙ button in the header) to configure:
- **Appearance**: Dark Mode / Light Mode
- **Language**: English / Persian (فارسی)
- **System Tray**: Enable/disable minimize-to-tray
- **About**: App info

## ⚠️ Requirements

- Windows 10/11 (uses `netsh` for DNS changes)
- Administrator privileges (auto-requested on launch)
- Python 3.8+ (or use the .exe build)

## 📜 License

MIT — do whatever you want with it.
