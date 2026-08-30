"""Tests for the pure scroll-routing logic in :mod:`scroll_router`.

These tests model the widget containment hierarchy with lightweight fakes —
``master``/``winfo_class()``/``yview()`` is all the router needs — so they
run without a display.

They encode the exact regression from v4.1.0: with the old implementation
the mouse wheel only worked over the left/right margins of the window,
because bindings were stripped from content widgets whenever the pointer
moved onto them.  The router must resolve the *nearest registered
scrollable* for events on ANY widget inside the scrollable content, while
leaving natively scrollable controls alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scroll_router import (
    can_scroll,
    clamp_target,
    find_scroll_target,
    has_scrollable_content,
    wheel_to_pixels,
)


class FakeWidget:
    """Minimal stand-in for a Tk widget in the containment hierarchy."""

    def __init__(self, cls: str = "Frame", master: "FakeWidget | None" = None,
                 yview=(0.0, 1.0)) -> None:
        self._cls = cls
        self.master = master
        self._yview = yview

    def winfo_class(self) -> str:
        return self._cls

    def yview(self):
        if isinstance(self._yview, Exception):
            raise self._yview
        return self._yview


class FakeScrollFrame:
    """Stands in for a SmoothScrollFrame's identity in the registry."""

    def __init__(self) -> None:
        self.destroyed = False


def _build_hierarchy(text_scrollable: bool = False):
    """Build: toplevel → ssf → canvas → inner → card → (label, button, text).

    Returns all pieces so tests can register the right widgets.
    """
    toplevel = FakeWidget("Tk")
    ssf_frame = FakeWidget("CTkFrame", master=toplevel)
    canvas = FakeWidget("Canvas", master=ssf_frame)
    inner = FakeWidget("CTkFrame", master=canvas)
    card = FakeWidget("CTkFrame", master=inner)
    label = FakeWidget("CTkLabel", master=card)
    button = FakeWidget("CTkButton", master=card)
    entry = FakeWidget("CTkEntry", master=card)
    text = FakeWidget(
        "Text", master=card,
        yview=(0.25, 0.75) if text_scrollable else (0.0, 1.0),
    )
    ssf = FakeScrollFrame()
    registry = {ssf_frame: ssf, canvas: ssf, inner: ssf}
    parts = {
        "toplevel": toplevel, "ssf_frame": ssf_frame, "canvas": canvas,
        "inner": inner, "card": card, "label": label, "button": button,
        "entry": entry, "text": text, "ssf": ssf,
    }
    return registry, parts


def test_event_on_label_routes_to_frame() -> None:
    registry, p = _build_hierarchy()
    assert find_scroll_target(p["label"], registry.get) is p["ssf"]
    print("test_event_on_label_routes_to_frame OK")


def test_event_on_button_routes_to_frame() -> None:
    registry, p = _build_hierarchy()
    assert find_scroll_target(p["button"], registry.get) is p["ssf"]
    print("test_event_on_button_routes_to_frame OK")


def test_event_on_entry_routes_to_frame() -> None:
    registry, p = _build_hierarchy()
    assert find_scroll_target(p["entry"], registry.get) is p["ssf"]
    print("test_event_on_entry_routes_to_frame OK")


def test_event_on_inner_background_routes_to_frame() -> None:
    registry, p = _build_hierarchy()
    # The empty margins of the scrollable content (the previous "working
    # left/right edges") must keep working.
    assert find_scroll_target(p["inner"], registry.get) is p["ssf"]
    print("test_event_on_inner_background_routes_to_frame OK")


def test_event_on_canvas_routes_to_frame() -> None:
    registry, p = _build_hierarchy()
    assert find_scroll_target(p["canvas"], registry.get) is p["ssf"]
    print("test_event_on_canvas_routes_to_frame OK")


def test_event_on_card_routes_to_frame() -> None:
    registry, p = _build_hierarchy()
    assert find_scroll_target(p["card"], registry.get) is p["ssf"]
    print("test_event_on_card_routes_to_frame OK")


def test_event_outside_any_scrollable_returns_none() -> None:
    _registry, p = _build_hierarchy()
    # A widget attached directly to the toplevel (not inside the scroller).
    free = FakeWidget("CTkToplevel", master=p["toplevel"])
    assert find_scroll_target(free, _registry.get) is None
    print("test_event_outside_any_scrollable_returns_none OK")


def test_scrollable_text_widget_keeps_its_event() -> None:
    registry, p = _build_hierarchy(text_scrollable=True)
    # A Text widget whose content exceeds its view must keep its native
    # wheel scroll — the page must NOT scroll instead.
    assert find_scroll_target(p["text"], registry.get) is None
    print("test_scrollable_text_widget_keeps_its_event OK")


def test_fully_visible_text_widget_falls_through() -> None:
    registry, p = _build_hierarchy(text_scrollable=False)
    # A Text widget with nothing to scroll must not swallow the page scroll.
    assert find_scroll_target(p["text"], registry.get) is p["ssf"]
    print("test_fully_visible_text_widget_falls_through OK")


def test_listbox_keeps_event_when_scrollable() -> None:
    registry, p = _build_hierarchy()
    lb = FakeWidget("Listbox", master=p["card"], yview=(0.1, 0.9))
    assert find_scroll_target(lb, registry.get) is None
    print("test_listbox_keeps_event_when_scrollable OK")


def test_unregistered_scrollable_canvas_keeps_event() -> None:
    # e.g. the internal canvas of CustomTkinter's own CTkScrollableFrame,
    # or any other library widget placed inside our content.
    registry, p = _build_hierarchy()
    other_canvas = FakeWidget("Canvas", master=p["card"], yview=(0.0, 0.5))
    assert find_scroll_target(other_canvas, registry.get) is None
    print("test_unregistered_scrollable_canvas_keeps_event OK")


def test_unregistered_non_scrollable_canvas_falls_through() -> None:
    registry, p = _build_hierarchy()
    other_canvas = FakeWidget("Canvas", master=p["card"], yview=(0.0, 1.0))
    assert find_scroll_target(other_canvas, registry.get) is p["ssf"]
    print("test_unregistered_non_scrollable_canvas_falls_through OK")


def test_nested_scrollers_innermost_wins() -> None:
    registry, p = _build_hierarchy()
    # A second (inner) scroll frame placed inside the outer one.
    inner_ssf = FakeScrollFrame()
    inner_frame = FakeWidget("CTkFrame", master=p["card"])
    inner_canvas = FakeWidget("Canvas", master=inner_frame)
    inner_inner = FakeWidget("CTkFrame", master=inner_canvas)
    deep_label = FakeWidget("CTkLabel", master=inner_inner)
    registry[inner_frame] = inner_ssf
    registry[inner_canvas] = inner_ssf
    registry[inner_inner] = inner_ssf
    assert find_scroll_target(deep_label, registry.get) is inner_ssf
    # ... while a sibling label still belongs to the outer scroller.
    assert find_scroll_target(p["label"], registry.get) is p["ssf"]
    print("test_nested_scrollers_innermost_wins OK")


def test_has_scrollable_content() -> None:
    assert has_scrollable_content(FakeWidget(yview=(0.1, 0.6))) is True
    assert has_scrollable_content(FakeWidget(yview=(0.0, 1.0))) is False
    # If the query itself fails we must assume the widget can scroll, so we
    # never steal its wheel events.
    assert has_scrollable_content(
        FakeWidget(yview=RuntimeError("gone")),
    ) is True
    print("test_has_scrollable_content OK")


def test_wheel_to_pixels_windows_notch() -> None:
    assert wheel_to_pixels(120, "win32") == -60.0    # wheel up scrolls up
    assert wheel_to_pixels(-120, "win32") == 60.0    # wheel down scrolls down
    print("test_wheel_to_pixels_windows_notch OK")


def test_wheel_to_pixels_precision_touchpad() -> None:
    # Precision touchpads emit sub-notch deltas; they must accumulate
    # proportionally instead of being rounded away.
    assert wheel_to_pixels(40, "win32") == -20.0
    assert wheel_to_pixels(-36, "win32") == 18.0
    print("test_wheel_to_pixels_precision_touchpad OK")


def test_wheel_to_pixels_dpi_scaling() -> None:
    assert wheel_to_pixels(120, "win32", scaling=1.5) == -90.0
    assert wheel_to_pixels(120, "win32", scaling=1.25) == -75.0
    print("test_wheel_to_pixels_dpi_scaling OK")


def test_wheel_to_pixels_darwin() -> None:
    assert wheel_to_pixels(5, "darwin") < 0
    assert wheel_to_pixels(-5, "darwin") > 0
    print("test_wheel_to_pixels_darwin OK")


def test_clamp_target() -> None:
    assert clamp_target(-10, total=1000, visible=200) == 0.0
    assert clamp_target(5000, total=1000, visible=200) == 800.0
    assert clamp_target(300, total=1000, visible=200) == 300.0
    # Content that fits the viewport has exactly one valid offset: 0.
    assert clamp_target(100, total=200, visible=200) == 0.0
    print("test_clamp_target OK")


def test_can_scroll() -> None:
    assert can_scroll(1000, 200) is True
    assert can_scroll(200, 200) is False
    assert can_scroll(100, 200) is False
    assert can_scroll(0, 0) is False
    print("test_can_scroll OK")


def test_master_loop_is_bounded() -> None:
    # A corrupt hierarchy (master cycle) must never hang the router.
    a = FakeWidget("Frame")
    b = FakeWidget("Frame", master=a)
    a.master = b
    assert find_scroll_target(a, {}.get) is None
    print("test_master_loop_is_bounded OK")


if __name__ == "__main__":
    test_event_on_label_routes_to_frame()
    test_event_on_button_routes_to_frame()
    test_event_on_entry_routes_to_frame()
    test_event_on_inner_background_routes_to_frame()
    test_event_on_canvas_routes_to_frame()
    test_event_on_card_routes_to_frame()
    test_event_outside_any_scrollable_returns_none()
    test_scrollable_text_widget_keeps_its_event()
    test_fully_visible_text_widget_falls_through()
    test_listbox_keeps_event_when_scrollable()
    test_unregistered_scrollable_canvas_keeps_event()
    test_unregistered_non_scrollable_canvas_falls_through()
    test_nested_scrollers_innermost_wins()
    test_has_scrollable_content()
    test_wheel_to_pixels_windows_notch()
    test_wheel_to_pixels_precision_touchpad()
    test_wheel_to_pixels_dpi_scaling()
    test_wheel_to_pixels_darwin()
    test_clamp_target()
    test_can_scroll()
    test_master_loop_is_bounded()
    print("\nAll scroll router tests passed.")
