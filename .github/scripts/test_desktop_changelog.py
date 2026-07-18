#!/usr/bin/env python3
"""Unit tests for desktop-changelog.py I/O encoding (stdlib unittest).

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


if __name__ == "__main__":
    unittest.main()
