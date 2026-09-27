import csv
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from action_items_to_linear import (
    clean_text,
    parse_time,
    parse_offset,
    load_action_items,
    format_linear_row,
    convert
)

class TestActionItemsToLinear(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  update   docs  "), "update docs")
        self.assertEqual(clean_text(None), "")

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+07:00"), timedelta(hours=7))
        self.assertEqual(parse_offset("-04:00"), timedelta(hours=-4))
        with self.assertRaises(ValueError):
            parse_offset("invalid")

    def test_format_linear_row(self):
        raw = {
            "id": "act-123",
            "description": "Send meeting minutes to team",
            "completed": False,
            "due_at": "2026-09-30T17:00:00Z",
            "created_at": "2026-09-27T10:00:00Z",
            "conversation_id": "conv-999"
        }
        row = format_linear_row(raw, offset=timedelta(hours=7), extra_labels=["sprint-1"])
        self.assertEqual(row["Title"], "Send meeting minutes to team")
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
                {"id": "1", "description": "Task 1", "completed": False},
                {"id": "2", "description": "Task 2", "completed": True}
            ]))

            # Filter pending only
            cnt = convert([str(src)], str(out), status_filter="pending")
            self.assertEqual(cnt, 1)
            self.assertTrue(out.exists())

            with open(out, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["Title"], "Task 1")
                self.assertEqual(rows[0]["Status"], "Todo")

            # Protection against overwrite
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(out))

if __name__ == '__main__':
    unittest.main()
