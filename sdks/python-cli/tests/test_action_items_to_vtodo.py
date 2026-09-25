"""Tests for Omi action items to RFC 5545 VTODO export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_vtodo.py"
spec = importlib.util.spec_from_file_location("action_items_to_vtodo", script_path)
a2v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2v)


class TestActionItemsToVtodo(unittest.TestCase):
    def test_ical_escape(self):
        self.assertEqual(a2v.ical_escape("Hello, world; test\nline"), "Hello\\, world\\; test\\nline")
        self.assertEqual(a2v.ical_escape("Clean"), "Clean")

    def test_format_ical_dt(self):
        self.assertEqual(a2v.format_ical_dt("2026-09-24T15:30:00Z"), "20260924T153000Z")
        self.assertIsNone(a2v.format_ical_dt(None))

    def test_render_vtodo_calendar_components(self):
        items = [
            {
                "id": "act-1",
                "description": "Fix bug in production",
                "completed": False,
                "due_at": "2026-09-25T18:00:00Z",
            },
            {
                "id": "act-2",
                "description": "Submit bounty PR",
                "completed": True,
            },
        ]
        cal = a2v.render_vtodo_calendar(items)

        self.assertIn("BEGIN:VCALENDAR", cal)
        self.assertIn("BEGIN:VTODO", cal)
        self.assertIn("UID:act-1@omi.me", cal)
        self.assertIn("SUMMARY:Fix bug in production", cal)
        self.assertIn("STATUS:NEEDS-ACTION", cal)
        self.assertIn("PERCENT-COMPLETE:0", cal)
        self.assertIn("DUE:20260925T180000Z", cal)

        self.assertIn("UID:act-2@omi.me", cal)
        self.assertIn("STATUS:COMPLETED", cal)
        self.assertIn("PERCENT-COMPLETE:100", cal)
        self.assertIn("END:VCALENDAR", cal)

    def test_convert_to_vtodo_file_output(self):
        item = {"id": "act-5", "description": "Single action item"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "data.json"
            out = tmp / "tasks.ics"

            f.write_text(json.dumps([item]), encoding="utf-8")
            count = a2v.convert_to_vtodo([f], out)

            self.assertEqual(count, 1)
            content = out.read_text(encoding="utf-8")
            self.assertIn("BEGIN:VTODO", content)
            self.assertIn("Single action item", content)


if __name__ == "__main__":
    unittest.main()
