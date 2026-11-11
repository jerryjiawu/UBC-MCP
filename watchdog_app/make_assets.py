"""Generate watchdog.ico. Run once."""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
S = 256
ACCENT, SILK, BOARD = (79, 168, 255, 255), (242, 242, 242, 255), (17, 17, 17, 255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((4, 4, S - 5, S - 5), radius=52, fill=BOARD, outline=(48, 48, 48, 255), width=3)
font = ImageFont.truetype(os.path.join(HERE, "ui", "fonts", "Orbitron.ttf"), 150)
try:
    font.set_variation_by_name("Black")
except Exception:
    pass
d.text((S / 2, S / 2 - 6), "W", font=font, fill=SILK, anchor="mm")
d.rounded_rectangle((78, 196, S - 79, 206), radius=5, fill=ACCENT)  # blue underline accent
img.save(os.path.join(HERE, "watchdog.ico"), sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
print("wrote watchdog.ico")

# The art (ui/img/frieren-mask.png) is used as-is: any white-on-black image works,
# so edit or replace that file directly -- nothing here regenerates it.
