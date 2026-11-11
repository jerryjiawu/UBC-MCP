"""Split the Frieren art into its two layers (shared by make_nuc_screen.py and
watchdog_phone/build.py; ui/index.html does the same in JavaScript).

The art is white line work plus coloured parts (e.g. blue eyes). Where the two
meet, the drawing app anti-aliased them into pale blends ("residual white"). Each
pixel is treated as  white * e + colour * (1 - e):
  - lines layer:  the white share -> gets tinted (grey idle / blue studying)
  - colour layer: the colour share, un-mixed back to its pure colour
"""
import io

import numpy as np
from PIL import Image, ImageCms

CHROMA_MIN = 40  # below this a pixel is plain line work (white/grey)


def load_srgb(path):
    """Open as RGBA in sRGB, converting from an embedded colour profile (e.g.
    Display P3 from an iPad) so colours match what the screen shows."""
    im = Image.open(path)
    icc = im.info.get("icc_profile")
    rgba = im.convert("RGBA")
    if not icc:
        return rgba
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        rgb = ImageCms.profileToProfile(rgba.convert("RGB"), src, ImageCms.createProfile("sRGB"), outputMode="RGB")
    except Exception:
        return rgba
    rgb.putalpha(rgba.getchannel("A"))
    return rgb


def split(rgba):
    """-> (lines_alpha: 'L' image, colour: 'RGBA' image, has_colour: bool)."""
    px = np.asarray(rgba.convert("RGBA"), dtype=np.float32)
    rgb, a = px[..., :3], px[..., 3] / 255.0
    hi, lo = rgb.max(-1), rgb.min(-1)
    coloured = (hi - lo) >= CHROMA_MIN
    if not coloured.any():
        lum = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        return Image.fromarray((lum * a).clip(0, 255).astype(np.uint8), "L"), \
            Image.new("RGBA", rgba.size, (0, 0, 0, 0)), False
    # the colour's own darkest channel: the most common value among solidly coloured pixels
    solid = coloured & (a > 0.9)
    base = float(np.bincount(lo[solid].astype(np.int64), minlength=256).argmax()) if solid.any() else 0.0
    # white share of each coloured pixel: how far its darkest channel sits above the base
    e = np.where(coloured, ((lo - base) / max(1.0, 255.0 - base)).clip(0, 0.98), 1.0)
    denom = np.where(coloured, 1.0 - e, 1.0)[..., None]  # non-coloured pixels: alpha 0 below anyway
    pure = ((rgb - 255.0 * e[..., None]) / denom).clip(0, 255)
    colour = np.dstack([pure, (a * (1.0 - e) * 255.0)]).clip(0, 255).astype(np.uint8)
    lum = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    line_alpha = np.where(coloured, 255.0 * e * a, lum * a)  # blends contribute only their white share
    return Image.fromarray(line_alpha.clip(0, 255).astype(np.uint8), "L"), Image.fromarray(colour, "RGBA"), True
