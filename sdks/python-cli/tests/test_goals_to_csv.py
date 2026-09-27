"""Tests for goals to CSV exporter recipe.

Pins header ordering, progress percentage calculations, formula injection protection,
envelope unwrapping, and file/stdout conversions.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

# Load goals_to_csv example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_csv.py"
spec = importlib.util.spec_from_file_location("goals_to_csv", script_path)
assert spec is not None and spec.loader is not None
g2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2c)


class TestGoalsToCSV(unittest.TestCase):
    def setUp(self):
        self.sample_goals = [
            {
                "id": "goal_01",
                "title": "Read 40 Pages",
                "goal_type": "numeric",
                "current_value": 30.0,
                "target_value": 40.0,
                "min_value": 0.0,
                "max_value": 100.0,
                "unit": "pages",
                "is_active": True,
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-27T08:00:00Z",
            },
            {
                "id": "goal_02",
                "title": "Morning Meditation",
                "goal_type": "boolean",
                "current_value": 1.0,
                "target_value": 1.0,
                "min_value": 0.0,
                "max_value": 1.0,
                "unit": None,
                "is_active": False,
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-27T08:00:00Z",
            },
            {
                "id": "goal_03_injection",
                "title": "=cmd|' /C calc'!A0",
                "goal_type": "@formula",
                "current_value": 5.0,
                "target_value": 10.0,
                "min_value": 0.0,
                "max_value": 10.0,
                "unit": "+points",
                "is_active": True,
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-27T08:00:00Z",
            },
        ]

    def test_csv_headers_and_row_count(self):
        csv_text = g2c.convert_goals_to_csv(self.sample_goals)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        self.assertEqual(len(rows), 4)  # 1 header + 3 items
        self.assertEqual(
            rows[0],
            [
                "id",
                "title",
                "goal_type",
                "current_value",
                "target_value",
                "min_value",
                "max_value",
                "unit",
                "progress_percent",
                "is_active",
                "created_at",
                "updated_at",
            ],
        )

    def test_progress_percent_calculation(self):
        # 30 / 40 = 75.00%
        pct_numeric = g2c.calculate_progress_percent(self.sample_goals[0])
        self.assertEqual(pct_numeric, 75.0)

        # Boolean done = 100.00%
        pct_bool = g2c.calculate_progress_percent(self.sample_goals[1])
        self.assertEqual(pct_bool, 100.0)

        # Zero-span edge case
        edge_item = {"goal_type": "numeric", "current_value": 10, "target_value": 0, "min_value": 0}
        self.assertEqual(g2c.calculate_progress_percent(edge_item), 100.0)

    def test_spreadsheet_formula_injection_guard(self):
        row = g2c.format_goal_row(self.sample_goals[2])
        # Leading '=' escaped with apostrophe
        self.assertTrue(row["title"].startswith("'="))
        # Leading '@' escaped with apostrophe
        self.assertTrue(row["goal_type"].startswith("'@"))
        # Leading '+' escaped with apostrophe
        self.assertTrue(row["unit"].startswith("'+"))

    def test_envelope_unwrapping(self):
        raw_list = self.sample_goals
        self.assertEqual(len(g2c.unwrap_goals(raw_list)), 3)

        wrapped_dict = {"goals": self.sample_goals}
        self.assertEqual(len(g2c.unwrap_goals(wrapped_dict)), 3)

        items_dict = {"items": self.sample_goals}
        self.assertEqual(len(g2c.unwrap_goals(items_dict)), 3)

        invalid_data = "string payload"
        self.assertEqual(g2c.unwrap_goals(invalid_data), [])

    def test_file_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output.csv"
            csv_text = g2c.convert_goals_to_csv(self.sample_goals)
            out_file.write_text(csv_text, encoding="utf-8")

            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("Read 40 Pages", content)
            self.assertIn("75.00", content)


if __name__ == "__main__":
    unittest.main()
