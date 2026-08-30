"""
Main application UI for Modern DNS Changer v4.1.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from app_paths import (
    presets_path,
    settings_path,
    user_data_dir,
)
from dns_manager import (
    DnsResult,
    apply_dhcp,
    apply_static,
    list_adapters,
    ping_color,
    ping_host,
    ping_text,
    validate_preset,
)
from logger import get_logger
from platform_utils import (
    apply_windows11_effects,
    get_hwnd,
    is_admin,
    is_windows,
    request_admin_elevation,
)
from presets import is_builtin_name, merge_user_presets
from storage import (
    load_settings,
    load_user_presets,
    save_presets,
    save_settings,
)
from hotkeys import hotkey_str_to_tk
from translations import get_text
from tray import TRAY_AVAILABLE, TrayController
from widgets import SmoothScrollFrame


APP_VERSION = "4.1"
GITHUB_REPO = "Testalireza/modern-dns-changer"
GITHUB_BRANCH = "main"
# ZIP of the repository at the chosen ref; a redirect to the actual
# archive download (no API call required).
GITHUB_ZIP_URL = (
    f"https://codeload.github.com/{GITHUB_REPO}/zip/refs/heads/{GITHUB_BRANCH}"
)


# ============================================================ THEME PALETTES

THEMES = {
    "dark": {
        "bg":              "#141414",
        "card":            "#1E1E1E",
        "card2":           "#252525",
        "entry":           "#2A2A2A",
        "selected":        "#0D2540",
        "selected_border": "#1565C0",
        "text":            "#F0F0F0",
        "muted":           "#909090",
        "accent":          "#1565C0",
        "accent_hover":    "#0D47A1",
        "accent_light":    "#42A5F5",
        "success":         "#4CAF50",
        "danger":          "#F44336",
        "ping_green":      "#4CAF50",
        "ping_orange":     "#FF9800",
        "ping_red":        "#F44336",
        "ping_blue":       "#1565C0",
        "secondary_btn":   "#2C2C2C",
        "secondary_hover": "#3A3A3A",
        "delete_btn":      "#3B1212",
        "delete_hover":    "#5C1A1A",
        "border":          "#333333",
        "scrollbar":       "#333333",
        "scrollbar_hover": "#1565C0",
    },
    "light": {
        "bg":              "#F0F2F5",
        "card":            "#FFFFFF",
        "card2":           "#F7F8FA",
        "entry":           "#EAECEF",
        "selected":        "#DBEAFE",
        "selected_border": "#1D4ED8",
        "text":            "#111827",
        "muted":           "#6B7280",
        "accent":          "#1D4ED8",
        "accent_hover":    "#1E40AF",
        "accent_light":    "#2563EB",
        "success":         "#16A34A",
        "danger":          "#DC2626",
        "ping_green":      "#16A34A",
        "ping_orange":     "#D97706",
        "ping_red":        "#DC2626",
        "ping_blue":       "#1D4ED8",
        "secondary_btn":   "#E5E7EB",
        "secondary_hover": "#D1D5DB",
        "delete_btn":      "#FEE2E2",
        "delete_hover":    "#FECACA",
        "border":          "#E5E7EB",
        "scrollbar":       "#D1D5DB",
        "scrollbar_hover": "#1D4ED8",
    },
}


# ============================================================ APP CLASS

class DNSChangerApp(ctk.CTk):
    """The top-level Tk application."""

    def __init__(self) -> None:
        super().__init__()
        self._log = get_logger()
        self._shutting_down = False
        self._tray = TrayController()
        self._hotkey_seq: str | None = None
        self._settings_win: ctk.CTkToplevel | None = None
        self._admin_dialog: ctk.CTkToplevel | None = None
        self._worker_threads: list[threading.Thread] = []
        self._busy = False

        # Load persisted data.  User presets live on disk; built-in defaults
        # are merged in at display time so they can never overwrite user data.
        self.user_presets: dict = load_user_presets(presets_path())
        self.presets: dict = merge_user_presets(self.user_presets)
        raw_settings = load_settings(settings_path())
        # Persist the (possibly migrated) settings immediately so the schema
        # upgrade survives a crash.
        save_settings(settings_path(), raw_settings)
        self.settings: dict = raw_settings
        self.lang: str = self.settings.get("language", "en")
        self.colors: dict = THEMES.get(self.settings.get("theme", "dark"), THEMES["dark"])

        self.toggle_state = 0
        self.selected_preset: str | None = None
        self.ping_labels: dict[str, ctk.CTkLabel] = {}
        self.ping_buttons: dict[str, ctk.CTkButton] = {}
        self._adapters: list[dict] = []

        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        self.title(f"Modern DNS Changer v{APP_VERSION}")
        try:
            self.geometry(self.settings.get("window_geometry") or "800x580")
        except tk.TclError:
            self.geometry("800x580")
        self.minsize(700, 520)
        self.configure(fg_color=self.colors["bg"])
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._on_delete_window)

        # Build the UI
        self._build_ui()

        # Adapter loading runs in the background
        self._load_adapters_async()

        # Win11 effects (no-op on non-Windows)
        self.after(200, self._apply_window_effects)

        # Bind hotkey
        self._bind_hotkey()
        self.bind("<FocusIn>", lambda _e: self._bind_hotkey())
        self.bind("<FocusOut>", lambda _e: self._unbind_hotkey())

        # Start tray when available.  TrayController.start() is idempotent, so
        # closing/reopening or changing settings never creates a second icon.
        if TRAY_AVAILABLE:
            self._create_tray()

        # Show admin warning if not elevated
        if not is_admin() and is_windows():
            self.after(800, self._show_admin_warning)

        # Persist geometry on close
        self.bind("<Configure>", self._on_configure_event)

    # =================================================== TEXT / I18N

    def t(self, key: str, **kw) -> str:
        return get_text(self.lang, key, **kw)

    # =================================================== WINDOW EFFECTS

    def _apply_window_effects(self) -> None:
        hwnd = get_hwnd(self)
        if hwnd:
            apply_windows11_effects(hwnd, dark=(self.settings.get("theme") == "dark"))

    def _on_configure_event(self, event) -> None:
        # Only react to the root window's <Configure> events
        if event.widget is self and not self._shutting_down:
            try:
                geom = self.geometry()
                if geom and "x" in geom:
                    self.settings["window_geometry"] = geom
            except tk.TclError:
                pass

    # =================================================== HOTKEY

    @staticmethod
    def _hotkey_str_to_tk(hk: str) -> str | None:
        """Convert a human hotkey string (e.g. ``ctrl+shift+f9``) to a Tk
        binding sequence. Returns ``None`` for invalid input.

        Delegates to :mod:`hotkeys` so the UI, the settings entry and the
        automated tests all use exactly the same parser.
        """
        return hotkey_str_to_tk(hk)

    def _bind_hotkey(self) -> None:
        if self._shutting_down:
            return
        try:
            seq = self._hotkey_str_to_tk(self.settings.get("hotkey", "F9") or "F9")
            if not seq:
                return
            self.bind(seq, lambda _e: self._toggle_presets())
            self._hotkey_seq = seq
            self._log.debug("hotkey bound: %s", seq)
        except tk.TclError as exc:
            self._log.warning("bind hotkey failed: %s", exc)

    def _unbind_hotkey(self) -> None:
        if self._shutting_down:
            return
        if self._hotkey_seq:
            try:
                self.unbind(self._hotkey_seq)
            except tk.TclError:
                pass

    def _toggle_presets(self) -> None:
        if self._busy:
            self._set_status(self.t("operation_in_progress"), danger=True)
            return
        pa = self.settings.get("preset_a", "") or ""
        pb = self.settings.get("preset_b", "") or ""
        if not pa or not pb or pa not in self.presets or pb not in self.presets:
            self._set_status(self.t("toggle_failed"), danger=True)
            return
        adapter = self.adapter_var.get()  # capture on the Tk main thread
        name = pa if self.toggle_state == 0 else pb
        self.toggle_state = 1 - self.toggle_state
        self.selected_preset = name
        self._build_preset_list()
        self._set_busy(True)
        self._set_status(self.t("applying", name=name))
        self._spawn_worker(
            lambda n=name, d=dict(self.presets.get(name, {})), a=adapter:
            self._do_apply(n, d, a),
        )

    # =================================================== UI BUILD

    def _clear(self) -> None:
        for w in self.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass

    def _build_ui(self) -> None:
        self._clear()
        c = self.colors
        bg = c["bg"]

        # Smooth-scrolling body
        self.scroll_body = SmoothScrollFrame(self, bg_color=bg)
        self.scroll_body.pack(fill="both", expand=True)
        sb = self.scroll_body.inner

        # Header
        hdr = ctk.CTkFrame(sb, fg_color="transparent")
        hdr.pack(fill="x", padx=18, pady=(14, 2))

        ctk.CTkLabel(
            hdr, text="Modern DNS Changer",
            font=ctk.CTkFont("Segoe UI", 20, "bold"),
            text_color=c["text"],
        ).pack(side="left")

        ctk.CTkButton(
            hdr, text=self.t("settings_btn"),
            width=90, height=28,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=self._open_settings,
        ).pack(side="right")

        ctk.CTkLabel(
            sb, text=self.t("subtitle"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"],
        ).pack(anchor="w", padx=18, pady=(0, 10))

        # Adapter
        self._sec(sb, self.t("adapter"))
        af = self._card(sb)
        self.adapter_var = ctk.StringVar(value=self.settings.get("last_adapter") or "Wi-Fi")
        self.adapter_menu = ctk.CTkOptionMenu(
            af, variable=self.adapter_var,
            values=[self.adapter_var.get()],
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=7, height=32, font=ctk.CTkFont("Segoe UI", 12),
        )
        self.adapter_menu.pack(fill="x", padx=12, pady=10)

        # Quick Actions
        self._sec(sb, self.t("quick_actions"))
        qf = self._card(sb)

        br = ctk.CTkFrame(qf, fg_color="transparent")
        br.pack(fill="x", padx=12, pady=(10, 0))

        ctk.CTkButton(
            br, text=self.t("apply_dns"), height=34,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=self._apply_selected,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            br, text=self.t("auto_dhcp"), height=34,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["secondary_btn"], hover_color=c["secondary_hover"],
            text_color=c["text"], corner_radius=7, command=self._set_dhcp,
        ).pack(side="left", fill="x", expand=True)

        self.status_lbl = ctk.CTkLabel(
            qf, text=self.t("status_ready"),
            font=ctk.CTkFont("Segoe UI", 11), text_color=c["muted"],
        )
        self.status_lbl.pack(anchor="w", padx=12, pady=(4, 8))

        # Presets
        self._sec(sb, self.t("presets"))
        self.presets_card = self._card(sb)
        self.ping_labels = {}
        self.ping_buttons = {}
        self._build_preset_list()

        # Add new preset
        self._sec(sb, self.t("add_new_preset"))
        af2 = self._card(sb, bottom_pad=14)

        row1 = ctk.CTkFrame(af2, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(10, 6))

        eargs = dict(
            height=32, corner_radius=7,
            fg_color=c["entry"], text_color=c["text"],
            placeholder_text_color=c["muted"],
            border_color=c["border"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 12),
        )

        self.name_entry = ctk.CTkEntry(row1, placeholder_text=self.t("preset_name"), **eargs)
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.primary_entry = ctk.CTkEntry(row1, placeholder_text=self.t("preferred_dns"), **eargs)
        self.primary_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.secondary_entry = ctk.CTkEntry(row1, placeholder_text=self.t("secondary_dns"), **eargs)
        self.secondary_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            af2, text=self.t("add_preset_btn"), height=34,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=self._add_preset,
        ).pack(fill="x", padx=12, pady=(0, 10))

        # Footer / Download updated repository
        ctk.CTkButton(
            sb, text=self.t("download_repo_btn"), height=30,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=c["secondary_btn"], hover_color=c["secondary_hover"],
            text_color=c["text"], corner_radius=7,
            command=self._download_repo_dialog,
        ).pack(fill="x", padx=18, pady=(6, 14))

    def _sec(self, parent, label: str) -> None:
        ctk.CTkLabel(
            parent, text=label,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color=self.colors["muted"],
        ).pack(anchor="w", padx=18, pady=(8, 2))

    def _card(self, parent, bottom_pad: int = 6) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color=self.colors["card"], corner_radius=10)
        f.pack(fill="x", padx=18, pady=(0, bottom_pad))
        return f

    # =================================================== PRESET LIST

    def _build_preset_list(self) -> None:
        c = self.colors
        card = self.presets_card

        for w in card.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.ping_labels = {}
        self.ping_buttons = {}

        if not self.presets:
            ctk.CTkLabel(
                card, text=self.t("no_presets"),
                font=ctk.CTkFont("Segoe UI", 12),
                text_color=c["muted"],
            ).pack(pady=18)
            self._add_ping_all_row(card)
            return

        if self.selected_preset not in self.presets:
            self.selected_preset = None

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=(8, 4))

        for name, dns in self.presets.items():
            self._make_preset_row(inner, name, dns)

        self._add_ping_all_row(card)

    def _make_preset_row(self, parent, name: str, dns: dict) -> None:
        c = self.colors
        is_sel = (name == self.selected_preset)
        row = ctk.CTkFrame(
            parent,
            fg_color=c["selected"] if is_sel else c["card2"],
            corner_radius=8,
            border_width=1,
            border_color=c["selected_border"] if is_sel else c["border"],
        )
        row.pack(fill="x", pady=3)

        dot = ctk.CTkLabel(
            row, text="●" if is_sel else "○",
            font=ctk.CTkFont("Segoe UI", 14),
            text_color=c["accent"] if is_sel else c["border"], width=22,
        )
        dot.pack(side="left", padx=(10, 0))

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            info, text=name,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color=c["text"], anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            info,
            text=f"{dns.get('primary', '—')}  /  {dns.get('secondary', '—')}",
            font=ctk.CTkFont("Consolas", 11),
            text_color=c["muted"], anchor="w",
        ).pack(anchor="w")

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="right", padx=8)

        ping_lbl = ctk.CTkLabel(
            btn_frame, text="",
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
            text_color=c["muted"], width=60, anchor="e",
        )
        ping_lbl.pack(side="left", padx=(0, 4))
        self.ping_labels[name] = ping_lbl

        ping_btn = ctk.CTkButton(
            btn_frame, text=self.t("ping"), width=44, height=28, corner_radius=6,
            fg_color=c["ping_blue"], hover_color=c["accent_hover"],
            font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color="white",
            command=lambda n=name: self._ping_preset(n),
        )
        ping_btn.pack(side="left", padx=(0, 4))
        self.ping_buttons[name] = ping_btn

        is_user = name in self.user_presets
        if is_user:
            ctk.CTkButton(
                btn_frame, text="✕", width=28, height=28, corner_radius=6,
                fg_color=c["delete_btn"], hover_color=c["delete_hover"],
                font=ctk.CTkFont("Segoe UI", 11, "bold"),
                text_color=c["danger"],
                command=lambda n=name: self._delete_preset(n),
            ).pack(side="left")
        else:
            # Built-in presets are read-only.
            ctk.CTkLabel(
                btn_frame, text=self.t("builtin_badge"),
                font=ctk.CTkFont("Segoe UI", 10),
                text_color=c["muted"], width=54, anchor="e",
            ).pack(side="left")

        # Click row to select
        for w in [row, info, dot, *info.winfo_children()]:
            try:
                w.bind("<Button-1>", lambda _e, n=name: self._select_preset(n))
            except tk.TclError:
                pass

    def _add_ping_all_row(self, parent) -> None:
        c = self.colors
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(2, 10))

        self.ping_all_btn = ctk.CTkButton(
            row, text=self.t("ping_all"), width=100, height=28, corner_radius=6,
            fg_color=c["ping_blue"], hover_color=c["accent_hover"],
            font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color="white",
            command=self._ping_all,
        )
        self.ping_all_btn.pack(side="left")

        self.ping_summary_lbl = ctk.CTkLabel(
            row, text="",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=c["muted"], anchor="w",
        )
        self.ping_summary_lbl.pack(side="left", padx=(10, 0))

    def _select_preset(self, name: str) -> None:
        self.selected_preset = name
        self._build_preset_list()

    # =================================================== PING

    def _ping_preset(self, name: str) -> None:
        dns = self.presets.get(name, {})
        primary = dns.get("primary", "")
        if not primary:
            return
        if name in self.ping_buttons:
            try:
                self.ping_buttons[name].configure(text="...", state="disabled")
            except tk.TclError:
                pass
        if name in self.ping_labels:
            try:
                self.ping_labels[name].configure(text="", text_color=self.colors["muted"])
            except tk.TclError:
                pass

        def worker(p: str = primary, n: str = name) -> None:
            ms = ping_host(p)
            self._safe_after(0, lambda: self._show_ping_result(n, ms))

        self._spawn_worker(worker)

    def _show_ping_result(self, name: str, ms: int) -> None:
        if self._shutting_down:
            return
        c = self.colors
        if name in self.ping_buttons:
            try:
                self.ping_buttons[name].configure(text=self.t("ping"), state="normal")
            except tk.TclError:
                pass
        if name in self.ping_labels:
            try:
                self.ping_labels[name].configure(
                    text=ping_text(ms), text_color=c[f"ping_{ping_color(ms)}"],
                )
            except tk.TclError:
                pass

    def _ping_all(self) -> None:
        if not self.presets:
            self._set_status(self.t("no_presets_warning"), danger=True)
            return
        names = list(self.presets.keys())
        try:
            self.ping_all_btn.configure(text=self.t("pinging"), state="disabled")
            self.ping_summary_lbl.configure(text="", text_color=self.colors["muted"])
        except tk.TclError:
            return
        for n in names:
            if n in self.ping_buttons:
                try:
                    self.ping_buttons[n].configure(text="...", state="disabled")
                except tk.TclError:
                    pass
            if n in self.ping_labels:
                try:
                    self.ping_labels[n].configure(text="...", text_color=self.colors["muted"])
                except tk.TclError:
                    pass

        def worker(ns: list[str] = names) -> None:
            results: dict[str, int] = {}
            for n in ns:
                primary = self.presets.get(n, {}).get("primary", "")
                ms = ping_host(primary) if primary else -1
                results[n] = ms
                self._safe_after(0, lambda nn=n, m=ms: self._show_ping_result(nn, m))

            def done() -> None:
                if self._shutting_down:
                    return
                try:
                    self.ping_all_btn.configure(text=self.t("ping_all"), state="normal")
                except tk.TclError:
                    return
                valid = {n: ms for n, ms in results.items() if ms >= 0}
                if valid:
                    best = min(valid, key=valid.get)
                    try:
                        self.ping_summary_lbl.configure(
                            text=f"{self.t('best')}: {best} ({valid[best]}ms)",
                            text_color=self.colors["success"],
                        )
                    except tk.TclError:
                        pass
                    self._set_status(
                        self.t("best_dns", name=best, ms=valid[best]), success=True,
                    )
                else:
                    try:
                        self.ping_summary_lbl.configure(
                            text=self.t("all_timed_out"), text_color=self.colors["danger"],
                        )
                    except tk.TclError:
                        pass
                    self._set_status(self.t("all_timed_out_status"), danger=True)

            self._safe_after(0, done)

        self._spawn_worker(worker)

    # =================================================== ACTIONS

    def _apply_selected(self) -> None:
        if self._busy:
            self._set_status(self.t("operation_in_progress"), danger=True)
            return
        if not self.selected_preset:
            if self.presets:
                self.selected_preset = next(iter(self.presets))
                self._build_preset_list()
            else:
                self._set_status(self.t("no_presets_warning"), danger=True)
                return
        name = self.selected_preset
        dns = self.presets.get(name, {})
        adapter = self.adapter_var.get()  # capture on the Tk main thread
        self._set_busy(True)
        self._set_status(self.t("applying", name=name))
        self._spawn_worker(lambda n=name, d=dict(dns), a=adapter: self._do_apply(n, d, a))

    def _do_apply(self, name: str, dns: dict, adapter: str) -> None:
        self._safe_after(0, lambda: self._remember_adapter(adapter))
        result: DnsResult = apply_static(
            adapter, dns.get("primary", ""), dns.get("secondary", ""),
        )
        if result.success:
            self._safe_after(0, lambda: self._set_status(
                self.t("applied", name=name, adapter=adapter), success=True,
            ))
            self._safe_after(0, lambda: self._tray.notify(
                "Modern DNS Changer", f"Applied {name} to {adapter}",
            ))
        else:
            self._safe_after(0, lambda: self._show_apply_failure(result))
        self._safe_after(0, lambda: setattr(self, "_busy", False))

    def _show_apply_failure(self, result: DnsResult, prefix_key: str = "apply_failed") -> None:
        """Render a DNS failure in the UI.

        Verification failures carry structured details (see
        :class:`dns_manager.DnsResult`), which are shown in a fully localised
        diagnostic dialog instead of a raw one-line dump — users should never
        see Python representations like ``IPv4=['...']``.
        """
        self._log.error("DNS operation failed: %s", result.message)
        code = (result.details or {}).get("code")
        if code == "verification_failed":
            self._set_status(
                f"{self.t('apply_failed')}: {self.t('verify_failed_short')}",
                danger=True,
            )
            self._open_verify_failed_dialog(
                result.details, self.t("verify_failed_title"),
            )
        elif code == "dhcp_verification_failed":
            self._set_status(
                f"{self.t('dhcp_failed')}: {self.t('dhcp_verify_failed')}",
                danger=True,
            )
            self._open_verify_failed_dialog(
                result.details, self.t("dhcp_verify_failed_title"),
            )
        else:
            self._set_status(f"{self.t(prefix_key)}: {result.message}",
                             danger=True)

    def _open_verify_failed_dialog(self, details: dict, title: str) -> None:
        """Show a localised, readable verification-failure diagnostic."""
        if self._shutting_down:
            return

        def _fmt(servers) -> str:
            items = [str(s) for s in (servers or []) if s]
            return "\n".join(items) if items else self.t("verify_none")

        c = self.colors
        win = ctk.CTkToplevel(self)
        win.title(title)
        try:
            win.geometry("480x440")
        except tk.TclError:
            pass
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)
        win.after(100, lambda: self._safe_grab_set(win))
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        ctk.CTkLabel(
            win, text=title,
            font=ctk.CTkFont("Segoe UI", 15, "bold"),
            text_color=c["danger"],
        ).pack(pady=(16, 4))

        body = self.t(
            "verify_failed_detail",
            adapter=details.get("adapter", ""),
            expected_v4=_fmt(details.get("expected_ipv4")),
            expected_v6=_fmt(details.get("expected_ipv6")),
            detected_v4=_fmt(details.get("detected_ipv4")),
            detected_v6=_fmt(details.get("detected_ipv6")),
        )
        ctk.CTkLabel(
            win, text=body,
            font=ctk.CTkFont("Consolas", 11),
            text_color=c["text"], justify="left", wraplength=440,
        ).pack(padx=18, anchor="w")

        ctk.CTkButton(
            win, text=self.t("close"), height=32, corner_radius=6,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=win.destroy,
        ).pack(fill="x", padx=18, pady=(10, 14))

    def _set_dhcp(self) -> None:
        if self._busy:
            self._set_status(self.t("operation_in_progress"), danger=True)
            return
        adapter = self.adapter_var.get()
        self._set_busy(True)
        self._set_status(self.t("dhcp_applying"))
        self._safe_after(0, lambda: self._remember_adapter(adapter))

        def worker(a: str = adapter) -> None:
            result: DnsResult = apply_dhcp(a)
            if result.success:
                self._safe_after(0, lambda: self._set_status(
                    self.t("dhcp_done", adapter=a), success=True,
                ))
            else:
                self._safe_after(
                    0, lambda r=result: self._show_apply_failure(r, prefix_key="dhcp_failed"),
                )
            self._safe_after(0, lambda: setattr(self, "_busy", False))

        self._spawn_worker(worker)

    def _set_busy(self, value: bool) -> None:
        self._busy = value

    def _set_status(self, msg: str, success: bool = False, danger: bool = False) -> None:
        if self._shutting_down:
            return
        c = self.colors
        color = c["success"] if success else (c["danger"] if danger else c["muted"])
        try:
            self.status_lbl.configure(text=msg, text_color=color)
        except tk.TclError:
            pass

    def _remember_adapter(self, name: str) -> None:
        if not name:
            return
        self.settings["last_adapter"] = name
        save_settings(settings_path(), self.settings)

    def _add_preset(self) -> None:
        name = self.name_entry.get().strip()
        primary = self.primary_entry.get().strip()
        secondary = self.secondary_entry.get().strip()
        clean_name, p, s, errs = validate_preset(name, primary, secondary)
        if errs:
            self._set_status(errs[0], danger=True)
            return
        if is_builtin_name(clean_name) and clean_name not in self.user_presets:
            # Built-in presets are read-only.  A legacy user preset with the
            # same name is still editable/deletable (existing user data wins).
            self._set_status(self.t("preset_builtin_readonly", name=clean_name), danger=True)
            return
        self.user_presets[clean_name] = {"primary": p, "secondary": s}
        self.presets = merge_user_presets(self.user_presets)
        if not save_presets(presets_path(), self.user_presets):
            self._set_status(self.t("preset_save_failed"), danger=True)
            return
        try:
            self.name_entry.delete(0, "end")
            self.primary_entry.delete(0, "end")
            self.secondary_entry.delete(0, "end")
        except tk.TclError:
            pass
        if not self.selected_preset:
            self.selected_preset = clean_name
        self._build_preset_list()
        self._set_status(self.t("preset_saved", name=clean_name), success=True)

    def _delete_preset(self, name: str) -> None:
        is_builtin = is_builtin_name(name)
        if is_builtin and name not in self.user_presets:
            # This is a pure built-in entry — read-only.
            self._set_status(self.t("preset_builtin_readonly", name=name), danger=True)
            return
        if name in self.user_presets:
            del self.user_presets[name]
            self.presets = merge_user_presets(self.user_presets)
            if not save_presets(presets_path(), self.user_presets):
                self._set_status(self.t("preset_save_failed"), danger=True)
                return
            if self.selected_preset == name:
                self.selected_preset = next(iter(self.presets), None)
            self._build_preset_list()
            self._set_status(self.t("preset_deleted", name=name))

    # =================================================== ADAPTERS

    def _load_adapters_async(self) -> None:
        def worker() -> None:
            adapters = list_adapters()
            self._safe_after(0, lambda: self._update_adapters(adapters))

        self._spawn_worker(worker)

    def _update_adapters(self, adapters: list[dict]) -> None:
        if not adapters:
            return
        self._adapters = adapters
        names = [a["name"] for a in adapters if a.get("name")]
        if not names:
            return
        # Preserve previous selection if still present
        current = self.adapter_var.get()
        try:
            self.adapter_menu.configure(values=names)
        except tk.TclError:
            return
        if current in names:
            self.adapter_var.set(current)
            return
        # Prefer a connected wireless or ethernet adapter
        for a in adapters:
            name = a.get("name", "")
            desc = (a.get("description", "") + " " + name).lower()
            type_ = a.get("interface_type", "").lower()
            status = a.get("status", "").lower()
            if status == "up" and ("wireless" in type_ or "wi-fi" in desc or "wifi" in desc or "wlan" in desc):
                self.adapter_var.set(name)
                return
        # Otherwise pick the first connected adapter
        for a in adapters:
            if a.get("status", "").lower() == "up" and a.get("name"):
                self.adapter_var.set(a["name"])
                return
        self.adapter_var.set(names[0])

    # =================================================== SETTINGS

    def _open_settings(self) -> None:
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.focus_force()
                    return
            except tk.TclError:
                pass

        c = self.colors
        win = ctk.CTkToplevel(self)
        self._settings_win = win
        win.title(self.t("settings_title"))
        try:
            win.geometry("500x700")
        except tk.TclError:
            pass
        win.configure(fg_color=c["bg"])
        win.resizable(False, True)
        win.attributes("-topmost", True)
        win.transient(self)
        win.after(100, lambda: self._safe_grab_set(win))

        def on_close() -> None:
            self._settings_win = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        win.protocol("WM_DELETE_WINDOW", on_close)

        ctk.CTkLabel(
            win, text=self.t("settings_title"),
            font=ctk.CTkFont("Segoe UI", 18, "bold"),
            text_color=c["text"],
        ).pack(pady=(16, 8))

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent", scrollbar_button_color=c["accent"])
        scroll.pack(fill="both", expand=True)

        def section(label: str) -> None:
            ctk.CTkLabel(
                scroll, text=label,
                font=ctk.CTkFont("Segoe UI", 12, "bold"),
                text_color=c["accent_light"],
            ).pack(anchor="w", padx=18, pady=(8, 3))

        # Theme
        section(self.t("appearance"))
        theme_var = ctk.StringVar(value=self.t("dark_mode") if self.settings.get("theme") == "dark" else self.t("light_mode"))
        ctk.CTkSegmentedButton(
            scroll, values=[self.t("dark_mode"), self.t("light_mode")],
            variable=theme_var,
            fg_color=c["card2"], selected_color=c["accent"],
            selected_hover_color=c["accent_hover"],
            unselected_color=c["card2"],
            unselected_hover_color=c["secondary_hover"],
            text_color="white", corner_radius=6, height=32,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            command=lambda v: self._change_theme("dark" if v == self.t("dark_mode") else "light"),
        ).pack(fill="x", padx=18, pady=(0, 2))

        # Language
        section(self.t("language_section"))
        lang_var = ctk.StringVar(value=self.t("english") if self.lang == "en" else self.t("persian"))
        ctk.CTkSegmentedButton(
            scroll, values=[self.t("english"), self.t("persian")],
            variable=lang_var,
            fg_color=c["card2"], selected_color=c["accent"],
            selected_hover_color=c["accent_hover"],
            unselected_color=c["card2"],
            unselected_hover_color=c["secondary_hover"],
            text_color="white", corner_radius=6, height=32,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            command=lambda v: self._change_language("en" if v == self.t("english") else "fa"),
        ).pack(fill="x", padx=18, pady=(0, 2))

        # Hotkey
        section(self.t("hotkey"))
        ctk.CTkLabel(
            scroll, text=self.t("hotkey_desc"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], wraplength=440, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 4))

        hk_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        hk_frame.pack(fill="x", padx=18, pady=(0, 2))

        hk_entry = ctk.CTkEntry(
            hk_frame, height=30, corner_radius=6,
            fg_color=c["entry"], text_color=c["text"],
            border_color=c["accent"], border_width=1,
            font=ctk.CTkFont("Segoe UI", 12),
            placeholder_text=self.t("hotkey_placeholder"),
        )
        hk_entry.insert(0, self.settings.get("hotkey", "F9"))
        hk_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def save_hk() -> None:
            val = hk_entry.get().strip() or "F9"
            seq = self._hotkey_str_to_tk(val)
            if seq is None:
                self._set_status(self.t("hotkey_invalid"), danger=True)
                return
            self.settings["hotkey"] = val
            save_settings(settings_path(), self.settings)
            self._unbind_hotkey()
            self._bind_hotkey()
            self._set_status(self.t("hotkey_saved", key=val), success=True)

        ctk.CTkButton(
            hk_frame, text=self.t("save_hotkey"), width=70, height=30,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=6, command=save_hk,
        ).pack(side="left")

        keys_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        keys_frame.pack(fill="x", padx=18, pady=(0, 6))
        for key in ["F5", "F6", "F7", "F8", "F9", "F10", "ctrl+d", "ctrl+shift+d"]:
            ctk.CTkButton(
                keys_frame, text=key, width=72, height=24,
                font=ctk.CTkFont("Segoe UI", 10),
                fg_color=c["card2"], hover_color=c["secondary_hover"],
                text_color=c["text"], corner_radius=5,
                command=lambda k=key: (hk_entry.delete(0, "end"), hk_entry.insert(0, k)),
            ).pack(side="left", padx=1, pady=2)

        # A/B presets
        section(self.t("toggle_presets_section"))
        ctk.CTkLabel(
            scroll, text=self.t("toggle_presets_desc"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], wraplength=440, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 4))

        preset_names = list(self.presets.keys()) or [self.t("no_presets_option")]
        ab_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        ab_frame.pack(fill="x", padx=18, pady=(0, 4))

        ctk.CTkLabel(
            ab_frame, text=self.t("a_label"), width=18,
            font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=c["text"],
        ).pack(side="left", padx=(0, 3))
        self.hk_a_var = ctk.StringVar(
            value=self.settings.get("preset_a", "") or preset_names[0],
        )
        ctk.CTkOptionMenu(
            ab_frame, variable=self.hk_a_var, values=preset_names,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=6, height=30, font=ctk.CTkFont("Segoe UI", 12),
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkLabel(
            ab_frame, text=self.t("b_label"), width=18,
            font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=c["text"],
        ).pack(side="left", padx=(0, 3))
        b_def = self.settings.get("preset_b", "")
        if not b_def and len(preset_names) > 1:
            b_def = preset_names[1]
        self.hk_b_var = ctk.StringVar(value=b_def or preset_names[0])
        ctk.CTkOptionMenu(
            ab_frame, variable=self.hk_b_var, values=preset_names,
            fg_color=c["accent"], button_color=c["accent"],
            button_hover_color=c["accent_hover"], text_color="white",
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            dropdown_hover_color=c["accent"],
            corner_radius=6, height=30, font=ctk.CTkFont("Segoe UI", 12),
        ).pack(side="left", fill="x", expand=True)

        def save_ab() -> None:
            a_val = self.hk_a_var.get()
            b_val = self.hk_b_var.get()
            if a_val == b_val:
                self._set_status(self.t("ab_must_differ"), danger=True)
                return
            self.settings["preset_a"] = a_val
            self.settings["preset_b"] = b_val
            save_settings(settings_path(), self.settings)
            self._set_status(self.t("toggle_saved", a=a_val, b=b_val), success=True)

        ctk.CTkButton(
            scroll, text=self.t("save_ab"), height=30,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=6, command=save_ab,
        ).pack(fill="x", padx=18, pady=(0, 6))

        # Close behavior
        section(self.t("close_behavior"))
        ctk.CTkLabel(
            scroll, text=self.t("close_behavior_desc"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], wraplength=440, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 4))
        close_var = ctk.StringVar(
            value=self.t("close_minimize") if self.settings.get("close_behavior", "tray") == "tray"
            else self.t("close_exit"),
        )
        ctk.CTkSegmentedButton(
            scroll, values=[self.t("close_minimize"), self.t("close_exit")],
            variable=close_var,
            fg_color=c["card2"], selected_color=c["accent"],
            selected_hover_color=c["accent_hover"],
            unselected_color=c["card2"],
            unselected_hover_color=c["secondary_hover"],
            text_color="white", corner_radius=6, height=30,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            command=lambda v: self._change_close_behavior(
                "tray" if v == self.t("close_minimize") else "exit",
            ),
        ).pack(fill="x", padx=18, pady=(0, 6))

        # About
        section(self.t("about_section"))
        ctk.CTkLabel(
            scroll, text=self.t("about_text", version=APP_VERSION),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], justify="center",
        ).pack(padx=18, pady=(0, 8))

        ctk.CTkButton(
            win, text=self.t("close"), height=34, corner_radius=6,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=on_close,
        ).pack(fill="x", padx=18, pady=(4, 12))

    def _change_theme(self, theme: str) -> None:
        self.settings["theme"] = theme
        self.colors = THEMES[theme]
        save_settings(settings_path(), self.settings)
        ctk.set_appearance_mode(theme)
        self.configure(fg_color=self.colors["bg"])
        self._build_ui()
        self._apply_window_effects()
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.destroy()
            except tk.TclError:
                pass
        self._open_settings()

    def _change_language(self, lang: str) -> None:
        self.settings["language"] = lang
        self.lang = lang
        save_settings(settings_path(), self.settings)
        self._build_ui()
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.destroy()
            except tk.TclError:
                pass
        self._open_settings()

    def _change_close_behavior(self, behavior: str) -> None:
        """Persist the window-close behaviour (``"tray"`` or ``"exit"``)."""
        if behavior not in ("tray", "exit"):
            return
        self.settings["close_behavior"] = behavior
        self.settings["minimize_to_tray"] = behavior == "tray"
        save_settings(settings_path(), self.settings)
        if behavior == "tray" and TRAY_AVAILABLE:
            # Idempotent: never spawn a second tray icon.
            self._create_tray()
        self._set_status(self.t("close_behavior_saved"), success=True)

    def _toggle_tray(self, enabled: bool) -> None:
        """Backwards-compatible wrapper kept for callers that predate the
        close-behaviour setting."""
        self._change_close_behavior("tray" if enabled else "exit")

    # =================================================== TRAY

    def _create_tray(self) -> None:
        # TrayController.start() is idempotent, so reopening the window,
        # changing settings, or closing/reopening can never add a second icon.
        self._tray.start(
            on_show=lambda: self._safe_after(0, self._restore_from_tray),
            on_toggle=lambda: self._safe_after(0, self._toggle_presets),
            on_quit=lambda: self._safe_after(0, self._quit_app),
            tooltip="Modern DNS Changer",
        )

    def _on_delete_window(self) -> None:
        # The close-behaviour setting controls only the normal window Close.
        # "tray" hides to the tray; "exit" (and any tray Quit) fully exits.
        if self.settings.get("close_behavior", "tray") == "tray" and TRAY_AVAILABLE:
            try:
                if self._tray.is_running():
                    self.withdraw()
                    return
            except (AttributeError, tk.TclError):
                pass
        self._quit_app()

    def _restore_from_tray(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def _quit_app(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._log.info("shutting down")
        # Persist final window state
        try:
            geom = self.geometry()
            if geom and "x" in geom:
                self.settings["window_geometry"] = geom
            save_settings(settings_path(), self.settings)
        except (tk.TclError, OSError):
            pass
        # Tray callbacks use _safe_after, which drops work once _shutting_down
        # is True, so an in-flight tray-quit cannot re-enter.
        self._tray.stop()
        # Worker threads are daemon threads; stopping the tray, unbinding the
        # window and destroying the Tk root lets the process exit promptly.
        try:
            self.unbind_all("<<FocusIn>>")
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    # =================================================== ADMIN

    def _show_admin_warning(self) -> None:
        if self._admin_dialog is not None:
            try:
                if self._admin_dialog.winfo_exists():
                    return
            except tk.TclError:
                pass
        c = self.colors
        win = ctk.CTkToplevel(self)
        self._admin_dialog = win
        win.title(self.t("admin_needed"))
        try:
            win.geometry("380x180")
        except tk.TclError:
            pass
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)
        win.after(100, lambda: self._safe_grab_set(win))

        def on_close() -> None:
            self._admin_dialog = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        win.protocol("WM_DELETE_WINDOW", on_close)

        ctk.CTkLabel(
            win, text=self.t("admin_needed"),
            font=ctk.CTkFont("Segoe UI", 15, "bold"),
            text_color=c["accent_light"],
        ).pack(pady=(20, 4))
        ctk.CTkLabel(
            win, text=self.t("admin_msg"),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], justify="center",
        ).pack(pady=(0, 14))
        def restart_admin() -> None:
            if request_admin_elevation():
                on_close()
                self._quit_app()
            else:
                self._set_status(self.t("admin_elevation_failed"), danger=True)

        ctk.CTkButton(
            win, text=self.t("restart_admin"), width=180, height=34,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            corner_radius=7, command=restart_admin,
        ).pack()

    # =================================================== DOWNLOAD REPO

    def _download_repo_dialog(self) -> None:
        """Open a small modal that explains the source-download flow and lets
        the user choose a destination folder. The download itself is performed
        in a background thread."""
        if not is_windows():
            self._set_status("Download is only available on Windows", danger=True)
            return

        c = self.colors
        win = ctk.CTkToplevel(self)
        win.title(self.t("download_repo_title"))
        try:
            win.geometry("480x220")
        except tk.TclError:
            pass
        win.configure(fg_color=c["bg"])
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self)
        win.after(100, lambda: self._safe_grab_set(win))

        ctk.CTkLabel(
            win, text=self.t("download_repo_title"),
            font=ctk.CTkFont("Segoe UI", 15, "bold"),
            text_color=c["text"],
        ).pack(pady=(16, 4))
        ctk.CTkLabel(
            win, text=self.t("download_repo_desc", url=GITHUB_ZIP_URL),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"], justify="left", wraplength=440,
        ).pack(padx=18, pady=(0, 10))

        progress = ctk.CTkLabel(
            win, text="",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=c["muted"],
        )
        progress.pack(pady=(0, 6))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(2, 14))

        def start_download() -> None:
            target_dir = user_data_dir()
            ok_btn.configure(state="disabled")
            progress.configure(text=self.t("downloading"))
            self._spawn_worker(lambda: self._download_repo_worker(target_dir, win, progress, ok_btn))

        ok_btn = ctk.CTkButton(
            btn_row, text=self.t("download"), height=32, corner_radius=6,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["accent"], hover_color=c["accent_hover"],
            command=start_download,
        )
        ok_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            btn_row, text=self.t("cancel"), height=32, corner_radius=6,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=c["secondary_btn"], hover_color=c["secondary_hover"],
            text_color=c["text"], command=win.destroy,
        ).pack(side="left", fill="x", expand=True)

    def _download_repo_worker(
        self, target_dir: Path, win: ctk.CTkToplevel,
        progress: ctk.CTkLabel, ok_btn: ctk.CTkButton,
    ) -> None:
        """Download the GitHub repository ZIP and place it in ``target_dir``."""
        log = get_logger()
        try:
            target_zip = target_dir / f"modern-dns-changer-{GITHUB_BRANCH}.zip"
            self._safe_after(0, lambda: progress.configure(
                text=self.t("downloading_url", url=GITHUB_ZIP_URL),
            ))
            _url_download(GITHUB_ZIP_URL, target_zip,
                          progress_cb=lambda done, total: self._safe_after(
                              0, lambda d=done, t=total: progress.configure(
                                  text=self.t("downloading_progress",
                                              done=done, total=total),
                              ),
                          ))
            self._safe_after(0, lambda: progress.configure(
                text=self.t("downloaded_to", path=str(target_zip)),
                text_color=self.colors["success"],
            ))
            self._safe_after(0, lambda: ok_btn.configure(state="normal"))
            log.info("downloaded repo zip to %s", target_zip)
        except (urllib.error.URLError, urllib.error.ContentTooShortError,
                OSError, TimeoutError) as exc:
            log.error("download failed: %s", exc)
            err_msg = str(exc)
            self._safe_after(0, lambda e=err_msg: progress.configure(
                text=self.t("download_failed", error=e),
                text_color=self.colors["danger"],
            ))
            self._safe_after(0, lambda: ok_btn.configure(state="normal"))

    # =================================================== THREAD HELPERS

    def _safe_after(self, ms: int, fn: Callable[[], None]) -> None:
        """Schedule ``fn`` on the Tk main thread, but only if the app is
        still alive. Silently drops the call during shutdown."""
        if self._shutting_down:
            return
        try:
            self.after(ms, fn)
        except (tk.TclError, RuntimeError) as exc:
            self._log.debug("_safe_after dropped: %s", exc)

    def _spawn_worker(self, target: Callable[[], None]) -> None:
        """Run ``target`` in a daemon thread. Tracks the thread so we can
        wait for it during shutdown."""
        if self._shutting_down:
            return
        t = threading.Thread(target=target, daemon=True, name="dns-worker")
        self._worker_threads.append(t)
        # Periodically prune the list so it doesn't grow unbounded
        self._worker_threads = [x for x in self._worker_threads if x.is_alive()]
        t.start()

    def _safe_grab_set(self, win: ctk.CTkToplevel) -> None:
        try:
            if win.winfo_exists():
                win.grab_set()
        except tk.TclError:
            pass


# ============================================================ helpers

def _url_download(url: str, dest: Path, progress_cb=None) -> None:
    """Download ``url`` to ``dest`` with a 30-second timeout.

    Uses :mod:`urllib.request` so we don't pull in another dependency.
    Reports progress via ``progress_cb(done_bytes, total_bytes)`` (if given).
    """
    log = get_logger()
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ModernDNSChanger/4.1"})
    tmp = dest.with_name(f"{dest.name}.part")
    with urllib.request.urlopen(req, timeout=30) as response:
        total = int(response.headers.get("Content-Length") or 0)
        chunk_size = 32 * 1024
        done = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb is not None:
                    try:
                        progress_cb(done, total)
                    except (ValueError, TypeError) as exc:
                        log.debug("progress_cb error: %s", exc)
            f.flush()
    os.replace(tmp, dest)
    log.info("downloaded %s -> %s (%d bytes)", url, dest, done)
