"""Tests for action items to HTML dashboard exporter.

Verifies:
- Self-contained HTML output structure and embedded CSS
- Executive statistics computation (total, open, completed, rate)
- Pending and completed task table rendering
- Filtering by status (all, open, completed)
- Both bare array and wrapped {"action_items": [...]} JSON formats
- Automatic item deduplication by ID
- XSS prevention / HTML escaping for special characters (<, >, &, ")
- Error handling on malformed input
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# Load action_items_to_html script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_html.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "action_items_to_html.py"

spec = importlib.util.spec_from_file_location("action_items_to_html", script_path)
ai2html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2html)


class TestActionItemsToHtml(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "item-001",
                "description": "Prepare Q3 roadmap presentation",
                "completed": False,
                "due_at": "2026-09-30T17:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "conversation_id": "conv-101"
            },
            {
                "id": "item-002",
                "description": "Send follow-up email to partners",
                "completed": True,
                "due_at": "2026-09-22T12:00:00Z",
                "created_at": "2026-09-19T09:30:00Z",
                "conversation_id": "conv-102"
            }
        ]

    def test_basic_rendering_and_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            dst = Path(tmpdir) / "dashboard.html"
            src.write_text(json.dumps(self.sample_items), encoding="utf-8")

            count = ai2html.convert(str(src), str(dst), title="My Work Tasks")
            self.assertEqual(count, 2)
            self.assertTrue(dst.exists())

            html = dst.read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("<title>My Work Tasks</title>", html)
            self.assertIn("Total Tasks", html)
            self.assertIn("50.0%", html)  # 1 of 2 completed
            self.assertIn("Prepare Q3 roadmap presentation", html)
            self.assertIn("Send follow-up email to partners", html)
            self.assertIn("Pending", html)
            self.assertIn("Done", html)
            self.assertIn("2026-09-30", html)

    def test_wrapped_json_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "wrapped.json"
            dst = Path(tmpdir) / "dashboard.html"
            src.write_text(json.dumps({"action_items": self.sample_items}), encoding="utf-8")

            count = ai2html.convert(str(src), str(dst))
            self.assertEqual(count, 2)
            self.assertTrue(dst.exists())

    def test_status_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            src.write_text(json.dumps(self.sample_items), encoding="utf-8")

            # Filter open only
            dst_open = Path(tmpdir) / "open.html"
            count_open = ai2html.convert(str(src), str(dst_open), status_filter="open")
            self.assertEqual(count_open, 1)
            content_open = dst_open.read_text(encoding="utf-8")
            self.assertIn("Prepare Q3 roadmap presentation", content_open)
            self.assertNotIn("Send follow-up email to partners", content_open)

            # Filter completed only
            dst_done = Path(tmpdir) / "done.html"
            count_done = ai2html.convert(str(src), str(dst_done), status_filter="completed")
            self.assertEqual(count_done, 1)
            content_done = dst_done.read_text(encoding="utf-8")
            self.assertNotIn("Prepare Q3 roadmap presentation", content_done)
            self.assertIn("Send follow-up email to partners", content_done)

    def test_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "dup.json"
            dst = Path(tmpdir) / "dashboard.html"
            # Duplicate item-001 twice
            items_with_dup = [self.sample_items[0], self.sample_items[0], self.sample_items[1]]
            src.write_text(json.dumps(items_with_dup), encoding="utf-8")

            count = ai2html.convert(str(src), str(dst))
            self.assertEqual(count, 2)

    def test_html_escaping_xss_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "xss.json"
            dst = Path(tmpdir) / "dashboard.html"
            xss_item = [{
                "id": "xss-1",
                "description": "<script>alert('xss')</script> & <b>bold</b>",
                "completed": False,
                "conversation_id": "<conv-bad>"
            }]
            src.write_text(json.dumps(xss_item), encoding="utf-8")

            count = ai2html.convert(str(src), str(dst))
            self.assertEqual(count, 1)

            html = dst.read_text(encoding="utf-8")
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", html)
            self.assertIn("&lt;conv-bad&gt;", html)

    def test_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            dst = Path(tmpdir) / "dashboard.html"
            src.write_text(json.dumps(self.sample_items), encoding="utf-8")
            dst.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                ai2html.convert(str(src), str(dst), overwrite=False)

    def test_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.json"
            dst = Path(tmpdir) / "dashboard.html"
            bad.write_text(json.dumps("string not array"), encoding="utf-8")

            with self.assertRaises(ValueError):
                ai2html.convert(str(bad), str(dst))


if __name__ == "__main__":
    unittest.main()
