"""Pure-Python mouse-wheel scroll routing logic.

This module is deliberately free of any :mod:`tkinter` imports so that the
routing decisions can be unit-tested without a display.  ``widgets.py`` glues
these helpers to real Tk events.

Background / why this exists
============================
The old implementation bound ``<MouseWheel>`` to the scroll canvas and then
tried to add/remove bindings on child widgets in ``<Enter>`` / ``<Leave>``
handlers.  Two properties of Tk made that approach fail:

* Tk fires ``<Leave>`` (with detail ``NotifyInferior``) on a frame every time
  the pointer moves *onto a child widget*.  The handler responded by
  **unbinding every descendant**, so the wheel stopped working as soon as the
  cursor rested on any label/button in the centre of the window.
* Widgets created after the pointer entered the area (dynamic content, e.g.
  rebuilt preset rows) never received a binding at all.

The result was that the mouse wheel only worked over the bare left/right
margins of the content — the only parts of the scroll frame not covered by
child widgets.

Routing approach
================
A single ``<MouseWheel>`` binding is placed on each *toplevel* window (a
toplevel is present in the bindtags of every descendant, so one binding sees
all wheel events inside that window — without using the global ``all`` tag,
which would break nested scrollables, popups, text widgets and the system
tray).  For every event the router walks from ``event.widget`` up the
``.master`` chain:

* the first widget that is registered to a ``SmoothScrollFrame`` wins — the
  frame that contains the pointer scrolls (correct for nested scrollers);
* an *unregistered* widget that natively scrolls (``Text``, ``Listbox``,
  ``ttk::treeview``, another ``Canvas``) stops the walk only when it actually
  has scrollable content, so e.g. a log text box inside the page keeps its
  own wheel behaviour while the page still scrolls everywhere else.

Everything here works on duck-typed widget objects (``master``,
``winfo_class()``, ``yview()``) so tests can supply fakes.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

# Tk widget classes (as reported by ``winfo_class()``) that have their own
# built-in vertical mouse-wheel behaviour on Windows.  ``Canvas`` is included
# because many composite widgets (including CustomTkinter's own
# ``CTkScrollableFrame``) are built on an internal scrollable canvas.
_NATIVE_SCROLL_CLASSES = {"Text", "Listbox", "Treeview", "Canvas"}

# One full wheel notch (delta == 120 on Windows) scrolls this many logical
# pixels.  Roughly three lines of text — a comfortable default.
PIXELS_PER_NOTCH = 60.0

# macOS delivers already-small deltas (pixels), not 1/120 notches.
DARWIN_PIXEL_MULTIPLIER = 3.0


def _widget_class(widget: Any) -> str:
    """Return the Tk class of ``widget`` (``""`` when it cannot be told)."""
    try:
        return str(widget.winfo_class())
    except Exception:  # pragma: no cover - defensive; TclError etc.
        return ""


def has_scrollable_content(widget: Any) -> bool:
    """Return True when ``widget`` can actually scroll vertically.

    A widget whose content fits entirely inside its view reports
    ``yview() == (0.0, 1.0)`` and therefore has nothing to scroll.  When the
    query itself fails we conservatively assume the widget *can* scroll, so we
    never steal a wheel event from a control that might need it.
    """
    try:
        first, last = widget.yview()
    except Exception:  # pragma: no cover - defensive; TclError etc.
        return True
    try:
        return not (float(first) <= 0.0 and float(last) >= 1.0)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return True


def find_scroll_target(
    widget: Any,
    owner_of: Callable[[Any], Optional[Any]],
) -> Optional[Any]:
    """Decide which (if any) scrollable container should own a wheel event.

    Parameters
    ----------
    widget:
        The widget directly under the mouse pointer (``event.widget``).
    owner_of:
        Lookup that returns the owning scroll container when the given widget
        is registered to one (its frame / canvas / inner frame), else None.

    Returns the owning scroll container, or ``None`` when the event belongs
    to a natively scrollable control or to no scrollable at all.
    """
    w = widget
    visited = 0
    while w is not None and visited < 128:  # 128: paranoia against master loops
        visited += 1
        owner = owner_of(w)
        if owner is not None:
            return owner
        if _widget_class(w) in _NATIVE_SCROLL_CLASSES and has_scrollable_content(w):
            # A natively scrollable widget (log view, listbox, another
            # library's scrollable canvas) that can really scroll keeps the
            # event for its own class bindings.
            return None
        w = getattr(w, "master", None)
    return None


def wheel_to_pixels(delta: float, platform: str, scaling: float = 1.0) -> float:
    """Convert a Tk ``<MouseWheel>`` ``event.delta`` to signed pixels.

    * Windows / X11: ``delta`` is in 1/120-notch units (precision touchpads
      emit smaller values, sometimes fractional); one notch scrolls
      ``PIXELS_PER_NOTCH`` logical pixels.
    * macOS: ``delta`` is already a small pixel-ish value.

    ``scaling`` is the CustomTkinter window scaling factor (1.0 at 100% DPI).
    """
    if platform == "darwin":
        px = -float(delta) * DARWIN_PIXEL_MULTIPLIER
    else:
        px = -float(delta) / 120.0 * PIXELS_PER_NOTCH
    return px * max(scaling, 0.01)


def clamp_target(target: float, total: float, visible: float) -> float:
    """Clamp a desired scroll offset (px) to the valid range.

    ``total`` is the full content height in pixels and ``visible`` the height
    of the viewport.  When the content fits inside the viewport the only
    valid offset is 0.
    """
    max_y = max(total - visible, 0.0)
    if target < 0.0:
        return 0.0
    if target > max_y:
        return max_y
    return target


def can_scroll(total: float, visible: float) -> bool:
    """Return True when the content is taller than the viewport."""
    return total > visible > 0
