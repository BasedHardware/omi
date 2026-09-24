"""Tests for action items to HTML exporter.

Pins HTML escaping (XSS prevention), status separation, timestamp
formatting, multi-page deduplication, and document structure.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

# Add examples and tests directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_html import format_iso, load_action_items, render_html_report


class TestActionItemsToHtml(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "task_1",
                "description": "Send wire transfer <script>alert(1)</script>",
                "completed": False,
                "due_at": "2026-09-25T14:00:00Z",
                "created_at": "2026-09-24T08:00:00Z",
                "conversation_id": "conv_99",
            },
            {
                "id": "task_2",
                "description": "Review smart contract audits & fees",
                "completed": True,
                "due_at": None,
                "created_at": "2026-09-24T09:00:00Z",
                "conversation_id": "conv_100",
            },
            {
                "id": "task_3",
                "description": "Prepare quarterly financial statement",
                "completed": False,
                "due_at": "2026-09-30T18:00:00Z",
                "created_at": "2026-09-24T10:00:00Z",
                "conversation_id": "conv_101",
            },
        ]

    def test_format_iso(self):
        self.assertEqual(format_iso("2026-09-24T10:30:00Z"), "2026-09-24 10:30 UTC")
        self.assertEqual(format_iso("2026-09-24T12:30:00+02:00"), "2026-09-24 10:30 UTC")
        self.assertEqual(format_iso(None), "—")
        self.assertEqual(format_iso(""), "—")
        self.assertEqual(format_iso("not-a-date"), "not-a-date")

    def test_html_escaping(self):
        """Dynamic user input must be HTML escaped to prevent XSS."""
        html = render_html_report(self.sample_items)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("Review smart contract audits &amp; fees", html)

    def test_status_separation_and_stats(self):
        """Pending and completed tasks are rendered into separate sections with correct stats."""
        html = render_html_report(self.sample_items)

        # Check stats
        self.assertIn("3 total action item(s)", html)
        self.assertIn('<div class="stat-value" style="color: #d97706;">2</div>', html)  # 2 pending
        self.assertIn('<div class="stat-value" style="color: #059669;">1</div>', html)  # 1 completed
        self.assertIn('<div class="stat-value">33%</div>', html)  # 1/3 = 33%

        # Check section headings
        self.assertIn("Pending Action Items (2)", html)
        self.assertIn("Completed Action Items (1)", html)

        # Completed description has line-through class
        self.assertIn('<span class="completed-desc">Review smart contract audits &amp; fees</span>', html)

    def test_load_and_deduplication(self):
        """Loading from multiple pages deduplicates tasks with identical IDs."""
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "page1.json"
            p2 = Path(td) / "page2.json"

            p1.write_text(json.dumps([self.sample_items[0], self.sample_items[1]]), encoding="utf-8")
            # Page 2 has updated task_1 and new task_3
            updated_task_1 = dict(self.sample_items[0], description="Updated transfer")
            p2.write_text(json.dumps([updated_task_1, self.sample_items[2]]), encoding="utf-8")

            items = load_action_items([str(p1), str(p2)])
            self.assertEqual(len(items), 3)

            by_id = {it["id"]: it for it in items}
            self.assertEqual(by_id["task_1"]["description"], "Updated transfer")

    def test_wrapped_json_and_bom(self):
        """Tolerates wrapped JSON payloads and UTF-8 BOM."""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "wrapped.json"
            data = {"action_items": [self.sample_items[0]]}
            f.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))

            items = load_action_items([str(f)])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], "task_1")

    def test_empty_action_items_wrapper(self):
        """Empty action_items array yields empty list without falling back to [data]."""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "empty.json"
            f.write_text(json.dumps({"action_items": []}), encoding="utf-8")

            items = load_action_items([str(f)])
            self.assertEqual(items, [])

    def test_error_handling(self):
        """Invalid files or items without IDs raise ValueError."""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "bad.json"
            f.write_text(json.dumps([{"description": "No id"}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_action_items([str(f)])


if __name__ == "__main__":
    unittest.main()
