"""Image canonicalisation for screen-frame egress (contract §4 step 2).

The canonical digest computed here is authoritative, not the client's
transport-check digest from step 1. Every downstream decision — the judge,
the approval, the writer — is bound to these exact re-encoded bytes.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps

# Guard against decompression-bomb inputs before any pixel buffer is
# allocated. 64MP is generous headroom over any real screenshot (a 6K
# display is ~22MP) while still bounding worst-case memory.
Image.MAX_IMAGE_PIXELS = 64_000_000

CANONICAL_LONG_EDGE_PX = 1600
CANONICAL_JPEG_QUALITY = 82
THUMBNAIL_LONG_EDGE_PX = 480
THUMBNAIL_JPEG_QUALITY = 75


class ScreenFrameCanonicalizationError(Exception):
    """A candidate could not be turned into a safe canonical JPEG.

    Callers MUST treat this as a per-candidate fail-closed rejection
    (reject_reason="unreadable") — never a request-level error, and never
    stored bytes. It short-circuits before the judge is ever called, since
    there is nothing safe to send it.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class CanonicalFrame:
    jpeg_bytes: bytes
    sha256_hex: str
    width: int
    height: int
    thumbnail_jpeg_bytes: bytes


def _resize_long_edge(image: Image.Image, long_edge_px: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= long_edge_px:
        return image
    scale = long_edge_px / float(longest)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    # No exif= or icc_profile= kwarg is passed, so nothing from image.info
    # rides along into the re-encoded bytes.
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def canonicalize_candidate(raw_bytes: bytes) -> CanonicalFrame:
    """Decode, apply EXIF orientation, strip metadata, bound size, re-encode.

    Raises ScreenFrameCanonicalizationError for corrupt/undecodable bytes or
    an animated/multi-frame image (GIF, APNG, multi-page). See the class
    docstring for the fail-closed contract this implies for callers.
    """
    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
    except Exception as error:  # Pillow raises a wide variety of error types here.
        raise ScreenFrameCanonicalizationError("decode_failed") from error

    if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
        raise ScreenFrameCanonicalizationError("animated")

    try:
        # in_place defaults to False, so this always returns a new Image
        # (never None — None is only possible with in_place=True, which we
        # don't use).
        oriented = ImageOps.exif_transpose(image)
    except Exception as error:
        raise ScreenFrameCanonicalizationError("decode_failed") from error

    # convert("RGB") drops any alpha channel (screenshots are opaque) and,
    # combined with never passing icc_profile= to save(), leaves the output
    # an untagged sRGB-assumed buffer — the practical form of "convert to
    # sRGB, drop ICC" for content that was never wide-gamut to begin with.
    rgb_image = oriented.convert("RGB")

    bounded = _resize_long_edge(rgb_image, CANONICAL_LONG_EDGE_PX)
    canonical_bytes = _encode_jpeg(bounded, CANONICAL_JPEG_QUALITY)
    digest = hashlib.sha256(canonical_bytes).hexdigest()

    thumb_image = _resize_long_edge(bounded, THUMBNAIL_LONG_EDGE_PX)
    thumbnail_bytes = _encode_jpeg(thumb_image, THUMBNAIL_JPEG_QUALITY)

    width, height = bounded.size
    return CanonicalFrame(
        jpeg_bytes=canonical_bytes,
        sha256_hex=digest,
        width=width,
        height=height,
        thumbnail_jpeg_bytes=thumbnail_bytes,
    )
