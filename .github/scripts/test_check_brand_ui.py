#!/usr/bin/env python3
"""Unit tests for check_brand_ui.py count_purple helper."""

from __future__ import annotations

import unittest

from check_brand_ui import count_purple, is_ui_source


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


if __name__ == "__main__":
    unittest.main()
