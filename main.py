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
        "bg":              "#131313",   # slightly brighter than #0A0A0A
        "card":            "#1A1A1A",
        "card2":           "#222222",
        "entry":           "#242424",
        "selected":        "#0D2137",
        "selected_border": "#0D5C9E",
        "text":            "#F0F0F0",
        "muted":           "#808080",
        "accent":          "#0D5C9E",
        "accent_hover":    "#0A4A80",
        "accent_light":    "#1A7FCC",
        "success":         "#4ADE80",
        "danger":          "#EF4444",
        "ping_good":       "#3B82F6",
        "ping_ok":         "#4ADE80",
        "ping_bad":        "#F59E0B",
        "ping_fail":       "#EF4444",
        "secondary_btn":   "#2A2A2A",
        "secondary_hover": "#383838",
        "delete_btn":      "#2A1010",
        "delete_hover":    "#4A1A1A",
        "border":          "#2E2E2E",
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
        "ping_good":       "#2563EB",
        "ping_ok":         "#16A34A",
        "ping_bad":        "#D97706",
        "ping_fail":       "#DC2626",
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

def _run_batch(cmds, timeout=6):
    try:
        cf = 0x08000000 if sys.platform == 'win32' else 0
        full = ' && '.join(cmds)
        subprocess.run(full, shell=True, capture_output=True,
                       text=True, timeout=timeout, creationflags=cf)
    except Exception:
        pass
    return True

def set_dns(primary, secondary, adapter=DEFAULT_ADAPTER):
    cmds = [f'netsh interface ip set dns name="{adapter}" dhcp']
    if primary:
        cmds.append(f'netsh interface ip set dns name="{adapter}" static {primary} primary validate=no')
    if secondary:
        cmds.append(f'netsh interface ip add dns name="{adapter}" {secondary} index=2 validate=no')
    return _run_batch(cmds)

def set_dns_dhcp(adapter=DEFAULT_ADAPTER):
    return _run_batch([
        f'netsh interface ip set dns name="{adapter}" dhcp',
        f'netsh interface ip delete dns name="{adapter}" all',
    ])

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

# ======================== PING ========================

def ping_dns(ip, count=3, timeout=2000):
    """Ping a DNS server and return (avg_ms, min_ms, loss_pct) or (None, None, 100) on failure."""
    try:
        cf = 0x08000000 if sys.platform == 'win32' else 0
        r = subprocess.run(
            f'ping -n {count} -w {timeout} {ip}',
            shell=True, capture_output=True, text=True, timeout=15, creationflags=cf)

        times = []
        lost = 0
        for line in r.stdout.splitlines():
            line = line.strip()
            if 'time=' in line.lower() or 'time<' in line.lower():
                # Windows format: "Reply from 8.8.8.8: bytes=32 time=12ms TTL=117"
                for part in line.split():
                    part_lower = part.lower()
                    if part_lower.startswith('time=') or part_lower.startswith('time<'):
                        val = part_lower.split('=')[1].split('<')[1] if '<' in part_lower else part_lower.split('=')[1]
                        val = val.replace('ms', '').replace('M', '').replace('s', '')
                        try:
                            times.append(int(val))
                        except ValueError:
                            try:
                                times.append(int(float(val)))
                            except ValueError:
                                pass
            elif 'destination host unreachable' in line.lower() or 'request timed out' in line.lower():
                lost += 1

        if not times:
            return None, None, 100

        loss_pct = (lost / count) * 100
        avg = sum(times) // len(times)
        mn  = min(times)
        return avg, mn, loss_pct
    except Exception:
        return None, None, 100

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

        self.presets = load_json(PRESETS_FILE, {})
        raw = load_json(SETTINGS_FILE, {})

        if "theme" not in raw:
            raw["theme"] = detect_windows_theme()

        self.settings = {
            "theme":            raw.get("theme", "dark"),
            "language":         raw.get("language", "en"),
            "hotkey":           raw.get("hotkey", "F9"),
            "preset_a":         raw.get("preset_a", ""),
            "preset_b":         raw.get("preset_b", ""),
            "minimize_to_tray": raw.get("minimize_to_tray", True),
        }
        save_json(SETTINGS_FILE, self.settings)

        self.colors          = THEMES[self.settings["theme"]]
        self.lang            = self.settings["language"]
        self.toggle_state    = 0
        self.selected_preset = None
        self.ping_labels     = {}   # preset_name -> CTkLabel for ping result
        self.ping_buttons    = {}   # preset_name -> CTkButton for ping button

        ctk.set_appearance_mode(self.settings["theme"])
        self.title("Modern DNS Changer")
        self.geometry("780x560")
        self.minsize(640, 480)
        self.configure(fg_color=self.colors["bg"])
        self.resizable(True, True)

        self.tray_icon = None
        self._build_ui()

        self.after(120, lambda: apply_windows11_effects(
            get_hwnd(self), dark=(self.settings["theme"] == "dark")))

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

    def t(self, key, **kw):
        return get_text(self.lang, key, **kw)

    # ======================== HOTKEY (window-focus only) ========================

    def _hotkey_str_to_tk(self, hk):
        parts = [p.strip().lower() for p in hk.split('+')]
        mods  = []
        key   = parts[-1]
        for p in parts[:-1]:
            if p == 'ctrl':    mods.append('Control')
            elif p == 'shift':  mods.append('Shift')
            elif p == 'alt':    mods.append('Alt')
        mod_str = ''.join(f'<{m}-' for m in mods)
        if mods:
            return mod_str + key + '>'
        if key.startswith('f') and key[1:].isdigit():
            return f'<{key.upper()}>'
        return f'<{key}>'

    def _bind_hotkey(self):
        hk = self.settings.get("hotkey", "F9").strip()
        try:
            seq = self._hotkey_str_to_tk(hk)
            self.bind(seq, lambda e: self._toggle_presets())
            self._hotkey_seq = seq
        except Exception:
            pass

    def _unbind_hotkey(self):
        try:
            if hasattr(self, '_hotkey_seq'):
                self.unbind(self._hotkey_seq)
        except Exception:
            pass

    def _toggle_presets(self):
        pa = self.settings.get("preset_a", "")
        pb = self.settings.get("preset_b", "")
        if not pa or not pb or pa not in self.presets or pb not in self.presets:
            self._set_status("Set Preset A and B in Settings first", danger=True)
            return
        name = pa if self.toggle_state == 0 else pb
        self.toggle_state = 1 - self.toggle_state
        dns  = self.presets[name]
        self.selected_preset = name
        self._build_preset_list()
        self._set_status(f"Applying {name}...")
        threading.Thread(target=lambda: self._do_apply(name, dns), daemon=True).start()

    # ======================== UI BUILD ========================

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _build_ui(self):
        self._clear()
        c = self.colors

        # ---- MAIN SCROLLABLE CONTAINER (so nothing gets cut off) ----
        self.scroll_body = ctk.CTkScrollableFrame(self, fg_color="transparent",
            scrollbar_button_color=c["accent"],
            scrollbar_button_hover_color=c["accent_hover"])
        self.scroll_body.pack(fill="both", expand=True)

        sb = self.scroll_body  # shorthand

        # ---- HEADER ----
        hdr = ctk.CTkFrame(sb, fg_color="transparent")
        hdr.pack(fill="x", padx=18, pady=(12, 2))

        ctk.CTkLabel(hdr, text="Modern DNS Changer",
            font=ctk.CTkFont("Segoe UI", 18, "bold"),
            text_color=c["text"]).pack(side="left")

        ctk.CTkButton(hdr, text=self.t("settings_btn"),
            width=85, height=26,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=6, command=self._open_settings
        ).pack(side="right")

        ctk.CTkLabel(sb, text=self.t("subtitle"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"]
        ).pack(anchor="w", padx=18, pady=(0, 8))

        # ---- ADAPTER ----
        self._sec(sb, self.t("adapter"))
        af = ctk.CTkFrame(sb, fg_color=c["card"], corner_radius=8)
        af.pack(fill="x", padx=18, pady=(2, 6))

        self.adapter_var  = ctk.StringVar(value=DEFAULT_ADAPTER)
        self.adapter_menu = ctk.CTkOptionMenu(
            af, variable=self.adapter_var,
            values=[DEFAULT_ADAPTER],
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=6, height=30, font=ctk.CTkFont("Segoe UI", 12))
        self.adapter_menu.pack(fill="x", padx=10, pady=8)
        threading.Thread(target=self._load_adapters, daemon=True).start()

        # ---- QUICK ACTIONS ----
        self._sec(sb, self.t("quick_actions"))
        qf = ctk.CTkFrame(sb, fg_color=c["card"], corner_radius=8)
        qf.pack(fill="x", padx=18, pady=(2, 6))

        br = ctk.CTkFrame(qf, fg_color="transparent")
        br.pack(fill="x", padx=10, pady=(8, 0))

        ctk.CTkButton(br, text=self.t("apply_dns"), height=32,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=6, command=self._apply_selected
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(br, text=self.t("auto_dhcp"), height=32,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["secondary_btn"], hover_color=c["secondary_hover"],
            text_color=c["text"], corner_radius=6, command=self._set_dhcp
        ).pack(side="left", fill="x", expand=True)

        self.status_lbl = ctk.CTkLabel(qf, text=self.t("status_ready"),
            font=ctk.CTkFont("Segoe UI", 11), text_color=c["muted"])
        self.status_lbl.pack(anchor="w", padx=10, pady=(3, 6))

        # ---- PRESETS ----
        self._sec(sb, self.t("presets"))

        # Presets header row with Ping All button
        presets_hdr = ctk.CTkFrame(sb, fg_color="transparent")
        presets_hdr.pack(fill="x", padx=18, pady=(0, 2))

        # Card containing presets list
        self.presets_outer = ctk.CTkFrame(sb, fg_color=c["card"], corner_radius=8)
        self.presets_outer.pack(fill="x", padx=18, pady=(0, 6))

        self.presets_scroll = ctk.CTkScrollableFrame(
            self.presets_outer, fg_color="transparent",
            scrollbar_button_color=c["accent"],
            scrollbar_button_hover_color=c["accent_hover"],
            height=140)
        self.presets_scroll.pack(fill="x", padx=8, pady=6)
        self._build_preset_list()

        # ---- ADD PRESET ----
        self._sec(sb, self.t("add_new_preset"))
        af2 = ctk.CTkFrame(sb, fg_color=c["card"], corner_radius=8)
        af2.pack(fill="x", padx=18, pady=(2, 10))

        row1 = ctk.CTkFrame(af2, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 4))

        eargs = dict(height=30, corner_radius=6,
            fg_color=c["entry"], text_color=c["text"],
            placeholder_text_color=c["muted"],
            border_color=c["border"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 12))

        self.name_entry = ctk.CTkEntry(row1, placeholder_text=self.t("preset_name"), **eargs)
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.primary_entry = ctk.CTkEntry(row1, placeholder_text=self.t("preferred_dns"), **eargs)
        self.primary_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.secondary_entry = ctk.CTkEntry(row1, placeholder_text=self.t("secondary_dns"), **eargs)
        self.secondary_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(af2, text=self.t("add_preset_btn"), height=30,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=6, command=self._add_preset
        ).pack(fill="x", padx=10, pady=(0, 8))

    def _sec(self, parent, label):
        ctk.CTkLabel(parent, text=label,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color=self.colors["muted"]
        ).pack(anchor="w", padx=18, pady=(4, 0))

    # ======================== PRESET LIST (with ping buttons) ========================

    def _build_preset_list(self):
        c = self.colors
        for w in self.presets_scroll.winfo_children():
            w.destroy()
        self.ping_labels = {}
        self.ping_buttons = {}

        if not self.presets:
            ctk.CTkLabel(self.presets_scroll,
                text=self.t("no_presets"),
                font=ctk.CTkFont("Segoe UI", 12),
                text_color=c["muted"]).pack(pady=15)
            # Even with no presets, show Ping All button placeholder
            self._build_ping_all_area()
            return

        if self.selected_preset not in self.presets:
            self.selected_preset = None

        for name, dns in self.presets.items():
            is_sel = (name == self.selected_preset)
            row = ctk.CTkFrame(self.presets_scroll,
                fg_color=c["selected"] if is_sel else c["card2"],
                corner_radius=6,
                border_width=1,
                border_color=c["selected_border"] if is_sel else c["border"])
            row.pack(fill="x", pady=2)

            # Selection dot
            dot = ctk.CTkLabel(row, text="●" if is_sel else "○",
                font=ctk.CTkFont("Segoe UI", 13),
                text_color=c["accent"] if is_sel else c["border"], width=20)
            dot.pack(side="left", padx=(6, 0))

            # Name + DNS info
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=4, pady=5)

            ctk.CTkLabel(info, text=name,
                font=ctk.CTkFont("Segoe UI", 12, "bold"),
                text_color=c["text"], anchor="w").pack(anchor="w")

            dns_text = f"{dns.get('primary','—')}  /  {dns.get('secondary','—')}"
            ctk.CTkLabel(info, text=dns_text,
                font=ctk.CTkFont("Consolas", 11),
                text_color=c["muted"], anchor="w").pack(anchor="w")

            # Ping result label (shows latency after ping)
            ping_lbl = ctk.CTkLabel(row, text="",
                font=ctk.CTkFont("Segoe UI", 10, "bold"),
                text_color=c["muted"], width=55, anchor="e")
            ping_lbl.pack(side="right", padx=(4, 2))
            self.ping_labels[name] = ping_lbl

            # Ping button
            ping_btn = ctk.CTkButton(row, text="Ping", width=40, height=24,
                corner_radius=5,
                fg_color=c["ping_good"], hover_color=c["accent_hover"],
                font=ctk.CTkFont("Segoe UI", 10, "bold"),
                text_color="white",
                command=lambda n=name: self._ping_preset(n))
            ping_btn.pack(side="right", padx=2)
            self.ping_buttons[name] = ping_btn

            # Delete button
            ctk.CTkButton(row, text="X", width=24, height=24,
                corner_radius=5,
                fg_color=c["delete_btn"], hover_color=c["delete_hover"],
                font=ctk.CTkFont("Segoe UI", 10, "bold"),
                text_color=c["text"],
                command=lambda n=name: self._delete_preset(n)
            ).pack(side="right", padx=(0, 2))

            # Click to select
            for w in [row, info, dot] + list(info.winfo_children()):
                w.bind("<Button-1>", lambda e, n=name: self._select_preset(n))

        # Ping All button below the list
        self._build_ping_all_area()

    def _build_ping_all_area(self):
        """Add a Ping All button + a 'best result' label below the preset list, inside the card."""
        c = self.colors
        bottom = ctk.CTkFrame(self.presets_outer, fg_color="transparent")
        bottom.pack(fill="x", padx=8, pady=(0, 6))

        self.ping_all_btn = ctk.CTkButton(bottom, text="Ping All", height=26,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            fg_color=c["ping_good"], hover_color=c["accent_hover"],
            text_color="white", corner_radius=5,
            command=self._ping_all)
        self.ping_all_btn.pack(side="left", padx=(0, 8))

        self.ping_summary_lbl = ctk.CTkLabel(bottom, text="",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=c["muted"], anchor="w")
        self.ping_summary_lbl.pack(side="left", fill="x", expand=True)

    def _select_preset(self, name):
        self.selected_preset = name
        self._build_preset_list()

    # ======================== PING ACTIONS ========================

    def _ping_preset(self, name):
        """Ping a single preset's primary DNS and show the result."""
        dns = self.presets.get(name, {})
        primary = dns.get("primary", "")
        if not primary:
            return

        # Show "pinging..." state
        if name in self.ping_buttons:
            self.ping_buttons[name].configure(text="...", state="disabled")
        if name in self.ping_labels:
            self.ping_labels[name].configure(text="pinging...", text_color=self.colors["muted"])

        def worker():
            avg, mn, loss = ping_dns(primary, count=3, timeout=2000)
            self.after(0, lambda: self._show_ping_result(name, avg, mn, loss))

        threading.Thread(target=worker, daemon=True).start()

    def _show_ping_result(self, name, avg, mn, loss):
        c = self.colors
        btn = self.ping_buttons.get(name)
        lbl = self.ping_labels.get(name)

        if btn:
            btn.configure(text="Ping", state="normal")

        if avg is None or loss >= 100:
            if lbl:
                lbl.configure(text="timeout", text_color=c["ping_fail"])
        else:
            # Color code by latency
            if avg < 30:
                color = c["ping_ok"]    # green = excellent
            elif avg < 80:
                color = c["ping_good"]   # blue = good
            elif avg < 150:
                color = c["ping_bad"]    # orange = slow
            else:
                color = c["ping_fail"]   # red = very slow

            loss_str = f" ({loss:.0f}% loss)" if loss > 0 else ""
            if lbl:
                lbl.configure(text=f"{avg}ms{loss_str}", text_color=color)

    def _ping_all(self):
        """Ping all presets one by one, then show which is best."""
        if not self.presets:
            self._set_status("No presets to ping", danger=True)
            return

        names = list(self.presets.keys())
        self.ping_all_btn.configure(text="Pinging...", state="disabled")
        self.ping_summary_lbl.configure(text="Pinging all presets...", text_color=self.colors["muted"])

        # Disable all individual ping buttons
        for n in names:
            if n in self.ping_buttons:
                self.ping_buttons[n].configure(text="...", state="disabled")
            if n in self.ping_labels:
                self.ping_labels[n].configure(text="...", text_color=self.colors["muted"])

        def worker():
            results = {}
            for name in names:
                dns = self.presets.get(name, {})
                primary = dns.get("primary", "")
                if primary:
                    avg, mn, loss = ping_dns(primary, count=3, timeout=2000)
                    results[name] = (avg, mn, loss)
                    self.after(0, lambda n=name, a=avg, m=mn, l=loss: self._show_ping_result(n, a, m, l))
                else:
                    results[name] = (None, None, 100)
                    self.after(0, lambda n=name: self._show_ping_result(n, None, None, 100))

            # Find best
            best_name = None
            best_avg  = float('inf')
            for name, (avg, mn, loss) in results.items():
                if avg is not None and avg < best_avg:
                    best_avg = avg
                    best_name = name

            def update_summary():
                self.ping_all_btn.configure(text="Ping All", state="normal")
                if best_name:
                    self.ping_summary_lbl.configure(
                        text=f"Best: {best_name} ({best_avg}ms)",
                        text_color=self.colors["success"])
                    self._set_status(f"Best DNS: {best_name} at {best_avg}ms", success=True)
                else:
                    self.ping_summary_lbl.configure(
                        text="All presets timed out",
                        text_color=self.colors["danger"])
                    self._set_status("All presets timed out", danger=True)

            self.after(0, update_summary)

        threading.Thread(target=worker, daemon=True).start()

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
        self._set_status(self.t("applying", name=name))
        threading.Thread(target=lambda: self._do_apply(name, dns), daemon=True).start()

    def _do_apply(self, name, dns):
        set_dns(dns.get("primary", ""), dns.get("secondary", ""), self.adapter_var.get())
        self.after(0, lambda: self._set_status(
            self.t("applied", name=name, adapter=self.adapter_var.get()), success=True))

    def _set_dhcp(self):
        adapter = self.adapter_var.get()
        self._set_status(self.t("dhcp_applying"))
        def worker():
            set_dns_dhcp(adapter)
            self.after(0, lambda: self._set_status(
                self.t("dhcp_done", adapter=adapter), success=True))
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
            self._set_status(self.t("enter_name"), danger=True); return
        if not primary:
            self._set_status(self.t("enter_primary"), danger=True); return
        self.presets[name] = {"primary": primary, "secondary": secondary}
        save_json(PRESETS_FILE, self.presets)
        self.name_entry.delete(0, "end")
        self.primary_entry.delete(0, "end")
        self.secondary_entry.delete(0, "end")
        if not self.selected_preset:
            self.selected_preset = name
        self._build_preset_list()
        self._set_status(self.t("preset_saved", name=name), success=True)

    def _delete_preset(self, name):
        if name in self.presets:
            del self.presets[name]
            save_json(PRESETS_FILE, self.presets)
            if self.selected_preset == name:
                self.selected_preset = list(self.presets.keys())[0] if self.presets else None
            self._build_preset_list()
            self._set_status(self.t("preset_deleted", name=name))

    # ======================== ADAPTER ========================

    def _load_adapters(self):
        adapters = get_adapters()
        try:
            cf = 0x08000000 if sys.platform == 'win32' else 0
            r = subprocess.run('netsh wlan show interfaces',
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
        win.title(self.t("settings_title"))
        win.geometry("460x580")
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text=self.t("settings_title"),
            font=ctk.CTkFont("Segoe UI", 18, "bold"),
            text_color=c["text"]).pack(pady=(16, 12))

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent",
            scrollbar_button_color=c["accent"])
        scroll.pack(fill="both", expand=True)

        def section(parent, label):
            ctk.CTkLabel(parent, text=label,
                font=ctk.CTkFont("Segoe UI", 12, "bold"),
                text_color=c["accent_light"]
            ).pack(anchor="w", padx=18, pady=(8, 3))

        def seg(parent, values, current, cmd):
            s = ctk.CTkSegmentedButton(parent, values=values, command=cmd,
                fg_color=c["card2"], selected_color=c["accent"],
                selected_hover_color=c["accent_hover"],
                unselected_color=c["card2"],
                unselected_hover_color=c["secondary_hover"],
                text_color="white", corner_radius=6, height=32,
                font=ctk.CTkFont("Segoe UI", 12, "bold"))
            s.set(current)
            s.pack(fill="x", padx=18, pady=(0, 2))
            return s

        # Theme
        section(scroll, self.t("appearance"))
        seg(scroll, [self.t("dark_mode"), self.t("light_mode")],
            self.t("dark_mode") if self.settings["theme"] == "dark" else self.t("light_mode"),
            lambda v: self._change_theme("dark" if v == self.t("dark_mode") else "light", win))

        # Language
        section(scroll, self.t("language_section"))
        seg(scroll, [self.t("english"), self.t("persian")],
            self.t("english") if self.lang == "en" else self.t("persian"),
            lambda v: self._change_language("en" if v == self.t("english") else "fa", win))

        # Hotkey
        section(scroll, self.t("hotkey"))
        ctk.CTkLabel(scroll, text=self.t("hotkey_desc"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], wraplength=400, justify="left"
        ).pack(anchor="w", padx=18, pady=(0, 4))

        hk_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        hk_frame.pack(fill="x", padx=18, pady=(0, 2))

        hk_entry = ctk.CTkEntry(hk_frame, height=30, corner_radius=6,
            fg_color=c["entry"], text_color=c["text"],
            border_color=c["accent"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 12),
            placeholder_text="e.g. F9 or ctrl+d")
        hk_entry.insert(0, self.settings.get("hotkey", "F9"))
        hk_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def save_hk():
            val = hk_entry.get().strip() or "F9"
            self.settings["hotkey"] = val
            save_json(SETTINGS_FILE, self.settings)
            self._unbind_hotkey()
            self._bind_hotkey()
            self._set_status(self.t("hotkey_saved", key=val), success=True)

        ctk.CTkButton(hk_frame, text=self.t("save_hotkey"), width=70, height=30,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=6, command=save_hk).pack(side="left")

        keys_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        keys_frame.pack(fill="x", padx=18, pady=(0, 6))
        for key in ["F5", "F6", "F7", "F8", "F9", "F10", "ctrl+d", "ctrl+shift+d"]:
            ctk.CTkButton(keys_frame, text=key, width=72, height=24,
                font=ctk.CTkFont("Segoe UI", 10),
                fg_color=c["card2"], hover_color=c["secondary_hover"],
                text_color=c["text"], corner_radius=5,
                command=lambda k=key: (hk_entry.delete(0, "end"), hk_entry.insert(0, k))
            ).pack(side="left", padx=1, pady=2)

        # Toggle Presets A / B
        section(scroll, "Toggle Presets (A / B)")
        ctk.CTkLabel(scroll,
            text="Pressing the hotkey switches between Preset A and B.",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], wraplength=400, justify="left"
        ).pack(anchor="w", padx=18, pady=(0, 4))

        preset_names = list(self.presets.keys()) or ["(no presets)"]

        ab_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        ab_frame.pack(fill="x", padx=18, pady=(0, 4))

        ctk.CTkLabel(ab_frame, text="A", width=18,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=c["text"]).pack(side="left", padx=(0, 3))

        self.hk_a_var = ctk.StringVar()
        self.hk_a_var.set(self.settings.get("preset_a", "") or preset_names[0])
        ctk.CTkOptionMenu(ab_frame, variable=self.hk_a_var,
            values=preset_names,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=6, height=30, font=ctk.CTkFont("Segoe UI", 12)
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkLabel(ab_frame, text="B", width=18,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=c["text"]).pack(side="left", padx=(0, 3))

        self.hk_b_var = ctk.StringVar()
        b_def = self.settings.get("preset_b", "")
        if not b_def and len(preset_names) > 1:
            b_def = preset_names[1]
        self.hk_b_var.set(b_def or preset_names[0])
        ctk.CTkOptionMenu(ab_frame, variable=self.hk_b_var,
            values=preset_names,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=6, height=30, font=ctk.CTkFont("Segoe UI", 12)
        ).pack(side="left", fill="x", expand=True)

        def save_ab():
            self.settings["preset_a"] = self.hk_a_var.get()
            self.settings["preset_b"] = self.hk_b_var.get()
            save_json(SETTINGS_FILE, self.settings)
            self._set_status(
                f"Toggle: {self.settings['preset_a']} <-> {self.settings['preset_b']}",
                success=True)

        ctk.CTkButton(scroll, text="Save A / B", height=30,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=6, command=save_ab
        ).pack(fill="x", padx=18, pady=(0, 6))

        # Tray
        section(scroll, self.t("tray_section"))
        tray_var = ctk.StringVar(value="On" if self.settings.get("minimize_to_tray", True) else "Off")
        def _tray_toggle(v):
            self.settings["minimize_to_tray"] = (v == "On")
            save_json(SETTINGS_FILE, self.settings)
        seg(scroll, ["On", "Off"], tray_var.get(), _tray_toggle)

        # About
        section(scroll, self.t("about_section"))
        ctk.CTkLabel(scroll, text=self.t("about_text"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], justify="center").pack(padx=18, pady=(0, 8))

        ctk.CTkButton(win, text=self.t("close"), height=34, corner_radius=6,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=win.destroy).pack(fill="x", padx=18, pady=(4, 12))

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
                pystray.MenuItem(self.t("tray_show"),
                    lambda *_: self.after(0, self._restore_from_tray), default=True),
                pystray.MenuItem(self.t("tray_toggle"),
                    lambda *_: self.after(0, self._toggle_presets)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(self.t("tray_quit"),
                    lambda *_: self.after(0, self._quit_app)),
            )
            self.tray_icon = pystray.Icon("dns_changer", create_tray_image(64),
                                          self.t("tray_tooltip"), menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"Tray error: {e}")

    def _on_close(self): self.withdraw()
    def _restore_from_tray(self): self.deiconify(); self.lift(); self.focus_force()

    def _quit_app(self):
        if self.tray_icon:
            try: self.tray_icon.stop()
            except Exception: pass
        self.destroy()

    # ======================== ADMIN ========================

    def _show_admin_warning(self):
        c = self.colors
        win = ctk.CTkToplevel(self)
        win.title(self.t("admin_needed"))
        win.geometry("360x160")
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)

        ctk.CTkLabel(win, text=self.t("admin_needed"),
            font=ctk.CTkFont("Segoe UI", 15, "bold"),
            text_color=c["accent_light"]).pack(pady=(20, 4))
        ctk.CTkLabel(win, text=self.t("admin_msg"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], justify="center").pack(pady=(0, 12))
        ctk.CTkButton(win, text=self.t("restart_admin"), width=150, height=32,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=6, command=self._restart_as_admin).pack()

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
