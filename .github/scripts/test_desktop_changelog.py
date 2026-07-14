#!/usr/bin/env python3
"""Behavioral contract tests for desktop changelog JSON encoding."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from typing import cast

SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "desktop-changelog.py"
SPEC = importlib.util.spec_from_file_location("desktop_changelog", MODULE_PATH)
assert SPEC and SPEC.loader
desktop_changelog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(desktop_changelog)


class _Utf8OnlyReadPath:
    def __init__(self, text: str) -> None:
        self.text = text
        self.encoding: str | None = None

    def read_text(self, encoding: str | None = None) -> str:
        self.encoding = encoding
        if encoding != "utf-8":
            raise UnicodeError("host locale cannot decode this UTF-8 file")
        return self.text


class _RecordingParent:
    def __init__(self) -> None:
        self.created = False

    def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
        self.created = parents and exist_ok


class _Utf8OnlyWritePath:
    def __init__(self) -> None:
        self.parent = _RecordingParent()
        self.text = ""
        self.encoding: str | None = None

    def write_text(self, text: str, encoding: str | None = None) -> int:
        self.encoding = encoding
        if encoding != "utf-8":
            raise UnicodeError("host locale cannot encode this changelog")
        self.text = text
        return len(text)


class JsonEncodingTests(unittest.TestCase):
    def test_read_json_uses_utf8_instead_of_the_host_locale(self) -> None:
        expected = {"change": "Fixes \u2014 \U0001f6e0\ufe0f"}
        path = _Utf8OnlyReadPath(json.dumps(expected, ensure_ascii=False))

        actual = desktop_changelog.read_json(cast(Path, path))

        self.assertEqual(actual, expected)
        self.assertEqual(path.encoding, "utf-8")

    def test_write_json_uses_utf8_and_preserves_unicode(self) -> None:
        expected = {"change": "Fixes \u2014 \U0001f6e0\ufe0f"}
        path = _Utf8OnlyWritePath()

        desktop_changelog.write_json(cast(Path, path), expected)

        self.assertTrue(path.parent.created)
        self.assertEqual(path.encoding, "utf-8")
        self.assertEqual(json.loads(path.text), expected)
        self.assertIn(expected["change"], path.text)


if __name__ == "__main__":
    unittest.main()
