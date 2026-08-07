#!/usr/bin/env python3
"""Unit tests for check_brand_ui.py count_purple helper."""

from __future__ import annotations

import unittest

from check_brand_ui import count_purple, is_purple_hex, is_ui_source


class BrandUiTests(unittest.TestCase):
    def test_counts_color_purple_and_hex(self) -> None:
        text = "Color.purple\nlet x = Color(hex: 0x8B5CF6)\n#8B5CF6\npurplePrimary\n"
        # Color.purple + #8B5CF6 + purplePrimary = 3 (0x8B5CF6 not matched — hex with # only)
        self.assertGreaterEqual(count_purple(text), 3)

    def test_is_ui_source(self) -> None:
        self.assertTrue(is_ui_source("desktop/macos/Desktop/Sources/Foo.swift"))
        self.assertFalse(is_ui_source("backend/main.py"))
        self.assertFalse(is_ui_source("desktop/macos/Desktop/Sources/Theme/OmiColors.swift"))

    def test_counts_swiftui_dot_purple(self) -> None:
        self.assertGreaterEqual(count_purple(".foregroundStyle(.purple)"), 1)

    def test_counts_flutter_colors_purple(self) -> None:
        self.assertGreaterEqual(count_purple("color: Colors.purple"), 1)

    def test_counts_tailwind_bg_purple_500(self) -> None:
        self.assertGreaterEqual(count_purple('className="bg-purple-500 text-purple-700"'), 2)

    def test_counts_css_color_purple(self) -> None:
        self.assertGreaterEqual(count_purple("color: purple;"), 1)

    def test_counts_tailwind_ramps_that_are_purple_by_sight_not_by_name(self) -> None:
        # These shipped past the check: the web marketplace had a violet promo
        # card, violet and indigo category themes, and violet capability chips.
        self.assertGreaterEqual(count_purple('className="bg-violet-500 text-indigo-300"'), 2)
        self.assertGreaterEqual(count_purple('className="from-fuchsia-600"'), 1)

    def test_hex_is_judged_by_hue_not_by_membership(self) -> None:
        # #6C2BD9 is one digit from the listed #6D28D9 and shipped the app-store
        # developer banner's purple gradient past a green check.
        for digits in ("6C2BD9", "2D1B69", "7C3AED", "A855F7", "C4B5FD", "D946EF"):
            self.assertTrue(is_purple_hex(digits), digits)

    def test_hue_test_leaves_blues_greys_and_pinks_alone(self) -> None:
        # A false positive here blocks unrelated PRs, so the negative cases
        # matter as much as the positive ones. Includes the app palette's own
        # backgrounds and the blues sitting nearest the purple boundary.
        for digits in ("3B82F6", "6C8EEF", "2563EB", "818CF6", "EC4899", "0F0F0F", "1F1F25", "35343B", "FFFFFF"):
            self.assertFalse(is_purple_hex(digits), digits)

    def test_near_black_is_neutral_whatever_hue_it_computes(self) -> None:
        # #0D0D0F is the content pane's fill and sits at a blue-purple hue with
        # almost no saturation; counting it would make the pane unfixable.
        self.assertFalse(is_purple_hex("0D0D0F"))


if __name__ == "__main__":
    unittest.main()
