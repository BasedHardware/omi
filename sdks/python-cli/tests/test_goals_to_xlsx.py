import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

import openpyxl
from goals_to_xlsx import convert, cell_text, cell_number, cell_datetime


class TestGoalsToXlsx(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.xlsx_path = self.dir_path / "test_goals.xlsx"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cell_helpers(self):
        self.assertEqual(cell_text("=SUM(A1)"), "=SUM(A1)")
        self.assertEqual(cell_number("42"), 42)
        self.assertEqual(cell_number("3.14"), 3.14)
        self.assertIsNone(cell_number(None))
        self.assertIsInstance(cell_datetime("2026-09-20T10:00:00Z"), datetime)

    def test_convert_workbook(self):
        sample_goals = [
            {
                "id": "g_100",
                "title": "Read 20 Books",
                "goal_type": "numeric",
                "current_value": 15,
                "target_value": 20,
                "unit": "books",
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T09:00:00Z",
            },
            {
                "id": "g_101",
                "title": "=Dangerous Formula Title",
                "goal_type": "boolean",
                "current_value": 1,
                "target_value": 1,
                "unit": "",
                "is_active": False,
                "created_at": "2026-09-19T08:00:00Z",
                "updated_at": "2026-09-19T08:00:00Z",
            },
        ]
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(sample_goals), encoding="utf-8")

        convert(str(json_file), str(self.xlsx_path))
        self.assertTrue(self.xlsx_path.exists())

        wb = openpyxl.load_workbook(str(self.xlsx_path))
        sheet = wb.active
        self.assertEqual(sheet.title, "goals")

        # Row 1: Headers
        headers = [c.value for c in sheet[1]]
        self.assertIn("title", headers)
        self.assertIn("progress_pct", headers)

        # Row 2: Goal 1 (Read 20 Books -> 75% progress)
        self.assertEqual(sheet.cell(row=2, column=2).value, "Read 20 Books")
        self.assertEqual(sheet.cell(row=2, column=6).value, 75.0)

        # Row 3: Goal 2 (Formula Injection defense check)
        cell_formula = sheet.cell(row=3, column=2)
        self.assertEqual(cell_formula.value, "=Dangerous Formula Title")
        self.assertEqual(cell_formula.data_type, "s")  # Explicit string type

        wb.close()


if __name__ == "__main__":
    unittest.main()
