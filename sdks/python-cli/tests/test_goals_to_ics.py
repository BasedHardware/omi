#!/usr/bin/env python3
"""
Unit tests for sdks/python-cli/examples/goals_to_ics.py
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
import sys
from pathlib import Path
from unittest.mock import patch

# Add examples and tests directory to sys.path so pytest discovers example modules in CI
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goals_to_ics import (
    compute_progress,
    convert,
    fold,
    generate_ics,
    ics_datetime,
    ics_text,
    load,
    stamp,
)


class TestGoalsToIcs(unittest.TestCase):

    def test_ics_text_escaping(self):
        self.assertEqual(ics_text(None), "")
        self.assertEqual(ics_text("Read; write, repeat\\done"), "Read\\; write\\, repeat\\\\done")
        self.assertEqual(ics_text("Line 1\nLine 2\r\nLine 3"), "Line 1\\nLine 2\\nLine 3")
        self.assertEqual(ics_text(100), "100")
        self.assertEqual(ics_text({"a": 1}), '{"a": 1}')

    def test_ics_datetime(self):
        self.assertIsNone(ics_datetime(None))
        self.assertIsNone(ics_datetime(""))
        self.assertIsNone(ics_datetime("bad-date"))

        dt_z = ics_datetime("2026-09-20T10:00:00Z")
        self.assertIsNotNone(dt_z)
        self.assertEqual(dt_z.year, 2026)
        self.assertEqual(dt_z.month, 9)
        self.assertEqual(dt_z.day, 20)
        self.assertEqual(stamp(dt_z), "20260920T100000Z")

        dt_offset = ics_datetime("2026-09-20T18:00:00+08:00")
        self.assertEqual(stamp(dt_offset), "20260920T100000Z")

    def test_line_folding(self):
        short = "SUMMARY:Short text"
        self.assertEqual(fold(short), [short])

        long_line = "DESCRIPTION:" + "a" * 100
        folded = fold(long_line)
        self.assertTrue(len(folded) > 1)
        # Check first line is <= 75 bytes
        self.assertTrue(len(folded[0].encode("utf-8")) <= 75)
        # Check subsequent lines begin with a space
        for continuation in folded[1:]:
            self.assertTrue(continuation.startswith(" "))

    def test_compute_progress(self):
        # Completed
        self.assertEqual(compute_progress({}, False), (100, "100% (Completed)"))

        # Qualitative
        self.assertEqual(compute_progress({"goal_type": "qualitative"}, True), (None, "Qualitative"))

        # Boolean
        self.assertEqual(compute_progress({"goal_type": "boolean", "current_value": 0, "target_value": 1}, True), (0, "0%"))
        self.assertEqual(compute_progress({"goal_type": "boolean", "current_value": 1, "target_value": 1}, True), (100, "100%"))

        # Numeric / Scale
        pct, label = compute_progress({"goal_type": "numeric", "current_value": 12, "target_value": 20, "unit": "km"}, True)
        self.assertEqual(pct, 60)
        self.assertIn("60%", label)
        self.assertIn("12/20 km", label)

    def test_generate_ics_vtodo(self):
        goals = {
            "g1": {
                "id": "g1",
                "title": "Complete Python 3.12 course",
                "goal_type": "numeric",
                "current_value": 75,
                "target_value": 100,
                "unit": "%",
                "status": "active",
                "target_date": "2026-10-01T12:00:00Z",
                "created_at": "2026-09-01T08:00:00Z",
            },
            "g2": {
                "id": "g2",
                "title": "Launch new feature",
                "status": "completed",
                "created_at": "2026-09-05T08:00:00Z",
                "updated_at": "2026-09-15T08:00:00Z",
            }
        }
        fixed_now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        ics_text_out = generate_ics(goals, component_format="todo", now_dt=fixed_now)

        self.assertIn("BEGIN:VCALENDAR", ics_text_out)
        self.assertIn("PRODID:-//omi-cli examples//goals_to_ics//EN", ics_text_out)
        self.assertIn("X-WR-CALNAME:Omi Goals", ics_text_out)

        # Active goal assertions
        self.assertIn("UID:goal-g1@omi", ics_text_out)
        self.assertIn("SUMMARY:Complete Python 3.12 course", ics_text_out)
        self.assertIn("STATUS:NEEDS-ACTION", ics_text_out)
        self.assertIn("PERCENT-COMPLETE:75", ics_text_out)
        self.assertIn("DUE:20261001T120000Z", ics_text_out)
        self.assertIn("BEGIN:VALARM", ics_text_out)

        # Completed goal assertions
        self.assertIn("UID:goal-g2@omi", ics_text_out)
        self.assertIn("STATUS:COMPLETED", ics_text_out)
        self.assertIn("PERCENT-COMPLETE:100", ics_text_out)
        self.assertIn("COMPLETED:20260915T080000Z", ics_text_out)
        self.assertIn("END:VCALENDAR", ics_text_out)

    def test_generate_ics_vevent(self):
        goals = {
            "g1": {
                "id": "g1",
                "title": "Marathon",
                "status": "active",
                "target_date": "2026-11-15T08:00:00Z",
            }
        }
        ics_text_out = generate_ics(goals, component_format="event")
        self.assertIn("BEGIN:VEVENT", ics_text_out)
        self.assertIn("UID:goal-event-g1@omi", ics_text_out)
        self.assertIn("DTSTART:20261115T080000Z", ics_text_out)
        self.assertIn("END:VEVENT", ics_text_out)
        self.assertNotIn("BEGIN:VTODO", ics_text_out)

    def test_load_and_deduplicate(self):
        d1 = [{"id": "g1", "title": "Goal 1", "status": "active"}]
        d2 = [{"id": "g1", "title": "Goal 1 Updated", "status": "completed"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "p1.json"
            p2 = Path(tmpdir) / "p2.json"
            p1.write_text(json.dumps(d1), encoding="utf-8")
            p2.write_text(json.dumps(d2), encoding="utf-8")

            res = load([str(p1), str(p2)])
            self.assertEqual(len(res), 1)
            self.assertEqual(res["g1"]["title"], "Goal 1 Updated")
            self.assertEqual(res["g1"]["status"], "completed")

    def test_load_stdin(self):
        d = [{"id": "g_stdin", "title": "Stdin goal"}]
        with patch("sys.stdin", io.StringIO(json.dumps(d))):
            res = load(["-"])
            self.assertEqual(len(res), 1)
            self.assertEqual(res["g_stdin"]["title"], "Stdin goal")

    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                load([str(Path(tmpdir) / "missing.json")])

            bad_p = Path(tmpdir) / "bad.json"
            bad_p.write_text("{corrupt", encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(bad_p)])

            noid_p = Path(tmpdir) / "no_id.json"
            noid_p.write_text('[{"title": "No ID"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(noid_p)])

    def test_convert_file_overwrite_protection(self):
        sample = [{"id": "g1", "title": "Test"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            dst = Path(tmpdir) / "goals.ics"
            src.write_text(json.dumps(sample), encoding="utf-8")
            dst.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                convert([str(src)], str(dst), force=False)

            convert([str(src)], str(dst), force=True)
            self.assertTrue(dst.read_bytes().startswith(b"BEGIN:VCALENDAR"))


if __name__ == "__main__":
    unittest.main()
