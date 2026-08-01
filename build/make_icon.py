"""One-time generator for the LabScribe icon (assets/icon.png + icon.ico).

Draws a simple 'document with a scan line' mark — green on dark — so the tray
icon is legible at 16x16. Rerun if you ever want to restyle it:
    python build/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "assets"

BG = (15, 20, 25, 255)        # matches dashboard --bg
GREEN = (52, 192, 122, 255)   # matches dashboard --accent
LIGHT = (214, 222, 232, 255)


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64  # design on a 64px grid, scale everything

    # rounded dark tile
    d.rounded_rectangle([2 * s, 2 * s, 62 * s, 62 * s], radius=12 * s, fill=BG)
    # document body
    d.rounded_rectangle([16 * s, 12 * s, 48 * s, 52 * s], radius=4 * s,
                        outline=LIGHT, width=max(1, int(3 * s)))
    # text lines
    for y in (22, 30, 38):
        d.line([22 * s, y * s, 42 * s, y * s], fill=LIGHT, width=max(1, int(2 * s)))
    # green scan line across the document
    d.line([10 * s, 45 * s, 54 * s, 45 * s], fill=GREEN, width=max(2, int(4 * s)))
    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    draw(256).save(ASSETS / "icon.png")
    draw(256).save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)],
    )
    print(f"Wrote {ASSETS / 'icon.png'} and {ASSETS / 'icon.ico'}")


if __name__ == "__main__":
    main()
