from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta

# Load action_items_to_jira example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_jira.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "action_items_to_jira.py"

spec = importlib.util.spec_from_file_location("action_items_to_jira", script_path)
a2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2j)

clean_text = a2j.clean_text
spreadsheet_text = a2j.spreadsheet_text
parse_time = a2j.parse_time
parse_offset = a2j.parse_offset
load_action_items = a2j.load_action_items
format_jira_row = a2j.format_jira_row
convert = a2j.convert


class TestActionItemsToJira(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  prepare   sprint   demo  "), "prepare sprint demo")
        self.assertEqual(clean_text(None), "")

    def test_spreadsheet_text_neutralization(self):
        self.assertEqual(spreadsheet_text("=CMD('calc')"), "'=CMD('calc')")
        self.assertEqual(spreadsheet_text("+999"), "'+999")
        self.assertEqual(spreadsheet_text("-sub"), "'-sub")
        self.assertEqual(spreadsheet_text("@user"), "'@user")
        self.assertEqual(spreadsheet_text("Safe Jira Task"), "Safe Jira Task")

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+05:30"), timedelta(hours=5, minutes=30))
        self.assertEqual(parse_offset("-08:00"), timedelta(hours=-8))
        with self.assertRaises(ValueError):
            parse_offset("invalid")

    def test_format_jira_row(self):
        raw = {
            "id": "act-555",
            "description": "=SUM(A1) Fix memory leak in websocket listener",
            "completed": False,
            "due_at": "2026-10-05T12:00:00Z",
            "created_at": "2026-09-27T08:00:00Z",
            "conversation_id": "conv-888"
        }
        row = format_jira_row(raw, offset=timedelta(0), default_priority="High", extra_labels=["backend bug"])
        self.assertEqual(row["Summary"], "'=SUM(A1) Fix memory leak in websocket listener")
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
                {"id": "j1", "description": "Story 1", "completed": True},
                {"id": "j2", "description": "Story 2", "completed": False}
            ]))

            # Filter for done items
            cnt = convert([str(src)], str(out), status_filter="done")
            self.assertEqual(cnt, 1)
            self.assertTrue(out.exists())

            with out.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["Summary"], "Story 1")
                self.assertEqual(rows[0]["Status"], "Done")

            # Overwrite protection
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(out))


if __name__ == '__main__':
    unittest.main()
