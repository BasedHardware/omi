"""Unit tests for the Omi goals to Excel (.xlsx) export recipe."""

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pytest

# Guard openpyxl import so pytest skips gracefully if openpyxl is not installed in basic CI
pytest.importorskip("openpyxl")
from openpyxl import load_workbook  # noqa: E402

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "goals_to_xlsx.py"
spec = importlib.util.spec_from_file_location("goals_to_xlsx", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {RECIPE_PATH}")
goals_xlsx = importlib.util.module_from_spec(spec)
sys.modules["goals_to_xlsx"] = goals_xlsx
spec.loader.exec_module(goals_xlsx)


class TestGoalsToXlsx(unittest.TestCase):
    def test_cell_text(self) -> None:
        self.assertIsNone(goals_xlsx.cell_text(None))
        self.assertEqual(goals_xlsx.cell_text("Reading books"), "Reading books")
        self.assertEqual(goals_xlsx.cell_text(123), "123")
        self.assertEqual(goals_xlsx.cell_text({"k": "v"}), '{"k": "v"}')

    def test_cell_number(self) -> None:
        self.assertIsNone(goals_xlsx.cell_number(None))
        self.assertEqual(goals_xlsx.cell_number(42), 42)
        self.assertEqual(goals_xlsx.cell_number(3.14), 3.14)
        self.assertEqual(goals_xlsx.cell_number("100"), 100)
        self.assertEqual(goals_xlsx.cell_number("75.5"), 75.5)
        self.assertIsNone(goals_xlsx.cell_number("not-a-number"))

    def test_cell_datetime(self) -> None:
        self.assertIsNone(goals_xlsx.cell_datetime(None))
        self.assertIsNone(goals_xlsx.cell_datetime(""))

        # UTC Z offset
        dt_z = goals_xlsx.cell_datetime("2026-10-05T12:00:00Z")
        self.assertIsInstance(dt_z, datetime)
        self.assertIsNone(dt_z.tzinfo)
        self.assertEqual(dt_z.hour, 12)

        # Numeric offset (+02:00 -> 10:00 UTC)
        dt_offset = goals_xlsx.cell_datetime("2026-10-05T12:00:00+02:00")
        self.assertIsInstance(dt_offset, datetime)
        self.assertIsNone(dt_offset.tzinfo)
        self.assertEqual(dt_offset.hour, 10)

    def test_cell_boolean(self) -> None:
        self.assertEqual(goals_xlsx.cell_boolean(True), "active")
        self.assertEqual(goals_xlsx.cell_boolean(False), "inactive")
        self.assertEqual(goals_xlsx.cell_boolean(1), "active")
        self.assertEqual(goals_xlsx.cell_boolean(0), "inactive")
        self.assertEqual(goals_xlsx.cell_boolean("true"), "active")
        self.assertEqual(goals_xlsx.cell_boolean("inactive"), "inactive")

    def test_calculate_progress_pct(self) -> None:
        # Numeric goal
        num_item = {
            "goal_type": "numeric",
            "current_value": 75,
            "target_value": 100,
        }
        self.assertEqual(goals_xlsx.calculate_progress_pct(num_item), 75.0)

        # Scale goal with min_value
        scale_item = {
            "goal_type": "scale",
            "current_value": 60,
            "min_value": 20,
            "target_value": 100,
        }
        self.assertEqual(goals_xlsx.calculate_progress_pct(scale_item), 50.0)

        # Boolean goal
        bool_active = {"goal_type": "boolean", "is_active": True}
        self.assertEqual(goals_xlsx.calculate_progress_pct(bool_active), 0.0)

        bool_done = {"goal_type": "boolean", "current_value": 1}
        self.assertEqual(goals_xlsx.calculate_progress_pct(bool_done), 100.0)

    def test_validate_path(self) -> None:
        safe_path = goals_xlsx.validate_path("output.xlsx")
        self.assertEqual(str(safe_path), "output.xlsx")

        with self.assertRaises(ValueError):
            goals_xlsx.validate_path("../traversal.xlsx")

    def test_convert_goals_to_xlsx_e2e(self) -> None:
        sample_goals = [
            {
                "id": "goal_1",
                "title": "=SUM(A1:A5) Formula Title",  # Injection test
                "goal_type": "numeric",
                "current_value": 50,
                "target_value": 100,
                "unit": "km",
                "is_active": True,
                "created_at": "2026-10-01T10:00:00Z",
                "updated_at": "2026-10-05T14:30:00Z",
            },
            {
                "id": "goal_2",
                "title": "Read 12 books",
                "goal_type": "scale",
                "current_value": 3,
                "min_value": 0,
                "target_value": 12,
                "unit": "books",
                "is_active": True,
                "created_at": "2026-09-15T08:00:00Z",
                "updated_at": "2026-10-02T16:00:00Z",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "test_goals.xlsx"
            count = goals_xlsx.convert_goals_to_xlsx(sample_goals, str(out_file))
            self.assertEqual(count, 2)
            self.assertTrue(out_file.exists())

            # Load generated workbook and inspect content
            wb = load_workbook(out_file)
            sheet = wb["goals"]
            self.assertEqual(sheet.title, "goals")
            self.assertEqual(sheet.freeze_panes, "A2")

            # Check header
            headers = [cell.value for cell in sheet[1]]
            self.assertIn("id", headers)
            self.assertIn("title", headers)
            self.assertIn("progress_pct", headers)
            self.assertIn("created_at (UTC)", headers)

            # Check row 2 (formula injection defense: data_type MUST be 's')
            title_cell = sheet["B2"]
            self.assertEqual(title_cell.value, "=SUM(A1:A5) Formula Title")
            self.assertEqual(title_cell.data_type, "s")

            # Check numeric progress
            prog_cell = sheet["G2"]
            self.assertEqual(prog_cell.value, 50.0)

            # Check datetime formatting
            created_cell = sheet["I2"]
            self.assertIsInstance(created_cell.value, datetime)
            self.assertEqual(created_cell.number_format, "yyyy-mm-dd hh:mm:ss")

    def test_overwrite_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "goals.xlsx"
            out_file.write_text("DUMMY CONTENT", encoding="utf-8")

            # Refuse overwrite when False
            with self.assertRaises(FileExistsError):
                goals_xlsx.convert_goals_to_xlsx([], str(out_file), overwrite=False)

            # Overwrite succeeds when True
            count = goals_xlsx.convert_goals_to_xlsx([], str(out_file), overwrite=True)
            self.assertEqual(count, 0)
            self.assertTrue(out_file.exists())

    def test_malformed_array_entry_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "invalid.xlsx"
            with self.assertRaises(ValueError):
                goals_xlsx.convert_goals_to_xlsx(["not-a-dict"], str(out_file))

    def test_load_input_json_with_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bom_file = Path(tmp_dir) / "goals_bom.json"
            data = [{"id": "g_bom", "title": "BOM Goal"}]
            bom_file.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))

            loaded = goals_xlsx.load_input_json(str(bom_file))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["id"], "g_bom")

    def test_cli_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "goals.json"
            out_file = Path(tmp_dir) / "goals_out.xlsx"
            data = [{"id": "cli_g", "title": "CLI Test Goal", "current_value": 10, "target_value": 20}]
            in_file.write_text(json.dumps(data), encoding="utf-8")

            exit_code = goals_xlsx.main(["-i", str(in_file), "-o", str(out_file), "--overwrite"])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())


if __name__ == "__main__":
    unittest.main()
