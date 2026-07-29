# Modern DNS Changer

A modern Windows 11 DNS changer desktop app with a beautiful dark mode UI and blue accent colors.

## ✨ Features

- **One-click DNS switching** — Change DNS for your WiFi adapter instantly (silent `netsh` commands)
- **Custom DNS presets** — Save preferred + secondary DNS combos with custom names
- **Global hotkey toggle** — Switch between two selected presets with a keyboard shortcut (default: `Ctrl+Shift+D`)
- **Auto (DHCP) reset** — Reset DNS back to automatic with one click
- **Windows 11 native styling** — Mica backdrop, dark title bar, rounded corners
- **Auto-elevate** — Requests admin privileges automatically (required for DNS changes)
- **Dark mode UI** — Deep navy theme with blue accent buttons (`#1F6AA5`)
- **Auto-detects WiFi adapter** — Prioritizes wireless adapters

## 📸 Preview

- Dark navy background (`#1A1A2E`)
- Card-based layout (`#16213E`)
- Blue accent buttons (`#1F6AA5`)
- Segoe UI typography
- Rounded corners everywhere

## 🚀 Quick Start (Python)

1. Install dependencies:
   ```bash
   pip install customtkinter keyboard
   ```

2. Run as Administrator:
   ```bash
   python main.py
   ```

Or right-click `run.ps1` → "Run with PowerShell" (auto-elevates to Admin).

## 📦 Build .exe (Windows 11)

1. Install build dependencies:
   ```powershell
   pip install customtkinter keyboard pyinstaller pillow
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
- Can be copied anywhere — no Python needed

## 📁 Project Structure

```
modern-dns-changer/
├── main.py              # Main application
├── build.spec           # PyInstaller build configuration
├── build.ps1            # Windows build script
├── run.ps1              # Run script (auto-elevates to admin)
├── generate_icon.py     # Generates the app .ico icon
├── requirements.txt     # Python dependencies
├── presets.json          # Saved DNS presets (auto-generated)
├── hotkey_config.json   # Hotkey settings (auto-generated)
└── icon.ico             # App icon (auto-generated)
```

## ⌨️ Hotkey Setup

1. Add at least 2 DNS presets
2. In the "Toggle Hotkey" section, select **Preset A** and **Preset B**
3. Set your hotkey (default: `ctrl+shift+d`)
4. Click "Save Hotkey"
5. Now pressing the hotkey anywhere on your PC toggles between the two presets

## 🎨 Customization

Edit the color constants at the top of `main.py`:
- `ACCENT_BLUE` — Button color
- `BG_COLOR` — Window background
- `CARD_COLOR` — Card backgrounds
- `TEXT_COLOR` — Main text color

## ⚠️ Requirements

- Windows 10/11 (uses `netsh` for DNS changes)
- Administrator privileges (auto-requested on launch)
- Python 3.8+ (or use the .exe build)

## 📜 License

MIT — do whatever you want with it.
