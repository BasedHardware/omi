import csv
import io
import unittest
from pathlib import Path
import sys

# Ensure examples directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_csv import (
    compute_progress_pct,
    goals_to_csv,
    parse_input_payload,
    sanitize_cell_value,
)


class TestGoalsToCsv(unittest.TestCase):
    def test_sanitize_cell_value(self):
        self.assertEqual(sanitize_cell_value("=SUM(A1:A5)"), "'=SUM(A1:A5)")
        self.assertEqual(sanitize_cell_value("+cmd"), "'+cmd")
        self.assertEqual(sanitize_cell_value("-minus"), "'-minus")
        self.assertEqual(sanitize_cell_value("@danger"), "'@danger")
        self.assertEqual(sanitize_cell_value("Normal title"), "Normal title")
        self.assertEqual(sanitize_cell_value(True), "true")
        self.assertEqual(sanitize_cell_value(False), "false")
        self.assertEqual(sanitize_cell_value(None), "")

    def test_compute_progress_pct(self):
        self.assertEqual(compute_progress_pct(50, 100), "50.0%")
        self.assertEqual(compute_progress_pct(35, 50), "70.0%")
        self.assertEqual(compute_progress_pct(0, 100), "0.0%")
        self.assertEqual(compute_progress_pct(10, 0), "")
        self.assertEqual(compute_progress_pct(None, 50), "")

    def test_goals_to_csv_output(self):
        sample_goals = [
            {
                "id": "goal_1",
                "title": "Read 12 books",
                "goal_type": "numeric",
                "current_value": 6,
                "target_value": 12,
                "unit": "books",
                "min_value": 0,
                "max_value": 12,
                "is_active": True,
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-20T10:00:00Z",
            },
            {
                "id": "goal_2",
                "title": "=Dangerous Formula Goal",
                "goal_type": "boolean",
                "current_value": 1,
                "target_value": 1,
                "unit": "",
                "min_value": 0,
                "max_value": 1,
                "is_active": False,
                "created_at": "2026-09-19T08:00:00Z",
                "updated_at": "2026-09-19T08:00:00Z",
            },
        ]

        csv_text = goals_to_csv(sample_goals, status_filter="all")
        reader = list(csv.reader(io.StringIO(csv_text)))

        # Header check
        self.assertIn("progress_pct", reader[0])
        self.assertEqual(len(reader), 3)

        # Row 1 check
        self.assertEqual(reader[1][1], "Read 12 books")
        self.assertEqual(reader[1][5], "50.0%")

        # Formula injection check on Row 2
        self.assertEqual(reader[2][1], "'=Dangerous Formula Goal")

    def test_status_filter(self):
        sample = [
            {"id": "1", "title": "A", "is_active": True, "target_value": 10},
            {"id": "2", "title": "B", "is_active": False, "target_value": 10},
        ]
        active_csv = goals_to_csv(sample, status_filter="active")
        active_rows = list(csv.reader(io.StringIO(active_csv)))
        self.assertEqual(len(active_rows), 2)  # Header + 1 active row

        inactive_csv = goals_to_csv(sample, status_filter="inactive")
        inactive_rows = list(csv.reader(io.StringIO(inactive_csv)))
        self.assertEqual(len(inactive_rows), 2)  # Header + 1 inactive row


if __name__ == "__main__":
    unittest.main()
