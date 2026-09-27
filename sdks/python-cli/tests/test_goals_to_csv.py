"""Tests for goals to CSV exporter recipe.

Pins header ordering, progress percentage calculations, formula injection protection,
envelope unwrapping, overwrite protection, active-only filtering, and CLI conversions.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

# Ensure examples directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goals_to_csv import (
    CSV_HEADERS,
    spreadsheet_text,
    calculate_progress_percent,
    unwrap_goals,
    format_goal_row,
    convert_goals_to_csv,
    main,
)


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
        csv_text = convert_goals_to_csv(self.sample_goals)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        self.assertEqual(len(rows), 4)  # 1 header + 3 items
        self.assertEqual(
            rows[0],
            list(CSV_HEADERS),
        )

    def test_progress_percent_calculation(self):
        # 30 / 40 = 75.00%
        pct_numeric = calculate_progress_percent(self.sample_goals[0])
        self.assertEqual(pct_numeric, 75.0)

        # Boolean done = 100.00%
        pct_bool = calculate_progress_percent(self.sample_goals[1])
        self.assertEqual(pct_bool, 100.0)

        # Zero-span edge case
        edge_item = {"goal_type": "numeric", "current_value": 10, "target_value": 0, "min_value": 0}
        self.assertEqual(calculate_progress_percent(edge_item), 100.0)

        # Clamping
        overflow_item = {"goal_type": "numeric", "current_value": 150, "target_value": 100, "min_value": 0}
        self.assertEqual(calculate_progress_percent(overflow_item), 100.0)
        underflow_item = {"goal_type": "numeric", "current_value": -10, "target_value": 100, "min_value": 0}
        self.assertEqual(calculate_progress_percent(underflow_item), 0.0)

    def test_spreadsheet_formula_injection_guard(self):
        row = format_goal_row(self.sample_goals[2])
        self.assertTrue(row["title"].startswith("'="))
        self.assertTrue(row["goal_type"].startswith("'@"))
        self.assertTrue(row["unit"].startswith("'+"))
        self.assertEqual(spreadsheet_text("  -123  "), "'-123")
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text(True), "true")

    def test_envelope_unwrapping(self):
        self.assertEqual(len(unwrap_goals(self.sample_goals)), 3)
        self.assertEqual(len(unwrap_goals({"goals": self.sample_goals})), 3)
        self.assertEqual(len(unwrap_goals({"items": self.sample_goals})), 3)
        self.assertEqual(len(unwrap_goals({"data": self.sample_goals})), 3)
        self.assertEqual(len(unwrap_goals({"goals": []})), 0)
        # Single goal dict
        self.assertEqual(len(unwrap_goals(self.sample_goals[0])), 1)
        # Invalid input
        self.assertEqual(unwrap_goals("invalid string"), [])
        self.assertEqual(unwrap_goals(None), [])

    def test_file_output_and_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "goals.json"
            out_file = Path(tmpdir) / "output.csv"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            # Positional CLI execution
            exit_code = main([str(json_file), str(out_file)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())

            # Verify UTF-8 BOM
            raw_bytes = out_file.read_bytes()
            self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))
            content = raw_bytes.decode("utf-8-sig")
            self.assertIn("Read 40 Pages", content)
            self.assertIn("75.00", content)

            # Refuse overwrite without --force
            exit_code_overwrite = main([str(json_file), str(out_file)])
            self.assertNotEqual(exit_code_overwrite, 0)

            # Overwrite with --force
            exit_code_forced = main([str(json_file), str(out_file), "--force"])
            self.assertEqual(exit_code_forced, 0)

    def test_active_only_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "goals.json"
            out_file = Path(tmpdir) / "active.csv"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            exit_code = main([str(json_file), "-o", str(out_file), "--active-only"])
            self.assertEqual(exit_code, 0)

            content = out_file.read_text(encoding="utf-8-sig")
            # goal_01 and goal_03 are active, goal_02 is inactive
            self.assertIn("goal_01", content)
            self.assertIn("goal_03_injection", content)
            self.assertNotIn("Morning Meditation", content)


if __name__ == "__main__":
    unittest.main()
