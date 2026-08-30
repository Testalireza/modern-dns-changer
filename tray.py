"""
System tray icon for Modern DNS Changer.
"""
from __future__ import annotations

import threading
from typing import Callable

from logger import get_logger

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None
    ImageDraw = None

try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:  # pragma: no cover
    TRAY_AVAILABLE = False


def _create_tray_image(size: int = 64):
    """Create the tray icon image. Returns a ``PIL.Image`` or ``None``."""
    if Image is None or ImageDraw is None:
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    m = int(size * 0.08)
    draw.rounded_rectangle(
        [m, m, size - m, size - m],
        radius=int(size * 0.2),
        fill=(21, 101, 192, 255),
    )
    c = size // 2
    r = int(size * 0.28)
    lw = max(2, int(size * 0.04))
    w = (255, 255, 255, 200)
    draw.ellipse([c - r, c - r // 2, c + r, c + r // 2], outline=w, width=lw)
    draw.ellipse([c - r // 2, c - r, c + r // 2, c + r], outline=w, width=lw)
    draw.ellipse([c - r, c - r, c + r, c + r], outline=w, width=lw)
    return img


class TrayController:
    """Owns a single :mod:`pystray` icon and its background thread."""

    def __init__(self) -> None:
        self._icon = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(
        self,
        on_show: Callable[[], None],
        on_toggle: Callable[[], None],
        on_quit: Callable[[], None],
        tooltip: str = "Modern DNS Changer",
    ) -> bool:
        """Start the tray icon. Returns True on success, False otherwise."""
        log = get_logger()
        if not TRAY_AVAILABLE:
            log.info("pystray not available — tray disabled")
            return False
        with self._lock:
            if self._icon is not None:
                return True
            try:
                image = _create_tray_image(64)
                if image is None:
                    log.error("Cannot create tray image (Pillow missing)")
                    return False
                menu = pystray.Menu(
                    pystray.MenuItem("Show", lambda _i: on_show(), default=True, visible=True),
                    pystray.MenuItem("Toggle DNS", lambda _i: on_toggle()),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Quit", lambda _i: on_quit()),
                )
                self._icon = pystray.Icon(
                    "modern_dns_changer", image, tooltip, menu
                )
                self._thread = threading.Thread(
                    target=self._icon.run, daemon=True, name="pystray"
                )
                self._thread.start()
                return True
            except (OSError, RuntimeError) as exc:
                log.error("Failed to start tray icon: %s", exc)
                self._icon = None
                self._thread = None
                return False

    def is_running(self) -> bool:
        """Return True if the tray icon is currently running."""
        with self._lock:
            return self._icon is not None

    def stop(self) -> None:
        """Stop the tray icon. Safe to call multiple times."""
        with self._lock:
            if self._icon is not None:
                try:
                    self._icon.stop()
                except (OSError, RuntimeError) as exc:
                    get_logger().debug("tray stop: %s", exc)
                self._icon = None
            self._thread = None

    def notify(self, title: str, message: str) -> None:
        """Show a tray notification if the icon is running."""
        with self._lock:
            icon = self._icon
        if icon is not None:
            try:
                icon.notify(message, title)
            except (OSError, RuntimeError, AttributeError) as exc:
                get_logger().debug("tray notify: %s", exc)
