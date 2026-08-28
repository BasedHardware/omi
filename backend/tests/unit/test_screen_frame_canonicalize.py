"""Tests for utils/screen_frames/canonicalize.py (contract §4 step 2).

Covers: metadata (EXIF/ICC) is stripped from the re-encoded bytes, an
animated GIF is rejected before ever reaching the judge, and a corrupt/
undecodable payload is rejected the same way (both raise
ScreenFrameCanonicalizationError, which callers must treat as a fail-closed
per-candidate rejection).
"""

import io

import pytest
from PIL import Image

from utils.screen_frames.canonicalize import (
    CANONICAL_LONG_EDGE_PX,
    ScreenFrameCanonicalizationError,
    canonicalize_candidate,
)


def _jpeg_with_exif(size=(400, 300)) -> bytes:
    """Build a JPEG carrying real EXIF (camera make + orientation + a
    timestamp) using only Pillow's own Exif writer — no extra dependency
    needed just for a test fixture."""
    image = Image.new("RGB", size, color=(200, 100, 50))
    exif = Image.Exif()
    exif[271] = "OmiTestCamera"  # Make
    exif[274] = 1  # Orientation
    exif[306] = "2024:01:01 12:00:00"  # DateTime
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _animated_gif() -> bytes:
    frames = [Image.new("RGB", (100, 100), color=c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buf.getvalue()


def _large_jpeg(long_edge=3000) -> bytes:
    image = Image.new("RGB", (long_edge, long_edge // 2), color=(10, 200, 10))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


class TestMetadataStripped:
    def test_exif_is_not_present_in_canonical_bytes(self):
        raw = _jpeg_with_exif()
        canonical = canonicalize_candidate(raw)

        reopened = Image.open(io.BytesIO(canonical.jpeg_bytes))
        # Pillow surfaces EXIF via .info['exif'] / .getexif(); both must be empty
        # since save() was never given exif=/icc_profile= kwargs.
        assert not reopened.info.get("exif")
        exif = reopened.getexif()
        assert len(exif) == 0

    def test_canonical_digest_differs_from_source_bytes_digest(self):
        import hashlib

        raw = _jpeg_with_exif()
        canonical = canonicalize_candidate(raw)
        assert canonical.sha256_hex != hashlib.sha256(raw).hexdigest()


class TestAnimatedRejected:
    def test_animated_gif_raises_before_reaching_judge(self):
        with pytest.raises(ScreenFrameCanonicalizationError) as exc_info:
            canonicalize_candidate(_animated_gif())
        assert exc_info.value.reason == "animated"


class TestCorruptRejected:
    def test_garbage_bytes_raise_decode_failed(self):
        with pytest.raises(ScreenFrameCanonicalizationError) as exc_info:
            canonicalize_candidate(b"not an image, just garbage bytes" * 10)
        assert exc_info.value.reason == "decode_failed"

    def test_empty_bytes_raise_decode_failed(self):
        with pytest.raises(ScreenFrameCanonicalizationError):
            canonicalize_candidate(b"")


class TestLongEdgeBounded:
    def test_long_edge_is_bounded(self):
        canonical = canonicalize_candidate(_large_jpeg(3000))
        assert max(canonical.width, canonical.height) == CANONICAL_LONG_EDGE_PX

    def test_thumbnail_is_smaller_than_canonical(self):
        canonical = canonicalize_candidate(_large_jpeg(3000))
        thumb = Image.open(io.BytesIO(canonical.thumbnail_jpeg_bytes))
        assert max(thumb.size) <= 480
