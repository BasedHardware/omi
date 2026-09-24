#!/usr/bin/env python3
"""
Unit tests for sdks/python-cli/examples/goals_to_csv.py
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

# Add examples and tests directory to sys.path so pytest discovers example modules in CI
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goals_to_csv import (
    FIELDS,
    compute_progress,
    convert,
    goals_to_rows,
    load,
    main,
    spreadsheet_text,
)


class TestGoalsToCsv(unittest.TestCase):

    def test_spreadsheet_text_escaping(self):
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text("  Learn Rust  \n"), "Learn Rust")

        # Test formula injection prevention
        self.assertEqual(spreadsheet_text("=SUM(A1:A10)"), "'=SUM(A1:A10)")
        self.assertEqual(spreadsheet_text("+12345"), "'+12345")
        self.assertEqual(spreadsheet_text("-cmd|' /C calc'!A0"), "'-cmd|' /C calc'!A0")
        self.assertEqual(spreadsheet_text("@eval"), "'@eval")
        self.assertEqual(spreadsheet_text("\t=cmd"), "'=cmd")

        # Non-string coercions
        self.assertEqual(spreadsheet_text(42), "42")
        self.assertEqual(spreadsheet_text({"metric": "count"}), '{"metric": "count"}')

    def test_compute_progress(self):
        # Completed
        self.assertEqual(compute_progress({}, False), 100.0)

        # Qualitative
        self.assertIsNone(compute_progress({"goal_type": "qualitative"}, True))

        # Boolean
        self.assertEqual(compute_progress({"goal_type": "boolean", "current_value": 0, "target_value": 1}, True), 0.0)
        self.assertEqual(compute_progress({"goal_type": "boolean", "current_value": 1, "target_value": 1}, True), 100.0)

        # Numeric / Scale
        self.assertEqual(compute_progress({"goal_type": "numeric", "current_value": 15, "target_value": 30, "min_value": 0}, True), 50.0)
        self.assertEqual(compute_progress({"goal_type": "scale", "current_value": 8, "target_value": 10}, True), 80.0)

    def test_compute_progress_edge_cases(self):
        # min_value == target_value
        self.assertEqual(compute_progress({"goal_type": "numeric", "current_value": 10, "target_value": 10, "min_value": 10}, True), 100.0)
        # target is None
        self.assertIsNone(compute_progress({"goal_type": "numeric", "current_value": 10}, True))
        # target using max_value fallback
        self.assertEqual(compute_progress({"goal_type": "numeric", "current_value": 5, "max_value": 10}, True), 50.0)
        # invalid numbers
        self.assertIsNone(compute_progress({"goal_type": "numeric", "current_value": "abc", "target_value": "xyz"}, True))

    def test_goals_to_rows(self):
        goals = {
            "g1": {
                "id": "g1",
                "title": "Gym visits",
                "goal_type": "numeric",
                "current_value": 15,
                "target_value": 30,
                "unit": "sessions",
                "status": "active",
                "created_at": "2026-09-01T10:00:00Z",
                "updated_at": "2026-09-20T10:00:00Z",
            }
        }
        rows = goals_to_rows(goals)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r[0], "g1")
        self.assertEqual(r[1], "Gym visits")
        self.assertEqual(r[2], "active")
        self.assertEqual(r[3], "numeric")
        self.assertEqual(r[4], "15")
        self.assertEqual(r[5], "30")
        self.assertEqual(r[6], "sessions")
        self.assertEqual(r[7], "50.00%")
        self.assertEqual(r[8], "2026-09-01T10:00:00Z")

        # Test achieved / abandoned fallback when is_active is omitted
        inactive_goals = {
            "g2": {"id": "g2", "title": "Run marathon", "status": "achieved"},
            "g3": {"id": "g3", "title": "Drop course", "status": "abandoned"},
        }
        rows_inactive = goals_to_rows(inactive_goals)
        self.assertEqual(rows_inactive[0][2], "achieved")
        self.assertEqual(rows_inactive[0][7], "100.00%")
        self.assertEqual(rows_inactive[1][2], "abandoned")
        self.assertEqual(rows_inactive[1][7], "100.00%")

    def test_load_and_deduplicate(self):
        d1 = [{"id": "g1", "title": "Goal 1", "status": "active"}]
        d2 = [{"id": "g1", "title": "Goal 1 Updated", "status": "completed"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "p1.json"
            p2 = Path(tmpdir) / "p2.json"
            p1.write_text(json.dumps(d1), encoding="utf-8")
            p2.write_text(json.dumps(d2), encoding="utf-8")

            res = load([str(p1), str(p2)])
            self.assertEqual(len(res), 1)
            self.assertEqual(res["g1"]["title"], "Goal 1 Updated")
            self.assertEqual(res["g1"]["status"], "completed")

    def test_load_dict_wrapper(self):
        d_goals = {"goals": [{"id": "g_wrap1", "title": "Wrapped in goals"}]}
        d_data = {"data": [{"id": "g_wrap2", "title": "Wrapped in data"}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "w1.json"
            p2 = Path(tmpdir) / "w2.json"
            p1.write_text(json.dumps(d_goals), encoding="utf-8")
            p2.write_text(json.dumps(d_data), encoding="utf-8")

            res = load([str(p1), str(p2)])
            self.assertEqual(len(res), 2)
            self.assertIn("g_wrap1", res)
            self.assertIn("g_wrap2", res)

    def test_load_stdin(self):
        d = [{"id": "g_pipe", "title": "Stdin goal"}]
        with patch("sys.stdin", io.StringIO(json.dumps(d))):
            res = load(["-"])
            self.assertEqual(len(res), 1)
            self.assertEqual(res["g_pipe"]["title"], "Stdin goal")

    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                load([str(Path(tmpdir) / "missing.json")])

            bad_p = Path(tmpdir) / "bad.json"
            bad_p.write_text("{corrupt", encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(bad_p)])

            noid_p = Path(tmpdir) / "no_id.json"
            noid_p.write_text('[{"title": "No ID"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(noid_p)])

    def test_convert_creates_utf8_bom_csv(self):
        sample = [{"id": "g1", "title": "Read books", "status": "active"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            dst = Path(tmpdir) / "goals.csv"
            src.write_text(json.dumps(sample), encoding="utf-8")

            # Protection test
            dst.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(dst), force=False)

            convert([str(src)], str(dst), force=True)
            content_bytes = dst.read_bytes()
            # Check UTF-8 BOM
            self.assertTrue(content_bytes.startswith(b"\xef\xbb\xbf"))

            # Read CSV content
            decoded_text = content_bytes.decode("utf-8-sig")
            reader = list(csv.reader(io.StringIO(decoded_text)))
            self.assertEqual(reader[0], list(FIELDS))
            self.assertEqual(reader[1][0], "g1")
            self.assertEqual(reader[1][1], "Read books")

    def test_cli_execution(self):
        sample = [{"id": "g_cli", "title": "CLI goal", "status": "active"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.json"
            dst = Path(tmpdir) / "output.csv"
            dst2 = Path(tmpdir) / "output2.csv"
            src.write_text(json.dumps(sample), encoding="utf-8")

            with patch("sys.argv", ["goals_to_csv.py", str(src), str(dst)]):
                main()
            self.assertTrue(dst.exists())

            # Test failure exit code with missing source file
            with patch("sys.argv", ["goals_to_csv.py", str(Path(tmpdir) / "nonexistent.json"), str(dst2)]):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
