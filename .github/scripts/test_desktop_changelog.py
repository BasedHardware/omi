#!/usr/bin/env python3
"""Unit tests for desktop changelog tooling (stdlib unittest).

Regression coverage for #9717: read_json/write_json must always use UTF-8 so a
contributor on a non-UTF-8 host locale (e.g. GBK on native Windows Python) does
not crash with a UnicodeDecodeError. The CI host is UTF-8, so a plain round-trip
would not catch a missing encoding; these tests assert the encoding is forwarded
on every platform.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
import unittest.mock
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "desktop_changelog", Path(__file__).with_name("desktop-changelog.py")
)
changelog = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(changelog)

_CHECK_SPEC = importlib.util.spec_from_file_location(
    "check_desktop_changelog", Path(__file__).with_name("check-desktop-changelog.py")
)
checker = importlib.util.module_from_spec(_CHECK_SPEC)
_CHECK_SPEC.loader.exec_module(checker)


class EncodingTests(unittest.TestCase):
    def test_read_json_forces_utf8(self) -> None:
        captured: dict[str, object] = {}
        real_read_text = Path.read_text

        def spy(self: Path, *args: object, **kwargs: object) -> str:
            captured["encoding"] = kwargs.get("encoding")
            return real_read_text(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.json"
            path.write_text('{"note": "“curly”"}', encoding="utf-8")
            with unittest.mock.patch.object(Path, "read_text", spy):
                self.assertEqual(changelog.read_json(path), {"note": "“curly”"})
        self.assertEqual(captured["encoding"], "utf-8")

    def test_write_json_forces_utf8(self) -> None:
        captured: dict[str, object] = {}
        real_write_text = Path.write_text

        def spy(self: Path, *args: object, **kwargs: object) -> int:
            captured["encoding"] = kwargs.get("encoding")
            return real_write_text(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out" / "changelog.json"
            with unittest.mock.patch.object(Path, "write_text", spy):
                changelog.write_json(path, {"note": "“curly”"})
        self.assertEqual(captured["encoding"], "utf-8")

    def test_round_trip_preserves_non_ascii(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.json"
            payload = {"note": "“curly” — café"}
            changelog.write_json(path, payload)
            self.assertEqual(changelog.read_json(path), payload)


class ChangelogRequirementTests(unittest.TestCase):
    def test_internal_release_controls_are_exempt_but_product_source_is_not(self) -> None:
        for path in (
            "desktop/macos/docs/release.md",
            "desktop/macos/scripts/qualify-desktop-beta.sh",
            # Sibling qualification-runner helper (EXEMPT_DESKTOP_PATHS).
            "desktop/macos/scripts/qualification-swift-cache.sh",
            # Test files are never user-facing app changes (EXEMPT_DESKTOP_PATH_PREFIXES).
            # #10374's timeout bump touched this file; without the exemption the
            # post-merge push run of the changelog gate reddened main (#10387).
            "desktop/macos/tests/test-qualify-desktop-beta-contract.sh",
            "desktop/macos/tests/some-other-desktop-test.sh",
            # Rust backend prefix.
            "desktop/macos/Backend-Rust/src/main.rs",
            # Generated Swift is derived from the OpenAPI contract, never a
            # user-facing app note (EXEMPT_DESKTOP_PATH_PREFIXES).
            "desktop/macos/Desktop/Sources/Generated/OmiApi.generated.swift",
        ):
            with self.subTest(path=path):
                self.assertFalse(checker.is_desktop_change_requiring_changelog(path))

        # Product source still requires a changelog — the exemptions must not leak.
        # Note the hand-written Sources file is NOT under Sources/Generated/.
        for path in (
            "desktop/macos/Desktop/Sources/AppDelegate.swift",
            "desktop/macos/scripts/some-user-facing-script.sh",
        ):
            with self.subTest(path=path):
                self.assertTrue(checker.is_desktop_change_requiring_changelog(path))


if __name__ == "__main__":
    unittest.main()
