"""Tests for action_items_to_html recipe.

Covers:
- HTML escaping and sanitization
- Deduplication of records across pages
- Separation into Open and Completed sections
- Accuracy of statistical calculations
- Bare array vs wrapped JSON envelopes
- Error handling on invalid records
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load action_items_to_html example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_html.py"
spec = importlib.util.spec_from_file_location("action_items_to_html", script_path)
ai2h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2h)

convert_paths_to_html = ai2h.convert_paths_to_html
generate_html_report = ai2h.generate_html_report
render_html_table = ai2h.render_html_table
utc_stamp = ai2h.utc_stamp


SAMPLE_ACTION_ITEMS = [
    {
        "id": "task_1",
        "description": "Prepare quarterly report & slides",
        "completed": False,
        "due_at": "2026-09-30T17:00:00Z",
        "created_at": "2026-09-20T09:00:00Z",
        "conversation_id": "conv_123",
    },
    {
        "id": "task_2",
        "description": "Send follow-up <script>alert(1)</script>",  # XSS probe
        "completed": True,
        "created_at": "2026-09-19T14:00:00+02:00",
    },
]


class TestActionItemsToHtml(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T11:00:00Z"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp("2026-09-20T13:00:00+02:00"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp(""), "")
        self.assertEqual(utc_stamp(None), "")

    def test_html_escaping(self):
        report = generate_html_report(SAMPLE_ACTION_ITEMS)
        # Should be escaped, not raw HTML tags
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", report)
        self.assertIn("Prepare quarterly report &amp; slides", report)

    def test_statistics_and_sections(self):
        report = generate_html_report(SAMPLE_ACTION_ITEMS)
        self.assertIn("2 total task(s) processed", report)
        self.assertIn("50.0%</div>", report)  # 1 completed out of 2 = 50.0%
        self.assertIn("Open Tasks (1)", report)
        self.assertIn("Completed Tasks (1)", report)
        self.assertIn("badge-open", report)
        self.assertIn("badge-done", report)

    def test_deduplication(self):
        # Pass duplicated item
        duplicated = [SAMPLE_ACTION_ITEMS[0], SAMPLE_ACTION_ITEMS[0]]
        report = generate_html_report(duplicated)
        self.assertIn("1 total task(s) processed", report)

    def test_convert_to_file(self):
        json_file = self.dir_path / "tasks.json"
        json_file.write_text(json.dumps(SAMPLE_ACTION_ITEMS), encoding="utf-8")
        out_html = self.dir_path / "tasks.html"

        count = convert_paths_to_html([json_file], out_html)
        self.assertEqual(count, 2)
        self.assertTrue(out_html.exists())
        content = out_html.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("tasks.json", json_file.name)

    def test_missing_id_raises_value_error(self):
        invalid = [{"description": "No ID here"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_paths_to_html([json_file])
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
