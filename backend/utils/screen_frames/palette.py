"""Server-side banner ground (palette) extraction.

Port of desktop/macos/Desktop/Sources/MeetingScreenshots/MeetingBannerPalette.swift
— read that file's header for the full reasoning. Short version: both the
macOS and web clients render the banner gradient from
ConversationScreenFrame.ground; neither samples pixels itself. A signed,
cross-origin GCS URL cannot reliably be read back via canvas.getImageData in
a browser, and two independent extractions (Swift on macOS, JS on web) would
drift from each other anyway. This module is the ONE extraction, run once
over the canonical bytes at approval time and persisted to Firestore —
never recomputed per read.

Two things a naive implementation gets wrong, both guarded against here:

1. A mean over hues returns mud — averaging a diff's reds and greens lands
   on a color that was never in the picture. This takes the *mode* (the
   heaviest bin of a 24-bin hue histogram), then refines only within that
   bin via a circular mean of its members.
2. Most screenshots have no hue at all. A terminal, a plain document: those
   are achromatic, and a mean over their noise still yields *some* angle.
   Below a weight floor this returns the neutral ground instead of
   inventing a confident but arbitrary color.
"""

from __future__ import annotations

import colorsys
import io
import math
from typing import List, Tuple

from PIL import Image

from models.screen_frame import ScreenFrameGround

# 24 bins ~ 15 deg each: fine enough to separate a blue chrome from a green
# diff, coarse enough that antialiasing around text doesn't split one real
# color across two bins.
BIN_COUNT = 24

# Below this, the frame is achromatic and any hue would be invented. Scaled
# per sample so it is independent of the sampling grid size.
CHROMA_FLOOR_PER_SAMPLE = 0.045

# White body text must clear this against the *lighter* stop. 4.5:1 is the
# WCAG AA threshold for normal text.
MINIMUM_CONTRAST_FOR_WHITE = 4.5

# 16x16 rather than 8x8: 256 samples still costs nothing and stops one
# accent button in a corner from carrying a whole bin on its own. Matches
# the Swift AppKit bridge's sampling grid exactly.
_SAMPLE_GRID = 16

_NEUTRAL_HUE = 0.62
_STOP_HUE_OFFSET = 0.06
_STOP_SATURATION = 0.42
_STOP_SATURATION_STEP = 0.13
_STOP_BRIGHTNESS_START = 0.46
_STOP_BRIGHTNESS_FLOOR = 0.16
_STOP_BRIGHTNESS_STEP = 0.02
_SECOND_STOP_BRIGHTNESS_DROP = 0.18
_SECOND_STOP_BRIGHTNESS_FLOOR = 0.12


def _relative_luminance(r: float, g: float, b: float) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_with_white(hue: float, saturation: float, brightness: float) -> float:
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, brightness)
    return 1.05 / (_relative_luminance(r, g, b) + 0.05)


def _hex(hue: float, saturation: float, brightness: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, brightness)
    clamp = lambda v: max(0, min(255, round(v * 255)))  # noqa: E731
    return "#{:02X}{:02X}{:02X}".format(clamp(r), clamp(g), clamp(b))


def _neutral_ground() -> ScreenFrameGround:
    return ScreenFrameGround(
        stops=[_hex(_NEUTRAL_HUE, 0.12, 0.40), _hex(_NEUTRAL_HUE, 0.16, 0.24)],
        is_neutral=True,
    )


def _stops_for_hue(hue: float) -> List[str]:
    """Two stops at a fixed saturation, darkened until white text clears AA
    contrast on the lighter one. Yellows and cyans are much brighter than
    blues at identical HSB brightness, so a constant isn't good enough —
    this measures rather than assumes.
    """
    brightness = _STOP_BRIGHTNESS_START
    saturation = _STOP_SATURATION
    while brightness > _STOP_BRIGHTNESS_FLOOR and _contrast_with_white(hue, saturation, brightness) < (
        MINIMUM_CONTRAST_FOR_WHITE
    ):
        brightness -= _STOP_BRIGHTNESS_STEP

    second_hue = (hue + _STOP_HUE_OFFSET) % 1.0
    second_saturation = saturation + _STOP_SATURATION_STEP
    second_brightness = max(_SECOND_STOP_BRIGHTNESS_FLOOR, brightness - _SECOND_STOP_BRIGHTNESS_DROP)
    return [_hex(hue, saturation, brightness), _hex(second_hue, second_saturation, second_brightness)]


def ground_from_rgb_samples(samples: List[Tuple[int, int, int]]) -> ScreenFrameGround:
    """Pure core, ported 1:1 from MeetingBannerPalette.ground(fromRGBA:)."""
    if not samples:
        return _neutral_ground()

    bins = [0.0] * BIN_COUNT
    bin_x = [0.0] * BIN_COUNT
    bin_y = [0.0] * BIN_COUNT
    total_weight = 0.0

    for r8, g8, b8 in samples:
        r, g, b = r8 / 255.0, g8 / 255.0, b8 / 255.0
        hue, saturation, brightness = colorsys.rgb_to_hsv(r, g, b)

        # Discount both ends of the brightness range: near-white paper and
        # near-black editor chrome are the two most common things on screen
        # and neither says anything about the meeting.
        midness = 1 - abs(brightness - 0.5) * 2
        weight = saturation * saturation * max(0.0, midness)
        if weight <= 0:
            continue

        bin_index = min(BIN_COUNT - 1, int(hue * BIN_COUNT))
        bins[bin_index] += weight
        radians = hue * 2 * math.pi
        bin_x[bin_index] += math.cos(radians) * weight
        bin_y[bin_index] += math.sin(radians) * weight
        total_weight += weight

    sample_count = len(samples)
    winner = max(range(BIN_COUNT), key=lambda i: bins[i])
    if total_weight < CHROMA_FLOOR_PER_SAMPLE * sample_count or bins[winner] <= 0:
        return _neutral_ground()

    # Circular mean *within* the winning bin only — precision without
    # letting an unrelated hue on the other side of the wheel drag the
    # answer.
    hue = math.atan2(bin_y[winner], bin_x[winner]) / (2 * math.pi)
    if hue < 0:
        hue += 1

    return ScreenFrameGround(stops=_stops_for_hue(hue), is_neutral=False)


def compute_ground(canonical_jpeg_bytes: bytes) -> ScreenFrameGround:
    """Downsample the canonical JPEG to 16x16 RGB and derive its ground.

    Called exactly once, at approval time, over the canonical bytes — see
    module docstring. Never raises: any decode failure here falls back to
    the neutral ground rather than blocking approval over a cosmetic field.
    """
    try:
        image = Image.open(io.BytesIO(canonical_jpeg_bytes)).convert("RGB")
        small = image.resize((_SAMPLE_GRID, _SAMPLE_GRID), Image.Resampling.BILINEAR)
        # .tobytes() rather than .getdata(): a flat, unambiguously-typed byte
        # buffer for an "RGB" mode image is exactly 3 bytes per pixel.
        raw = small.tobytes()
        samples = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
    except Exception:
        return _neutral_ground()
    return ground_from_rgb_samples(samples)
