"""Tests for action items to HTML exporter.

Pins HTML structure, stats grid, status badges, overdue calculation,
escaping against XSS, timezone offset handling, envelope unwrapping,
idempotent deduplication, and overwrite protection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_html.py"
spec = importlib.util.spec_from_file_location("action_items_to_html", script_path)
ai2html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2html)


class TestActionItemsToHtml(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fixed_now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        self.sample_items = [
            {
                "id": "act_01_overdue",
                "description": "Submit quarterly tax review <urgent> & file",
                "completed": False,
                "due_at": "2026-10-01T15:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "conversation_id": "conv_101",
            },
            {
                "id": "act_02_upcoming",
                "description": "Prepare release notes for v0.4.0",
                "completed": False,
                "due_at": "2026-10-05T18:00:00Z",
                "created_at": "2026-09-25T08:00:00Z",
                "conversation_id": "conv_102",
            },
            {
                "id": "act_03_undated",
                "description": "Organize repository documentation tags",
                "completed": False,
                "due_at": None,
                "created_at": "2026-09-26T09:00:00Z",
                "conversation_id": None,
            },
            {
                "id": "act_04_completed",
                "description": "Fix bug in audio stream decoding",
                "completed": True,
                "due_at": "2026-09-30T12:00:00Z",
                "created_at": "2026-09-18T14:00:00Z",
                "conversation_id": "conv_104",
            },
        ]

    def tearDown(self):
        self._tmp.cleanup()

    def test_report_structure_and_stats(self):
        items_dict = {it["id"]: it for it in self.sample_items}
        html_out = ai2html.report(
            items_dict,
            timedelta(0),
            "",
            title="Sprint Checklist",
            now=self.fixed_now,
        )
        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("<title>Sprint Checklist</title>", html_out)
        self.assertIn("<h1>Sprint Checklist</h1>", html_out)
        self.assertIn("Total: 4 · Open: 3 · Completed: 1 · Overdue: 1", html_out)
        self.assertIn('<div class="stat-card"><div class="num">4</div><div class="lbl">Total</div></div>', html_out)
        self.assertIn('<div class="stat-card"><div class="num" style="color:var(--badge-open-text);">3</div><div class="lbl">Open</div></div>', html_out)
        self.assertIn('<div class="stat-card"><div class="num" style="color:var(--badge-done-text);">1</div><div class="lbl">Completed</div></div>', html_out)
        self.assertIn('<div class="stat-card"><div class="num" style="color:var(--badge-overdue-text);">1</div><div class="lbl">Overdue</div></div>', html_out)

    def test_escaping_against_xss(self):
        malicious = {
            "xss": {
                "id": "evil_id",
                "description": "<script>alert('xss')</script> & 'quotes'",
                "completed": False,
                "due_at": None,
                "conversation_id": "<script>",
            }
        }
        html_out = ai2html.report(malicious, timedelta(0), "")
        self.assertNotIn("<script>", html_out)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt; &amp; &#x27;quotes&#x27;", html_out)
        self.assertIn("&lt;script&gt;", html_out)

    def test_badges_and_sections(self):
        items_dict = {it["id"]: it for it in self.sample_items}
        html_out = ai2html.report(items_dict, timedelta(0), "", now=self.fixed_now)
        self.assertIn("badge-overdue", html_out)
        self.assertIn("badge-open", html_out)
        self.assertIn("badge-done", html_out)
        self.assertIn("Overdue Items", html_out)
        self.assertIn("Open Tasks (Scheduled)", html_out)
        self.assertIn("Open Tasks (Undated)", html_out)
        self.assertIn("Completed Tasks", html_out)

    def test_timezone_offset(self):
        items_dict = {
            "item_tz": {
                "id": "item_tz",
                "description": "Meeting",
                "completed": False,
                "due_at": "2026-10-01T23:30:00Z",
                "created_at": "2026-10-01T15:00:00Z",
            }
        }
        jst_offset = timedelta(hours=9)
        html_out = ai2html.report(items_dict, jst_offset, "+09:00", now=self.fixed_now)
        self.assertIn("2026-10-02 08:30", html_out)
        self.assertIn("Times shown in UTC+09:00.", html_out)

    def test_parse_offset_validation(self):
        self.assertEqual(ai2html.parse_offset("+09:00"), timedelta(hours=9))
        self.assertEqual(ai2html.parse_offset("-05:30"), timedelta(hours=-5, minutes=-30))
        with self.assertRaises(ValueError):
            ai2html.parse_offset("invalid")
        with self.assertRaises(ValueError):
            ai2html.parse_offset("+15:00")
        with self.assertRaises(ValueError):
            ai2html.parse_offset("+05:70")

    def test_envelope_unwrapping(self):
        raw_nested = {"action_items": self.sample_items}
        unwrapped = ai2html.unwrap_items(raw_nested)
        self.assertEqual(len(unwrapped), 4)

        raw_items_key = {"items": self.sample_items}
        self.assertEqual(len(ai2html.unwrap_items(raw_items_key)), 4)

        single = {"id": "single", "description": "solo"}
        self.assertEqual(len(ai2html.unwrap_items(single)), 1)

    def test_load_and_deduplication(self):
        f1 = self.tmp / "f1.json"
        f2 = self.tmp / "f2.json"
        f1.write_text(json.dumps([self.sample_items[0]]), encoding="utf-8")
        f2.write_text(json.dumps([self.sample_items[0], self.sample_items[1]]), encoding="utf-8")

        loaded = ai2html.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 2)
        self.assertIn("act_01_overdue", loaded)
        self.assertIn("act_02_upcoming", loaded)

    def test_completed_coercion(self):
        self.assertTrue(ai2html.is_completed({"completed": True}))
        self.assertTrue(ai2html.is_completed({"completed": 1}))
        self.assertTrue(ai2html.is_completed({"completed": "yes"}))
        self.assertTrue(ai2html.is_completed({"completed": "DONE"}))
        self.assertFalse(ai2html.is_completed({"completed": False}))
        self.assertFalse(ai2html.is_completed({"completed": 0}))
        self.assertFalse(ai2html.is_completed({"completed": "no"}))
        self.assertFalse(ai2html.is_completed({}))

    def test_empty_export(self):
        html_out = ai2html.report({}, timedelta(0), "")
        self.assertIn("No action items in the export.", html_out)

    def test_convert_file_creation_and_overwrite(self):
        source = self.tmp / "input.json"
        source.write_text(json.dumps(self.sample_items), encoding="utf-8")
        dest = self.tmp / "output.html"

        count = ai2html.convert([str(source)], str(dest), timedelta(0), "")
        self.assertEqual(count, 4)
        self.assertTrue(dest.exists())

        # Second call without overwrite must raise FileExistsError
        with self.assertRaises(FileExistsError):
            ai2html.convert([str(source)], str(dest), timedelta(0), "", overwrite=False)

        # With overwrite=True it should succeed
        count2 = ai2html.convert([str(source)], str(dest), timedelta(0), "", overwrite=True)
        self.assertEqual(count2, 4)

    def test_main_cli_execution(self):
        source = self.tmp / "tasks.json"
        dest = self.tmp / "cli_out.html"
        source.write_text(json.dumps(self.sample_items), encoding="utf-8")

        ret = ai2html.main([str(dest), str(source), "--title", "CLI Test"])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        content = dest.read_text(encoding="utf-8")
        self.assertIn("CLI Test", content)


if __name__ == "__main__":
    unittest.main()
