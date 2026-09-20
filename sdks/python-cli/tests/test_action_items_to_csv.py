"""Unit tests for action_items_to_csv recipe."""

from __future__ import annotations

import csv
import importlib.util
import io
from pathlib import Path
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_csv.py"
spec = importlib.util.spec_from_file_location("action_items_to_csv", script_path)
a2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2c)


class TestActionItemsToCSV(unittest.TestCase):
    def test_basic_conversion(self):
        items = [
            {
                "id": "item-1",
                "completed": False,
                "description": "Buy groceries",
                "due_at": "2026-09-25T15:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-20T10:00:00Z",
                "conversation_id": "conv-123",
            },
            {
                "id": "item-2",
                "completed": True,
                "description": "Submit quarterly report",
                "due_at": None,
                "created_at": "2026-09-18T09:00:00Z",
                "updated_at": "2026-09-19T14:00:00Z",
                "conversation_id": None,
            },
        ]

        csv_str = a2c.action_items_to_csv(items)
        reader = list(csv.reader(io.StringIO(csv_str)))

        self.assertEqual(reader[0], list(a2c.FIELDS))
        self.assertEqual(len(reader), 3)

        # First item checks
        row1 = reader[1]
        self.assertEqual(row1[0], "item-1")
        self.assertEqual(row1[1], "false")
        self.assertEqual(row1[2], "Buy groceries")
        self.assertEqual(row1[3], "2026-09-25 15:00:00")
        self.assertEqual(row1[6], "conv-123")

        # Second item checks
        row2 = reader[2]
        self.assertEqual(row2[0], "item-2")
        self.assertEqual(row2[1], "true")
        self.assertEqual(row2[3], "")

    def test_formula_injection_escaping(self):
        dangerous_items = [
            {"id": "=1+2", "description": "=cmd|' /C calc'!A0", "completed": False},
            {"id": "safe-id", "description": "+123456789", "completed": False},
            {"id": "@dangerous", "description": "-100", "completed": False},
        ]

        csv_str = a2c.action_items_to_csv(dangerous_items)
        reader = list(csv.reader(io.StringIO(csv_str)))

        # Verify all formula prefixes were escaped with apostrophe
        self.assertTrue(reader[1][0].startswith("'="))
        self.assertTrue(reader[1][2].startswith("'="))
        self.assertTrue(reader[2][2].startswith("'+"))
        self.assertTrue(reader[3][0].startswith("'@"))
        self.assertTrue(reader[3][2].startswith("'-"))

    def test_filter_open_and_completed(self):
        items = [
            {"id": "1", "completed": False, "description": "Open task"},
            {"id": "2", "completed": True, "description": "Completed task"},
        ]

        open_csv = a2c.action_items_to_csv(items, status_filter="open")
        open_rows = list(csv.reader(io.StringIO(open_csv)))
        self.assertEqual(len(open_rows), 2)
        self.assertEqual(open_rows[1][2], "Open task")

        comp_csv = a2c.action_items_to_csv(items, status_filter="completed")
        comp_rows = list(csv.reader(io.StringIO(comp_csv)))
        self.assertEqual(len(comp_rows), 2)
        self.assertEqual(comp_rows[1][2], "Completed task")

    def test_unicode_and_special_characters(self):
        items = [
            {
                "id": "es-1",
                "completed": False,
                "description": "Comprar plátanos y café 🍌☕ (revisión)",
            }
        ]
        csv_str = a2c.action_items_to_csv(items)
        reader = list(csv.reader(io.StringIO(csv_str)))
        self.assertEqual(reader[1][2], "Comprar plátanos y café 🍌☕ (revisión)")


if __name__ == "__main__":
    unittest.main()
