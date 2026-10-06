"""Hermetic unit tests for goals_to_csv.py recipe."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add examples directory to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_csv import (
    FIELDS,
    calculate_progress_pct,
    clean_num,
    convert,
    spreadsheet_text,
    validate_path,
)


class TestGoalsToCsv(unittest.TestCase):
    def test_spreadsheet_text(self):
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text("Normal title"), "Normal title")
        self.assertEqual(spreadsheet_text(123), "123")
        self.assertEqual(spreadsheet_text(["a", "b"]), '["a", "b"]')

        # Formula injection characters
        self.assertEqual(spreadsheet_text("=SUM(A1)"), "'=SUM(A1)")
        self.assertEqual(spreadsheet_text("+1234"), "'+1234")
        self.assertEqual(spreadsheet_text("-CMD"), "'-CMD")
        self.assertEqual(spreadsheet_text("@EVIL"), "'@EVIL")
        self.assertEqual(spreadsheet_text("   =SUM(1)"), "'   =SUM(1)")

    def test_clean_num(self):
        self.assertEqual(clean_num(10.0), "10")
        self.assertEqual(clean_num(10.5), "10.5")
        self.assertEqual(clean_num(0), "0")
        self.assertEqual(clean_num(None), "0")

    def test_calculate_progress_pct(self):
        # Numeric
        self.assertEqual(
            calculate_progress_pct({"goal_type": "numeric", "current_value": 25, "target_value": 50}),
            50.0,
        )
        # Scale
        self.assertEqual(
            calculate_progress_pct({
                "goal_type": "scale",
                "current_value": 7,
                "min_value": 2,
                "max_value": 12,
            }),
            50.0,
        )
        # Boolean
        self.assertEqual(
            calculate_progress_pct({"goal_type": "boolean", "current_value": 1, "target_value": 1}),
            100.0,
        )
        self.assertEqual(
            calculate_progress_pct({"goal_type": "boolean", "current_value": 0, "target_value": 1}),
            0.0,
        )

    def test_validate_path(self):
        self.assertEqual(validate_path("safe/path.csv"), Path("safe/path.csv"))
        with self.assertRaises(ValueError):
            validate_path("../traversal.csv")

    def test_envelope_unwrapping(self):
        envelope = {
            "goals": [
                {
                    "id": "g_env",
                    "title": "Wrapped goal",
                    "current_value": 10,
                    "target_value": 20,
                    "is_active": True,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "envelope.json"
            dst = Path(tmpdir) / "envelope.csv"
            src.write_text(json.dumps(envelope), encoding="utf-8")
            count = convert(src, dst)
            self.assertEqual(count, 1)

            with dst.open(encoding="utf-8") as f:
                reader = list(csv.reader(f))
                self.assertEqual(len(reader), 2)
                self.assertEqual(reader[0], list(FIELDS))
                self.assertEqual(reader[1][0], "g_env")
                self.assertEqual(reader[1][1], "Wrapped goal")

    def test_convert_goals_to_csv_e2e(self):
        sample = [
            {
                "id": "0012",
                "title": "Meditate daily",
                "goal_type": "numeric",
                "current_value": 15,
                "target_value": 30,
                "min_value": 0,
                "max_value": 30,
                "unit": "days",
                "is_active": True,
                "created_at": "2026-09-17T10:00:00Z",
                "updated_at": "2026-09-17T11:00:00Z",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sample.json"
            dst = Path(tmpdir) / "goals.csv"
            src.write_text(json.dumps(sample), encoding="utf-8")

            count = convert(src, dst)
            self.assertEqual(count, 1)

            with dst.open(encoding="utf-8") as f:
                reader = list(csv.reader(f))
                self.assertEqual(len(reader), 2)
                self.assertEqual(reader[0], list(FIELDS))
                row = reader[1]
                self.assertEqual(row[0], "0012")  # Preserves leading zero
                self.assertEqual(row[1], "Meditate daily")
                self.assertEqual(row[2], "numeric")
                self.assertEqual(row[3], "30")  # target_value
                self.assertEqual(row[4], "15")  # current_value
                self.assertEqual(row[7], "days")  # unit
                self.assertEqual(row[8], "true")  # is_active
                self.assertEqual(row[9], "50.0%")  # progress_pct

    def test_overwrite_behavior(self):
        sample = [{"id": "g1", "title": "Test"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sample.json"
            dst = Path(tmpdir) / "goals.csv"
            src.write_text(json.dumps(sample), encoding="utf-8")

            convert(src, dst)
            self.assertTrue(dst.exists())

            with self.assertRaises(FileExistsError):
                convert(src, dst, overwrite=False)

            convert(src, dst, overwrite=True)
            self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
