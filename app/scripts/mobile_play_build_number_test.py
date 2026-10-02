#!/usr/bin/env python3
"""Tests for the prod Android Play-floor build-number resolution."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("mobile_play_build_number.py")
SPEC = importlib.util.spec_from_file_location("mobile_play_build_number", SCRIPT)
assert SPEC and SPEC.loader
floor_mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = floor_mod
SPEC.loader.exec_module(floor_mod)

CLI = [sys.executable, str(SCRIPT)]


class MobilePlayBuildNumberTests(unittest.TestCase):
    def test_tag_number_above_floor_is_kept(self) -> None:
        self.assertEqual(
            floor_mod.resolve_build_number(1242, "1241\n"),
            (1242, floor_mod.BUILD_NUMBER_SOURCE_TAG),
        )

    def test_floor_at_or_above_tag_allocates_floor_plus_one(self) -> None:
        self.assertEqual(
            floor_mod.resolve_build_number(1238, "1238\n"),
            (1239, floor_mod.BUILD_NUMBER_SOURCE_PLAY_FLOOR),
        )
        self.assertEqual(
            floor_mod.resolve_build_number(1238, "1241\n"),
            (1242, floor_mod.BUILD_NUMBER_SOURCE_PLAY_FLOOR),
        )

    def test_empty_play_history_keeps_tag_number(self) -> None:
        self.assertEqual(
            floor_mod.resolve_build_number(7, "\n"),
            (7, floor_mod.BUILD_NUMBER_SOURCE_TAG),
        )

    def test_malformed_play_output_fails_closed(self) -> None:
        for raw in ("abc", "-1", "0", "12.5", "9" * 100):
            with self.subTest(raw=raw):
                with self.assertRaises(floor_mod.StoreLookupError):
                    floor_mod.resolve_build_number(10, raw)

    def test_exhausted_floor_space_fails_closed(self) -> None:
        with self.assertRaisesRegex(floor_mod.StoreLookupError, "no allocatable"):
            floor_mod.resolve_build_number(10, str(floor_mod.MAX_BUILD_NUMBER))

    def test_invalid_tag_numbers_are_rejected(self) -> None:
        for raw in ("", "0", "-3", "12x", str(floor_mod.MAX_BUILD_NUMBER + 1)):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    floor_mod._require_tag_number(raw)

    def test_cli_reports_kept_and_allocated_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            play = Path(tmp) / "play.txt"
            play.write_text("1241\n", encoding="utf-8")
            kept = subprocess.run(
                CLI + ["--tag-number", "1242", "--play-output", str(play)],
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(
                json.loads(kept.stdout),
                {"build_number": 1242, "source": "tag"},
            )
            allocated = subprocess.run(
                CLI + ["--tag-number", "1238", "--play-output", str(play)],
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(
                json.loads(allocated.stdout),
                {"build_number": 1242, "source": "play_floor"},
            )

    def test_cli_fails_closed_on_malformed_play_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            play = Path(tmp) / "play.txt"
            play.write_text("not-a-number\n", encoding="utf-8")
            result = subprocess.run(
                CLI + ["--tag-number", "1242", "--play-output", str(play)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("play", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
