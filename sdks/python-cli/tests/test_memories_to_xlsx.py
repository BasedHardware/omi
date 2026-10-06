"""Hermetic unit tests for memories_to_xlsx.py recipe."""

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
from memories_to_xlsx import (
    FIELDS,
    cell_boolean,
    cell_datetime,
    cell_text,
    convert,
    validate_path,
)


class TestMemoriesToXlsx(unittest.TestCase):
    def test_cell_text(self):
        self.assertIsNone(cell_text(None))
        self.assertEqual(cell_text("Hello"), "Hello")
        self.assertEqual(cell_text(123), "123")
        self.assertEqual(cell_text(["work", "career"]), "work, career")
        self.assertEqual(cell_text({"k": "v"}), '{"k": "v"}')

    def test_cell_datetime(self):
        self.assertIsNone(cell_datetime(None))
        dt = cell_datetime("2026-09-17T14:30:00Z")
        self.assertIsInstance(dt, datetime)
        self.assertIsNone(dt.tzinfo)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.hour, 14)

        # Non-parseable fallback
        self.assertEqual(cell_datetime("invalid-date"), "invalid-date")

    def test_cell_boolean(self):
        self.assertIsNone(cell_boolean(None))
        self.assertTrue(cell_boolean(True))
        self.assertFalse(cell_boolean(False))
        self.assertTrue(cell_boolean("true"))
        self.assertFalse(cell_boolean("no"))
        self.assertTrue(cell_boolean(1))
        self.assertFalse(cell_boolean(0))

    def test_validate_path(self):
        self.assertEqual(validate_path("safe/path/file.xlsx"), Path("safe/path/file.xlsx"))
        with self.assertRaises(ValueError):
            validate_path("../traversal/file.xlsx")

    def test_load_input_with_bom(self):
        sample = [{"id": "mem_bom", "content": "Memory with BOM"}]
        raw = b"\xef\xbb\xbf" + json.dumps(sample).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "in_bom.json"
            dst = Path(tmpdir) / "out_bom.xlsx"
            src.write_bytes(raw)
            count = convert(src, dst)
            self.assertEqual(count, 1)
            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            self.assertEqual(ws.cell(row=2, column=1).value, "mem_bom")

    def test_envelope_unwrapping(self):
        envelope = {
            "memories": [
                {"id": "mem_1", "content": "First memory"},
                {"id": "mem_2", "content": "Second memory"},
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
                "category": "@SUM(1,2)",
                "content": "=CMD|' /C calc'!A0",
                "tags": ["+urgent", "-review"],
                "visibility": "private",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "formula.json"
            dst = Path(tmpdir) / "formula.xlsx"
            src.write_text(json.dumps(sample), encoding="utf-8")
            convert(src, dst)

            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            # Content cell is column 3 (content)
            content_cell = ws.cell(row=2, column=3)
            self.assertEqual(content_cell.data_type, "s")
            self.assertEqual(content_cell.value, "=CMD|' /C calc'!A0")

    def test_convert_memories_to_xlsx_e2e(self):
        sample = [
            {
                "id": "00123",
                "category": "work",
                "content": "Quarterly presentation details",
                "tags": ["presentation", "q3"],
                "visibility": "private",
                "created_at": "2026-09-17T10:00:00Z",
                "updated_at": "2026-09-17T11:00:00Z",
                "manually_added": True,
                "reviewed": False,
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
            self.assertEqual(ws.title, "memories")
            self.assertEqual(ws.freeze_panes, "A2")

            # Check headers
            headers = [cell.value for cell in ws[1]]
            self.assertIn("id", headers)
            self.assertIn("content", headers)
            self.assertIn("created_at (UTC)", headers)
            self.assertIn("updated_at (UTC)", headers)

            # Check bold headers
            for cell in ws[1]:
                self.assertTrue(cell.font.bold)

            # Check row values
            self.assertEqual(ws.cell(row=2, column=1).value, "00123")
            self.assertEqual(ws.cell(row=2, column=1).data_type, "s")
            self.assertEqual(ws.cell(row=2, column=4).value, "presentation, q3")
            self.assertTrue(isinstance(ws.cell(row=2, column=6).value, datetime))
            self.assertEqual(ws.cell(row=2, column=8).value, True)
            self.assertEqual(ws.cell(row=2, column=9).value, False)

    def test_overwrite_behavior(self):
        sample = [{"id": "mem_1", "content": "Memory"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "mem.json"
            dst = Path(tmpdir) / "mem.xlsx"
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
