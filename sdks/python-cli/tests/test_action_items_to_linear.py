from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta

# Load action_items_to_linear example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_linear.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "action_items_to_linear.py"

spec = importlib.util.spec_from_file_location("action_items_to_linear", script_path)
a2l = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2l)

clean_text = a2l.clean_text
spreadsheet_text = a2l.spreadsheet_text
parse_time = a2l.parse_time
parse_offset = a2l.parse_offset
load_action_items = a2l.load_action_items
format_linear_row = a2l.format_linear_row
convert = a2l.convert


class TestActionItemsToLinear(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  update   docs  "), "update docs")
        self.assertEqual(clean_text(None), "")

    def test_spreadsheet_text_neutralization(self):
        # Neutralizes formula prefixes =, +, -, @
        self.assertEqual(spreadsheet_text("=SUM(A1:A10)"), "'=SUM(A1:A10)")
        self.assertEqual(spreadsheet_text("+12345"), "'+12345")
        self.assertEqual(spreadsheet_text("-calc"), "'-calc")
        self.assertEqual(spreadsheet_text("@danger"), "'@danger")
        self.assertEqual(spreadsheet_text("Regular task"), "Regular task")

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+07:00"), timedelta(hours=7))
        self.assertEqual(parse_offset("-04:00"), timedelta(hours=-4))
        with self.assertRaises(ValueError):
            parse_offset("invalid")

    def test_format_linear_row(self):
        raw = {
            "id": "act-123",
            "description": "=SUM(1, 2) meeting minutes",
            "completed": False,
            "due_at": "2026-09-30T17:00:00Z",
            "created_at": "2026-09-27T10:00:00Z",
            "conversation_id": "conv-999"
        }
        row = format_linear_row(raw, offset=timedelta(hours=7), extra_labels=["sprint-1"])
        self.assertEqual(row["Title"], "'=SUM(1, 2) meeting minutes")
        self.assertEqual(row["Status"], "Todo")
        self.assertEqual(row["Due Date"], "2026-10-01")  # +7h moves 17:00 to 00:00 next day
        self.assertIn("omi", row["Labels"])
        self.assertIn("sprint-1", row["Labels"])
        self.assertIn("conv-999", row["Description"])

    def test_load_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "f1.json"
            f2 = Path(tmpdir) / "f2.json"
            f1.write_text(json.dumps([
                {"id": "task-1", "description": "Draft proposal", "completed": False}
            ]))
            f2.write_text(json.dumps([
                {"id": "task-1", "description": "Draft proposal (v2)", "completed": True},
                {"id": "task-2", "description": "Deploy cluster", "completed": False}
            ]))
            items = load_action_items([str(f1), str(f2)])
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["description"], "Draft proposal (v2)")

    def test_convert_filter_and_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            out = Path(tmpdir) / "linear.csv"
            src.write_text(json.dumps([
                {"id": "t1", "description": "Task 1", "completed": True},
                {"id": "t2", "description": "Task 2", "completed": False}
            ]))

            # Filter for todo items
            cnt = convert([str(src)], str(out), status_filter="todo")
            self.assertEqual(cnt, 1)
            self.assertTrue(out.exists())

            # Read back CSV
            with out.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["Title"], "Task 2")
                self.assertEqual(rows[0]["Status"], "Todo")

            # Protection against overwrite
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(out))


if __name__ == '__main__':
    unittest.main()
