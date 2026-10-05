import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from examples.conversations_to_ics import (
    convert,
    fold,
    ics_datetime,
    ics_text,
    stamp,
)


class TestConversationsToICS(unittest.TestCase):
    def test_ics_text_escaping_and_coercion(self):
        self.assertEqual(ics_text(None), "")
        self.assertEqual(ics_text("plain text"), "plain text")
        self.assertEqual(
            ics_text("hello; world, with \\ slash and \r\n newline"),
            "hello\\; world\\, with \\\\ slash and \\n newline",
        )
        self.assertEqual(ics_text(12345), "12345")
        self.assertEqual(ics_text(True), "True")
        self.assertEqual(ics_text(["tag1", "tag2"]), '["tag1"\\, "tag2"]')
        self.assertEqual(ics_text({"key": "val"}), '{"key": "val"}')

    def test_ics_datetime_parsing(self):
        self.assertIsNone(ics_datetime(None))
        self.assertIsNone(ics_datetime(""))
        self.assertIsNone(ics_datetime("invalid-date-string"))
        self.assertIsNone(ics_datetime(123456789))

        parsed_z = ics_datetime("2026-10-04T15:30:00Z")
        self.assertIsNotNone(parsed_z)
        self.assertEqual(parsed_z.year, 2026)
        self.assertEqual(parsed_z.month, 10)
        self.assertEqual(parsed_z.day, 4)
        self.assertEqual(parsed_z.hour, 15)
        self.assertEqual(parsed_z.minute, 30)
        self.assertEqual(parsed_z.tzinfo, timezone.utc)

        parsed_offset = ics_datetime("2026-10-04T12:30:00-03:00")
        self.assertIsNotNone(parsed_offset)
        self.assertEqual(parsed_offset.hour, 15)
        self.assertEqual(parsed_offset.tzinfo, timezone.utc)

    def test_stamp(self):
        dt = datetime(2026, 10, 4, 15, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(stamp(dt), "20261004T153000Z")

    def test_fold_short_and_long_lines(self):
        short = "SUMMARY:Short line"
        self.assertEqual(fold(short), [short])

        long_line = "DESCRIPTION:" + "A" * 100
        folded = fold(long_line)
        self.assertGreater(len(folded), 1)
        self.assertTrue(all(len(part.encode("utf-8")) <= 75 for part in folded))
        reconstructed = folded[0] + "".join(part[1:] for part in folded[1:])
        self.assertEqual(reconstructed, long_line)

    def test_fold_utf8_boundary_safety(self):
        multibyte = "SUMMARY:" + "ñ" * 50
        folded = fold(multibyte)
        for part in folded:
            part.encode("utf-8")
        reconstructed = folded[0] + "".join(part[1:] for part in folded[1:])
        self.assertEqual(reconstructed, multibyte)

    def test_convert_success_and_rfc_structure(self):
        conversations = [
            {
                "id": "conv-1",
                "started_at": "2026-10-04T10:00:00Z",
                "finished_at": "2026-10-04T10:45:00Z",
                "structured": {
                    "title": "Meeting with Alice, Bob; & Team",
                    "category": "work",
                },
                "source": "omi-device",
            },
            {
                "id": "conv-2",
                "started_at": "2026-10-04T12:00:00Z",
                "finished_at": None,
                "structured": None,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "conversations.json"
            dst = Path(tmpdir) / "output.ics"
            src.write_text(json.dumps(conversations), encoding="utf-8")

            written, skipped = convert(src, dst)
            self.assertEqual(written, 2)
            self.assertEqual(skipped, 0)
            self.assertTrue(dst.exists())

            content = dst.read_text(encoding="utf-8")
            self.assertIn("BEGIN:VCALENDAR", content)
            self.assertIn("VERSION:2.0", content)
            self.assertIn("END:VCALENDAR", content)
            self.assertIn("UID:omi-conversation-conv-1@omi-cli", content)
            self.assertIn("DTSTART:20261004T100000Z", content)
            self.assertIn("DTEND:20261004T104500Z", content)
            self.assertIn("UID:omi-conversation-conv-2@omi-cli", content)
            self.assertIn("DTSTART:20261004T120000Z", content)
            self.assertIn("DTEND:20261004T123000Z", content)

    def test_convert_skipped_without_start_time(self):
        conversations = [
            {
                "id": "conv-valid",
                "started_at": "2026-10-04T10:00:00Z",
                "finished_at": "2026-10-04T10:30:00Z",
            },
            {
                "id": "conv-nostart",
                "started_at": None,
                "finished_at": "2026-10-04T11:00:00Z",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "conversations.json"
            dst = Path(tmpdir) / "output.ics"
            src.write_text(json.dumps(conversations), encoding="utf-8")

            written, skipped = convert(src, dst)
            self.assertEqual(written, 1)
            self.assertEqual(skipped, 1)

    def test_convert_exclusive_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "conversations.json"
            dst = Path(tmpdir) / "output.ics"
            src.write_text("[]", encoding="utf-8")
            dst.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                convert(src, dst)

    def test_convert_invalid_json_shapes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "conversations.json"
            dst = Path(tmpdir) / "output.ics"

            src.write_text('{"not": "a list"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                convert(src, dst)

            src.write_text('["not a dict"]', encoding="utf-8")
            with self.assertRaises(ValueError):
                convert(src, dst)


if __name__ == "__main__":
    unittest.main()
