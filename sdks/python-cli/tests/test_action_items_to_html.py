import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from action_items_to_html import (
    clean_text,
    parse_time,
    parse_offset,
    load_action_items,
    build_report_html,
    convert
)

class TestActionItemsToHtml(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  hello   world  "), "hello world")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text(123), "123")

    def test_parse_time(self):
        dt = parse_time("2026-09-26T12:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.tzinfo, timezone.utc)

        self.assertIsNone(parse_time(None))
        self.assertIsNone(parse_time(""))
        self.assertIsNone(parse_time("invalid-timestamp"))

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+07:00"), timedelta(hours=7))
        self.assertEqual(parse_offset("-05:00"), timedelta(hours=-5))
        with self.assertRaises(ValueError):
            parse_offset("invalid")
        with self.assertRaises(ValueError):
            parse_offset("+20:00")

    def test_load_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "f1.json"
            file2 = Path(tmpdir) / "f2.json"
            
            data1 = [
                {"id": "task-1", "description": "Buy groceries", "completed": False, "created_at": "2026-09-26T10:00:00Z"},
                {"id": "task-2", "description": "Review PR", "completed": True, "created_at": "2026-09-26T11:00:00Z"}
            ]
            data2 = [
                # Duplicate task-1
                {"id": "task-1", "description": "Buy groceries (updated)", "completed": True, "created_at": "2026-09-26T10:00:00Z"},
                {"id": "task-3", "description": "Deploy release", "completed": False, "created_at": "2026-09-26T12:00:00Z"}
            ]
            file1.write_text(json.dumps(data1))
            file2.write_text(json.dumps(data2))

            items = load_action_items([str(file1), str(file2)])
            self.assertEqual(len(items), 3)
            ids = [it["id"] for it in items]
            self.assertEqual(ids, ["task-1", "task-2", "task-3"])
            # task-1 was updated from file2
            self.assertEqual(items[0]["description"], "Buy groceries (updated)")

    def test_xss_escaping_and_stats(self):
        sample = [
            {"id": "xss-1", "description": "<script>alert('xss')</script>", "completed": False, "created_at": "2026-09-26T10:00:00Z"},
            {"id": "task-clean", "description": "Rock & Roll", "completed": True, "created_at": "2026-09-26T11:00:00Z"}
        ]
        html_content = build_report_html(sample, timedelta(0), "", title="Test & Verify")
        # Ensure raw dangerous script is escaped
        self.assertNotIn("<script>alert('xss')</script>", html_content)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", html_content)
        self.assertIn("Rock &amp; Roll", html_content)
        self.assertIn("Test &amp; Verify", html_content)
        # Stats checks
        self.assertIn("Total Tasks", html_content)
        self.assertIn("50.0%", html_content)  # 1 of 2 completed = 50%

    def test_convert_exclusive_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            dest = Path(tmpdir) / "report.html"
            src.write_text(json.dumps([{"id": "t1", "description": "Test task", "completed": True}]))
            
            convert([str(src)], str(dest), timedelta(0), "")
            self.assertTrue(dest.exists())
            
            # Second attempt must fail with FileExistsError
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(dest), timedelta(0), "")

if __name__ == '__main__':
    unittest.main()
