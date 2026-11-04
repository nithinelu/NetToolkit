#!/usr/bin/env python3
"""
Generate the NetToolkit application icon (icon.ico + icon.png).

A rounded blue tile with a white network hub-and-spoke motif. Run with Pillow
installed:  python assets/make_icon.py
Outputs icon.ico and icon.png in the repo root.
"""

import os
from PIL import Image, ImageDraw

ACCENT = (31, 78, 120)      # #1f4e78
ACCENT2 = (46, 111, 176)    # #2e6fb0
WHITE = (255, 255, 255)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024  # supersample canvas


def build() -> Image.Image:
    # vertical gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        c = tuple(int(ACCENT[i] + (ACCENT2[i] - ACCENT[i]) * t) for i in range(3))
        gd.line([(0, y), (S, y)], fill=c + (255,))

    # rounded-square mask
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    def px(fx, fy):
        return (fx * S, fy * S)

    hub = px(0.50, 0.52)
    nodes = [px(0.50, 0.24), px(0.26, 0.74), px(0.74, 0.74)]
    line_w = int(S * 0.028)

    # connecting links
    for n in nodes:
        d.line([hub, n], fill=WHITE + (255,), width=line_w)

    def disc(c, r, fill):
        d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=fill)

    # satellite nodes
    for n in nodes:
        disc(n, S * 0.085, WHITE + (255,))
        disc(n, S * 0.045, ACCENT + (255,))
    # central hub (larger)
    disc(hub, S * 0.125, WHITE + (255,))
    disc(hub, S * 0.070, ACCENT2 + (255,))

    return img


def main():
    img = build()
    base = img.resize((256, 256), Image.LANCZOS)
    base.save(os.path.join(ROOT, "icon.png"))
    base.save(os.path.join(ROOT, "icon.ico"), format="ICO",
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                     (128, 128), (256, 256)])
    # crisp small sizes for the header / About dialog
    for sz in (48, 64):
        img.resize((sz, sz), Image.LANCZOS).save(
            os.path.join(ROOT, f"icon_{sz}.png"))
    print("wrote icon.png, icon.ico, icon_48.png, icon_64.png in", ROOT)


if __name__ == "__main__":
    main()
