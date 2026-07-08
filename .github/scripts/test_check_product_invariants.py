#!/usr/bin/env python3
"""Unit tests for check_product_invariants.py (stdlib unittest)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_product_invariants import matched_invariants, parse_invariant, path_matches


SAMPLE = """# INV-CHAT-1: One shared transcript

**Status:** locked
**Statement:** Test.

## Path globs

- `desktop/macos/agent/src/runtime/**`
- `desktop/macos/Desktop/Sources/Chat/**`

## PR rule

Name `INV-CHAT-1` in the PR body if you touch the path globs above.
"""

SAMPLE_UI = """# INV-UI-1: No purple

**Status:** locked

## Path globs

- `web/**`

## PR rule

Do **not** require naming `INV-UI-1` in routine UI PRs.
"""


class PathMatchTests(unittest.TestCase):
    def test_globstar_prefix(self) -> None:
        self.assertTrue(path_matches("desktop/macos/agent/src/runtime/kernel.ts", "desktop/macos/agent/src/runtime/**"))
        self.assertFalse(path_matches("desktop/macos/agent/tests/x.ts", "desktop/macos/agent/src/runtime/**"))

    def test_globstar_zero_segments(self) -> None:
        self.assertTrue(
            path_matches(
                "desktop/macos/Desktop/Sources/MemoryExportService.swift",
                "desktop/macos/Desktop/Sources/**/MemoryExport*",
            )
        )
        self.assertTrue(
            path_matches(
                "desktop/macos/Desktop/Sources/Foo/MemoryExportService.swift",
                "desktop/macos/Desktop/Sources/**/MemoryExport*",
            )
        )

    def test_exact_file(self) -> None:
        self.assertTrue(
            path_matches(
                "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift",
                "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift",
            )
        )


class ParseTests(unittest.TestCase):
    def test_parse_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat.md"
            path.write_text(SAMPLE, encoding="utf-8")
            parsed = parse_invariant(path)
            assert parsed is not None
            self.assertEqual(parsed["id"], "INV-CHAT-1")
            self.assertEqual(parsed["status"], "locked")
            self.assertTrue(parsed["require_naming"])
            self.assertEqual(len(parsed["globs"]), 2)

    def test_skip_naming(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui.md"
            path.write_text(SAMPLE_UI, encoding="utf-8")
            parsed = parse_invariant(path)
            assert parsed is not None
            self.assertFalse(parsed["require_naming"])


class MatchTests(unittest.TestCase):
    def test_matched_requires_naming(self) -> None:
        inv = {
            "id": "INV-CHAT-1",
            "status": "locked",
            "globs": ["desktop/macos/agent/src/runtime/**"],
            "require_naming": True,
            "path": "x",
        }
        ui = {
            "id": "INV-UI-1",
            "status": "locked",
            "globs": ["web/**"],
            "require_naming": False,
            "path": "y",
        }
        hits = matched_invariants(
            ["desktop/macos/agent/src/runtime/kernel.ts", "web/app/x.ts"],
            [inv, ui],
        )
        self.assertEqual([h["id"] for h in hits], ["INV-CHAT-1"])


if __name__ == "__main__":
    unittest.main()
