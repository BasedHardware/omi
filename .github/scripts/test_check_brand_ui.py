#!/usr/bin/env python3
"""Unit tests for check_brand_ui.py count_purple helper."""

from __future__ import annotations

import unittest

from check_brand_ui import count_purple, is_ui_source


class BrandUiTests(unittest.TestCase):
    def test_counts_color_purple_and_hex(self) -> None:
        text = "Color.purple\nlet x = Color(hex: 0x8B5CF6)\n#8B5CF6\npurplePrimary\n"
        # Color.purple + 0x8B5CF6 + #8B5CF6 + purplePrimary
        self.assertGreaterEqual(count_purple(text), 4)

    def test_counts_flutter_deep_purple(self) -> None:
        """`deepPurple` is the spelling most of the Flutter app actually uses.

        It went uncounted because camelCase leaves no word boundary before
        `purple`, so `\\bpurple\\b` cannot see it and no other pattern spelt it.
        """
        self.assertGreaterEqual(count_purple("color: Colors.deepPurple"), 1)
        self.assertGreaterEqual(count_purple("Colors.deepPurpleAccent"), 1)
        self.assertGreaterEqual(count_purple("Colors.deepPurple.shade300"), 1)

    def test_counts_dart_hex_literal(self) -> None:
        """Flutter writes `Color(0xFF8B5CF6)`, never `#8B5CF6`."""
        self.assertGreaterEqual(count_purple("const Color(0xFF8B5CF6)"), 1)
        self.assertGreaterEqual(count_purple("const Color(0xff7c3aed)"), 1)

    def test_ignores_colours_that_merely_contain_purple_hex_digits(self) -> None:
        """A non-purple hue must not be counted just for sharing digits."""
        self.assertEqual(count_purple("const Color(0xFF1A2B3C)"), 0)
        self.assertEqual(count_purple("const Color(0xFF00FF00)"), 0)

    def test_dart_hex_literal_must_start_a_token(self) -> None:
        """`0x` has to begin a token, or the ratchet fails files containing no purple.

        Without a leading boundary the pattern matches inside an identifier or a longer
        literal, so an unrelated constant ending in a purple hue is reported as a purple
        increase.
        """
        self.assertEqual(count_purple("foo0x8B5CF6"), 0)
        self.assertEqual(count_purple("SOME_CONST0x8B5CF6"), 0)
        # ...while a real literal in the shapes Flutter writes still counts.
        self.assertGreaterEqual(count_purple("Color(0xFF8B5CF6)"), 1)
        self.assertGreaterEqual(count_purple("value = 0x8B5CF6;"), 1)

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


if __name__ == "__main__":
    unittest.main()
