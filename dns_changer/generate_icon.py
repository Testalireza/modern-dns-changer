"""
Generate a modern app icon for the DNS Changer.
Creates a blue globe/network icon in .ico format.
Run: python generate_icon.py
"""
from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size=256):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle (dark navy)
    margin = int(size * 0.06)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=int(size * 0.18),
        fill=(22, 33, 62, 255)  # #16213E
    )

    # Globe/network rings (blue)
    center = size // 2
    radius = int(size * 0.30)
    blue = (45, 143, 214, 255)  # #2D8FD6
    line_width = max(2, int(size * 0.025))

    # Horizontal ellipse
    draw.ellipse(
        [center - radius, center - radius // 2,
         center + radius, center + radius // 2],
        outline=blue, width=line_width
    )
    # Vertical ellipse
    draw.ellipse(
        [center - radius // 2, center - radius,
         center + radius // 2, center + radius],
        outline=blue, width=line_width
    )
    # Full circle
    draw.ellipse(
        [center - radius, center - radius,
         center + radius, center + radius],
        outline=blue, width=line_width
    )
    # Center dot
    dot_r = max(3, int(size * 0.04))
    draw.ellipse(
        [center - dot_r, center - dot_r,
         center + dot_r, center + dot_r],
        fill=blue
    )

    return img

def main():
    icon = create_icon(256)
    # Also create smaller sizes for the .ico
    sizes = [16, 32, 48, 64, 128, 256]
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    icon.save(icon_path, format='ICO', sizes=[(s, s) for s in sizes])
    print(f"Icon saved to: {icon_path}")

    # Also save a PNG for reference
    png_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    icon.save(png_path, format='PNG')
    print(f"PNG saved to: {png_path}")

if __name__ == "__main__":
    main()
