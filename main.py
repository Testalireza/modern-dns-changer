import customtkinter as ctk
import json
import os
import subprocess
import sys
import ctypes
import threading
import keyboard
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
        "bg":              "#0A0A0A",   # near-black background
        "card":            "#111111",   # cards / sections
        "card2":           "#1A1A1A",   # slightly lighter for inner cards
        "entry":           "#1C1C1C",   # input fields
        "selected":        "#0D2137",   # selected preset highlight
        "selected_border": "#0D5C9E",   # selected preset border
        "text":            "#F0F0F0",
        "muted":           "#707070",
        "accent":          "#0D5C9E",   # darker blue buttons
        "accent_hover":    "#0A4A80",
        "accent_light":    "#1A7FCC",
        "success":         "#4ADE80",
        "danger":          "#EF4444",
        "secondary_btn":   "#252525",
        "secondary_hover": "#333333",
        "delete_btn":      "#2A1010",
        "delete_hover":    "#4A1A1A",
        "border":          "#2A2A2A",
    },
    "light": {
        "bg":              "#F3F4F6",
        "card":            "#FFFFFF",
        "card2":           "#F8F9FA",
        "entry":           "#EEF0F3",
        "selected":        "#DBEAFE",
        "selected_border": "#1D4ED8",
        "text":            "#111827",
        "muted":           "#6B7280",
        "accent":          "#1D4ED8",   # darker blue
        "accent_hover":    "#1E40AF",
        "accent_light":    "#2563EB",
        "success":         "#16A34A",
        "danger":          "#DC2626",
        "secondary_btn":   "#E5E7EB",
        "secondary_hover": "#D1D5DB",
        "delete_btn":      "#FEE2E2",
        "delete_hover":    "#FECACA",
        "border":          "#E5E7EB",
    }
}

# ======================== WINDOWS UTILS ========================

def detect_windows_theme():
    """Returns 'dark' or 'light' based on Windows registry setting."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if val == 1 else "dark"
    except Exception:
        return "dark"

def apply_windows11_effects(hwnd, dark=True):
    if not sys.platform == 'win32' or not hwnd:
        return
    try:
        dwm = ctypes.WinDLL("dwmapi.dll")
        try:
            dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_int(38),
                ctypes.byref(ctypes.c_int(2)), ctypes.c_int(4))
        except Exception:
            pass
        for attr in (20, 19):
            try:
                dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_int(attr),
                    ctypes.byref(ctypes.c_int(1 if dark else 0)), ctypes.c_int(4))
            except Exception:
                pass
        try:
            dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_int(33),
                ctypes.byref(ctypes.c_int(2)), ctypes.c_int(4))
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
        cf = 0x08000000 if sys.platform == 'win32' else 0
        subprocess.run(command, shell=True, capture_output=True,
                       text=True, timeout=10, creationflags=cf)
        return True
    except Exception:
        return False

def set_dns(primary, secondary, adapter=DEFAULT_ADAPTER):
    run_cmd(f'netsh interface ip set dns name="{adapter}" dhcp')
    ok1 = run_cmd(f'netsh interface ip set dns name="{adapter}" static {primary} primary') if primary else True
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
        adapters = []
        for line in result.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 4 and parts[0] not in ('Admin', '---'):
                name = ' '.join(parts[3:])
                if name:
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
            pass
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ======================== TRAY ========================
try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

def create_tray_image(size=64):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    m = int(size * 0.08)
    draw.rounded_rectangle([m, m, size-m, size-m], radius=int(size*0.2), fill=(13, 92, 158, 255))
    c, r = size // 2, int(size * 0.28)
    lw = max(2, int(size * 0.04))
    blue = (255, 255, 255, 200)
    draw.ellipse([c-r, c-r//2, c+r, c+r//2], outline=blue, width=lw)
    draw.ellipse([c-r//2, c-r, c+r//2, c+r], outline=blue, width=lw)
    draw.ellipse([c-r, c-r, c+r, c+r], outline=blue, width=lw)
    return img

# ======================== MAIN APP ========================

class DNSChangerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.presets = load_json(PRESETS_FILE, {})
        raw_settings = load_json(SETTINGS_FILE, {})

        # --- Auto-detect Windows theme on FIRST launch ---
        if "theme" not in raw_settings:
            raw_settings["theme"] = detect_windows_theme()

        self.settings = {
            "theme":            raw_settings.get("theme", "dark"),
            "language":         raw_settings.get("language", "en"),
            "hotkey":           raw_settings.get("hotkey", "ctrl+shift+d"),
            "preset_a":         raw_settings.get("preset_a", ""),
            "preset_b":         raw_settings.get("preset_b", ""),
            "minimize_to_tray": raw_settings.get("minimize_to_tray", True),
        }
        save_json(SETTINGS_FILE, self.settings)

        self.colors = THEMES[self.settings["theme"]]
        self.lang   = self.settings["language"]
        self.toggle_state = 0
        self.selected_preset = None

        ctk.set_appearance_mode(self.settings["theme"])

        self.title(self.t("title"))
        self.geometry("900x680")
        self.minsize(700, 600)
        self.configure(fg_color=self.colors["bg"])
        self.resizable(True, True)

        self.tray_icon = None
        self._build_ui()

        self.after(120, lambda: apply_windows11_effects(
            get_hwnd(self), dark=(self.settings["theme"] == "dark")))
        self._start_hotkey()

        if self.settings.get("minimize_to_tray") and TRAY_AVAILABLE:
            self._create_tray()
            self.protocol("WM_DELETE_WINDOW", self._on_close)
        else:
            self.protocol("WM_DELETE_WINDOW", self._quit_app)

        if not is_admin():
            self.after(600, self._show_admin_warning)

    # ---- helpers ----
    def t(self, key, **kw):
        return get_text(self.lang, key, **kw)

    def c(self, key):
        return self.colors[key]

    # ======================== UI BUILD ========================

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _build_ui(self):
        self._clear()
        c = self.colors

        # ---- MAIN SCROLLABLE CONTAINER ----
        # Everything goes in one scrollable frame so nothing gets cut off
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
            scrollbar_button_color=c["accent"],
            scrollbar_button_hover_color=c["accent_hover"])
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ---- HEADER ----
        hdr = ctk.CTkFrame(scroll, fg_color="transparent")
        hdr.pack(fill="x", padx=30, pady=(20, 8))

        ctk.CTkLabel(hdr, text=self.t("title"),
            font=ctk.CTkFont("Segoe UI", 24, "bold"),
            text_color=c["text"]).pack(side="left")

        ctk.CTkButton(hdr, text="⚙  " + self.t("settings_btn"),
            width=110, height=32,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=8, command=self._open_settings
        ).pack(side="right")

        ctk.CTkLabel(scroll, text=self.t("subtitle"),
            font=ctk.CTkFont("Segoe UI", 13),
            text_color=c["muted"]
        ).pack(anchor="w", padx=30, pady=(0, 16))

        # ---- ADAPTER ----
        self._section(scroll, self.t("adapter"))

        af = ctk.CTkFrame(scroll, fg_color=c["card"], corner_radius=10)
        af.pack(fill="x", padx=30, pady=(0, 14))

        self.adapter_var = ctk.StringVar(value=DEFAULT_ADAPTER)
        self.adapter_menu = ctk.CTkOptionMenu(
            af, variable=self.adapter_var,
            values=[DEFAULT_ADAPTER],
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"],
            text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=8, height=38,
            font=ctk.CTkFont("Segoe UI", 13)
        )
        self.adapter_menu.pack(fill="x", padx=16, pady=14)
        threading.Thread(target=self._load_adapters, daemon=True).start()

        # ---- QUICK ACTIONS ----
        self._section(scroll, self.t("quick_actions"))

        qf = ctk.CTkFrame(scroll, fg_color=c["card"], corner_radius=10)
        qf.pack(fill="x", padx=30, pady=(0, 14))

        br = ctk.CTkFrame(qf, fg_color="transparent")
        br.pack(fill="x", padx=16, pady=(14, 0))

        self.apply_btn = ctk.CTkButton(
            br, text="⚡  " + self.t("apply_dns"), height=42,
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=8, command=self._apply_selected
        )
        self.apply_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            br, text=self.t("auto_dhcp"), height=42,
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=c["secondary_btn"], hover_color=c["secondary_hover"],
            text_color=c["text"],
            corner_radius=8, command=self._set_dhcp
        ).pack(side="left", fill="x", expand=True)

        self.status_lbl = ctk.CTkLabel(
            qf, text="● " + self.t("status_ready"),
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=c["muted"]
        )
        self.status_lbl.pack(anchor="w", padx=16, pady=(8, 12))

        # ---- PRESETS ----
        self._section(scroll, self.t("presets"))

        self.presets_outer = ctk.CTkFrame(scroll, fg_color=c["card"], corner_radius=10)
        # Fixed height — not expand=True — so Add Preset below is always visible
        self.presets_outer.pack(fill="x", padx=30, pady=(0, 14))

        self.presets_scroll = ctk.CTkScrollableFrame(
            self.presets_outer, fg_color="transparent",
            scrollbar_button_color=c["accent"],
            scrollbar_button_hover_color=c["accent_hover"],
            height=180,
        )
        self.presets_scroll.pack(fill="x", padx=12, pady=12)
        self._build_preset_list()

        # ---- ADD PRESET ----
        self._section(scroll, self.t("add_new_preset"))

        af2 = ctk.CTkFrame(scroll, fg_color=c["card"], corner_radius=10)
        af2.pack(fill="x", padx=30, pady=(0, 14))

        # Two-column layout for inputs
        row1 = ctk.CTkFrame(af2, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(14, 6))

        self.name_entry = ctk.CTkEntry(row1, placeholder_text=self.t("preset_name"),
            height=38, corner_radius=8,
            fg_color=c["entry"], text_color=c["text"],
            placeholder_text_color=c["muted"],
            border_color=c["border"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 13))
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.primary_entry = ctk.CTkEntry(row1, placeholder_text=self.t("preferred_dns"),
            height=38, corner_radius=8,
            fg_color=c["entry"], text_color=c["text"],
            placeholder_text_color=c["muted"],
            border_color=c["border"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 13))
        self.primary_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.secondary_entry = ctk.CTkEntry(row1, placeholder_text=self.t("secondary_dns"),
            height=38, corner_radius=8,
            fg_color=c["entry"], text_color=c["text"],
            placeholder_text_color=c["muted"],
            border_color=c["border"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 13))
        self.secondary_entry.pack(side="left", fill="x", expand=True)

        # Save preset button — big, prominent
        self.add_btn = ctk.CTkButton(
            af2, text="＋  " + self.t("add_preset_btn"), height=42,
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=8, command=self._add_preset
        )
        self.add_btn.pack(fill="x", padx=16, pady=(4, 16))

        # ---- HOTKEY ----
        self._section(scroll, self.t("hotkey"))

        hkf = ctk.CTkFrame(scroll, fg_color=c["card"], corner_radius=10)
        hkf.pack(fill="x", padx=30, pady=(0, 24))

        ctk.CTkLabel(hkf, text=self.t("hotkey_desc"),
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=c["muted"]
        ).pack(anchor="w", padx=16, pady=(12, 8))

        hkrow = ctk.CTkFrame(hkf, fg_color="transparent")
        hkrow.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(hkrow, text="A:", width=24, text_color=c["muted"],
                     font=ctk.CTkFont("Segoe UI", 13)).pack(side="left", padx=(0,4))
        self.hk_a_var = ctk.StringVar()
        self.hk_a_menu = ctk.CTkOptionMenu(hkrow, values=[], variable=self.hk_a_var,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=8, height=36, font=ctk.CTkFont("Segoe UI", 13))
        self.hk_a_menu.pack(side="left", fill="x", expand=True, padx=(0, 12))

        ctk.CTkLabel(hkrow, text="B:", width=24, text_color=c["muted"],
                     font=ctk.CTkFont("Segoe UI", 13)).pack(side="left", padx=(0,4))
        self.hk_b_var = ctk.StringVar()
        self.hk_b_menu = ctk.CTkOptionMenu(hkrow, values=[], variable=self.hk_b_var,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=8, height=36, font=ctk.CTkFont("Segoe UI", 13))
        self.hk_b_menu.pack(side="left", fill="x", expand=True)

        hkrow2 = ctk.CTkFrame(hkf, fg_color="transparent")
        hkrow2.pack(fill="x", padx=16, pady=(0, 14))

        self.hotkey_entry = ctk.CTkEntry(hkrow2, height=36, corner_radius=8,
            fg_color=c["entry"], text_color=c["text"],
            border_color=c["accent"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 13))
        self.hotkey_entry.insert(0, self.settings.get("hotkey", "ctrl+shift+d"))
        self.hotkey_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(hkrow2, text=self.t("save_hotkey"), width=120, height=36,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=8, command=self._save_hotkey
        ).pack(side="left")

        self._refresh_hk_dropdowns()

    def _section(self, parent, label):
        c = self.colors
        ctk.CTkLabel(parent, text=label,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color=c["muted"]
        ).pack(anchor="w", padx=30, pady=(0, 6))

    # ======================== PRESET LIST (clickable selection) ========================

    def _build_preset_list(self):
        c = self.colors
        for w in self.presets_scroll.winfo_children():
            w.destroy()

        if not self.presets:
            ctk.CTkLabel(self.presets_scroll,
                text=self.t("no_presets"),
                font=ctk.CTkFont("Segoe UI", 13),
                text_color=c["muted"]
            ).pack(pady=30)
            return

        if self.selected_preset not in self.presets:
            self.selected_preset = None

        for name, dns in self.presets.items():
            is_sel = (name == self.selected_preset)

            bg     = c["selected"]  if is_sel else c["card2"]
            border = c["selected_border"] if is_sel else c["border"]

            row = ctk.CTkFrame(self.presets_scroll,
                fg_color=bg, corner_radius=8,
                border_width=1, border_color=border)
            row.pack(fill="x", pady=3)

            dot = ctk.CTkLabel(row, text="●" if is_sel else "○",
                font=ctk.CTkFont("Segoe UI", 16),
                text_color=c["accent"] if is_sel else c["border"], width=32)
            dot.pack(side="left", padx=(12, 0))

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=8, pady=10)

            ctk.CTkLabel(info, text=name,
                font=ctk.CTkFont("Segoe UI", 14, "bold"),
                text_color=c["text"], anchor="w"
            ).pack(anchor="w")

            dns_str = f"{dns.get('primary','—')}   /   {dns.get('secondary','—')}"
            ctk.CTkLabel(info, text=dns_str,
                font=ctk.CTkFont("Consolas", 12),
                text_color=c["muted"], anchor="w"
            ).pack(anchor="w")

            del_btn = ctk.CTkButton(row, text="🗑", width=34, height=34,
                corner_radius=6,
                fg_color=c["delete_btn"], hover_color=c["delete_hover"],
                font=ctk.CTkFont("Segoe UI", 13),
                command=lambda n=name: self._delete_preset(n))
            del_btn.pack(side="right", padx=12)

            for widget in [row, info, dot]:
                widget.bind("<Button-1>", lambda e, n=name: self._select_preset(n))
            for child in info.winfo_children():
                child.bind("<Button-1>", lambda e, n=name: self._select_preset(n))

    def _select_preset(self, name):
        self.selected_preset = name
        self._build_preset_list()

    # ======================== ACTIONS ========================

    def _apply_selected(self):
        if not self.selected_preset:
            if self.presets:
                self.selected_preset = list(self.presets.keys())[0]
                self._build_preset_list()
            else:
                self._set_status(self.t("no_presets_warning"), danger=True)
                return

        name = self.selected_preset
        dns  = self.presets.get(name, {})
        self._do_apply(name, dns)

    def _do_apply(self, name, dns):
        adapter = self.adapter_var.get()
        self._set_status("⏳ " + self.t("applying", name=name))

        def worker():
            ok = set_dns(dns.get("primary",""), dns.get("secondary",""), adapter)
            if ok:
                self.after(0, lambda: self._set_status(
                    "✓ " + self.t("applied", name=name, adapter=adapter), success=True))
            else:
                self.after(0, lambda: self._set_status(self.t("apply_failed"), danger=True))

        threading.Thread(target=worker, daemon=True).start()

    def _set_dhcp(self):
        adapter = self.adapter_var.get()
        self._set_status("⏳ " + self.t("dhcp_applying"))

        def worker():
            ok = set_dns_dhcp(adapter)
            msg = ("✓ " + self.t("dhcp_done", adapter=adapter)) if ok else self.t("dhcp_failed")
            self.after(0, lambda: self._set_status(msg, success=ok, danger=not ok))

        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, msg, success=False, danger=False):
        c = self.colors
        color = c["success"] if success else (c["danger"] if danger else c["muted"])
        self.status_lbl.configure(text=msg, text_color=color)

    def _add_preset(self):
        name    = self.name_entry.get().strip()
        primary = self.primary_entry.get().strip()
        secondary = self.secondary_entry.get().strip()

        if not name:
            self._set_status(self.t("enter_name"), danger=True); return
        if not primary:
            self._set_status(self.t("enter_primary"), danger=True); return

        self.presets[name] = {"primary": primary, "secondary": secondary}
        save_json(PRESETS_FILE, self.presets)

        self.name_entry.delete(0, 'end')
        self.primary_entry.delete(0, 'end')
        self.secondary_entry.delete(0, 'end')

        if not self.selected_preset:
            self.selected_preset = name

        self._build_preset_list()
        self._refresh_hk_dropdowns()
        self._set_status("✓ " + self.t("preset_saved", name=name), success=True)

    def _delete_preset(self, name):
        if name in self.presets:
            del self.presets[name]
            save_json(PRESETS_FILE, self.presets)
            if self.selected_preset == name:
                self.selected_preset = list(self.presets.keys())[0] if self.presets else None
            self._build_preset_list()
            self._refresh_hk_dropdowns()
            self._set_status("✓ " + self.t("preset_deleted", name=name), success=True)

    # ======================== ADAPTER ========================

    def _load_adapters(self):
        adapters = get_adapters()
        try:
            result = subprocess.run('netsh wlan show interfaces',
                shell=True, capture_output=True, text=True, timeout=10)
            for line in result.stdout.split('\n'):
                if 'Name' in line and ':' in line:
                    wn = line.split(':', 1)[1].strip()
                    if wn and wn not in adapters:
                        adapters.insert(0, wn)
        except Exception:
            pass
        self.after(0, lambda: self._update_adapters(adapters))

    def _update_adapters(self, adapters):
        if not adapters:
            adapters = [DEFAULT_ADAPTER]
        self.adapter_menu.configure(values=adapters)
        for a in adapters:
            if any(k in a.lower() for k in ('wi', 'wifi', 'wireless', 'wlan')):
                self.adapter_var.set(a)
                return
        self.adapter_var.set(adapters[0])

    # ======================== HOTKEY ========================

    def _refresh_hk_dropdowns(self):
        names = list(self.presets.keys()) or [""]
        self.hk_a_menu.configure(values=names)
        self.hk_b_menu.configure(values=names)

        a = self.settings.get("preset_a", "")
        b = self.settings.get("preset_b", "")
        self.hk_a_var.set(a if a in names else names[0])
        self.hk_b_var.set(b if b in names else (names[1] if len(names) > 1 else names[0]))

    def _save_hotkey(self):
        self.settings["hotkey"]   = self.hotkey_entry.get().strip() or "ctrl+shift+d"
        self.settings["preset_a"] = self.hk_a_var.get()
        self.settings["preset_b"] = self.hk_b_var.get()
        save_json(SETTINGS_FILE, self.settings)
        self._stop_hotkey()
        self._start_hotkey()
        self._set_status("✓ " + self.t("hotkey_saved", key=self.settings["hotkey"]), success=True)

    def _start_hotkey(self):
        hk = self.settings.get("hotkey", "ctrl+shift+d")
        try:
            keyboard.add_hotkey(hk, self._toggle_presets)
        except Exception:
            pass

    def _stop_hotkey(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def _toggle_presets(self):
        pa = self.settings.get("preset_a", "")
        pb = self.settings.get("preset_b", "")
        if not pa or not pb or pa not in self.presets or pb not in self.presets:
            return
        name = pa if self.toggle_state == 0 else pb
        self.toggle_state = 1 - self.toggle_state
        dns = self.presets[name]
        self.selected_preset = name
        self.after(0, self._build_preset_list)
        ok = set_dns(dns.get("primary",""), dns.get("secondary",""), self.adapter_var.get())
        if ok:
            self.after(0, lambda: self._set_status(
                "✓ " + self.t("hotkey_applied", name=name), success=True))

    # ======================== SETTINGS WINDOW ========================

    def _open_settings(self):
        c = self.colors
        win = ctk.CTkToplevel(self)
        win.title(self.t("settings_title"))
        win.geometry("460x560")
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text=self.t("settings_title"),
            font=ctk.CTkFont("Segoe UI", 20, "bold"),
            text_color=c["text"]).pack(pady=(20, 16))

        def seg(values, current, cmd):
            s = ctk.CTkSegmentedButton(win, values=values, command=cmd,
                fg_color=c["card2"], selected_color=c["accent"],
                selected_hover_color=c["accent_hover"],
                unselected_color=c["card2"],
                unselected_hover_color=c["secondary_hover"],
                text_color="white", corner_radius=8, height=38,
                font=ctk.CTkFont("Segoe UI", 13, "bold"))
            s.set(current)
            s.pack(fill="x", padx=24, pady=(0, 16))
            return s

        # Theme
        ctk.CTkLabel(win, text=self.t("appearance"),
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            text_color=c["accent_light"]).pack(anchor="w", padx=24, pady=(0, 8))

        seg([self.t("dark_mode"), self.t("light_mode")],
            self.t("dark_mode") if self.settings["theme"] == "dark" else self.t("light_mode"),
            lambda v: self._change_theme(
                "dark" if v in (self.t("dark_mode"),) else "light", win))

        # Language
        ctk.CTkLabel(win, text=self.t("language_section"),
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            text_color=c["accent_light"]).pack(anchor="w", padx=24, pady=(0, 8))

        seg([self.t("english"), self.t("persian")],
            self.t("english") if self.lang == "en" else self.t("persian"),
            lambda v: self._change_language("en" if "English" in v else "fa", win))

        # Tray
        ctk.CTkLabel(win, text=self.t("tray_section"),
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            text_color=c["accent_light"]).pack(anchor="w", padx=24, pady=(0, 8))

        ctk.CTkLabel(win, text=self.t("tray_desc"),
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=c["muted"]).pack(anchor="w", padx=24, pady=(0, 8))

        tray_var = ctk.StringVar(value="On" if self.settings.get("minimize_to_tray", True) else "Off")

        def _tray_toggle(v):
            self.settings["minimize_to_tray"] = (v == "On")
            save_json(SETTINGS_FILE, self.settings)

        ts = ctk.CTkSegmentedButton(win, values=["On", "Off"],
            command=_tray_toggle,
            fg_color=c["card2"], selected_color=c["accent"],
            selected_hover_color=c["accent_hover"],
            unselected_color=c["card2"],
            unselected_hover_color=c["secondary_hover"],
            text_color="white", corner_radius=8, height=38,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            variable=tray_var)
        ts.pack(fill="x", padx=24, pady=(0, 16))

        if not TRAY_AVAILABLE:
            ctk.CTkLabel(win, text="⚠ Install pystray for tray support",
                font=ctk.CTkFont("Segoe UI", 12),
                text_color=c["danger"]).pack(anchor="w", padx=24)

        # About
        ctk.CTkLabel(win, text=self.t("about_section"),
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            text_color=c["accent_light"]).pack(anchor="w", padx=24, pady=(10, 8))

        ctk.CTkLabel(win, text=self.t("about_text"),
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=c["muted"], justify="center").pack(padx=24, pady=(0, 16))

        ctk.CTkButton(win, text=self.t("close"), height=42, corner_radius=8,
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=win.destroy).pack(fill="x", padx=24, pady=(0, 24))

    def _change_theme(self, theme, win=None):
        self.settings["theme"] = theme
        self.colors = THEMES[theme]
        save_json(SETTINGS_FILE, self.settings)
        ctk.set_appearance_mode(theme)
        self.configure(fg_color=self.colors["bg"])
        self._build_ui()
        self.after(120, lambda: apply_windows11_effects(get_hwnd(self), dark=(theme == "dark")))
        if win and win.winfo_exists():
            win.destroy()
            self._open_settings()

    def _change_language(self, lang, win=None):
        self.settings["language"] = lang
        self.lang = lang
        save_json(SETTINGS_FILE, self.settings)
        self.title(self.t("title"))
        self._build_ui()
        if win and win.winfo_exists():
            win.destroy()
            self._open_settings()

    # ======================== TRAY ========================

    def _create_tray(self):
        if not TRAY_AVAILABLE:
            return
        try:
            img = create_tray_image(64)
            menu = pystray.Menu(
                pystray.MenuItem(self.t("tray_show"),
                    lambda *_: self.after(0, self._restore_from_tray), default=True),
                pystray.MenuItem(self.t("tray_toggle"),
                    lambda *_: self.after(0, self._toggle_presets)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(self.t("tray_quit"),
                    lambda *_: self.after(0, self._quit_app)),
            )
            self.tray_icon = pystray.Icon("dns_changer", img, self.t("tray_tooltip"), menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"Tray error: {e}")

    def _on_close(self):
        self.withdraw()

    def _restore_from_tray(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self):
        self._stop_hotkey()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.destroy()

    # ======================== ADMIN ========================

    def _show_admin_warning(self):
        c = self.colors
        win = ctk.CTkToplevel(self)
        win.title(self.t("admin_needed"))
        win.geometry("400x200")
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)

        ctk.CTkLabel(win, text=self.t("admin_needed"),
            font=ctk.CTkFont("Segoe UI", 18, "bold"),
            text_color=c["accent_light"]).pack(pady=(28, 8))

        ctk.CTkLabel(win, text=self.t("admin_msg"),
            font=ctk.CTkFont("Segoe UI", 13),
            text_color=c["muted"], justify="center").pack(pady=(0, 18))

        ctk.CTkButton(win, text=self.t("restart_admin"), width=180, height=40,
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=8, command=self._restart_as_admin).pack()

    def _restart_as_admin(self):
        try:
            exe = sys.executable
            args = f'"{os.path.abspath(__file__)}"' if not getattr(sys, 'frozen', False) else None
            ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
            self._quit_app()
        except Exception as e:
            print(f"Restart error: {e}")


# ======================== ENTRY ========================

if __name__ == "__main__":
    app = DNSChangerApp()
    app.mainloop()
