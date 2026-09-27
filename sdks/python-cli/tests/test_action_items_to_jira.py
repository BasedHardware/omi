import csv
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from action_items_to_jira import (
    clean_text,
    parse_time,
    parse_offset,
    load_action_items,
    format_jira_row,
    convert
)

class TestActionItemsToJira(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  prepare   sprint   demo  "), "prepare sprint demo")
        self.assertEqual(clean_text(None), "")

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+05:30"), timedelta(hours=5, minutes=30))
        self.assertEqual(parse_offset("-08:00"), timedelta(hours=-8))
        with self.assertRaises(ValueError):
            parse_offset("invalid")

    def test_format_jira_row(self):
        raw = {
            "id": "act-555",
            "description": "Fix memory leak in websocket listener",
            "completed": False,
            "due_at": "2026-10-05T12:00:00Z",
            "created_at": "2026-09-27T08:00:00Z",
            "conversation_id": "conv-888"
        }
        row = format_jira_row(raw, offset=timedelta(0), default_priority="High", extra_labels=["backend bug"])
        self.assertEqual(row["Summary"], "Fix memory leak in websocket listener")
        self.assertEqual(row["Status"], "To Do")
        self.assertEqual(row["Issue Type"], "Task")
        self.assertEqual(row["Priority"], "High")
        self.assertEqual(row["Due Date"], "2026-10-05")
        self.assertIn("omi", row["Labels"])
        self.assertIn("backend-bug", row["Labels"])
        self.assertIn("act-555", row["Description"])

    def test_load_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "f1.json"
            f2 = Path(tmpdir) / "f2.json"
            f1.write_text(json.dumps([
                {"id": "item-1", "description": "Prepare release notes", "completed": False}
            ]))
            f2.write_text(json.dumps([
                {"id": "item-1", "description": "Prepare release notes (final)", "completed": True},
                {"id": "item-2", "description": "Tag v1.0", "completed": False}
            ]))
            items = load_action_items([str(f1), str(f2)])
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["description"], "Prepare release notes (final)")

    def test_convert_filter_and_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            out = Path(tmpdir) / "jira.csv"
            src.write_text(json.dumps([
                {"id": "1", "description": "Bug 1", "completed": False},
                {"id": "2", "description": "Bug 2", "completed": True}
            ]))

            # Filter completed only
            cnt = convert([str(src)], str(out), status_filter="completed")
            self.assertEqual(cnt, 1)
            self.assertTrue(out.exists())

            with open(out, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["Summary"], "Bug 2")
                self.assertEqual(rows[0]["Status"], "Done")

            # Protection against overwrite
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(out))

if __name__ == '__main__':
    unittest.main()
