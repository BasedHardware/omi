"""Tests for action items to self-contained HTML checklist report converter.

Pins open/completed grouping, overdue highlighting, HTML-escaping of
untrusted description text, and atomic-write / overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_html.py"
spec = importlib.util.spec_from_file_location("action_items_to_html", script_path)
a2h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2h)


class TestActionItemsToHtml(unittest.TestCase):
    def setUp(self):
        past = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        future = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.sample_items = [
            {"id": "a1", "description": "Overdue task", "completed": False, "due_at": past},
            {"id": "a2", "description": "Future task", "completed": False, "due_at": future},
            {"id": "a3", "description": "Finished task", "completed": True, "due_at": past},
        ]

    def test_conversion_and_grouping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            a2h.convert(json_file, html_file, title="My Tasks")
            content = html_file.read_text(encoding="utf-8")

            self.assertIn("<title>My Tasks</title>", content)
            self.assertIn("<h2>Open</h2>", content)
            self.assertIn("<h2>Completed</h2>", content)
            self.assertIn("Overdue task", content)
            self.assertIn('class="due overdue"', content)
            self.assertIn('class="done"', content)

    def test_html_escaping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            unsafe = [{"id": "a1", "description": '<script>alert(1)</script> & "quotes"', "completed": False}]
            json_file.write_text(json.dumps(unsafe), encoding="utf-8")

            a2h.convert(json_file, html_file)
            content = html_file.read_text(encoding="utf-8")

            self.assertNotIn("<script>alert(1)</script>", content)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)

    def test_completed_item_not_marked_overdue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            a2h.convert(json_file, html_file)
            content = html_file.read_text(encoding="utf-8")
            # "Finished task" is completed and overdue, but must not get the overdue style.
            finished_line = [line for line in content.splitlines() if "Finished task" in line][0]
            self.assertNotIn("overdue", finished_line)

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text("[]", encoding="utf-8")

            a2h.convert(json_file, html_file)
            self.assertIn("No action items found", html_file.read_text(encoding="utf-8"))

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps({"action_items": self.sample_items}), encoding="utf-8")

            a2h.convert(json_file, html_file)
            self.assertTrue(html_file.is_file())

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(["nope"]), encoding="utf-8")

            with self.assertRaises(ValueError):
                a2h.convert(json_file, html_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            html_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                a2h.convert(json_file, html_file)


if __name__ == "__main__":
    unittest.main()
