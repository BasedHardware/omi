"""Tests for goal list to CSV exporter."""

from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_csv.py"
spec = importlib.util.spec_from_file_location("goals_to_csv", script_path)
g2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2c)


class TestGoalsToCSV(unittest.TestCase):
    def test_convert_valid_goals(self):
        sample_goals = [
            {
                "id": "goal-1",
                "title": "Read 12 books",
                "goal_type": "target",
                "current_value": 3,
                "target_value": 12,
                "unit": "books",
                "is_active": True,
                "description": "2026 reading challenge",
            },
            {
                "id": "goal-2",
                "title": "=SUM(A1:A5)",
                "goal_type": "metric",
                "current_value": 100,
                "target_value": 100,
                "unit": "km",
                "is_active": False,
                "description": "+formula risk description",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "goals.json"
            csv_file = Path(tmp_dir) / "goals.csv"
            json_file.write_text(json.dumps(sample_goals), encoding="utf-8")

            g2c.convert(str(json_file), str(csv_file))
            self.assertTrue(csv_file.exists())

            # Read CSV
            with csv_file.open(encoding="utf-8-sig") as f:
                reader = list(csv.reader(f))
                self.assertEqual(reader[0], list(g2c.FIELDS))
                # First row: progress should be 25.0%
                self.assertEqual(reader[1][0], "goal-1")
                self.assertEqual(reader[1][1], "Read 12 books")
                self.assertEqual(reader[1][7], "25.0")
                # Second row: formula escaping should precede title and description
                self.assertEqual(reader[2][1], "'=SUM(A1:A5)")
                self.assertEqual(reader[2][7], "100.0")
                self.assertEqual(reader[2][8], "'+formula risk description")

    def test_refuse_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "goals.json"
            csv_file = Path(tmp_dir) / "goals.csv"
            json_file.write_text(json.dumps([]), encoding="utf-8")
            csv_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2c.convert(str(json_file), str(csv_file))

    def test_invalid_json_structure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "invalid.json"
            csv_file = Path(tmp_dir) / "out.csv"
            json_file.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                g2c.convert(str(json_file), str(csv_file))


if __name__ == "__main__":
    unittest.main()
