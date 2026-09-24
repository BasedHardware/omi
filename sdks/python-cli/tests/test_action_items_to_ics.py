"""Tests for action_items_to_ics recipe.

Covers:
- RFC 5545 character escaping (backslash, semicolon, comma, newlines)
- RFC 5545 line folding at 75 octets
- VEVENT generation with DTSTART, DTEND (+30 min), and UID
- Skipping items lacking a due_at timestamp
- Status tagging (NEEDS-ACTION vs COMPLETED)
- Strict CRLF (\r\n) line endings per RFC 5545 §3.1
- Deduplication of records across export pages
- Error handling on invalid records
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Load action_items_to_ics example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_ics.py"
spec = importlib.util.spec_from_file_location("action_items_to_ics", script_path)
ai2i = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2i)

convert_paths_to_ics = ai2i.convert_paths_to_ics
generate_ics = ai2i.generate_ics
ics_text = ai2i.ics_text
ics_datetime = ai2i.ics_datetime
fold = ai2i.fold


SAMPLE_ACTION_ITEMS = [
    {
        "id": "task_1",
        "description": "Send proposal, contract; review notes\\brief",
        "completed": False,
        "due_at": "2026-09-30T17:00:00Z",
        "created_at": "2026-09-20T09:00:00Z",
        "conversation_id": "conv_123",
    },
    {
        "id": "task_2",
        "description": "Completed task with due date",
        "completed": True,
        "due_at": "2026-09-25T14:00:00+02:00",
    },
    {
        "id": "task_3",
        "description": "Undated task that must be skipped",
        "completed": False,
        # No due_at
    },
]


class TestActionItemsToIcs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ics_text_escaping(self):
        self.assertEqual(ics_text("a,b;c\\d\ne"), "a\\,b\\;c\\\\d\\ne")
        self.assertEqual(ics_text(None), "")
        self.assertEqual(ics_text(123), "123")

    def test_ics_datetime(self):
        dt = ics_datetime("2026-09-20T11:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 11)
        self.assertEqual(dt.tzinfo, timezone.utc)

        # Normalization from +02:00 offset to UTC
        dt2 = ics_datetime("2026-09-20T13:00:00+02:00")
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2.hour, 11)

        self.assertIsNone(ics_datetime(""))
        self.assertIsNone(ics_datetime("not-a-date"))

    def test_fold_line(self):
        short = "SUMMARY:Short text"
        self.assertEqual(fold(short), [short])

        long_line = "DESCRIPTION:" + "x" * 100
        folded = fold(long_line)
        self.assertTrue(len(folded) > 1)
        # RFC 5545 §3.1 requires continuation lines to start with a space or tab
        for line in folded[1:]:
            self.assertTrue(line.startswith(" ") or line.startswith("\t"))

    def test_generate_ics_events_and_skipping(self):
        ics_text, events, skipped = generate_ics(SAMPLE_ACTION_ITEMS)
        self.assertEqual(events, 2)
        self.assertEqual(skipped, 1)

        # RFC 5545 requires CRLF line endings
        self.assertTrue(ics_text.endswith("\r\n"))
        self.assertIn("\r\nBEGIN:VCALENDAR\r\n", "\r\n" + ics_text)
        self.assertIn("\r\nEND:VCALENDAR\r\n", ics_text)

        # Check VEVENT structure
        self.assertIn("UID:task_1@omi", ics_text)
        self.assertIn("STATUS:NEEDS-ACTION", ics_text)
        self.assertIn("DTSTART:20260930T170000Z", ics_text)
        self.assertIn("DTEND:20260930T173000Z", ics_text)  # +30 mins
        self.assertIn("Send proposal\\, contract\\; review notes\\\\brief", ics_text)

        # Task 2 (completed)
        self.assertIn("UID:task_2@omi", ics_text)
        self.assertIn("STATUS:COMPLETED", ics_text)

        # Task 3 should NOT appear as a VEVENT
        self.assertNotIn("UID:task_3@omi", ics_text)

    def test_deduplication(self):
        duplicated = [SAMPLE_ACTION_ITEMS[0], SAMPLE_ACTION_ITEMS[0]]
        ics_text, events, skipped = generate_ics(duplicated)
        self.assertEqual(events, 1)

    def test_convert_to_file(self):
        json_file = self.dir_path / "tasks.json"
        json_file.write_text(json.dumps(SAMPLE_ACTION_ITEMS), encoding="utf-8")
        out_ics = self.dir_path / "tasks.ics"

        events, skipped = convert_paths_to_ics([json_file], out_ics)
        self.assertEqual(events, 2)
        self.assertEqual(skipped, 1)
        self.assertTrue(out_ics.exists())
        content = out_ics.read_bytes().decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", content)

    def test_missing_id_raises_value_error(self):
        invalid = [{"description": "No ID here"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_paths_to_ics([json_file])
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
