"""Reusable CustomTkinter widgets.

The :class:`SmoothScrollFrame` below provides smooth, mouse-wheel-driven
scrolling for the main application content.

Scroll event routing
--------------------
Mouse-wheel events are routed, not sprinkled on individual widgets:

* exactly **one** ``<MouseWheel>`` binding per toplevel window (a toplevel is
  part of every descendant's bindtags, so that single binding sees the wheel
  no matter which widget the pointer is over — centre, sides, labels,
  buttons, or empty areas);
* a small router then decides which scrollable owns the event by walking
  from ``event.widget`` up the widget parent chain (see
  :mod:`scroll_router`).

That is deliberately *not* a ``bind_all`` handler: the global ``all`` tag is
process-wide and would also fire for dropdown popups, dialogs, text widgets
and the tray, breaking their native scrolling.  The per-toplevel binding plus
ancestor routing gives us:

* wheel works everywhere over the scrollable content (logs, labels, buttons,
  empty background, entry fields — the whole page);
* natively scrollable controls (``Text``, ``Listbox``, ``Treeview``, other
  canvases such as CustomTkinter's ``CTkScrollableFrame`` internals) keep
  their own wheel behaviour when they actually have something to scroll;
* dynamically added/removed content needs no rebinding at all;
* widgets in *other* toplevels (Settings window, dialogs, dropdown menus)
  are completely unaffected.

The routing decision lives in :mod:`scroll_router` as pure functions so it
can be unit-tested without a display.
"""
from __future__ import annotations

import sys
import tkinter as tk
import weakref

import customtkinter as ctk

from logger import get_logger
from scroll_router import (
    can_scroll,
    clamp_target,
    find_scroll_target,
    wheel_to_pixels,
)

# Attribute name used to store the per-toplevel router on its window object.
_ROUTER_ATTR = "_smooth_scroll_router"

# Synthetic deltas for X11 button-style wheel events (Button-4/5 carry no
# delta; treat each as one full notch).
_X11_WHEEL_UP_DELTA = 120
_X11_WHEEL_DOWN_DELTA = -120


class _ScrollRouter:
    """One router per toplevel; maps registered widgets to their
    :class:`SmoothScrollFrame` and dispatches wheel events.

    Keys are the scroll frame itself, its canvas and its inner frame — every
    widget where the ancestor walk is expected to terminate.  A
    :class:`weakref.WeakKeyDictionary` is used so a destroyed widget can
    never leak through the registry.
    """

    def __init__(self, toplevel: tk.Misc) -> None:
        self._toplevel = toplevel
        self._owners: "weakref.WeakKeyDictionary[tk.Misc, SmoothScrollFrame]" = (
            weakref.WeakKeyDictionary()
        )
        # ``add="+"`` so this never replaces a binding another widget may
        # have placed on the same toplevel.
        try:
            toplevel.bind("<MouseWheel>", self._dispatch, add="+")  # Windows / macOS
            toplevel.bind("<Button-4>", self._dispatch, add="+")    # X11 wheel up
            toplevel.bind("<Button-5>", self._dispatch, add="+")    # X11 wheel down
        except tk.TclError as exc:  # pragma: no cover - defensive
            get_logger().warning("SmoothScrollFrame router binding failed: %s", exc)

    # ---------------------------------------------- registration

    def register(self, frame: "SmoothScrollFrame") -> None:
        self._owners[frame] = frame
        self._owners[frame.canvas] = frame
        self._owners[frame.inner] = frame

    def unregister(self, frame: "SmoothScrollFrame") -> None:
        for key in (frame, frame.canvas, frame.inner):
            try:
                self._owners.pop(key, None)
            except (tk.TclError, TypeError):  # pragma: no cover - defensive
                pass

    def owner_of(self, widget: tk.Misc) -> "SmoothScrollFrame | None":
        owner = self._owners.get(widget)
        if owner is None or owner.destroyed:
            return None
        return owner

    # ---------------------------------------------- dispatch

    def _dispatch(self, event: "tk.Event") -> "str | None":
        target = find_scroll_target(event.widget, self.owner_of)
        if target is None:
            return None  # not ours — let native bindings handle it
        return target.handle_wheel_event(event)


def _router_for(toplevel: tk.Misc) -> _ScrollRouter:
    """Return the (single) :class:`_ScrollRouter` attached to ``toplevel``."""
    router = getattr(toplevel, _ROUTER_ATTR, None)
    if router is None:
        router = _ScrollRouter(toplevel)
        try:
            setattr(toplevel, _ROUTER_ATTR, router)
        except (tk.TclError, AttributeError):  # pragma: no cover - defensive
            pass
    return router


class SmoothScrollFrame(ctk.CTkFrame):
    """A smooth-scrolling container built on a ``tk.Canvas``.

    The widget uses interpolation to animate scroll changes, providing a
    nicer feel than the default stepped scrolling.

    Place children in :attr:`inner`.  Mouse-wheel scrolling works whenever
    the pointer is anywhere over this frame's content thanks to the
    per-toplevel :class:`_ScrollRouter`; no per-child bindings are used.
    """

    _STEP = 0.22
    _THRESHOLD = 0.5
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

        # Register with the per-toplevel router.  Exactly one ``<MouseWheel>``
        # binding exists per toplevel and routes events to us whenever the
        # pointer is over any of our descendants.
        self._router = _router_for(self.winfo_toplevel())
        self._router.register(self)

    # ------------------------------------------------------------------ API

    @property
    def destroyed(self) -> bool:
        return self._destroyed

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

    def handle_wheel_event(self, event: "tk.Event") -> "str | None":
        """Scroll in response to a routed ``<MouseWheel>``/``<Button-4/5>``.

        Returns ``"break"`` when the event was consumed (so class and ``all``
        bindings do not also fire) or ``None`` when this frame has nothing to
        scroll and the event should keep propagating.
        """
        if self._destroyed:
            return None
        delta = self._event_delta(event)
        if delta == 0:
            return None
        try:
            bbox = self.canvas.bbox("all")
        except tk.TclError:
            return None
        if not bbox:
            return None
        total = float(bbox[3] - bbox[1])
        visible = float(self.canvas.winfo_height())
        if not can_scroll(total, visible):
            # Nothing to scroll: don't consume the event — a nested widget
            # above us may still want it.
            return None
        try:
            scaling = float(self._get_window_scaling())
        except (tk.TclError, AttributeError):  # pragma: no cover - defensive
            scaling = 1.0
        scroll_px = wheel_to_pixels(delta, sys.platform, scaling=scaling)
        old_target = self._target_y
        # Keep the running target anchored to the real position if the user
        # grabbed the scrollbar in the meantime.
        if not self._animating:
            self._sync_target_from_view(total)
        self._target_y = clamp_target(self._target_y + scroll_px, total, visible)
        if self._target_y == old_target and not self._animating:
            return "break"  # already at the limit; absorb to avoid jitter
        if not self._animating:
            self._animating = True
            self._animate()
        return "break"

    # ------------------------------------------------------------ internals

    @staticmethod
    def _event_delta(event: "tk.Event") -> float:
        """Return the event's wheel delta; synthesise one for X11 buttons."""
        num = getattr(event, "num", None)
        if num == 4:
            return float(_X11_WHEEL_UP_DELTA)
        if num == 5:
            return float(_X11_WHEEL_DOWN_DELTA)
        try:
            return float(getattr(event, "delta", 0) or 0)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return 0.0

    def _sync_target_from_view(self, total: float) -> None:
        try:
            first = float(self.canvas.yview()[0])
        except tk.TclError:
            return
        if total > 0:
            self._target_y = first * total
            self._current_y = self._target_y

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

    def destroy(self) -> None:  # type: ignore[override]
        self._destroyed = True
        router = getattr(self, "_router", None)
        if router is not None:
            router.unregister(self)
        super().destroy()
