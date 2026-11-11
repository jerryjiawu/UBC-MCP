"""Build watchdog_app/watchdog.ico (window, taskbar and shortcut icon). Run after
changing the icon.

Source: your logo at <project root>/watchdog.ico (any size or shape). It's
centred on a transparent square, since Windows squashes non-square icons, and
saved at every size Windows uses. With no logo there, a plain "W" is drawn.
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(os.path.dirname(HERE), "watchdog.ico")
OUT = os.path.join(HERE, "watchdog.ico")
S = 256
SIZES = [(256, 256), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
ACCENT, TEXT, BG = (79, 168, 255, 255), (242, 242, 242, 255), (17, 17, 17, 255)


def from_logo(path):
    src = Image.open(path)
    # an .ico can hold several frames; use the largest
    if getattr(src, "info", {}).get("sizes"):
        src.size = max(src.info["sizes"], key=lambda s: s[0] * s[1])
        src.load()
    logo = src.convert("RGBA")
    logo = logo.crop(logo.getchannel("A").getbbox() or (0, 0, *logo.size))
    pad = 0.06  # small margin so it doesn't touch the edges
    scale = (S * (1 - 2 * pad)) / max(logo.size)
    logo = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.alpha_composite(logo, ((S - logo.width) // 2, (S - logo.height) // 2))
    return img


def fallback():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, S - 5, S - 5), radius=52, fill=BG, outline=(48, 48, 48, 255), width=3)
    font = ImageFont.truetype(os.path.join(HERE, "ui", "fonts", "Orbitron.ttf"), 150)
    font.set_variation_by_name("Black")
    d.text((S / 2, S / 2 - 6), "W", font=font, fill=TEXT, anchor="mm")
    d.rounded_rectangle((78, 196, S - 79, 206), radius=5, fill=ACCENT)
    return img


img = from_logo(SOURCE) if os.path.exists(SOURCE) else fallback()
img.save(OUT, sizes=SIZES)
print("wrote", OUT, "from", "your logo" if os.path.exists(SOURCE) else "the built-in W")

# The art (ui/img/frieren-mask.png) is used as-is: any white-on-black image works,
# so edit or replace that file directly -- nothing here regenerates it.
