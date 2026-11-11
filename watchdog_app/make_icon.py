"""Generate watchdog.ico (PCB style: black board, gold pads, white W). Run once."""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
S = 256
GOLD, SILK, BOARD = (227, 185, 77, 255), (242, 242, 242, 255), (17, 17, 17, 255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((4, 4, S - 5, S - 5), radius=34, fill=BOARD, outline=(60, 60, 60, 255), width=4)
# IC pads along top and bottom
for i in range(7):
    x = 38 + i * 28
    d.rectangle((x, 26, x + 14, 52), fill=GOLD)
    d.rectangle((x, S - 53, x + 14, S - 27), fill=GOLD)
# silkscreen outline of the chip
d.rectangle((28, 62, S - 29, S - 63), outline=SILK, width=5)
font = ImageFont.truetype(os.path.join(HERE, "ui", "fonts", "Orbitron.ttf"), 120)
try:
    font.set_variation_by_name("Black")
except Exception:
    pass
d.text((S / 2, S / 2 + 2), "W", font=font, fill=SILK, anchor="mm")
img.save(os.path.join(HERE, "watchdog.ico"), sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
print("wrote watchdog.ico")
