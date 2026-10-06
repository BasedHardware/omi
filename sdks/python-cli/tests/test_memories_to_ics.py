"""Hermetic unit tests for memories_to_ics.py recipe."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Add examples directory to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from memories_to_ics import (
    convert,
    fold,
    ics_datetime,
    ics_text,
    stamp,
    validate_path,
)


class TestMemoriesToIcs(unittest.TestCase):
    def test_ics_text(self):
        self.assertEqual(ics_text(None), "")
        self.assertEqual(ics_text("hello;world,here\\there"), "hello\\;world\\,here\\\\there")
        self.assertEqual(ics_text("line 1\r\nline 2\nline 3"), "line 1\\nline 2\\nline 3")
        self.assertEqual(ics_text(["a", "b"]), "a\\, b")

    def test_ics_datetime(self):
        self.assertIsNone(ics_datetime(None))
        self.assertIsNone(ics_datetime(""))
        self.assertIsNone(ics_datetime("not-a-date"))

        dt = ics_datetime("2026-09-17T14:30:00Z")
        self.assertIsInstance(dt, datetime)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.hour, 14)

        # Offset parsing
        dt_offset = ics_datetime("2026-09-17T10:00:00+02:00")
        self.assertIsInstance(dt_offset, datetime)
        self.assertEqual(dt_offset.hour, 8)  # 10:00 UTC+2 is 08:00 UTC

    def test_stamp(self):
        dt = datetime(2026, 9, 17, 14, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(stamp(dt), "20260917T143000Z")

    def test_fold(self):
        short = "SUMMARY:Short text"
        self.assertEqual(fold(short), [short])

        # Long line requiring folding at 75 octets
        long_line = "DESCRIPTION:" + "A" * 100
        folded = fold(long_line)
        self.assertTrue(len(folded) > 1)
        for part in folded:
            self.assertLessEqual(len(part.encode("utf-8")), 75)
        # Second part starts with space per RFC 5545
        self.assertTrue(folded[1].startswith(" "))

        # Multi-byte UTF-8 characters should never be split
        emoji_line = "SUMMARY:" + "🌟" * 30
        folded_emoji = fold(emoji_line)
        for part in folded_emoji:
            self.assertLessEqual(len(part.encode("utf-8")), 75)
            # Must decode cleanly without UnicodeDecodeError
            part.encode("utf-8").decode("utf-8")

    def test_validate_path(self):
        self.assertEqual(validate_path("safe/path.ics"), Path("safe/path.ics"))
        with self.assertRaises(ValueError):
            validate_path("../traversal.ics")

    def test_envelope_unwrapping(self):
        envelope = {
            "memories": [
                {
                    "id": "mem_1",
                    "content": "Meeting memory",
                    "created_at": "2026-09-17T10:00:00Z",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "envelope.json"
            dst = Path(tmpdir) / "envelope.ics"
            src.write_text(json.dumps(envelope), encoding="utf-8")
            exported, skipped = convert(src, dst)
            self.assertEqual(exported, 1)
            self.assertEqual(skipped, 0)
            self.assertTrue(dst.exists())

    def test_skip_missing_created_at(self):
        sample = [
            {"id": "mem_good", "content": "Has date", "created_at": "2026-09-17T10:00:00Z"},
            {"id": "mem_bad", "content": "No date"},
            {"id": "mem_invalid", "content": "Bad date", "created_at": "not-valid-iso"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "skip.json"
            dst = Path(tmpdir) / "skip.ics"
            src.write_text(json.dumps(sample), encoding="utf-8")
            exported, skipped = convert(src, dst)
            self.assertEqual(exported, 1)
            self.assertEqual(skipped, 2)

    def test_convert_memories_to_ics_e2e(self):
        sample = [
            {
                "id": "mem_100",
                "category": "work",
                "content": "Quarterly planning sync\nAction items discussed",
                "tags": ["planning", "q3"],
                "visibility": "private",
                "created_at": "2026-09-17T15:00:00Z",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sample.json"
            dst = Path(tmpdir) / "sample.ics"
            src.write_text(json.dumps(sample), encoding="utf-8")

            exported, skipped = convert(src, dst)
            self.assertEqual(exported, 1)
            self.assertEqual(skipped, 0)

            raw_content = dst.read_bytes()
            self.assertIn(b"\r\n", raw_content)
            content = raw_content.decode("utf-8")
            self.assertIn("BEGIN:VCALENDAR", content)
            self.assertIn("VERSION:2.0", content)
            self.assertIn("X-WR-CALNAME:Omi Memories", content)
            self.assertIn("BEGIN:VEVENT", content)
            self.assertIn("UID:omi-memory-mem_100@omi-cli", content)
            self.assertIn("DTSTART:20260917T150000Z", content)
            self.assertIn("DTEND:20260917T151500Z", content)
            self.assertIn("SUMMARY:Quarterly planning sync", content)
            self.assertIn("CATEGORIES:work", content)
            self.assertIn("END:VEVENT", content)
            self.assertIn("END:VCALENDAR", content)

    def test_overwrite_behavior(self):
        sample = [
            {"id": "mem_1", "content": "Test", "created_at": "2026-09-17T10:00:00Z"}
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sample.json"
            dst = Path(tmpdir) / "sample.ics"
            src.write_text(json.dumps(sample), encoding="utf-8")

            convert(src, dst)
            self.assertTrue(dst.exists())

            # Without overwrite, should raise FileExistsError
            with self.assertRaises(FileExistsError):
                convert(src, dst, overwrite=False)

            # With overwrite, should succeed
            convert(src, dst, overwrite=True)
            self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
