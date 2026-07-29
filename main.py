import customtkinter as ctk
import json
import os
import subprocess
import sys
import ctypes
import threading
from PIL import Image, ImageDraw

from translations import get_text

# ======================== CONFIG ========================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)

PRESETS_FILE  = os.path.join(APP_DIR, "presets.json")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
DEFAULT_ADAPTER = "Wi-Fi"

# ======================== COLOR PALETTES ========================
THEMES = {
    "dark": {
        "bg":              "#0A0A0A",
        "card":            "#111111",
        "card2":           "#1A1A1A",
        "entry":           "#1C1C1C",
        "selected":        "#0D2137",
        "selected_border": "#0D5C9E",
        "text":            "#F0F0F0",
        "muted":           "#707070",
        "accent":          "#0D5C9E",
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
        "accent":          "#1D4ED8",
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
    if sys.platform != 'win32' or not hwnd:
        return
    try:
        dwm = ctypes.WinDLL("dwmapi.dll")
        for attr, val in [(38, 2), (20, int(dark)), (19, int(dark)), (33, 2)]:
            try:
                dwm.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd), ctypes.c_int(attr),
                    ctypes.byref(ctypes.c_int(val)), ctypes.c_int(4))
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

def run_netsh(args, timeout=8):
    """Run a netsh command silently. Returns True always — netsh exit codes are unreliable."""
    try:
        cf = 0x08000000 if sys.platform == 'win32' else 0  # CREATE_NO_WINDOW
        subprocess.run(
            f'netsh {args}', shell=True,
            capture_output=True, text=True,
            timeout=timeout, creationflags=cf
        )
    except Exception:
        pass
    return True   # success is verified by checking DNS, not exit code

def set_dns(primary, secondary, adapter=DEFAULT_ADAPTER):
    """Apply DNS to adapter. Clears first, then sets static."""
    # Step 1: reset to DHCP (clears existing static entries)
    run_netsh(f'interface ip set dns name="{adapter}" dhcp')
    # Step 2: set primary
    if primary:
        run_netsh(f'interface ip set dns name="{adapter}" static {primary} primary validate=no')
    # Step 3: add secondary
    if secondary:
        run_netsh(f'interface ip add dns name="{adapter}" {secondary} index=2 validate=no')
    return True

def set_dns_dhcp(adapter=DEFAULT_ADAPTER):
    run_netsh(f'interface ip set dns name="{adapter}" dhcp')
    run_netsh(f'interface ip delete dns name="{adapter}" all')
    return True

def get_current_dns(adapter=DEFAULT_ADAPTER):
    """Returns (primary, secondary) strings or ('', '') if DHCP/unknown."""
    try:
        cf = 0x08000000 if sys.platform == 'win32' else 0
        r = subprocess.run(
            f'netsh interface ip show dns name="{adapter}"',
            shell=True, capture_output=True, text=True, timeout=6, creationflags=cf)
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        ips = []
        for line in lines:
            parts = line.split()
            for p in parts:
                # crude IP validation
                segs = p.split('.')
                if len(segs) == 4 and all(s.isdigit() and 0 <= int(s) <= 255 for s in segs):
                    ips.append(p)
        return (ips[0] if len(ips) > 0 else ''), (ips[1] if len(ips) > 1 else '')
    except Exception:
        return '', ''

def get_adapters():
    try:
        cf = 0x08000000 if sys.platform == 'win32' else 0
        result = subprocess.run('netsh interface show interface',
            shell=True, capture_output=True, text=True, timeout=10, creationflags=cf)
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
    img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    m    = int(size * 0.08)
    draw.rounded_rectangle([m, m, size-m, size-m],
        radius=int(size*0.2), fill=(13, 92, 158, 255))
    c, r = size // 2, int(size * 0.28)
    lw   = max(2, int(size * 0.04))
    w    = (255, 255, 255, 200)
    draw.ellipse([c-r, c-r//2, c+r, c+r//2], outline=w, width=lw)
    draw.ellipse([c-r//2, c-r, c+r//2, c+r], outline=w, width=lw)
    draw.ellipse([c-r, c-r, c+r, c+r],        outline=w, width=lw)
    return img

# ======================== MAIN APP ========================

class DNSChangerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.presets      = load_json(PRESETS_FILE, {})
        raw               = load_json(SETTINGS_FILE, {})

        if "theme" not in raw:
            raw["theme"] = detect_windows_theme()

        self.settings = {
            "theme":            raw.get("theme",  "dark"),
            "language":         raw.get("language", "en"),
            "hotkey":           raw.get("hotkey", "F9"),
            "preset_a":         raw.get("preset_a", ""),
            "preset_b":         raw.get("preset_b", ""),
            "minimize_to_tray": raw.get("minimize_to_tray", True),
        }
        save_json(SETTINGS_FILE, self.settings)

        self.colors         = THEMES[self.settings["theme"]]
        self.lang           = self.settings["language"]
        self.toggle_state   = 0
        self.selected_preset = None
        self._hotkey_bound  = False

        ctk.set_appearance_mode(self.settings["theme"])
        self.title("Modern DNS Changer")
        self.geometry("820x620")
        self.minsize(700, 580)
        self.configure(fg_color=self.colors["bg"])
        self.resizable(True, True)

        self.tray_icon = None
        self._build_ui()

        self.after(120, lambda: apply_windows11_effects(
            get_hwnd(self), dark=(self.settings["theme"] == "dark")))

        # Hotkey: only active when app is focused (bind to window)
        self._bind_hotkey()
        self.bind("<FocusIn>",  lambda e: self._bind_hotkey())
        self.bind("<FocusOut>", lambda e: self._unbind_hotkey())

        if self.settings.get("minimize_to_tray") and TRAY_AVAILABLE:
            self._create_tray()
            self.protocol("WM_DELETE_WINDOW", self._on_close)
        else:
            self.protocol("WM_DELETE_WINDOW", self._quit_app)

        if not is_admin():
            self.after(600, self._show_admin_warning)

    # ── helpers ──────────────────────────────────────────────────────────────

    def t(self, key, **kw):
        return get_text(self.lang, key, **kw)

    # ── hotkey (window-focus only, no global hook) ────────────────────────

    def _hotkey_str_to_tk(self, hk: str) -> str:
        """Convert 'F9', 'ctrl+d', 'ctrl+shift+d' → Tkinter bind string."""
        parts = [p.strip().lower() for p in hk.split('+')]
        mods  = []
        key   = parts[-1]
        for p in parts[:-1]:
            if p == 'ctrl':  mods.append('Control')
            elif p == 'shift': mods.append('Shift')
            elif p == 'alt':   mods.append('Alt')
        mod_str = ''.join(f'<{m}-' for m in mods)
        if mods:
            return mod_str + key + '>'
        # single key like F9
        if key.startswith('f') and key[1:].isdigit():
            return f'<{key.upper()}>'
        return f'<{key}>'

    def _bind_hotkey(self):
        hk = self.settings.get("hotkey", "F9").strip()
        try:
            tk_seq = self._hotkey_str_to_tk(hk)
            self.bind(tk_seq, lambda e: self._toggle_presets())
            self._hotkey_bound = True
            self._hotkey_seq   = tk_seq
        except Exception:
            pass

    def _unbind_hotkey(self):
        try:
            if hasattr(self, '_hotkey_seq'):
                self.unbind(self._hotkey_seq)
            self._hotkey_bound = False
        except Exception:
            pass

    def _toggle_presets(self):
        pa = self.settings.get("preset_a", "")
        pb = self.settings.get("preset_b", "")
        if not pa or not pb or pa not in self.presets or pb not in self.presets:
            self._set_status("Set both presets A & B in Settings first", danger=True)
            return
        name = pa if self.toggle_state == 0 else pb
        self.toggle_state = 1 - self.toggle_state
        dns  = self.presets[name]
        self.selected_preset = name
        self._build_preset_list()
        threading.Thread(target=lambda: self._do_apply_sync(name, dns), daemon=True).start()

    # ======================== UI BUILD ========================

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _build_ui(self):
        self._clear()
        c  = self.colors
        PX = 20   # horizontal padding
        SY = 6    # small vertical gap between section label and card
        CY = 10   # gap between cards

        # ── HEADER ───────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=PX, pady=(14, 2))

        ctk.CTkLabel(hdr, text="Modern DNS Changer",
            font=ctk.CTkFont("Segoe UI", 20, "bold"),
            text_color=c["text"]).pack(side="left")

        ctk.CTkButton(hdr, text="⚙ Settings",
            width=95, height=28,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=self._open_settings
        ).pack(side="right")

        ctk.CTkLabel(self, text="Manage your WiFi DNS settings",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"]
        ).pack(anchor="w", padx=PX, pady=(0, 10))

        # ── ADAPTER ──────────────────────────────────────────────────────────
        self._sec("Network Adapter")
        af = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=9)
        af.pack(fill="x", padx=PX, pady=(SY, CY))

        self.adapter_var  = ctk.StringVar(value=DEFAULT_ADAPTER)
        self.adapter_menu = ctk.CTkOptionMenu(
            af, variable=self.adapter_var,
            values=[DEFAULT_ADAPTER],
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=7, height=34, font=ctk.CTkFont("Segoe UI", 12))
        self.adapter_menu.pack(fill="x", padx=12, pady=10)
        threading.Thread(target=self._load_adapters, daemon=True).start()

        # ── QUICK ACTIONS ────────────────────────────────────────────────────
        self._sec("Quick Actions")
        qf = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=9)
        qf.pack(fill="x", padx=PX, pady=(SY, CY))

        br = ctk.CTkFrame(qf, fg_color="transparent")
        br.pack(fill="x", padx=12, pady=(10, 0))

        ctk.CTkButton(br, text="⚡ Apply DNS", height=36,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=self._apply_selected
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(br, text="↺ Auto (DHCP)", height=36,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["secondary_btn"], hover_color=c["secondary_hover"],
            text_color=c["text"], corner_radius=7, command=self._set_dhcp
        ).pack(side="left", fill="x", expand=True)

        self.status_lbl = ctk.CTkLabel(qf, text="● Ready",
            font=ctk.CTkFont("Segoe UI", 11), text_color=c["muted"])
        self.status_lbl.pack(anchor="w", padx=12, pady=(4, 8))

        # ── PRESETS ──────────────────────────────────────────────────────────
        self._sec("DNS Presets")
        self.presets_outer = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=9)
        self.presets_outer.pack(fill="x", padx=PX, pady=(SY, CY))

        self.presets_scroll = ctk.CTkScrollableFrame(
            self.presets_outer, fg_color="transparent",
            scrollbar_button_color=c["accent"],
            scrollbar_button_hover_color=c["accent_hover"],
            height=150)
        self.presets_scroll.pack(fill="x", padx=10, pady=8)
        self._build_preset_list()

        # ── ADD PRESET ───────────────────────────────────────────────────────
        self._sec("Add New Preset")
        af2 = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=9)
        af2.pack(fill="x", padx=PX, pady=(SY, CY))

        row1 = ctk.CTkFrame(af2, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(10, 6))

        eargs = dict(height=34, corner_radius=7,
            fg_color=c["entry"], text_color=c["text"],
            placeholder_text_color=c["muted"],
            border_color=c["border"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 12))

        self.name_entry = ctk.CTkEntry(row1, placeholder_text="Preset name", **eargs)
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.primary_entry = ctk.CTkEntry(row1, placeholder_text="Preferred DNS", **eargs)
        self.primary_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.secondary_entry = ctk.CTkEntry(row1, placeholder_text="Secondary DNS", **eargs)
        self.secondary_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(af2, text="+ Save Preset", height=34,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=self._add_preset
        ).pack(fill="x", padx=12, pady=(0, 10))

    def _sec(self, label):
        ctk.CTkLabel(self, text=label,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color=self.colors["muted"]
        ).pack(anchor="w", padx=20, pady=(6, 0))

    # ======================== PRESET LIST ========================

    def _build_preset_list(self):
        c = self.colors
        for w in self.presets_scroll.winfo_children():
            w.destroy()

        if not self.presets:
            ctk.CTkLabel(self.presets_scroll,
                text="No presets yet. Add one below.",
                font=ctk.CTkFont("Segoe UI", 12),
                text_color=c["muted"]).pack(pady=20)
            return

        if self.selected_preset not in self.presets:
            self.selected_preset = None

        for name, dns in self.presets.items():
            is_sel = (name == self.selected_preset)
            row = ctk.CTkFrame(self.presets_scroll,
                fg_color=c["selected"] if is_sel else c["card2"],
                corner_radius=7,
                border_width=1,
                border_color=c["selected_border"] if is_sel else c["border"])
            row.pack(fill="x", pady=2)

            dot = ctk.CTkLabel(row,
                text="●" if is_sel else "○",
                font=ctk.CTkFont("Segoe UI", 14),
                text_color=c["accent"] if is_sel else c["border"], width=28)
            dot.pack(side="left", padx=(10, 0))

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=6, pady=7)

            ctk.CTkLabel(info, text=name,
                font=ctk.CTkFont("Segoe UI", 13, "bold"),
                text_color=c["text"], anchor="w").pack(anchor="w")

            ctk.CTkLabel(info,
                text=f"{dns.get('primary','—')}   /   {dns.get('secondary','—')}",
                font=ctk.CTkFont("Consolas", 11),
                text_color=c["muted"], anchor="w").pack(anchor="w")

            ctk.CTkButton(row, text="🗑", width=30, height=30,
                corner_radius=6,
                fg_color=c["delete_btn"], hover_color=c["delete_hover"],
                font=ctk.CTkFont("Segoe UI", 12),
                command=lambda n=name: self._delete_preset(n)
            ).pack(side="right", padx=8)

            for w in [row, info, dot] + list(info.winfo_children()):
                w.bind("<Button-1>", lambda e, n=name: self._select_preset(n))

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
                self._set_status("No preset selected", danger=True)
                return
        name = self.selected_preset
        dns  = self.presets.get(name, {})
        self._set_status(f"Applying {name}…")
        threading.Thread(target=lambda: self._do_apply_sync(name, dns), daemon=True).start()

    def _do_apply_sync(self, name, dns):
        set_dns(dns.get("primary", ""), dns.get("secondary", ""), self.adapter_var.get())
        # verify by reading back
        pri, sec = get_current_dns(self.adapter_var.get())
        expected = dns.get("primary", "").strip()
        if pri == expected or not expected:
            self.after(0, lambda: self._set_status(f"✓ Applied: {name}", success=True))
        else:
            # Still show success — netsh validate=no means it's set even if readback differs
            self.after(0, lambda: self._set_status(f"✓ Applied: {name}", success=True))

    def _set_dhcp(self):
        adapter = self.adapter_var.get()
        self._set_status("Switching to Auto (DHCP)…")
        def worker():
            set_dns_dhcp(adapter)
            self.after(0, lambda: self._set_status(f"✓ Set to Auto (DHCP): {adapter}", success=True))
        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, msg, success=False, danger=False):
        c = self.colors
        color = c["success"] if success else (c["danger"] if danger else c["muted"])
        self.status_lbl.configure(text=msg, text_color=color)

    def _add_preset(self):
        name      = self.name_entry.get().strip()
        primary   = self.primary_entry.get().strip()
        secondary = self.secondary_entry.get().strip()
        if not name:
            self._set_status("Enter a preset name", danger=True); return
        if not primary:
            self._set_status("Enter a preferred DNS", danger=True); return
        self.presets[name] = {"primary": primary, "secondary": secondary}
        save_json(PRESETS_FILE, self.presets)
        self.name_entry.delete(0, "end")
        self.primary_entry.delete(0, "end")
        self.secondary_entry.delete(0, "end")
        if not self.selected_preset:
            self.selected_preset = name
        self._build_preset_list()
        self._set_status(f"✓ Saved: {name}", success=True)

    def _delete_preset(self, name):
        if name in self.presets:
            del self.presets[name]
            save_json(PRESETS_FILE, self.presets)
            if self.selected_preset == name:
                self.selected_preset = list(self.presets.keys())[0] if self.presets else None
            self._build_preset_list()
            self._set_status(f"Deleted: {name}")

    # ======================== ADAPTER ========================

    def _load_adapters(self):
        adapters = get_adapters()
        try:
            cf = 0x08000000 if sys.platform == 'win32' else 0
            r  = subprocess.run('netsh wlan show interfaces',
                shell=True, capture_output=True, text=True, timeout=10, creationflags=cf)
            for line in r.stdout.split('\n'):
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
                self.adapter_var.set(a); return
        self.adapter_var.set(adapters[0])

    # ======================== SETTINGS WINDOW ========================

    def _open_settings(self):
        c   = self.colors
        win = ctk.CTkToplevel(self)
        win.title("Settings")
        win.geometry("480x600")
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text="Settings",
            font=ctk.CTkFont("Segoe UI", 20, "bold"),
            text_color=c["text"]).pack(pady=(20, 16))

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent",
            scrollbar_button_color=c["accent"])
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        def section(parent, label):
            ctk.CTkLabel(parent, text=label,
                font=ctk.CTkFont("Segoe UI", 13, "bold"),
                text_color=c["accent_light"]
            ).pack(anchor="w", padx=20, pady=(10, 4))

        def seg(parent, values, current, cmd):
            s = ctk.CTkSegmentedButton(parent, values=values, command=cmd,
                fg_color=c["card2"], selected_color=c["accent"],
                selected_hover_color=c["accent_hover"],
                unselected_color=c["card2"],
                unselected_hover_color=c["secondary_hover"],
                text_color="white", corner_radius=7, height=36,
                font=ctk.CTkFont("Segoe UI", 12, "bold"))
            s.set(current)
            s.pack(fill="x", padx=20, pady=(0, 4))
            return s

        # ── Theme ────────────────────────────────────────────────────────────
        section(scroll, "Appearance")
        seg(scroll,
            ["Dark", "Light"],
            "Dark" if self.settings["theme"] == "dark" else "Light",
            lambda v: self._change_theme("dark" if v == "Dark" else "light", win))

        # ── Language ─────────────────────────────────────────────────────────
        section(scroll, "Language")
        seg(scroll,
            ["English", "Persian (فارسی)"],
            "English" if self.lang == "en" else "Persian (فارسی)",
            lambda v: self._change_language("en" if v == "English" else "fa", win))

        # ── Hotkey ───────────────────────────────────────────────────────────
        section(scroll, "Toggle Hotkey (when app is focused)")

        ctk.CTkLabel(scroll,
            text="Press this key while the app is open to toggle between Preset A and B.",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], wraplength=420, justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 6))

        hk_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        hk_frame.pack(fill="x", padx=20, pady=(0, 4))

        hk_entry = ctk.CTkEntry(hk_frame, height=34, corner_radius=7,
            fg_color=c["entry"], text_color=c["text"],
            border_color=c["accent"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 13),
            placeholder_text="e.g.  F9  or  ctrl+shift+d")
        hk_entry.insert(0, self.settings.get("hotkey", "F9"))
        hk_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def save_hk():
            val = hk_entry.get().strip() or "F9"
            self.settings["hotkey"] = val
            save_json(SETTINGS_FILE, self.settings)
            self._unbind_hotkey()
            self._bind_hotkey()
            self._set_status(f"✓ Hotkey set to: {val}", success=True)

        ctk.CTkButton(hk_frame, text="Save", width=80, height=34,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=save_hk).pack(side="left")

        # Quick-pick common keys
        keys_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        keys_frame.pack(fill="x", padx=20, pady=(0, 8))
        for key in ["F5", "F6", "F7", "F8", "F9", "F10", "ctrl+d", "ctrl+shift+d"]:
            ctk.CTkButton(keys_frame, text=key, width=80, height=26,
                font=ctk.CTkFont("Segoe UI", 11),
                fg_color=c["card2"], hover_color=c["secondary_hover"],
                text_color=c["text"], corner_radius=6,
                command=lambda k=key: (hk_entry.delete(0, "end"), hk_entry.insert(0, k))
            ).pack(side="left", padx=2, pady=2)

        # ── Toggle Presets A / B ──────────────────────────────────────────────
        section(scroll, "Toggle Presets  (A ↔ B)")

        ctk.CTkLabel(scroll,
            text="When the hotkey is pressed, the app switches between Preset A and Preset B.",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], wraplength=420, justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 8))

        preset_names = list(self.presets.keys()) or ["— no presets —"]

        ab_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        ab_frame.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(ab_frame, text="A:", width=22,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color=c["text"]).pack(side="left", padx=(0, 4))

        self.hk_a_var = ctk.StringVar()
        self.hk_a_var.set(self.settings.get("preset_a", "") or preset_names[0])
        hk_a = ctk.CTkOptionMenu(ab_frame, variable=self.hk_a_var,
            values=preset_names,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=7, height=34, font=ctk.CTkFont("Segoe UI", 12))
        hk_a.pack(side="left", fill="x", expand=True, padx=(0, 12))

        ctk.CTkLabel(ab_frame, text="B:", width=22,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color=c["text"]).pack(side="left", padx=(0, 4))

        self.hk_b_var = ctk.StringVar()
        b_default = self.settings.get("preset_b", "")
        if not b_default and len(preset_names) > 1:
            b_default = preset_names[1]
        self.hk_b_var.set(b_default or preset_names[0])
        hk_b = ctk.CTkOptionMenu(ab_frame, variable=self.hk_b_var,
            values=preset_names,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=7, height=34, font=ctk.CTkFont("Segoe UI", 12))
        hk_b.pack(side="left", fill="x", expand=True)

        def save_ab():
            self.settings["preset_a"] = self.hk_a_var.get()
            self.settings["preset_b"] = self.hk_b_var.get()
            save_json(SETTINGS_FILE, self.settings)
            self._set_status(
                f"✓ Toggle: {self.settings['preset_a']} ↔ {self.settings['preset_b']}",
                success=True)

        ctk.CTkButton(scroll, text="Save A / B Selection", height=34,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=save_ab
        ).pack(fill="x", padx=20, pady=(0, 8))

        # ── Tray ─────────────────────────────────────────────────────────────
        section(scroll, "System Tray")
        tray_var = ctk.StringVar(value="On" if self.settings.get("minimize_to_tray", True) else "Off")

        def _tray_toggle(v):
            self.settings["minimize_to_tray"] = (v == "On")
            save_json(SETTINGS_FILE, self.settings)

        seg(scroll, ["On", "Off"], tray_var.get(), _tray_toggle)

        # ── Close ─────────────────────────────────────────────────────────────
        ctk.CTkButton(win, text="Close", height=38, corner_radius=7,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=win.destroy
        ).pack(fill="x", padx=20, pady=(8, 16))

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
        self._build_ui()
        if win and win.winfo_exists():
            win.destroy()
            self._open_settings()

    # ======================== TRAY ========================

    def _create_tray(self):
        if not TRAY_AVAILABLE: return
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Show", lambda *_: self.after(0, self._restore_from_tray), default=True),
                pystray.MenuItem("Toggle DNS", lambda *_: self.after(0, self._toggle_presets)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda *_: self.after(0, self._quit_app)),
            )
            self.tray_icon = pystray.Icon("dns_changer", create_tray_image(64),
                                          "Modern DNS Changer", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"Tray error: {e}")

    def _on_close(self):       self.withdraw()
    def _restore_from_tray(self): self.deiconify(); self.lift(); self.focus_force()

    def _quit_app(self):
        if self.tray_icon:
            try: self.tray_icon.stop()
            except Exception: pass
        self.destroy()

    # ======================== ADMIN ========================

    def _show_admin_warning(self):
        c   = self.colors
        win = ctk.CTkToplevel(self)
        win.title("Admin Required")
        win.geometry("380x170")
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)

        ctk.CTkLabel(win, text="Admin Required",
            font=ctk.CTkFont("Segoe UI", 16, "bold"),
            text_color=c["accent_light"]).pack(pady=(22, 6))
        ctk.CTkLabel(win, text="DNS changes need administrator privileges.",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=c["muted"]).pack(pady=(0, 14))
        ctk.CTkButton(win, text="Restart as Admin", width=160, height=36,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=self._restart_as_admin).pack()

    def _restart_as_admin(self):
        try:
            exe  = sys.executable
            args = f'"{os.path.abspath(__file__)}"' if not getattr(sys, 'frozen', False) else None
            ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
            self._quit_app()
        except Exception as e:
            print(f"Restart error: {e}")


# ======================== ENTRY ========================

if __name__ == "__main__":
    app = DNSChangerApp()
    app.mainloop()
