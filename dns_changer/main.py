import customtkinter as ctk
import json
import os
import subprocess
import sys
import ctypes
import threading
import keyboard
from tkinter import messagebox

# ======================== CONFIG ========================
APP_NAME = "Modern DNS Changer"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
# When running as .exe, use the exe's directory
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)

PRESETS_FILE = os.path.join(APP_DIR, "presets.json")
DEFAULT_ADAPTER = "Wi-Fi"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Blue accent palette
ACCENT_BLUE = "#1F6AA5"
ACCENT_BLUE_HOVER = "#144870"
ACCENT_LIGHT = "#2D8FD6"
BG_COLOR = "#1A1A2E"
CARD_COLOR = "#16213E"
ENTRY_BG = "#0F3460"
TEXT_COLOR = "#EAEAEA"
MUTED_COLOR = "#8892B0"
SUCCESS_GREEN = "#4ADE80"
DANGER_RED = "#EF4444"

# ======================== WINDOWS 11 NATIVE EFFECTS ========================

def apply_windows11_effects(hwnd):
    """Apply Windows 11 Mica backdrop and rounded corners to the window."""
    if not sys.platform == 'win32':
        return

    try:
        dwm = ctypes.WinDLL("dwmapi.dll")

        # --- Mica Backdrop (Windows 11 22H2+) ---
        # DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_MAINWINDOW = 2  # Mica
        try:
            dwm.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_int(38),  # DWMWA_SYSTEMBACKDROP_TYPE
                ctypes.byref(ctypes.c_int(DWMSBT_MAINWINDOW)),
                ctypes.c_int(ctypes.sizeof(ctypes.c_int))
            )
        except Exception:
            pass

        # --- Dark mode title bar ---
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (before 20H1) or 19 (after)
        for attr in (20, 19):
            try:
                dwm.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_int(attr),
                    ctypes.byref(ctypes.c_int(1)),  # TRUE
                    ctypes.c_int(ctypes.sizeof(ctypes.c_int))
                )
            except Exception:
                pass

        # --- Rounded corners ---
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        try:
            dwm.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_int(33),
                ctypes.byref(ctypes.c_int(DWMWCP_ROUND)),
                ctypes.c_int(ctypes.sizeof(ctypes.c_int))
            )
        except Exception:
            pass

        # --- Extend frame into client area for backdrop ---
        # Extend frame to allow Mica to show through
        margins = ctypes.c_int(-1)  # -1 = extend to whole window
        try:
            dwm.DwmExtendFrameIntoClientArea(
                ctypes.c_void_p(hwnd),
                ctypes.byref(ctypes.c_int(margins))
            )
        except Exception:
            pass

    except Exception as e:
        print(f"Win11 effects: {e}")


def get_hwnd(window):
    """Get the Windows HWND from a tkinter/customtkinter window."""
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
    """Run a command silently via subprocess."""
    try:
        # CREATE_NO_WINDOW flag to hide console on .exe
        creationflags = 0x08000000 if sys.platform == 'win32' else 0
        subprocess.run(command, shell=True, capture_output=True, text=True,
                      timeout=10, creationflags=creationflags)
        return True
    except Exception as e:
        print(f"Command failed: {e}")
        return False

def set_dns(primary, secondary, adapter=DEFAULT_ADAPTER):
    """Set DNS for the given adapter using netsh."""
    run_cmd(f'netsh interface ip set dns name="{adapter}" dhcp')

    if primary:
        ok1 = run_cmd(f'netsh interface ip set dns name="{adapter}" static {primary} primary')
    else:
        ok1 = run_cmd(f'netsh interface ip set dns name="{adapter}" dhcp')

    if secondary:
        ok2 = run_cmd(f'netsh interface ip add dns name="{adapter}" {secondary} index=2')
    else:
        ok2 = True

    return ok1 and ok2

def set_dns_dhcp(adapter=DEFAULT_ADAPTER):
    """Reset DNS to automatic (DHCP)."""
    ok1 = run_cmd(f'netsh interface ip set dns name="{adapter}" dhcp')
    ok2 = run_cmd(f'netsh interface ip delete dns name="{adapter}" all')
    return ok1 and ok2

def get_current_dns(adapter=DEFAULT_ADAPTER):
    """Get current DNS settings for the adapter."""
    try:
        result = subprocess.run(
            f'netsh interface ip show dnsservers name="{adapter}"',
            shell=True, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return "Unable to read"

def get_adapters():
    """Get list of network adapters."""
    try:
        result = subprocess.run(
            'netsh interface show interface',
            shell=True, capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split('\n')
        adapters = []
        for line in lines:
            if 'Dedicated' in line or 'Loopback' in line:
                continue
            parts = line.split()
            if len(parts) >= 4:
                name = ' '.join(parts[3:])
                adapters.append(name)
        if not adapters:
            adapters = [DEFAULT_ADAPTER]
        return adapters
    except Exception:
        return [DEFAULT_ADAPTER]

# ======================== PRESET STORAGE ========================

def load_presets():
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_presets(presets):
    with open(PRESETS_FILE, 'w') as f:
        json.dump(presets, f, indent=2)

def load_hotkey_config():
    """Load hotkey toggle configuration."""
    config_path = os.path.join(APP_DIR, "hotkey_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {"hotkey": "ctrl+shift+d", "preset_a": "", "preset_b": ""}
    return {"hotkey": "ctrl+shift+d", "preset_a": "", "preset_b": ""}

def save_hotkey_config(config):
    config_path = os.path.join(APP_DIR, "hotkey_config.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

# ======================== UI ========================

class DNSChangerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.presets = load_presets()
        self.hotkey_config = load_hotkey_config()
        self.toggle_state = 0  # 0 = preset_a, 1 = preset_b

        self.title(APP_NAME)
        self.geometry("640x820")
        self.minsize(580, 740)
        self.configure(fg_color=BG_COLOR)

        self._build_ui()
        self._refresh_preset_dropdowns()
        self._start_hotkey_listener()

        # Apply Windows 11 native effects (Mica, dark titlebar, rounded corners)
        self.after(100, self._apply_win11_effects)

        # Admin warning
        if not is_admin():
            self.after(500, self._show_admin_warning)

    def _apply_win11_effects(self):
        """Apply Windows 11 Mica backdrop and rounded corners."""
        hwnd = get_hwnd(self)
        if hwnd:
            apply_windows11_effects(hwnd)

    # ---------- UI BUILD ----------

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 5))

        title_label = ctk.CTkLabel(
            header_frame, text="🌐  Modern DNS Changer",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=TEXT_COLOR
        )
        title_label.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header_frame, text="Manage your WiFi DNS settings with style",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=MUTED_COLOR
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # Adapter selection
        adapter_frame = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=15)
        adapter_frame.pack(fill="x", padx=30, pady=(20, 10))

        ctk.CTkLabel(
            adapter_frame, text="Network Adapter",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_COLOR
        ).pack(anchor="w", padx=20, pady=(15, 5))

        self.adapter_var = ctk.StringVar(value=DEFAULT_ADAPTER)
        self.adapter_menu = ctk.CTkOptionMenu(
            adapter_frame,
            values=[DEFAULT_ADAPTER],
            variable=self.adapter_var,
            fg_color=ACCENT_BLUE,
            button_color=ACCENT_BLUE,
            button_hover_color=ACCENT_BLUE_HOVER,
            text_color="white",
            dropdown_fg_color=CARD_COLOR,
            dropdown_text_color=TEXT_COLOR,
            dropdown_hover_color=ACCENT_BLUE,
            corner_radius=10,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=14)
        )
        self.adapter_menu.pack(fill="x", padx=20, pady=(0, 15))

        # Load adapters in background
        threading.Thread(target=self._load_adapters, daemon=True).start()

        # Quick Actions Card
        quick_frame = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=15)
        quick_frame.pack(fill="x", padx=30, pady=(10, 10))

        ctk.CTkLabel(
            quick_frame, text="Quick Actions",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_COLOR
        ).pack(anchor="w", padx=20, pady=(15, 5))

        btn_row = ctk.CTkFrame(quick_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 15))

        self.apply_btn = ctk.CTkButton(
            btn_row, text="⚡ Apply DNS", width=140, height=42,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER,
            corner_radius=10, command=self._apply_dns
        )
        self.apply_btn.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.dhcp_btn = ctk.CTkButton(
            btn_row, text="🔄 Auto (DHCP)", width=140, height=42,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color="#44475A", hover_color="#383B4D",
            corner_radius=10, command=self._set_dhcp
        )
        self.dhcp_btn.pack(side="left", fill="x", expand=True)

        # Status display
        self.status_label = ctk.CTkLabel(
            quick_frame, text="●  Ready",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=MUTED_COLOR
        )
        self.status_label.pack(anchor="w", padx=20, pady=(0, 10))

        # Presets section
        presets_frame = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=15)
        presets_frame.pack(fill="both", expand=True, padx=30, pady=(10, 10))

        ctk.CTkLabel(
            presets_frame, text="📋  DNS Presets",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_COLOR
        ).pack(anchor="w", padx=20, pady=(15, 10))

        # Preset list (scrollable)
        self.scroll_frame = ctk.CTkScrollableFrame(
            presets_frame, fg_color="transparent",
            scrollbar_button_color=ACCENT_BLUE,
            scrollbar_button_hover_color=ACCENT_BLUE_HOVER
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        self._build_preset_list()

        # Add new preset inputs
        add_frame = ctk.CTkFrame(presets_frame, fg_color="transparent")
        add_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            add_frame, text="Add New Preset",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_COLOR
        ).pack(anchor="w", pady=(0, 8))

        self.name_entry = ctk.CTkEntry(
            add_frame, placeholder_text="Preset name (e.g. Google DNS)",
            height=38, corner_radius=10,
            fg_color=ENTRY_BG, text_color=TEXT_COLOR,
            border_color=ACCENT_BLUE, border_width=1
        )
        self.name_entry.pack(fill="x", pady=(0, 8))

        self.primary_entry = ctk.CTkEntry(
            add_frame, placeholder_text="Preferred DNS  (e.g. 8.8.8.8)",
            height=38, corner_radius=10,
            fg_color=ENTRY_BG, text_color=TEXT_COLOR,
            border_color=ACCENT_BLUE, border_width=1
        )
        self.primary_entry.pack(fill="x", pady=(0, 8))

        self.secondary_entry = ctk.CTkEntry(
            add_frame, placeholder_text="Secondary DNS  (e.g. 8.8.4.4)",
            height=38, corner_radius=10,
            fg_color=ENTRY_BG, text_color=TEXT_COLOR,
            border_color=ACCENT_BLUE, border_width=1
        )
        self.secondary_entry.pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            add_frame, text="➕  Add Preset", height=40, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER,
            command=self._add_preset
        ).pack(fill="x")

        # Hotkey toggle section
        hotkey_frame = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=15)
        hotkey_frame.pack(fill="x", padx=30, pady=(10, 25))

        ctk.CTkLabel(
            hotkey_frame, text="⌨️  Toggle Hotkey",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_COLOR
        ).pack(anchor="w", padx=20, pady=(15, 5))

        ctk.CTkLabel(
            hotkey_frame,
            text="Press the hotkey to switch between two selected presets instantly.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=MUTED_COLOR
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # Hotkey preset selectors
        hk_row = ctk.CTkFrame(hotkey_frame, fg_color="transparent")
        hk_row.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(hk_row, text="Preset A:", width=70,
                     font=ctk.CTkFont(size=13), text_color=MUTED_COLOR
                     ).pack(side="left", padx=(0, 5))

        self.hk_a_var = ctk.StringVar(value="")
        self.hk_a_menu = ctk.CTkOptionMenu(
            hk_row, values=[], variable=self.hk_a_var,
            fg_color=ACCENT_BLUE, button_color=ACCENT_BLUE,
            button_hover_color=ACCENT_BLUE_HOVER, text_color="white",
            dropdown_fg_color=CARD_COLOR, dropdown_text_color=TEXT_COLOR,
            dropdown_hover_color=ACCENT_BLUE, corner_radius=10, height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13)
        )
        self.hk_a_menu.pack(side="left", padx=(0, 10), fill="x", expand=True)

        ctk.CTkLabel(hk_row, text="Preset B:", width=70,
                     font=ctk.CTkFont(size=13), text_color=MUTED_COLOR
                     ).pack(side="left", padx=(0, 5))

        self.hk_b_var = ctk.StringVar(value="")
        self.hk_b_menu = ctk.CTkOptionMenu(
            hk_row, values=[], variable=self.hk_b_var,
            fg_color=ACCENT_BLUE, button_color=ACCENT_BLUE,
            button_hover_color=ACCENT_BLUE_HOVER, text_color="white",
            dropdown_fg_color=CARD_COLOR, dropdown_text_color=TEXT_COLOR,
            dropdown_hover_color=ACCENT_BLUE, corner_radius=10, height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13)
        )
        self.hk_b_menu.pack(side="left", fill="x", expand=True)

        # Hotkey input
        hk_row2 = ctk.CTkFrame(hotkey_frame, fg_color="transparent")
        hk_row2.pack(fill="x", padx=20, pady=(10, 15))

        ctk.CTkLabel(hk_row2, text="Hotkey:", width=70,
                     font=ctk.CTkFont(size=13), text_color=MUTED_COLOR
                     ).pack(side="left", padx=(0, 5))

        self.hotkey_entry = ctk.CTkEntry(
            hk_row2, height=36, corner_radius=10,
            fg_color=ENTRY_BG, text_color=TEXT_COLOR,
            border_color=ACCENT_BLUE, border_width=1
        )
        self.hotkey_entry.insert(0, self.hotkey_config.get("hotkey", "ctrl+shift+d"))
        self.hotkey_entry.pack(side="left", padx=(0, 10), fill="x", expand=True)

        ctk.CTkButton(
            hk_row2, text="Save Hotkey", width=120, height=36, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER,
            command=self._save_hotkey
        ).pack(side="left")

    # ---------- PRESET LIST ----------

    def _build_preset_list(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not self.presets:
            ctk.CTkLabel(
                self.scroll_frame, text="No presets yet.\nAdd one below 👇",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=MUTED_COLOR, justify="center"
            ).pack(pady=30)
            return

        for name, dns in self.presets.items():
            card = ctk.CTkFrame(
                self.scroll_frame, fg_color=ENTRY_BG, corner_radius=10
            )
            card.pack(fill="x", pady=4, padx=2)

            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=15, pady=10)

            ctk.CTkLabel(
                info_frame, text=name,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=TEXT_COLOR
            ).pack(anchor="w")

            dns_text = f"{dns.get('primary', '—')}  /  {dns.get('secondary', '—')}"
            ctk.CTkLabel(
                info_frame, text=dns_text,
                font=ctk.CTkFont(family="Consolas", size=12),
                text_color=MUTED_COLOR
            ).pack(anchor="w", pady=(2, 0))

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(side="right", padx=10, pady=10)

            ctk.CTkButton(
                btn_frame, text="Apply", width=70, height=32, corner_radius=8,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER,
                command=lambda n=name, d=dns: self._apply_preset(n, d)
            ).pack(side="left", padx=(0, 5))

            ctk.CTkButton(
                btn_frame, text="🗑", width=32, height=32, corner_radius=8,
                font=ctk.CTkFont(size=13),
                fg_color="#3A1F2E", hover_color="#5C2740",
                command=lambda n=name: self._delete_preset(n)
            ).pack(side="left")

    # ---------- ACTIONS ----------

    def _load_adapters(self):
        adapters = get_adapters()
        try:
            result = subprocess.run(
                'netsh wlan show interfaces',
                shell=True, capture_output=True, text=True, timeout=10
            )
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

    def _add_preset(self):
        name = self.name_entry.get().strip()
        primary = self.primary_entry.get().strip()
        secondary = self.secondary_entry.get().strip()

        if not name:
            self._set_status("⚠  Please enter a preset name", danger=True)
            return
        if not primary:
            self._set_status("⚠  Please enter a preferred DNS", danger=True)
            return

        self.presets[name] = {"primary": primary, "secondary": secondary}
        save_presets(self.presets)

        self.name_entry.delete(0, 'end')
        self.primary_entry.delete(0, 'end')
        self.secondary_entry.delete(0, 'end')

        self._build_preset_list()
        self._refresh_preset_dropdowns()
        self._set_status(f"✓ Preset '{name}' saved", success=True)

    def _delete_preset(self, name):
        if name in self.presets:
            del self.presets[name]
            save_presets(self.presets)
            self._build_preset_list()
            self._refresh_preset_dropdowns()
            self._set_status(f"✓ Deleted '{name}'", success=True)

    def _apply_preset(self, name, dns):
        adapter = self.adapter_var.get()
        primary = dns.get("primary", "")
        secondary = dns.get("secondary", "")

        self._set_status(f"⏳ Applying '{name}'...")

        def do_apply():
            ok = set_dns(primary, secondary, adapter)
            if ok:
                self.after(0, lambda: self._set_status(f"✓ Applied '{name}' to {adapter}", success=True))
            else:
                self.after(0, lambda: self._set_status("✗ Failed to apply DNS", danger=True))

        threading.Thread(target=do_apply, daemon=True).start()

    def _apply_dns(self):
        """Apply DNS from the quick action."""
        adapter = self.adapter_var.get()
        if self.presets:
            first_name = list(self.presets.keys())[0]
            self._apply_preset(first_name, self.presets[first_name])
        else:
            self._set_status("⚠  No presets saved yet", danger=True)

    def _set_dhcp(self):
        adapter = self.adapter_var.get()
        self._set_status("⏳ Setting to Auto (DHCP)...")

        def do_dhcp():
            ok = set_dns_dhcp(adapter)
            if ok:
                self.after(0, lambda: self._set_status(f"✓ Reset to DHCP on {adapter}", success=True))
            else:
                self.after(0, lambda: self._set_status("✗ Failed to reset DNS", danger=True))

        threading.Thread(target=do_dhcp, daemon=True).start()

    def _set_status(self, msg, success=False, danger=False):
        color = MUTED_COLOR
        if success:
            color = SUCCESS_GREEN
        elif danger:
            color = DANGER_RED
        self.status_label.configure(text=f"●  {msg}", text_color=color)

    # ---------- HOTKEY ----------

    def _refresh_preset_dropdowns(self):
        names = list(self.presets.keys())
        self.hk_a_menu.configure(values=names)
        self.hk_b_menu.configure(values=names)

        if self.hotkey_config.get("preset_a") in names:
            self.hk_a_var.set(self.hotkey_config["preset_a"])
        elif names:
            self.hk_a_var.set(names[0])
        else:
            self.hk_a_var.set("")

        if self.hotkey_config.get("preset_b") in names:
            self.hk_b_var.set(self.hotkey_config["preset_b"])
        elif len(names) > 1:
            self.hk_b_var.set(names[1])
        elif names:
            self.hk_b_var.set(names[0])
        else:
            self.hk_b_var.set("")

    def _save_hotkey(self):
        self.hotkey_config["hotkey"] = self.hotkey_entry.get().strip() or "ctrl+shift+d"
        self.hotkey_config["preset_a"] = self.hk_a_var.get()
        self.hotkey_config["preset_b"] = self.hk_b_var.get()
        save_hotkey_config(self.hotkey_config)

        self._stop_hotkey_listener()
        self._start_hotkey_listener()

        self._set_status(f"✓ Hotkey saved: {self.hotkey_config['hotkey']}", success=True)

    def _start_hotkey_listener(self):
        hotkey_str = self.hotkey_config.get("hotkey", "ctrl+shift+d")
        try:
            keyboard.add_hotkey(hotkey_str, self._toggle_presets)
        except Exception as e:
            print(f"Failed to register hotkey: {e}")

    def _stop_hotkey_listener(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def _toggle_presets(self):
        """Toggle between preset A and preset B."""
        preset_a = self.hotkey_config.get("preset_a", "")
        preset_b = self.hotkey_config.get("preset_b", "")

        if not preset_a or not preset_b:
            return
        if preset_a not in self.presets or preset_b not in self.presets:
            return

        if self.toggle_state == 0:
            self.toggle_state = 1
            name, dns = preset_a, self.presets[preset_a]
        else:
            self.toggle_state = 0
            name, dns = preset_b, self.presets[preset_b]

        adapter = self.adapter_var.get()
        ok = set_dns(dns.get("primary", ""), dns.get("secondary", ""), adapter)

        if ok:
            self.after(0, lambda: self._set_status(f"✓ Hotkey → '{name}'", success=True))
        else:
            self.after(0, lambda: self._set_status("✗ Toggle failed", danger=True))

    # ---------- ADMIN ----------

    def _show_admin_warning(self):
        warn = ctk.CTkToplevel(self)
        warn.title("Administrator Required")
        warn.geometry("400x200")
        warn.configure(fg_color=BG_COLOR)
        warn.resizable(False, False)
        warn.attributes("-topmost", True)
        warn.transient(self)

        ctk.CTkLabel(
            warn, text="⚠️  Administrator Needed",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=ACCENT_LIGHT
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            warn, text="DNS changes require admin privileges.\nPlease run this app as Administrator.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=MUTED_COLOR, justify="center"
        ).pack(pady=(0, 20))

        ctk.CTkButton(
            warn, text="Restart as Admin", width=160, height=40, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER,
            command=self._restart_as_admin
        ).pack(pady=(0, 20))

    def _restart_as_admin(self):
        try:
            if getattr(sys, 'frozen', False):
                # Running as .exe
                exe_path = sys.executable
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", exe_path, None, None, 1
                )
            else:
                # Running as script
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable,
                    f'"{os.path.abspath(__file__)}"', None, 1
                )
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to restart as admin:\n{e}")

    def destroy(self):
        self._stop_hotkey_listener()
        super().destroy()


# ======================== MAIN ========================

if __name__ == "__main__":
    app = DNSChangerApp()
    app.mainloop()
