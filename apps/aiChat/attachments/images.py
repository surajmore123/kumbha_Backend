"""
Image validation and preparation.

The image is fully decoded (not just header-checked), bounded in pixel
count, downscaled when very large, and re-encoded when that is needed or
when it carries EXIF metadata, so location data in phone photos is not
stored or sent onward.
"""

import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from apps.aiChat import ai_config
from apps.aiChat.attachments.errors import AttachmentError

# Formats Gemini accepts directly. GIF is converted (first frame) to PNG.
_DIRECT = {"image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    mime_type: str
    extension: str
    width: int
    height: int
    reencoded: bool


def prepare_image(data: bytes, mime_type: str) -> PreparedImage:
    if len(data) > ai_config.max_image_bytes():
        raise AttachmentError(
            "file_too_large", limit=ai_config.max_image_bytes() // (1024 * 1024),
        )
    if mime_type not in _DIRECT and mime_type != "image/gif":
        # e.g. HEIC: Pillow cannot decode it here, so it can't be verified.
        raise AttachmentError("unsupported_image")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(data))
            width, height = probe.size
            if width * height > ai_config.max_image_pixels():
                raise AttachmentError("image_too_large")
            probe.verify()
            image = Image.open(io.BytesIO(data))
            image.load()
    except AttachmentError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise AttachmentError("image_too_large") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise AttachmentError("corrupt_image") from exc

    has_exif = bool(image.info.get("exif")) or bool(image.getexif())
    max_side = ai_config.max_image_side()
    needs_resize = max(width, height) > max_side
    convert_gif = mime_type == "image/gif"

    if not (needs_resize or has_exif or convert_gif):
        extension = {"image/jpeg": ".jpg", "image/png": ".png"}.get(
            mime_type, ".webp",
        )
        return PreparedImage(data, mime_type, extension, width, height, False)

    # Apply the EXIF orientation before metadata is dropped.
    image = ImageOps.exif_transpose(image)
    if needs_resize:
        image.thumbnail((max_side, max_side))

    keeps_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )
    buffer = io.BytesIO()
    if convert_gif or keeps_alpha or mime_type == "image/png":
        image.save(buffer, format="PNG", optimize=True)
        out_mime, extension = "image/png", ".png"
    else:
        image.convert("RGB").save(buffer, format="JPEG", quality=90)
        out_mime, extension = "image/jpeg", ".jpg"

    return PreparedImage(
        buffer.getvalue(), out_mime, extension, image.width, image.height, True,
    )
