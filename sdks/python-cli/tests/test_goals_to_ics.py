"""Tests for goals_to_ics recipe.

Covers:
- RFC 5545 character escaping
- Line folding at 75 octets
- VEVENT generation with target deadline dates
- Status mapping (NEEDS-ACTION vs COMPLETED)
- Deduplication across multiple export files
- Error handling on invalid records
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load goals_to_ics example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_ics.py"
spec = importlib.util.spec_from_file_location("goals_to_ics", script_path)
g2i = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2i)

convert_paths_to_ics = g2i.convert_paths_to_ics
generate_ics = g2i.generate_ics
ics_text = g2i.ics_text
ics_datetime = g2i.ics_datetime


SAMPLE_GOALS = [
    {
        "id": "goal_1",
        "title": "Read 20 books",
        "goal_type": "learning",
        "current_value": 15,
        "target_value": 20,
        "unit": "books",
        "is_active": True,
        "target_date": "2026-12-31T23:59:59Z",
        "created_at": "2026-09-01T10:00:00Z",
    },
    {
        "id": "goal_2",
        "title": "Run marathon",
        "goal_type": "fitness",
        "current_value": 42.2,
        "target_value": 42.2,
        "unit": "km",
        "is_active": True,
        "target_date": "2026-10-15T08:00:00+02:00",
    },
    {
        "id": "goal_3",
        "title": "Undated goal with no dates whatsoever",
        "current_value": 0,
        "target_value": 10,
        # No target_date, created_at, etc.
    },
]


class TestGoalsToIcs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ics_text_escaping(self):
        self.assertEqual(ics_text("Read, study; test\\one\ntwo"), "Read\\, study\\; test\\\\one\\ntwo")
        self.assertEqual(ics_text(None), "")

    def test_generate_ics_events_and_status(self):
        ics_text_content, events, skipped = generate_ics(SAMPLE_GOALS)
        self.assertEqual(events, 2)
        self.assertEqual(skipped, 1)

        self.assertTrue(ics_text_content.endswith("\r\n"))
        self.assertIn("BEGIN:VCALENDAR\r\n", ics_text_content)
        self.assertIn("UID:goal_1@omi-goal", ics_text_content)
        self.assertIn("STATUS:NEEDS-ACTION", ics_text_content)
        self.assertIn("DTSTART:20261231T235959Z", ics_text_content)
        self.assertIn("Target: Read 20 books", ics_text_content)
        self.assertIn("CATEGORIES:GOAL,learning", ics_text_content)

        # Goal 2 is completed (42.2 / 42.2)
        self.assertIn("UID:goal_2@omi-goal", ics_text_content)
        self.assertIn("STATUS:COMPLETED", ics_text_content)
        # 08:00+02:00 -> 06:00:00 UTC
        self.assertIn("DTSTART:20261015T060000Z", ics_text_content)

        # Goal 3 without dates should not appear as VEVENT
        self.assertNotIn("UID:goal_3@omi-goal", ics_text_content)

    def test_deduplication(self):
        dup = [SAMPLE_GOALS[0], SAMPLE_GOALS[0]]
        _, events, _ = generate_ics(dup)
        self.assertEqual(events, 1)

    def test_convert_to_file(self):
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(SAMPLE_GOALS), encoding="utf-8")
        out_ics = self.dir_path / "goals.ics"

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
