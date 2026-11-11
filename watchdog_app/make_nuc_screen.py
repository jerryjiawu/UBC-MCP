"""Render the 800x480 "WATCHDOG V1 ACTIVE" screen for the NUC's display.

Same look as the app: Orbitron, blue accent, Frieren line art on the left
(ui/img/frieren-mask.png, white-on-black or white-on-transparent) fading into
the text panel on the right.
Output: nuc/watchdog_active_800x480.png
"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from artsplit import load_srgb, split

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 800, 480
BG = (12, 12, 12)
TEXT = (242, 242, 242)
MUTED = (125, 125, 125)
ACCENT = (79, 168, 255)
ART = (160, 205, 255)
FONT = os.path.join(HERE, "ui", "fonts", "Orbitron.ttf")
ART_PATH = os.path.join(HERE, "ui", "img", "frieren-mask.png")
OUT = os.path.join(HERE, "nuc", "watchdog_active_800x480.png")

PANEL_X = 470  # text column centre



def font(size, weight="Black"):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_name(weight)
    return f


def spaced(draw, xy, text, fnt, fill, spacing):
    """Letter-spaced text centred on xy[0]; returns its width."""
    widths = [draw.textlength(c, font=fnt) for c in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x, y = xy[0] - total / 2, xy[1]
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=fnt, fill=fill)
        x += w + spacing
    return total


def art_layer():
    """Frieren on the left, fading out toward the text: line work tinted blue,
    coloured parts (eyes) in their own colour (see artsplit.py)."""
    lines, colour, has_colour = split(load_srgb(ART_PATH))
    scale = H / lines.height
    size = (round(lines.width * scale), H)
    area_w = 520
    left = max(0, min(round(size[0] * 0.40 - area_w / 2), size[0] - area_w))
    box = (left, 0, left + area_w, H)
    lines = lines.resize(size, Image.LANCZOS).crop(box)
    # horizontal fade: solid on the left, gone by the right edge of the art area
    fade = Image.linear_gradient("L").rotate(-90, expand=True).resize((area_w, H))  # white left -> black right
    fade = fade.point(lambda v: min(255, int(v * 1.8)))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    tint = Image.new("RGBA", (area_w, H), ART + (255,))
    tint.putalpha(ImageChops.multiply(lines, fade).point(lambda v: int(v * 0.85)))
    layer.paste(tint, (-20, 0), tint)
    if has_colour:
        colour = colour.resize(size, Image.LANCZOS).crop(box)
        colour.putalpha(ImageChops.multiply(colour.getchannel("A"), fade))
        layer.alpha_composite(colour, (-20, 0))
    return layer

def glow(img, draw_fn, radius):
    g = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(g))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(radius)))


def main():
    img = Image.new("RGBA", (W, H), BG + (255,))
    img.alpha_composite(art_layer())

    x = PANEL_X + 120  # centre of the right-hand column
    d = ImageDraw.Draw(img)
    spaced(d, (x, 118), "STUDY MODE", font(13, "Regular"), MUTED, 6)
    spaced(d, (x, 146), "WATCHDOG", font(46), TEXT, 2)
    spaced(d, (x, 204), "V1", font(16, "Bold"), ACCENT, 4)
    d.line((x - 50, 244, x + 50, 244), fill=(42, 42, 42), width=2)

    act = font(46)
    width = sum(d.textlength(c, font=act) for c in "ACTIVE") + 6 * 5
    tx = x + 14
    glow(img, lambda g: spaced(g, (tx, 268), "ACTIVE", act, ACCENT + (190,), 6), 12)
    spaced(ImageDraw.Draw(img), (tx, 268), "ACTIVE", act, ACCENT, 6)

    cx, cy, r = tx - width / 2 - 24, 296, 8
    glow(img, lambda g: g.ellipse((cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4), fill=ACCENT + (200,)), 8)
    ImageDraw.Draw(img).ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.convert("RGB").save(OUT, optimize=True)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
