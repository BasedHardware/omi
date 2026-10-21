"""Tests for utils/screen_frames/palette.py — the server-side port of
desktop/macos/Desktop/Sources/MeetingScreenshots/MeetingBannerPalette.swift.

Mirrors desktop/macos/Desktop/Tests/MeetingBannerPaletteTests.swift's cases:
achromatic frames go neutral, a mode (not a mean) resolves hue conflicts,
every hue clears WCAG contrast against white, and the second gradient stop
is always darker than the first.
"""

import colorsys

import pytest

from utils.screen_frames.palette import (
    MINIMUM_CONTRAST_FOR_WHITE,
    _neutral_ground,
    _contrast_with_white,
    _relative_luminance,
    _stops_for_hue,
    ground_from_rgb_samples,
)


def _hex_to_hsv(hex_color: str):
    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255
    return colorsys.rgb_to_hsv(r, g, b)


def _hex_to_rgb(hex_color: str):
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))


class TestAchromaticFallsBackToNeutral:
    def test_near_black_is_neutral(self):
        ground = ground_from_rgb_samples([(10, 10, 10)] * 50)
        assert ground.is_neutral is True
        assert len(ground.stops) == 2

    def test_near_white_is_neutral(self):
        ground = ground_from_rgb_samples([(245, 245, 245)] * 50)
        assert ground.is_neutral is True

    def test_empty_samples_is_neutral(self):
        ground = ground_from_rgb_samples([])
        assert ground.is_neutral is True


class TestModeNotMean:
    def test_seventy_red_thirty_green_resolves_to_red_not_yellow(self):
        # Mid-brightness, high-saturation red/green so neither sample is
        # discounted to zero weight by the near-white cutoff a pure (255,0,0)
        # primary would hit.
        red = (180, 60, 60)
        green = (60, 180, 60)
        ground = ground_from_rgb_samples([red] * 70 + [green] * 30)

        assert ground.is_neutral is False
        hue, _saturation, _value = _hex_to_hsv(ground.stops[0])
        # Red is hue 0.0; a naive weighted circular mean over ALL samples
        # (rather than the mode of a histogram) would land around hue
        # ~0.068 (orange/yellow) instead — see MeetingBannerPalette.swift's
        # header for why that's the wrong answer.
        assert hue < 0.02 or hue > 0.98, f"expected a red hue, got {hue}"


class TestContrastAgainstWhite:
    @pytest.mark.parametrize("bin_index", range(24))
    def test_every_hue_clears_aa_contrast(self, bin_index):
        hue = bin_index / 24
        stops = _stops_for_hue(hue)
        r, g, b = _hex_to_rgb(stops[0])
        contrast = 1.05 / (_relative_luminance(r, g, b) + 0.05)
        assert contrast >= MINIMUM_CONTRAST_FOR_WHITE - 1e-9


class TestSecondStopDarker:
    @pytest.mark.parametrize("bin_index", range(24))
    def test_second_stop_is_darker_than_first(self, bin_index):
        hue = bin_index / 24
        stops = _stops_for_hue(hue)
        r1, g1, b1 = _hex_to_rgb(stops[0])
        r2, g2, b2 = _hex_to_rgb(stops[1])
        assert _relative_luminance(r2, g2, b2) < _relative_luminance(r1, g1, b1)


class TestContrastHelper:
    def test_contrast_matches_direct_formula(self):
        # Sanity check the helper itself against the WCAG formula inline,
        # independent of the module's own implementation of the same math.
        hue, saturation, brightness = 0.6, 0.42, 0.3
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, brightness)

        def channel(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
        expected = 1.05 / (luminance + 0.05)
        assert _contrast_with_white(hue, saturation, brightness) == pytest.approx(expected)


class TestNeutralGroundIsPinnedAcrossAllThreeSurfaces:
    """The neutral ground exists in three languages and nothing else guards their agreement.

    The server emits `ground` on every frame it approves, so clients normally just render what
    they are given. But a record persisted before `ground` existed has none, and each client
    therefore carries its own copy of the fallback:

      - here, computed from _NEUTRAL_HUE
      - web/app/src/components/conversations/ConversationScreenFrameBanner.tsx (NEUTRAL_GROUND_STOPS)
      - desktop/.../MeetingScreenshots/MeetingBannerPalette.swift (MeetingBannerPalette.neutral)

    Three copies of one constant drift silently, and the symptom would be a banner that is a
    different colour on web than on macOS for exactly the oldest records — the ones least likely
    to be looked at during review. Pinning the literal here means a change to the hue or either
    stop breaks this test, and whoever changes it has to go and update the other two.
    """

    def test_neutral_stops_match_the_literals_the_clients_hardcode(self):
        ground = _neutral_ground()
        assert ground.stops == ["#5A5D66", "#33363D"]
        assert ground.is_neutral is True
