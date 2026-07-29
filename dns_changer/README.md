# DNS Changer App for Windows
A modern desktop DNS changer for the WiFi adapter.

## Features
- Change DNS for WiFi adapter (silent netsh commands)
- Custom DNS presets (preferred + secondary), saved to JSON
- Global hotkey to toggle between two selected presets
- Dark mode UI with blue accent colors (CustomTkinter)

## Requirements
- Python 3.8+
- Windows (uses netsh)
- Run as Administrator (required for DNS changes)

## Installation
```bash
pip install customtkinter keyboard
```

## Run
Run as Administrator:
```bash
python main.py
```
