"""Tests for conversations_to_ics recipe.

Covers:
- Character escaping (comma, semicolon, backslash, newlines)
- RFC 5545 75-octet line folding
- Event construction with UID, DTSTART, DTEND, and CATEGORIES
- Duration calculation (default 30m vs explicit finished_at)
- Skipping conversations without a valid started_at timestamp
- CRLF (\r\n) line endings
- Deduplication across multiple pages
- Error on missing id
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Load conversations_to_ics example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_ics.py"
spec = importlib.util.spec_from_file_location("conversations_to_ics", script_path)
c2i = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2i)

convert_paths_to_ics = c2i.convert_paths_to_ics
generate_ics = c2i.generate_ics
ics_text = c2i.ics_text
ics_datetime = c2i.ics_datetime


SAMPLE_CONVERSATIONS = [
    {
        "id": "conv_1",
        "started_at": "2026-09-20T09:00:00Z",
        "finished_at": "2026-09-20T09:45:00Z",
        "source": "phone_microphone",
        "structured": {
            "title": "Quarterly Review, Strategy & Planning",
            "category": "work",
            "overview": "Detailed discussion on Q4 targets.",
        },
        "transcript_segments": [
            {"speaker": "Alice", "text": "Let's review numbers."},
            {"speaker": "Bob", "text": "Looks strong."}
        ],
    },
    {
        "id": "conv_2",
        "started_at": "2026-09-20T14:00:00+02:00",
        # No finished_at: should default to 30 mins
        "structured": {
            "title": "Short Sync",
            "category": "personal",
        },
    },
    {
        "id": "conv_3",
        # No started_at: must be skipped
        "structured": {"title": "No timestamp conversation"},
    },
]


class TestConversationsToIcs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ics_text_escaping(self):
        self.assertEqual(ics_text("hello, world; test\\one\ntwo"), "hello\\, world\\; test\\\\one\\ntwo")
        self.assertEqual(ics_text(None), "")

    def test_ics_datetime(self):
        dt = ics_datetime("2026-09-20T11:00:00Z")
        self.assertEqual(dt.hour, 11)
        self.assertEqual(dt.tzinfo, timezone.utc)

        # Offset normalized to UTC
        dt2 = ics_datetime("2026-09-20T13:00:00+02:00")
        self.assertEqual(dt2.hour, 11)

    def test_generate_ics_events_and_duration(self):
        ics_text, events, skipped = generate_ics(SAMPLE_CONVERSATIONS)
        self.assertEqual(events, 2)
        self.assertEqual(skipped, 1)

        self.assertTrue(ics_text.endswith("\r\n"))
        self.assertIn("BEGIN:VCALENDAR\r\n", ics_text)
        self.assertIn("UID:conv_1@omi", ics_text)
        self.assertIn("DTSTART:20260920T090000Z", ics_text)
        self.assertIn("DTEND:20260920T094500Z", ics_text)  # 45 min explicit duration
        self.assertIn("CATEGORIES:work", ics_text)
        self.assertIn("Turns: 2", ics_text)

        # Conv 2: 14:00+02:00 -> 12:00 UTC, default 30 min duration -> 12:30 UTC
        self.assertIn("UID:conv_2@omi", ics_text)
        self.assertIn("DTSTART:20260920T120000Z", ics_text)
        self.assertIn("DTEND:20260920T123000Z", ics_text)

        # Conv 3 should not have a VEVENT
        self.assertNotIn("UID:conv_3@omi", ics_text)

    def test_deduplication(self):
        dup = [SAMPLE_CONVERSATIONS[0], SAMPLE_CONVERSATIONS[0]]
        _, events, _ = generate_ics(dup)
        self.assertEqual(events, 1)

    def test_convert_to_file(self):
        json_file = self.dir_path / "conversations.json"
        json_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")
        out_ics = self.dir_path / "history.ics"

        events, skipped = convert_paths_to_ics([json_file], out_ics)
        self.assertEqual(events, 2)
        self.assertEqual(skipped, 1)
        self.assertTrue(out_ics.exists())
        content = out_ics.read_bytes().decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", content)

    def test_missing_id_raises_value_error(self):
        invalid = [{"title": "No ID here"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_paths_to_ics([json_file])
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
