"""
Reusable CustomTkinter widgets.
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from logger import get_logger


class SmoothScrollFrame(ctk.CTkFrame):
    """A smooth-scrolling container built on a ``tk.Canvas``.

    The widget uses interpolation to animate scroll changes, providing a
    nicer feel than the default stepped scrolling.

    Place children in :attr:`inner`. The widget only attaches its mouse-wheel
    binding to itself and its immediate children; it does **not** use
    ``bind_all`` to avoid stealing scroll events from other widgets.
    """

    _STEP = 0.22
    _THRESHOLD = 0.5
    _PIXELS_PER_NOTCH = 60
    _FRAME_MS = 16  # ~60 fps

    def __init__(self, master, bg_color: str = "#141414", **kwargs) -> None:
        super().__init__(master, fg_color=bg_color, **kwargs)

        self._bg = bg_color
        self._target_y = 0.0
        self._current_y = 0.0
        self._animating = False
        self._destroyed = False

        self.canvas = tk.Canvas(
            self, bg=bg_color, highlightthickness=0, bd=0, relief="flat"
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        self.vbar = tk.Scrollbar(
            self, orient="vertical", command=self._on_scrollbar,
            width=6, bg=bg_color, troughcolor=bg_color,
            activebackground="#1565C0", relief="flat", bd=0,
        )
        self.vbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.inner = ctk.CTkFrame(self.canvas, fg_color=bg_color, corner_radius=0)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Bind mouse-wheel to the canvas and the inner frame only. We attach
        # to descendant widgets on demand via ``_bind_recursive`` when the
        # inner frame is populated.
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<Enter>", self._bind_descendants)
        self.inner.bind("<Leave>", self._unbind_descendants)

    # --- public ---

    def update_bg(self, bg_color: str) -> None:
        self._bg = bg_color
        try:
            self.configure(fg_color=bg_color)
            self.canvas.configure(bg=bg_color)
            self.inner.configure(fg_color=bg_color)
            self.vbar.configure(bg=bg_color, troughcolor=bg_color)
        except tk.TclError:
            pass  # widget may have been destroyed

    def scroll_to_top(self) -> None:
        self._target_y = 0.0
        self._current_y = 0.0
        try:
            self.canvas.yview_moveto(0)
        except tk.TclError:
            pass

    # --- internal ---

    def _on_inner_configure(self, _event) -> None:
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass

    def _on_canvas_configure(self, event) -> None:
        try:
            self.canvas.itemconfig(self._window, width=event.width)
        except tk.TclError:
            pass

    def _on_scrollbar(self, *args) -> None:
        try:
            self.canvas.yview(*args)
            bbox = self.canvas.bbox("all")
            if bbox:
                total = bbox[3] - bbox[1]
                if total > 0:
                    frac = float(self.canvas.yview()[0])
                    self._current_y = frac * total
                    self._target_y = self._current_y
        except tk.TclError:
            pass

    def _on_mousewheel(self, event) -> str | None:
        try:
            bbox = self.canvas.bbox("all")
        except tk.TclError:
            return None
        if not bbox:
            return None
        total = bbox[3] - bbox[1]
        vis = self.canvas.winfo_height()
        if total <= vis:
            return "break"
        delta = -event.delta / 120.0
        scroll = delta * self._PIXELS_PER_NOTCH
        self._target_y = max(0.0, min(self._target_y + scroll, total - vis))
        if not self._animating:
            self._animating = True
            self._animate()
        return "break"

    def _animate(self) -> None:
        if self._destroyed:
            return
        try:
            diff = self._target_y - self._current_y
            if abs(diff) < self._THRESHOLD:
                self._current_y = self._target_y
                self._animating = False
            else:
                self._current_y += diff * self._STEP
                self.after(self._FRAME_MS, self._animate)
            bbox = self.canvas.bbox("all")
            if bbox:
                total = max(bbox[3] - bbox[1], 1)
                frac = self._current_y / total
                self.canvas.yview_moveto(frac)
        except tk.TclError:
            self._animating = False

    def _bind_descendants(self, _event=None) -> None:
        """Attach mousewheel binding to all descendants of ``inner``."""
        try:
            self.inner.bind_all  # exists on Frame? no — use walk
        except AttributeError:
            pass
        # Use tk's walk to enumerate descendants. We bind only on Enter to
        # avoid the global-scope issue of bind_all.
        try:
            widget: tk.Misc = self.inner
            stack = [widget]
            seen: set[int] = set()
            while stack:
                w = stack.pop()
                wid = id(w)
                if wid in seen:
                    continue
                seen.add(wid)
                try:
                    w.bind("<MouseWheel>", self._on_mousewheel, add="+")
                except tk.TclError:
                    pass
                stack.extend(list(w.children.values()))
        except (tk.TclError, AttributeError) as exc:
            get_logger().debug("SmoothScrollFrame._bind_descendants: %s", exc)

    def _unbind_descendants(self, _event=None) -> None:
        try:
            widget: tk.Misc = self.inner
            stack = [widget]
            seen: set[int] = set()
            while stack:
                w = stack.pop()
                wid = id(w)
                if wid in seen:
                    continue
                seen.add(wid)
                try:
                    w.unbind("<MouseWheel>")
                except tk.TclError:
                    pass
                stack.extend(list(w.children.values()))
        except (tk.TclError, AttributeError):
            pass

    def destroy(self) -> None:  # type: ignore[override]
        self._destroyed = True
        super().destroy()
