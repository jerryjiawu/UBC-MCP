"""
Text recognition for screenshots using the OCR engine built into Windows
(Windows.Media.Ocr) -- no Tesseract install, no cloud API, works offline.

Requires the pywinrt packages listed in requirements.txt. If they're missing,
or Windows has no OCR language installed, available() returns False and the
uploader simply skips OCR.
"""
import asyncio

UPSCALE = 2.0

try:
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode,
        BitmapDecoder,
        BitmapInterpolationMode,
        BitmapPixelFormat,
        BitmapTransform,
        ColorManagementMode,
        ExifOrientationMode,
    )
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    _IMPORT_ERROR = None
except ImportError as e:  # pragma: no cover - depends on the machine
    _IMPORT_ERROR = e


def available():
    """Return (ok, reason) describing whether OCR can run on this machine."""
    if _IMPORT_ERROR is not None:
        return False, f"winrt packages not installed ({_IMPORT_ERROR})"
    if OcrEngine.try_create_from_user_profile_languages() is None:
        return False, "no Windows OCR language installed (Settings > Time & language > Language)"
    return True, ""


async def _recognize(data):
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)

    # Windows OCR misses words in small UI/code text at 1x; upscaling before
    # recognition noticeably improves accuracy. Stay within the engine's limit.
    max_dim = OcrEngine.max_image_dimension
    longest = max(decoder.pixel_width, decoder.pixel_height)
    scale = min(UPSCALE, max_dim / longest)
    transform = BitmapTransform()
    transform.scaled_width = int(decoder.pixel_width * scale)
    transform.scaled_height = int(decoder.pixel_height * scale)
    transform.interpolation_mode = BitmapInterpolationMode.CUBIC

    # The OCR engine only accepts Bgra8/Gray8 bitmaps.
    bitmap = await decoder.get_software_bitmap_transformed_async(
        BitmapPixelFormat.BGRA8,
        BitmapAlphaMode.PREMULTIPLIED,
        transform,
        ExifOrientationMode.IGNORE_EXIF_ORIENTATION,
        ColorManagementMode.DO_NOT_COLOR_MANAGE,
    )

    engine = OcrEngine.try_create_from_user_profile_languages()
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


def extract_text(data):
    """Run OCR on raw PNG/JPEG bytes and return the recognized text, one line
    per detected line of text ("" if nothing was found)."""
    return asyncio.run(_recognize(data))
