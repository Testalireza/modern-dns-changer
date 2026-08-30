# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Modern DNS Changer v4.1
#
# Build:
#     pyinstaller build.spec --clean --noconfirm
#
# Output:
#     dist/ModernDNSChanger.exe

import os
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Detect PyInstaller version for documentation purposes
PYI_VERSION = tuple(int(x) for x in getattr(sys, "pyinstaller_version", "5.0").split("."))

# Ensure the local source directory is on the path so PyInstaller can
# import our sibling modules.
PROJECT_DIR = os.path.abspath(SPECPATH)
sys.path.insert(0, PROJECT_DIR)

# Collect data files for third-party packages that need them
datas = [
    (os.path.join(PROJECT_DIR, "translations.py"), "."),
]

# CustomTkinter ships XML/JSON theme files inside the package. Bundle them.
try:
    import customtkinter
    ctk_dir = os.path.dirname(customtkinter.__file__)
    for entry in os.listdir(ctk_dir):
        if entry.endswith((".json", ".png", ".otf", ".ttf")):
            datas.append((os.path.join(ctk_dir, entry), "customtkinter"))
except Exception:
    pass

# Pillow may need its bundled resources at runtime
try:
    from PIL import Image
    pil_dir = os.path.dirname(Image.__file__)
    for entry in os.listdir(pil_dir):
        if entry.endswith((".pil", ".pdm", ".pyi", ".txt")):
            datas.append((os.path.join(pil_dir, entry), "PIL"))
except Exception:
    pass

# Hidden imports for libraries that are imported dynamically
hiddenimports = []
hiddenimports += collect_submodules("customtkinter")
hiddenimports += collect_submodules("pystray")
hiddenimports += ["pystray._win32", "pystray._base"]
hiddenimports += collect_submodules("PIL")
hiddenimports += ["PIL._tkinter_finder"]

# Our own modules
for mod in (
    "app_paths", "logger", "platform_utils", "validators", "hotkeys",
    "storage", "dns_manager", "tray", "widgets", "ui",
    "translations",
):
    hiddenimports.append(mod)

# Generate the icon if it doesn't exist; PyInstaller needs the .ico file at
# build time.
icon_path = os.path.join(PROJECT_DIR, "icon.ico")
if not os.path.exists(icon_path):
    try:
        import subprocess
        subprocess.check_call([sys.executable, "generate_icon.py"], cwd=PROJECT_DIR)
    except Exception:
        pass

# Bundle the icons so ``app_paths.resource_path("icon.ico")`` resolves even
# inside the onefile ``sys._MEIPASS`` directory.
for icon_name in ("icon.ico", "icon.png"):
    _icon_fn = os.path.join(PROJECT_DIR, icon_name)
    if os.path.exists(_icon_fn):
        datas.append((_icon_fn, "."))

a = Analysis(
    ["main.py"],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Strip heavy scientific/UI libraries we don't need to make the EXE smaller
    excludes=[
        "matplotlib", "numpy", "scipy", "pandas",
        "tkinter.test", "test", "unittest", "pydoc_data",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ModernDNSChanger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX can cause false-positive AV detections
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # No console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,      # Always request UAC elevation on launch
    icon=icon_path if os.path.exists(icon_path) else None,
)
