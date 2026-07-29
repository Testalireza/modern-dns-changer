import customtkinter as ctk
import json
import os
import subprocess
import sys
import ctypes
import threading
import keyboard
from tkinter import messagebox
from PIL import Image, ImageDraw
from translations import get_text

# ======================== CONFIG ========================
APP_NAME = "Modern DNS Changer"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)

PRESETS_FILE = os.path.join(APP_DIR, "presets.json")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
DEFAULT_ADAPTER = "Wi-Fi"

# ======================== COLOR PALETTES ========================
THEMES = {
    "dark": {
        "bg": "#1A1A2E",
        "card": "#16213E",
        "entry": "#0F3460",
        "text": "#EAEAEA",
        "muted": "#8892B0",
        "accent": "#1F6AA5",
        "accent_hover": "#144870",
        "accent_light": "#2D8FD6",
        "success": "#4ADE80",
        "danger": "#EF4444",
        "secondary_btn": "#44475A",
        "secondary_hover": "#383B4D",
        "delete_btn": "#3A1F2E",
        "delete_hover": "#5C2740",
    },
    "light": {
        "bg": "#F0F2F5",
        "card": "#FFFFFF",
        "entry": "#E8EDF2",
        "text": "#1A1A2E",
        "muted": "#64748B",
        "accent": "#1F6AA5",
        "accent_hover": "#144870",
        "accent_light": "#2D8FD6",
        "success": "#16A34A",
        "danger": "#DC2626",
        "secondary_btn": "#E2E8F0",
        "secondary_hover": "#CBD5E1",
        "delete_btn": "#FEE2E2",
        "delete_hover": "#FECACA",
    }
}

# ======================== WINDOWS 11 NATIVE EFFECTS ========================

def apply_windows11_effects(hwnd, dark=True):
    if not sys.platform == 'win32':
        return
    try:
        dwm = ctypes.WinDLL("dwmapi.dll")
        # Mica backdrop
        try:
            dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_int(38),
                ctypes.byref(ctypes.c_int(2)), ctypes.c_int(ctypes.sizeof(ctypes.c_int)))
        except Exception:
            pass
        # Dark/light title bar
        for attr in (20, 19):
            try:
                dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_int(attr),
                    ctypes.byref(ctypes.c_int(1 if dark else 0)),
                    ctypes.c_int(ctypes.sizeof(ctypes.c_int)))
            except Exception:
                pass
        # Rounded corners
        try:
            dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_int(33),
                ctypes.byref(ctypes.c_int(2)), ctypes.c_int(ctypes.sizeof(ctypes.c_int)))
        except Exception:
            pass
        # Extend frame
        try:
            dwm.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd),
                ctypes.byref(ctypes.c_int(-1)))
        except Exception:
            pass
    except Exception:
        pass

def get_hwnd(window):
    try:
        window.update_idletasks()
        return ctypes.windll.user32.GetParent(window.winfo_id())
    except Exception:
        return None

# ======================== DNS LOGIC ========================

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def run_cmd(command):
    try:
        creationflags = 0x08000000 if sys.platform == 'win32' else 0
        subprocess.run(command, shell=True, capture_output=True, text=True,
                      timeout=10, creationflags=creationflags)
        return True
    except Exception:
        return False

def set_dns(primary, secondary, adapter=DEFAULT_ADAPTER):
    run_cmd(f'netsh interface ip set dns name="{adapter}" dhcp')
    if primary:
        ok1 = run_cmd(f'netsh interface ip set dns name="{adapter}" static {primary} primary')
    else:
        ok1 = run_cmd(f'netsh interface ip set dns name="{adapter}" dhcp')
    ok2 = run_cmd(f'netsh interface ip add dns name="{adapter}" {secondary} index=2') if secondary else True
    return ok1 and ok2

def set_dns_dhcp(adapter=DEFAULT_ADAPTER):
    ok1 = run_cmd(f'netsh interface ip set dns name="{adapter}" dhcp')
    ok2 = run_cmd(f'netsh interface ip delete dns name="{adapter}" all')
    return ok1 and ok2

def get_adapters():
    try:
        result = subprocess.run('netsh interface show interface',
            shell=True, capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split('\n')
        adapters = []
        for line in lines:
            if 'Dedicated' in line or 'Loopback' in line:
                continue
            parts = line.split()
            if len(parts) >= 4:
                name = ' '.join(parts[3:])
                adapters.append(name)
        return adapters or [DEFAULT_ADAPTER]
    except Exception:
        return [DEFAULT_ADAPTER]

# ======================== STORAGE ========================

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ======================== TRAY ICON IMAGE ========================

def create_tray_icon_image(size=64):
    """Create a tray icon image (blue globe on dark navy)."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    m = int(size * 0.08)
    draw.rounded_rectangle([m, m, size-m, size-m], radius=int(size*0.2), fill=(22, 33, 62, 255))
    c = size // 2
    r = int(size * 0.28)
    blue = (45, 143, 214, 255)
    lw = max(2, int(size * 0.03))
    draw.ellipse([c-r, c-r//2, c+r, c+r//2], outline=blue, width=lw)
    draw.ellipse([c-r//2, c-r, c+r//2, c+r], outline=blue, width=lw)
    draw.ellipse([c-r, c-r, c+r, c+r], outline=blue, width=lw)
    dr = max(3, int(size * 0.05))
    draw.ellipse([c-dr, c-dr, c+dr, c+dr], fill=blue)
    return img

# ======================== TRY IMPORT PYSTRAY ========================
try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# ======================== MAIN APP ========================

class DNSChangerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Load configs
        self.presets = load_json(PRESETS_FILE, {})
        self.settings = load_json(SETTINGS_FILE, {
            "theme": "dark",
            "language": "en",
            "hotkey": "ctrl+shift+d",
            "preset_a": "",
            "preset_b": "",
            "minimize_to_tray": True,
        })
        self.toggle_state = 0

        # Theme colors (reference current palette)
        self.colors = THEMES[self.settings["theme"]]
        self.lang = self.settings["language"]
        self.rtl = self.lang == "fa"

        ctk.set_appearance_mode(self.settings["theme"])

        # Window
        self.title(get_text(self.lang, "title"))
        self.geometry("640x860")
        self.minsize(580, 780)
        self.configure(fg_color=self.colors["bg"])

        # Tray
        self.tray_icon = None
        self._tray_should_quit = False

        # Build UI
        self._build_ui()

        # Windows 11 effects
        self.after(100, lambda: apply_windows11_effects(get_hwnd(self), dark=(self.settings["theme"] == "dark")))

        # Start hotkey
        self._start_hotkey_listener()

        # Start tray
        if self.settings.get("minimize_to_tray", True) and TRAY_AVAILABLE:
            self._create_tray()
            self.protocol("WM_DELETE_WINDOW", self._on_close)
        else:
            self.protocol("WM_DELETE_WINDOW", self._quit_app)

        # Admin warning
        if not is_admin():
            self.after(500, self._show_admin_warning)

    # ---------- TEXT HELPER ----------
    def t(self, key, **kwargs):
        return get_text(self.lang, key, **kwargs)

    # ---------- UI BUILD ----------

    def _clear_widgets(self):
        for widget in self.winfo_children():
            widget.destroy()

    def _build_ui(self):
        self._clear_widgets()
        c = self.colors

        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(25, 5))

        title_label = ctk.CTkLabel(
            header, text=self.t("title"),
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=c["text"]
        )
        title_label.pack(side="left", anchor="w")

        # Settings button on the right
        ctk.CTkButton(
            header, text=self.t("settings_btn"), width=120, height=34,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=10, command=self._open_settings
        ).pack(side="right", anchor="e")

        ctk.CTkLabel(
            header, text=self.t("subtitle"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=c["muted"]
        ).pack(anchor="w", pady=(2, 0))

        # --- Adapter ---
        adapter_frame = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=15)
        adapter_frame.pack(fill="x", padx=30, pady=(20, 10))

        ctk.CTkLabel(
            adapter_frame, text=self.t("adapter"),
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=c["text"]
        ).pack(anchor="w", padx=20, pady=(15, 5))

        self.adapter_var = ctk.StringVar(value=DEFAULT_ADAPTER)
        self.adapter_menu = ctk.CTkOptionMenu(
            adapter_frame, values=[DEFAULT_ADAPTER], variable=self.adapter_var,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"], corner_radius=10, height=38,
            font=ctk.CTkFont(family="Segoe UI", size=14)
        )
        self.adapter_menu.pack(fill="x", padx=20, pady=(0, 15))
        threading.Thread(target=self._load_adapters, daemon=True).start()

        # --- Quick Actions ---
        quick_frame = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=15)
        quick_frame.pack(fill="x", padx=30, pady=(10, 10))

        ctk.CTkLabel(
            quick_frame, text=self.t("quick_actions"),
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=c["text"]
        ).pack(anchor="w", padx=20, pady=(15, 5))

        btn_row = ctk.CTkFrame(quick_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkButton(
            btn_row, text=self.t("apply_dns"), width=140, height=42,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=10, command=self._apply_dns
        ).pack(side="left", padx=(0, 10), fill="x", expand=True)

        ctk.CTkButton(
            btn_row, text=self.t("auto_dhcp"), width=140, height=42,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=c["secondary_btn"], hover_color=c["secondary_hover"],
            corner_radius=10, command=self._set_dhcp
        ).pack(side="left", fill="x", expand=True)

        self.status_label = ctk.CTkLabel(
            quick_frame, text=self.t("status_ready"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=c["muted"]
        )
        self.status_label.pack(anchor="w", padx=20, pady=(0, 10))

        # --- Presets ---
        presets_frame = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=15)
        presets_frame.pack(fill="both", expand=True, padx=30, pady=(10, 10))

        ctk.CTkLabel(
            presets_frame, text=self.t("presets"),
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=c["text"]
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.scroll_frame = ctk.CTkScrollableFrame(
            presets_frame, fg_color="transparent",
            scrollbar_button_color=c["accent"],
            scrollbar_button_hover_color=c["accent_hover"],
            height=150
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self._build_preset_list()

        # Add preset form
        add_frame = ctk.CTkFrame(presets_frame, fg_color="transparent")
        add_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            add_frame, text=self.t("add_new_preset"),
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=c["text"]
        ).pack(anchor="w", pady=(0, 8))

        self.name_entry = ctk.CTkEntry(
            add_frame, placeholder_text=self.t("preset_name"),
            height=38, corner_radius=10,
            fg_color=c["entry"], text_color=c["text"],
            border_color=c["accent"], border_width=1)
        self.name_entry.pack(fill="x", pady=(0, 8))

        self.primary_entry = ctk.CTkEntry(
            add_frame, placeholder_text=self.t("preferred_dns"),
            height=38, corner_radius=10,
            fg_color=c["entry"], text_color=c["text"],
            border_color=c["accent"], border_width=1)
        self.primary_entry.pack(fill="x", pady=(0, 8))

        self.secondary_entry = ctk.CTkEntry(
            add_frame, placeholder_text=self.t("secondary_dns"),
            height=38, corner_radius=10,
            fg_color=c["entry"], text_color=c["text"],
            border_color=c["accent"], border_width=1)
        self.secondary_entry.pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            add_frame, text=self.t("add_preset_btn"), height=40, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=self._add_preset
        ).pack(fill="x")

        # --- Hotkey section ---
        hotkey_frame = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=15)
        hotkey_frame.pack(fill="x", padx=30, pady=(10, 25))

        ctk.CTkLabel(
            hotkey_frame, text=self.t("hotkey"),
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=c["text"]
        ).pack(anchor="w", padx=20, pady=(15, 5))

        ctk.CTkLabel(
            hotkey_frame, text=self.t("hotkey_desc"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=c["muted"]
        ).pack(anchor="w", padx=20, pady=(0, 10))

        hk_row = ctk.CTkFrame(hotkey_frame, fg_color="transparent")
        hk_row.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(hk_row, text=self.t("preset_a"), width=75,
                     font=ctk.CTkFont(size=13), text_color=c["muted"]
                     ).pack(side="left", padx=(0, 5))

        self.hk_a_var = ctk.StringVar(value="")
        self.hk_a_menu = ctk.CTkOptionMenu(
            hk_row, values=[], variable=self.hk_a_var,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"], corner_radius=10, height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13))
        self.hk_a_menu.pack(side="left", padx=(0, 10), fill="x", expand=True)

        ctk.CTkLabel(hk_row, text=self.t("preset_b"), width=75,
                     font=ctk.CTkFont(size=13), text_color=c["muted"]
                     ).pack(side="left", padx=(0, 5))

        self.hk_b_var = ctk.StringVar(value="")
        self.hk_b_menu = ctk.CTkOptionMenu(
            hk_row, values=[], variable=self.hk_b_var,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"], corner_radius=10, height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13))
        self.hk_b_menu.pack(side="left", fill="x", expand=True)

        hk_row2 = ctk.CTkFrame(hotkey_frame, fg_color="transparent")
        hk_row2.pack(fill="x", padx=20, pady=(10, 15))

        ctk.CTkLabel(hk_row2, text=self.t("hotkey_label"), width=75,
                     font=ctk.CTkFont(size=13), text_color=c["muted"]
                     ).pack(side="left", padx=(0, 5))

        self.hotkey_entry = ctk.CTkEntry(
            hk_row2, height=36, corner_radius=10,
            fg_color=c["entry"], text_color=c["text"],
            border_color=c["accent"], border_width=1)
        self.hotkey_entry.insert(0, self.settings.get("hotkey", "ctrl+shift+d"))
        self.hotkey_entry.pack(side="left", padx=(0, 10), fill="x", expand=True)

        ctk.CTkButton(
            hk_row2, text=self.t("save_hotkey"), width=120, height=36, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=self._save_hotkey
        ).pack(side="left")

        self._refresh_preset_dropdowns()

    # ---------- PRESET LIST ----------

    def _build_preset_list(self):
        c = self.colors
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not self.presets:
            ctk.CTkLabel(
                self.scroll_frame, text=self.t("no_presets"),
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=c["muted"], justify="center"
            ).pack(pady=30)
            return

        for name, dns in self.presets.items():
            card = ctk.CTkFrame(self.scroll_frame, fg_color=c["entry"], corner_radius=10)
            card.pack(fill="x", pady=4, padx=2)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=15, pady=10)

            ctk.CTkLabel(info, text=name,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=c["text"]).pack(anchor="w")

            dns_text = f"{dns.get('primary', '—')}  /  {dns.get('secondary', '—')}"
            ctk.CTkLabel(info, text=dns_text,
                font=ctk.CTkFont(family="Consolas", size=12),
                text_color=c["muted"]).pack(anchor="w", pady=(2, 0))

            btns = ctk.CTkFrame(card, fg_color="transparent")
            btns.pack(side="right", padx=10, pady=10)

            ctk.CTkButton(btns, text=self.t("apply"), width=70, height=32, corner_radius=8,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                fg_color=c["accent"], hover_color=c["accent_hover"],
                command=lambda n=name, d=dns: self._apply_preset(n, d)
            ).pack(side="left", padx=(0, 5))

            ctk.CTkButton(btns, text="🗑", width=32, height=32, corner_radius=8,
                font=ctk.CTkFont(size=13),
                fg_color=c["delete_btn"], hover_color=c["delete_hover"],
                command=lambda n=name: self._delete_preset(n)
            ).pack(side="left")

    # ---------- SETTINGS WINDOW ----------

    def _open_settings(self):
        c = self.colors
        win = ctk.CTkToplevel(self)
        win.title(self.t("settings_title"))
        win.geometry("480x620")
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)
        win.grab_set()

        self._settings_win = win

        # --- Appearance ---
        ctk.CTkLabel(win, text=self.t("appearance"),
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=c["accent_light"]).pack(anchor="w", padx=25, pady=(20, 10))

        theme_frame = ctk.CTkFrame(win, fg_color=c["card"], corner_radius=12)
        theme_frame.pack(fill="x", padx=25, pady=(0, 15))

        ctk.CTkLabel(theme_frame, text=self.t("theme"),
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=c["text"]).pack(anchor="w", padx=20, pady=(12, 5))

        theme_switch = ctk.CTkSegmentedButton(
            theme_frame,
            values=[self.t("dark_mode"), self.t("light_mode")],
            command=lambda v: self._change_theme("dark" if "dark" in v.lower() or "تاریک" in v else "light", win),
            fg_color=c["entry"], selected_color=c["accent"],
            selected_hover_color=c["accent_hover"],
            text_color="white", corner_radius=10, height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
        current_theme_label = self.t("dark_mode") if self.settings["theme"] == "dark" else self.t("light_mode")
        theme_switch.set(current_theme_label)
        theme_switch.pack(fill="x", padx=20, pady=(0, 15))

        # --- Language ---
        ctk.CTkLabel(win, text=self.t("language_section"),
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=c["accent_light"]).pack(anchor="w", padx=25, pady=(5, 10))

        lang_frame = ctk.CTkFrame(win, fg_color=c["card"], corner_radius=12)
        lang_frame.pack(fill="x", padx=25, pady=(0, 15))

        ctk.CTkLabel(lang_frame, text=self.t("language"),
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=c["text"]).pack(anchor="w", padx=20, pady=(12, 5))

        lang_switch = ctk.CTkSegmentedButton(
            lang_frame,
            values=[self.t("english"), self.t("persian")],
            command=lambda v: self._change_language("en" if "English" in v else "fa", win),
            fg_color=c["entry"], selected_color=c["accent"],
            selected_hover_color=c["accent_hover"],
            text_color="white", corner_radius=10, height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
        current_lang_label = self.t("english") if self.lang == "en" else self.t("persian")
        lang_switch.set(current_lang_label)
        lang_switch.pack(fill="x", padx=20, pady=(0, 15))

        # --- Tray ---
        ctk.CTkLabel(win, text=self.t("tray_section"),
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=c["accent_light"]).pack(anchor="w", padx=25, pady=(5, 10))

        tray_frame = ctk.CTkFrame(win, fg_color=c["card"], corner_radius=12)
        tray_frame.pack(fill="x", padx=25, pady=(0, 15))

        ctk.CTkLabel(tray_frame, text=self.t("minimize_to_tray"),
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=c["text"]).pack(anchor="w", padx=20, pady=(12, 5))

        ctk.CTkLabel(tray_frame, text=self.t("tray_desc"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=c["muted"]).pack(anchor="w", padx=20, pady=(0, 8))

        tray_switch_var = ctk.StringVar(value="on" if self.settings.get("minimize_to_tray", True) else "off")

        def _toggle_tray(v):
            self.settings["minimize_to_tray"] = (v == "on")
            save_json(SETTINGS_FILE, self.settings)

        tray_switch = ctk.CTkSegmentedButton(
            tray_frame, values=["On", "Off"],
            command=_toggle_tray,
            fg_color=c["entry"], selected_color=c["accent"],
            selected_hover_color=c["accent_hover"],
            text_color="white", corner_radius=10, height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            variable=tray_switch_var
        )
        tray_switch.pack(fill="x", padx=20, pady=(0, 15))

        if not TRAY_AVAILABLE:
            ctk.CTkLabel(tray_frame,
                text="⚠ pystray not installed. Run: pip install pystray",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=c["danger"]).pack(anchor="w", padx=20, pady=(0, 10))

        # --- About ---
        ctk.CTkLabel(win, text=self.t("about_section"),
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=c["accent_light"]).pack(anchor="w", padx=25, pady=(5, 10))

        about_frame = ctk.CTkFrame(win, fg_color=c["card"], corner_radius=12)
        about_frame.pack(fill="x", padx=25, pady=(0, 15))

        ctk.CTkLabel(about_frame, text=self.t("about_text"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=c["muted"], justify="center").pack(padx=20, pady=15)

        # --- Close button ---
        ctk.CTkButton(
            win, text=self.t("close"), width=160, height=42, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=win.destroy
        ).pack(pady=(5, 20))

    def _change_theme(self, theme, settings_win=None):
        self.settings["theme"] = theme
        self.colors = THEMES[theme]
        save_json(SETTINGS_FILE, self.settings)
        ctk.set_appearance_mode(theme)

        # Rebuild main UI
        self.configure(fg_color=self.colors["bg"])
        self._build_ui()

        # Reapply Win11 effects
        self.after(100, lambda: apply_windows11_effects(get_hwnd(self), dark=(theme == "dark")))

        # Update settings window colors if open
        if settings_win and settings_win.winfo_exists():
            settings_win.configure(fg_color=self.colors["bg"])
            settings_win.destroy()
            self._open_settings()

    def _change_language(self, lang, settings_win=None):
        self.settings["language"] = lang
        self.lang = lang
        self.rtl = (lang == "fa")
        save_json(SETTINGS_FILE, self.settings)

        # Update window title
        self.title(get_text(self.lang, "title"))

        # Rebuild UI
        self._build_ui()

        # Reopen settings window in new language
        if settings_win and settings_win.winfo_exists():
            settings_win.destroy()
            self._open_settings()

    # ---------- ADAPTER ----------

    def _load_adapters(self):
        adapters = get_adapters()
        try:
            result = subprocess.run('netsh wlan show interfaces',
                shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Name' in line and ':' in line:
                        wifi_name = line.split(':')[1].strip()
                        if wifi_name and wifi_name not in adapters:
                            adapters.insert(0, wifi_name)
        except Exception:
            pass
        self.after(0, lambda: self._update_adapters(adapters))

    def _update_adapters(self, adapters):
        if not adapters:
            adapters = [DEFAULT_ADAPTER]
        self.adapter_menu.configure(values=adapters)
        for a in adapters:
            if 'wi' in a.lower() or 'wi-fi' in a.lower() or 'wifi' in a.lower():
                self.adapter_var.set(a)
                break
        else:
            self.adapter_var.set(adapters[0])

    # ---------- PRESET ACTIONS ----------

    def _add_preset(self):
        name = self.name_entry.get().strip()
        primary = self.primary_entry.get().strip()
        secondary = self.secondary_entry.get().strip()

        if not name:
            self._set_status(self.t("enter_name"), danger=True)
            return
        if not primary:
            self._set_status(self.t("enter_primary"), danger=True)
            return

        self.presets[name] = {"primary": primary, "secondary": secondary}
        save_json(PRESETS_FILE, self.presets)

        self.name_entry.delete(0, 'end')
        self.primary_entry.delete(0, 'end')
        self.secondary_entry.delete(0, 'end')

        self._build_preset_list()
        self._refresh_preset_dropdowns()
        self._set_status(self.t("preset_saved", name=name), success=True)

    def _delete_preset(self, name):
        if name in self.presets:
            del self.presets[name]
            save_json(PRESETS_FILE, self.presets)
            self._build_preset_list()
            self._refresh_preset_dropdowns()
            self._set_status(self.t("preset_deleted", name=name), success=True)

    def _apply_preset(self, name, dns):
        adapter = self.adapter_var.get()
        primary = dns.get("primary", "")
        secondary = dns.get("secondary", "")
        self._set_status(self.t("applying", name=name))

        def do_apply():
            ok = set_dns(primary, secondary, adapter)
            if ok:
                self.after(0, lambda: self._set_status(
                    self.t("applied", name=name, adapter=adapter), success=True))
            else:
                self.after(0, lambda: self._set_status(self.t("apply_failed"), danger=True))

        threading.Thread(target=do_apply, daemon=True).start()

    def _apply_dns(self):
        if self.presets:
            first_name = list(self.presets.keys())[0]
            self._apply_preset(first_name, self.presets[first_name])
        else:
            self._set_status(self.t("no_presets_warning"), danger=True)

    def _set_dhcp(self):
        adapter = self.adapter_var.get()
        self._set_status(self.t("dhcp_applying"))

        def do_dhcp():
            ok = set_dns_dhcp(adapter)
            if ok:
                self.after(0, lambda: self._set_status(
                    self.t("dhcp_done", adapter=adapter), success=True))
            else:
                self.after(0, lambda: self._set_status(self.t("dhcp_failed"), danger=True))

        threading.Thread(target=do_dhcp, daemon=True).start()

    def _set_status(self, msg, success=False, danger=False):
        c = self.colors
        color = c["muted"]
        if success: color = c["success"]
        elif danger: color = c["danger"]
        self.status_label.configure(text=msg, text_color=color)

    # ---------- HOTKEY ----------

    def _refresh_preset_dropdowns(self):
        names = list(self.presets.keys())
        self.hk_a_menu.configure(values=names)
        self.hk_b_menu.configure(values=names)

        if self.settings.get("preset_a") in names:
            self.hk_a_var.set(self.settings["preset_a"])
        elif names:
            self.hk_a_var.set(names[0])
        else:
            self.hk_a_var.set("")

        if self.settings.get("preset_b") in names:
            self.hk_b_var.set(self.settings["preset_b"])
        elif len(names) > 1:
            self.hk_b_var.set(names[1])
        elif names:
            self.hk_b_var.set(names[0])
        else:
            self.hk_b_var.set("")

    def _save_hotkey(self):
        self.settings["hotkey"] = self.hotkey_entry.get().strip() or "ctrl+shift+d"
        self.settings["preset_a"] = self.hk_a_var.get()
        self.settings["preset_b"] = self.hk_b_var.get()
        save_json(SETTINGS_FILE, self.settings)

        self._stop_hotkey_listener()
        self._start_hotkey_listener()
        self._set_status(self.t("hotkey_saved", key=self.settings["hotkey"]), success=True)

    def _start_hotkey_listener(self):
        hotkey_str = self.settings.get("hotkey", "ctrl+shift+d")
        try:
            keyboard.add_hotkey(hotkey_str, self._toggle_presets)
        except Exception:
            pass

    def _stop_hotkey_listener(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def _toggle_presets(self):
        pa = self.settings.get("preset_a", "")
        pb = self.settings.get("preset_b", "")
        if not pa or not pb or pa not in self.presets or pb not in self.presets:
            return

        if self.toggle_state == 0:
            self.toggle_state = 1
            name, dns = pa, self.presets[pa]
        else:
            self.toggle_state = 0
            name, dns = pb, self.presets[pb]

        adapter = self.adapter_var.get()
        ok = set_dns(dns.get("primary", ""), dns.get("secondary", ""), adapter)
        if ok:
            self.after(0, lambda: self._set_status(self.t("hotkey_applied", name=name), success=True))
        else:
            self.after(0, lambda: self._set_status(self.t("toggle_failed"), danger=True))

    # ---------- SYSTEM TRAY ----------

    def _create_tray(self):
        if not TRAY_AVAILABLE:
            return
        try:
            icon_image = create_tray_icon_image(64)

            def on_show(icon, item):
                self.after(0, self._restore_from_tray)

            def on_quit(icon, item):
                self.after(0, self._quit_app)

            def on_toggle(icon, item):
                self.after(0, self._toggle_presets)

            menu = pystray.Menu(
                pystray.MenuItem(self.t("tray_show"), on_show, default=True),
                pystray.MenuItem(self.t("tray_toggle"), on_toggle),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(self.t("tray_quit"), on_quit),
            )

            self.tray_icon = pystray.Icon("dns_changer", icon_image,
                self.t("tray_tooltip"), menu)

            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"Tray error: {e}")

    def _on_close(self):
        """Minimize to tray instead of closing."""
        self.withdraw()
        if self.tray_icon:
            self.tray_icon.visible = True

    def _restore_from_tray(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        if self.tray_icon:
            self.tray_icon.visible = False

    def _quit_app(self):
        self._tray_should_quit = True
        self._stop_hotkey_listener()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.destroy()

    # ---------- ADMIN ----------

    def _show_admin_warning(self):
        c = self.colors
        warn = ctk.CTkToplevel(self)
        warn.title(self.t("admin_needed"))
        warn.geometry("400x200")
        warn.configure(fg_color=c["bg"])
        warn.resizable(False, False)
        warn.attributes("-topmost", True)
        warn.transient(self)

        ctk.CTkLabel(warn, text=self.t("admin_needed"),
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=c["accent_light"]).pack(pady=(30, 10))

        ctk.CTkLabel(warn, text=self.t("admin_msg"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=c["muted"], justify="center").pack(pady=(0, 20))

        ctk.CTkButton(warn, text=self.t("restart_admin"), width=160, height=40, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=self._restart_as_admin).pack(pady=(0, 20))

    def _restart_as_admin(self):
        try:
            if getattr(sys, 'frozen', False):
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, None, None, 1)
            else:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                    f'"{os.path.abspath(__file__)}"', None, 1)
            self._quit_app()
        except Exception as e:
            messagebox.showerror("Error", str(e))


# ======================== MAIN ========================

if __name__ == "__main__":
    app = DNSChangerApp()
    app.mainloop()
