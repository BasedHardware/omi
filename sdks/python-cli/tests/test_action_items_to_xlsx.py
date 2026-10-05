from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Guard import in case openpyxl is not present in minimal environments
try:
    import pytest
    pytest.importorskip("openpyxl")
except ImportError:
    pass

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

# Load action_items_to_xlsx example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_xlsx.py"
spec = importlib.util.spec_from_file_location("action_items_to_xlsx", script_path)
ai2x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2x)


class TestActionItemsToXlsx(unittest.TestCase):
    def setUp(self):
        if load_workbook is None:
            self.skipTest("openpyxl is not installed")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.output_xlsx = self.dir_path / "test_tasks.xlsx"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cell_text(self):
        self.assertEqual(ai2x.cell_text("Follow up with client"), "Follow up with client")
        self.assertEqual(ai2x.cell_text(None), None)
        self.assertEqual(ai2x.cell_text({"tag": "urgent"}), '{"tag": "urgent"}')
        self.assertEqual(ai2x.cell_text(42), "42")

    def test_cell_datetime(self):
        dt = ai2x.cell_datetime("2026-10-04T15:30:00Z")
        self.assertIsInstance(dt, datetime)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 10)
        self.assertEqual(dt.day, 4)
        self.assertEqual(dt.hour, 15)
        self.assertEqual(dt.minute, 30)
        self.assertIsNone(dt.tzinfo)

        # Offset timezone converted to UTC
        dt_offset = ai2x.cell_datetime("2026-10-04T17:30:00+02:00")
        self.assertEqual(dt_offset.hour, 15)

        # Invalid string remains text
        self.assertEqual(ai2x.cell_datetime("not-a-date"), "not-a-date")
        self.assertIsNone(ai2x.cell_datetime(None))

    def test_cell_boolean(self):
        self.assertEqual(ai2x.cell_boolean(True), "completed")
        self.assertEqual(ai2x.cell_boolean(False), "open")
        self.assertEqual(ai2x.cell_boolean(1), "completed")
        self.assertEqual(ai2x.cell_boolean(0), "open")
        self.assertEqual(ai2x.cell_boolean("true"), "completed")
        self.assertEqual(ai2x.cell_boolean("no"), "open")

    def test_validate_path(self):
        valid = self.dir_path / "valid.xlsx"
        self.assertEqual(ai2x.validate_path(str(valid)), valid)
        with self.assertRaises(ValueError):
            ai2x.validate_path("../escape.xlsx")

    def test_convert_action_items_to_xlsx_e2e(self):
        items = [
            {
                "id": "act_001",
                "description": "=SUM(A1:A5) potential formula string",
                "completed": False,
                "due_at": "2026-10-10T14:00:00Z",
                "created_at": "2026-10-01T09:00:00Z",
                "updated_at": "2026-10-02T10:00:00Z",
                "conversation_id": "conv_42",
            },
            {
                "id": "act_002",
                "description": "Ship production hotfix",
                "completed": True,
                "due_at": None,
                "created_at": "2026-10-03T11:00:00Z",
                "conversation_id": "conv_43",
            },
        ]

        count = ai2x.convert_action_items_to_xlsx(items, str(self.output_xlsx))
        self.assertEqual(count, 2)
        self.assertTrue(self.output_xlsx.exists())

        wb = load_workbook(str(self.output_xlsx))
        sheet = wb.active
        self.assertEqual(sheet.title, "action_items")

        # Check headers
        header_vals = [cell.value for cell in sheet[1]]
        self.assertIn("id", header_vals)
        self.assertIn("due_at (UTC)", header_vals)
        self.assertIn("completed", header_vals)

        # Check freeze panes and autofilter
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertIsNotNone(sheet.auto_filter.ref)

        # Check data row 2
        row2_cells = sheet[2]
        self.assertEqual(row2_cells[0].value, "act_001")
        self.assertEqual(row2_cells[0].data_type, "s")  # Explicit string
        self.assertEqual(row2_cells[1].value, "=SUM(A1:A5) potential formula string")
        self.assertEqual(row2_cells[1].data_type, "s")  # Explicit string prevents formula execution
        self.assertEqual(row2_cells[2].value, "open")
        self.assertIsInstance(row2_cells[3].value, datetime)
        self.assertEqual(row2_cells[3].number_format, ai2x.DATETIME_FORMAT)

        # Check data row 3
        row3_cells = sheet[3]
        self.assertEqual(row3_cells[2].value, "completed")
        self.assertIsNone(row3_cells[3].value)

    def test_overwrite_behavior(self):
        items = [{"id": "act_ovr", "description": "Initial task"}]
        ai2x.convert_action_items_to_xlsx(items, str(self.output_xlsx))

        # Fails without overwrite flag
        with self.assertRaises(FileExistsError):
            ai2x.convert_action_items_to_xlsx(items, str(self.output_xlsx), overwrite=False)

        # Succeeds with overwrite=True
        updated_items = [{"id": "act_ovr", "description": "Updated task"}]
        count = ai2x.convert_action_items_to_xlsx(updated_items, str(self.output_xlsx), overwrite=True)
        self.assertEqual(count, 1)

        wb = load_workbook(str(self.output_xlsx))
        self.assertEqual(wb.active[2][1].value, "Updated task")

    def test_load_input_json_with_bom(self):
        test_file = self.dir_path / "wrapped_bom.json"
        # Write with UTF-8 BOM
        test_file.write_text('\ufeff{"action_items": [{"id": "wrapped_bom_1", "description": "Task"}]}', encoding="utf-8")
        data = ai2x.load_input_json(str(test_file))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "wrapped_bom_1")

    def test_malformed_array_entry_raises_error(self):
        malformed = [{"id": "valid_1", "description": "Good"}, "not_a_dict"]
        with self.assertRaises(ValueError):
            ai2x.convert_action_items_to_xlsx(malformed, str(self.output_xlsx))


if __name__ == "__main__":
    unittest.main()
