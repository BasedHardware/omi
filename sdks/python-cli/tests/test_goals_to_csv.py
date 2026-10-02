"""Tests for the goals_to_csv recipe."""

import csv
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "goals_to_csv.py"
spec = importlib.util.spec_from_file_location("goals_to_csv", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
g2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2csv)


class TestGoalsToCSV(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample_goals = [
            {
                "id": "goal_01",
                "title": "Morning 5km Run",
                "goal_type": "numeric",
                "current_value": 5.0,
                "target_value": 5.0,
                "unit": "km",
                "is_active": True,
                "created_at": "2026-09-20T07:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
            },
            {
                "id": "goal_02",
                "title": "Daily Reading",
                "goal_type": "numeric",
                "current_value": 12.0,
                "target_value": 20.0,
                "unit": "pages",
                "is_active": True,
                "created_at": "2026-09-25T09:00:00Z",
                "updated_at": "2026-10-01T18:00:00Z",
            },
            {
                "id": "goal_03",
                "title": "Mindfulness Meditation",
                "goal_type": "boolean",
                "current_value": 0.0,
                "target_value": 1.0,
                "unit": None,
                "is_active": True,
                "created_at": "2026-10-01T06:00:00Z",
                "updated_at": "2026-10-01T06:00:00Z",
            },
            {
                "id": "goal_04",
                "title": "Deep Focus Rating",
                "goal_type": "scale",
                "current_value": 7.0,
                "target_value": 10.0,
                "min_value": 1.0,
                "max_value": 10.0,
                "unit": "/10",
                "is_active": True,
                "created_at": "2026-10-01T12:00:00Z",
                "updated_at": "2026-10-02T10:00:00Z",
            },
            {
                "id": "goal_05",
                "title": "Old Archived Project",
                "goal_type": "numeric",
                "current_value": 2.0,
                "target_value": 10.0,
                "unit": "tasks",
                "is_active": False,
                "created_at": "2026-08-01T12:00:00Z",
                "updated_at": "2026-08-15T12:00:00Z",
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_spreadsheet_text_formula_injection(self):
        self.assertEqual(g2csv.spreadsheet_text("Regular Goal"), "Regular Goal")
        self.assertEqual(g2csv.spreadsheet_text("=cmd|' /C calc'!A0"), "'=cmd|' /C calc'!A0")
        self.assertEqual(g2csv.spreadsheet_text("+SUM(A1:A10)"), "'+SUM(A1:A10)")
        self.assertEqual(g2csv.spreadsheet_text("-10% progress"), "'-10% progress")
        self.assertEqual(g2csv.spreadsheet_text("@hyperlink(url)"), "'@hyperlink(url)")
        self.assertEqual(g2csv.spreadsheet_text(None), "")
        self.assertEqual(g2csv.spreadsheet_text("  spaced  out  "), "spaced out")

    def test_parse_float_finite_numbers(self):
        self.assertEqual(g2csv.parse_float(10), 10.0)
        self.assertEqual(g2csv.parse_float("25.5"), 25.5)
        self.assertIsNone(g2csv.parse_float("invalid"))
        self.assertIsNone(g2csv.parse_float(None))
        self.assertIsNone(g2csv.parse_float(float("inf")))
        self.assertIsNone(g2csv.parse_float(float("-inf")))
        self.assertIsNone(g2csv.parse_float(float("nan")))

    def test_calculate_progress_numeric_scale_boolean(self):
        # Numeric: 5/5 -> 100.0%
        self.assertEqual(g2csv.calculate_progress(self.sample_goals[0]), 100.0)
        # Numeric: 12/20 -> 60.0%
        self.assertEqual(g2csv.calculate_progress(self.sample_goals[1]), 60.0)
        # Boolean: 0/1 -> 0.0%
        self.assertEqual(g2csv.calculate_progress(self.sample_goals[2]), 0.0)
        # Scale: (7 - 1) / (10 - 1) = 6/9 = 66.7%
        self.assertEqual(g2csv.calculate_progress(self.sample_goals[3]), 66.7)

    def test_unwrap_goals_envelopes(self):
        for key in ("goals", "items", "data", "results"):
            envelope = {key: self.sample_goals}
            items = g2csv.unwrap_goals(envelope, "test")
            self.assertEqual(len(items), 5)

        # Bare list
        self.assertEqual(len(g2csv.unwrap_goals(self.sample_goals, "test")), 5)

        # Bare single dict
        single = {"id": "single", "title": "Single goal", "is_active": True}
        self.assertEqual(len(g2csv.unwrap_goals(single, "test")), 1)

        # Non-goal dict returns empty list
        self.assertEqual(len(g2csv.unwrap_goals({"error": "not found"}, "test")), 0)

        with self.assertRaises(ValueError):
            g2csv.unwrap_goals("invalid string", "test")

    def test_load_and_deduplication(self):
        f1 = self.tmp / "g1.json"
        f2 = self.tmp / "g2.json"
        f1.write_text(json.dumps(self.sample_goals[:3]), encoding="utf-8")
        f2.write_text(json.dumps(self.sample_goals[2:]), encoding="utf-8")

        loaded = g2csv.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 5)
        self.assertIn("goal_01", loaded)
        self.assertIn("goal_04", loaded)

    def test_build_rows_and_status_filtering(self):
        goals_dict = {g["id"]: g for g in self.sample_goals}

        # All rows
        all_rows = g2csv.build_rows(goals_dict, status_filter="all")
        self.assertEqual(len(all_rows), 5)

        # Active filter (goals that are active and not completed)
        active_rows = g2csv.build_rows(goals_dict, status_filter="active")
        self.assertEqual(len(active_rows), 3)
        self.assertTrue(all(r["status"] == "active" for r in active_rows))

        # Completed filter (achieved or inactive)
        completed_rows = g2csv.build_rows(goals_dict, status_filter="completed")
        self.assertEqual(len(completed_rows), 2)
        self.assertTrue(all(r["status"] == "completed" for r in completed_rows))

        # Type filter
        scale_rows = g2csv.build_rows(goals_dict, type_filter="scale")
        self.assertEqual(len(scale_rows), 1)
        self.assertEqual(scale_rows[0]["id"], "goal_04")

    def test_build_csv_payload_and_excel_bom(self):
        goals_dict = {g["id"]: g for g in self.sample_goals}
        rows = g2csv.build_rows(goals_dict)

        payload_plain = g2csv.build_csv_payload(rows, excel_bom=False)
        self.assertFalse(payload_plain.startswith(b"\xef\xbb\xbf"))
        text = payload_plain.decode("utf-8")
        reader = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(reader), 5)
        self.assertIn("Morning 5km Run", text)

        payload_bom = g2csv.build_csv_payload(rows, excel_bom=True)
        self.assertTrue(payload_bom.startswith(b"\xef\xbb\xbf"))

    def test_empty_goals_export(self):
        payload = g2csv.build_csv_payload([])
        text = payload.decode("utf-8")
        lines = text.strip().split("\r\n")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], ",".join(g2csv.COLUMNS))

    def test_convert_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "output.csv"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        count = g2csv.convert([str(src)], destination=str(dest))
        self.assertEqual(count, 5)
        self.assertTrue(dest.exists())

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            g2csv.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        count2 = g2csv.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(count2, 5)

    def test_failed_write_cleans_up_destination(self):
        src = self.tmp / "input_err.json"
        dest = self.tmp / "err.csv"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        real_open = Path.open

        def failing_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            mode = kwargs.get("mode", args[0] if args else "r")
            if "xb" in mode and str(self_path) == str(dest):
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk full"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_open):
            with self.assertRaises(OSError):
                g2csv.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_main_cli_execution(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_output.csv"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        ret = g2csv.main([str(src), "-o", str(dest), "--status", "active", "--excel-bom"])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())

        raw_bytes = dest.read_bytes()
        self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_goals).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = g2csv.load(["-"])
            self.assertEqual(len(loaded), 5)


if __name__ == "__main__":
    unittest.main()
