"""Hermetic unit tests for action_items_to_xlsx.py recipe."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Add examples directory to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

import openpyxl
from action_items_to_xlsx import (
    FIELDS,
    cell_boolean,
    cell_datetime,
    cell_text,
    convert,
    validate_path,
)


class TestActionItemsToXlsx(unittest.TestCase):
    def test_cell_text(self):
        self.assertIsNone(cell_text(None))
        self.assertEqual(cell_text("Follow up with client"), "Follow up with client")
        self.assertEqual(cell_text(123), "123")
        self.assertEqual(cell_text({"context": "urgent"}), '{"context": "urgent"}')

    def test_cell_datetime(self):
        self.assertIsNone(cell_datetime(None))
        dt = cell_datetime("2026-10-01T15:30:00Z")
        self.assertIsInstance(dt, datetime)
        self.assertIsNone(dt.tzinfo)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.hour, 15)

        # Non-parseable fallback
        self.assertEqual(cell_datetime("tomorrow noon"), "tomorrow noon")

    def test_cell_boolean(self):
        self.assertIsNone(cell_boolean(None))
        self.assertTrue(cell_boolean(True))
        self.assertFalse(cell_boolean(False))
        self.assertTrue(cell_boolean("true"))
        self.assertFalse(cell_boolean("false"))
        self.assertTrue(cell_boolean(1))
        self.assertFalse(cell_boolean(0))

    def test_validate_path(self):
        self.assertEqual(validate_path("tasks/output.xlsx"), Path("tasks/output.xlsx"))
        with self.assertRaises(ValueError):
            validate_path("../escaped/output.xlsx")

    def test_load_input_with_bom(self):
        sample = [{"id": "act_bom", "description": "Action item with BOM"}]
        raw = b"\xef\xbb\xbf" + json.dumps(sample).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "in_bom.json"
            dst = Path(tmpdir) / "out_bom.xlsx"
            src.write_bytes(raw)
            count = convert(src, dst)
            self.assertEqual(count, 1)
            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            self.assertEqual(ws.cell(row=2, column=1).value, "act_bom")

    def test_envelope_unwrapping(self):
        envelope = {
            "action_items": [
                {"id": "act_1", "description": "First task"},
                {"id": "act_2", "description": "Second task"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "envelope.json"
            dst = Path(tmpdir) / "envelope.xlsx"
            src.write_text(json.dumps(envelope), encoding="utf-8")
            count = convert(src, dst)
            self.assertEqual(count, 2)
            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            self.assertEqual(ws.max_row, 3)

    def test_formula_injection_defense(self):
        sample = [
            {
                "id": "=1+1",
                "description": "=CMD|' /C calc'!A0",
                "completed": False,
                "conversation_id": "@EVIL()",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "formula.json"
            dst = Path(tmpdir) / "formula.xlsx"
            src.write_text(json.dumps(sample), encoding="utf-8")
            convert(src, dst)

            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            desc_cell = ws.cell(row=2, column=2)
            self.assertEqual(desc_cell.data_type, "s")
            self.assertEqual(desc_cell.value, "=CMD|' /C calc'!A0")

    def test_deduplication_by_id(self):
        page1 = [{"id": "t1", "description": "Task version 1"}]
        page2 = [{"id": "t1", "description": "Task version 2"}, {"id": "t2", "description": "New task"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src1 = Path(tmpdir) / "p1.json"
            src2 = Path(tmpdir) / "p2.json"
            dst = Path(tmpdir) / "merged.xlsx"
            src1.write_text(json.dumps(page1), encoding="utf-8")
            src2.write_text(json.dumps(page2), encoding="utf-8")

            count = convert([src1, src2], dst)
            self.assertEqual(count, 2)
            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            self.assertEqual(ws.max_row, 3)
            self.assertEqual(ws.cell(row=2, column=2).value, "Task version 2")

    def test_convert_action_items_to_xlsx_e2e(self):
        sample = [
            {
                "id": "act_100",
                "description": "Deploy security patch",
                "completed": True,
                "due_at": "2026-10-15T18:00:00Z",
                "created_at": "2026-10-06T12:00:00Z",
                "updated_at": "2026-10-06T14:30:00Z",
                "conversation_id": "conv_999",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sample.json"
            dst = Path(tmpdir) / "sample.xlsx"
            src.write_text(json.dumps(sample), encoding="utf-8")

            count = convert(src, dst)
            self.assertEqual(count, 1)
            self.assertTrue(dst.exists())

            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            self.assertEqual(ws.title, "action_items")
            self.assertEqual(ws.freeze_panes, "A2")

            # Check headers
            headers = [cell.value for cell in ws[1]]
            self.assertEqual(headers[0], "id")
            self.assertEqual(headers[1], "description")
            self.assertEqual(headers[2], "completed")
            self.assertEqual(headers[3], "due_at (UTC)")
            self.assertEqual(headers[4], "created_at (UTC)")
            self.assertEqual(headers[5], "updated_at (UTC)")
            self.assertEqual(headers[6], "conversation_id")

            for cell in ws[1]:
                self.assertTrue(cell.font.bold)

            # Check row values
            self.assertEqual(ws.cell(row=2, column=1).value, "act_100")
            self.assertEqual(ws.cell(row=2, column=2).value, "Deploy security patch")
            self.assertEqual(ws.cell(row=2, column=3).value, True)
            self.assertIsInstance(ws.cell(row=2, column=4).value, datetime)
            self.assertIsInstance(ws.cell(row=2, column=5).value, datetime)
            self.assertEqual(ws.cell(row=2, column=7).value, "conv_999")

    def test_overwrite_behavior(self):
        sample = [{"id": "act_1", "description": "Write tests"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "act.json"
            dst = Path(tmpdir) / "act.xlsx"
            src.write_text(json.dumps(sample), encoding="utf-8")

            # First write succeeds
            convert(src, dst)
            self.assertTrue(dst.exists())

            # Second write without overwrite fails
            with self.assertRaises(FileExistsError):
                convert(src, dst, overwrite=False)

            # Second write with overwrite succeeds
            convert(src, dst, overwrite=True)
            self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
