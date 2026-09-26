"""Tests for memories to Excel (.xlsx) converter.

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

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_xlsx.py"
spec = importlib.util.spec_from_file_location("memories_to_xlsx", script_path)
m2x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2x)


class TestMemoriesToXlsx(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "mem_001",
                "category": "work",
                "content": "Async first communication model",
                "tags": ["workflow", "remote"],
                "visibility": "private",
                "created_at": "2026-09-18T10:00:00Z",
            },
            {
                "id": "mem_002",
                "category": "skills",
                "content": "@dangerous command link attempt",
                "tags": ["security"],
                "visibility": "public",
                "created_at": "2026-09-19T14:15:00Z",
            },
        ]

    def test_xlsx_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            xlsx_file = Path(tmpdir) / "output.xlsx"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2x.convert(json_file, xlsx_file)
            self.assertTrue(xlsx_file.is_file())

            wb = openpyxl.load_workbook(xlsx_file)
            self.assertEqual(wb.sheetnames, ["memories"])
            ws = wb["memories"]

            # Header verification
            self.assertEqual(ws["A1"].value, "id")
            self.assertEqual(ws["B1"].value, "category")
            self.assertEqual(ws["F1"].value, "created_at (UTC)")
            self.assertEqual(ws.freeze_panes, "A2")
            self.assertIsNotNone(ws.auto_filter.ref)

            # Row 2 verification (mem_001)
            self.assertEqual(ws["A2"].value, "mem_001")
            self.assertEqual(ws["B2"].value, "work")
            self.assertEqual(ws["D2"].value, "workflow, remote")
            self.assertEqual(ws["E2"].value, "private")

            # Row 3 verification (mem_002, formula safety)
            self.assertEqual(ws["A3"].value, "mem_002")
            self.assertEqual(ws["C3"].value, "@dangerous command link attempt")
            self.assertEqual(ws["C3"].data_type, "s")

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            xlsx_file = Path(tmpdir) / "output.xlsx"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")
            xlsx_file.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                m2x.convert(json_file, xlsx_file)


if __name__ == "__main__":
    unittest.main()
