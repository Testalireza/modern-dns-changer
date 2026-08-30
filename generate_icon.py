"""
Generate a modern app icon for the Modern DNS Changer v4.1.

Creates a multi-resolution ``icon.ico`` (used by both the EXE and the
tray) plus a reference ``icon.png``.

Run:
    python generate_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_DIR = Path(__file__).resolve().parent
NAVY = (22, 33, 62, 255)
BLUE = (45, 143, 214, 255)
WHITE = (255, 255, 255, 220)


def create_icon(size: int = 256) -> Image.Image:
    """Return the high-resolution app icon as a ``PIL.Image``."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background rounded square (dark navy)
    margin = int(size * 0.06)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=int(size * 0.18),
        fill=NAVY,
    )

    # Globe / network rings (blue)
    center = size // 2
    radius = int(size * 0.30)
    line_width = max(2, int(size * 0.025))
    draw.ellipse(
        [center - radius, center - radius // 2,
         center + radius, center + radius // 2],
        outline=BLUE, width=line_width,
    )
    draw.ellipse(
        [center - radius // 2, center - radius,
         center + radius // 2, center + radius],
        outline=BLUE, width=line_width,
    )
    draw.ellipse(
        [center - radius, center - radius,
         center + radius, center + radius],
        outline=BLUE, width=line_width,
    )
    dot_r = max(3, int(size * 0.04))
    draw.ellipse(
        [center - dot_r, center - dot_r,
         center + dot_r, center + dot_r],
        fill=BLUE,
    )
    return img


def main() -> int:
    icon = create_icon(256)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = PROJECT_DIR / "icon.ico"
    png_path = PROJECT_DIR / "icon.png"
    icon.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    icon.save(png_path, format="PNG")
    print(f"Icon saved to: {ico_path}")
    print(f"PNG saved to: {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
