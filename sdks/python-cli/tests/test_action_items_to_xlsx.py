"""Tests for action items to Excel (.xlsx) converter.

Pins workbook sheet title, frozen pane, AutoFilter range, datetime cell typing,
explicit string cell types, and atomic save resilience.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import openpyxl

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_xlsx.py"
spec = importlib.util.spec_from_file_location("action_items_to_xlsx", script_path)
a2x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2x)


class TestActionItemsToXlsx(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "act_001",
                "description": "Send follow-up email to stakeholders",
                "completed": False,
                "due_at": "2026-09-25T09:00:00Z",
                "created_at": "2026-09-18T10:00:00Z",
                "updated_at": "2026-09-18T10:30:00Z",
                "conversation_id": "conv_abc_123",
            },
            {
                "id": "act_002",
                "description": "=1+1 formula test",
                "completed": True,
                "due_at": None,
                "created_at": "2026-09-19T14:15:00Z",
                "updated_at": "2026-09-19T15:00:00Z",
                "conversation_id": "conv_def_456",
            },
        ]

    def test_xlsx_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            xlsx_file = Path(tmpdir) / "output.xlsx"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            a2x.convert(json_file, xlsx_file)
            self.assertTrue(xlsx_file.is_file())

            wb = openpyxl.load_workbook(xlsx_file)
            self.assertEqual(wb.sheetnames, ["action_items"])
            ws = wb["action_items"]

            # Header verification — due_at is col D, created_at is col E
            self.assertEqual(ws["A1"].value, "id")
            self.assertEqual(ws["D1"].value, "due_at (UTC)")
            self.assertEqual(ws["E1"].value, "created_at (UTC)")
            self.assertEqual(ws.freeze_panes, "A2")
            self.assertIsNotNone(ws.auto_filter.ref)

            # Row 2 verification (act_001)
            self.assertEqual(ws["A2"].value, "act_001")
            self.assertEqual(ws["C2"].value, "No")

            # due_at stored as datetime cell
            from datetime import datetime
            self.assertIsInstance(ws["D2"].value, datetime)

            # Row 3 verification (act_002, formula safety)
            self.assertEqual(ws["A3"].value, "act_002")
            self.assertEqual(ws["B3"].value, "=1+1 formula test")
            self.assertEqual(ws["B3"].data_type, "s")
            self.assertEqual(ws["C3"].value, "Yes")
            # due_at=None → None cell
            self.assertIsNone(ws["D3"].value)


    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            xlsx_file = Path(tmpdir) / "output.xlsx"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            xlsx_file.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                a2x.convert(json_file, xlsx_file)


if __name__ == "__main__":
    unittest.main()
