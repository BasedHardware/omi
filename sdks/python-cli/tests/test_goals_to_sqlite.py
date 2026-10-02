"""Tests for the goals_to_sqlite recipe."""

import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "goals_to_sqlite.py"
spec = importlib.util.spec_from_file_location("goals_to_sqlite", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
g2sql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2sql)


class TestGoalsToSQLite(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample_goals = [
            {
                "id": "goal_01",
                "title": "Read 20 Books",
                "goal_type": "numeric",
                "current_value": 12,
                "target_value": 20,
                "unit": "books",
                "is_active": True,
                "is_achieved": False,
                "created_at": "2026-09-01T12:00:00Z",
                "updated_at": "2026-09-15T15:30:00Z",
            },
            {
                "id": "goal_02",
                "title": "Run 50km",
                "goal_type": "numeric",
                "current_value": 50,
                "target_value": 50,
                "unit": "km",
                "is_active": True,
                "is_achieved": True,
                "created_at": "2026-09-05T08:00:00Z",
            },
            {
                "id": "goal_03",
                "title": "Old Archived Milestone",
                "goal_type": "numeric",
                "current_value": 5,
                "target_value": 100,
                "unit": "points",
                "is_active": False,
                "is_achieved": False,
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_validate_db_path(self):
        valid_path = self.tmp / "test.sqlite"
        g2sql.validate_db_path(str(valid_path))

        # Traversal refusal
        with self.assertRaises(ValueError):
            g2sql.validate_db_path(str(self.tmp / ".." / "outside.sqlite"))

        # Non-sqlite existing file refusal
        bad_file = self.tmp / "fake.sqlite"
        bad_file.write_text("not a sqlite file", encoding="utf-8")
        with self.assertRaises(ValueError):
            g2sql.validate_db_path(str(bad_file))

    def test_text_sanitization(self):
        self.assertEqual(g2sql.text("Clean Title"), "Clean Title")
        self.assertIsNone(g2sql.text(None))
        self.assertEqual(g2sql.text("Clean\x00\ufffe\uffff"), "Clean")
        self.assertEqual(g2sql.text({"nested": 1}), '{"nested": 1}')

    def test_utc_stamp_normalization(self):
        self.assertEqual(
            g2sql.utc_stamp("2026-10-02T12:00:00Z"),
            "2026-10-02 12:00:00",
        )
        self.assertEqual(
            g2sql.utc_stamp("2026-10-02T14:00:00+02:00"),
            "2026-10-02 12:00:00",
        )
        self.assertIsNone(g2sql.utc_stamp("invalid"))
        self.assertIsNone(g2sql.utc_stamp(None))

    def test_derive_status_precedence(self):
        # Inactive takes strict precedence
        self.assertEqual(g2sql.derive_status({"is_active": False, "is_achieved": True}), (0, 0))
        self.assertEqual(g2sql.derive_status({"is_active": "0", "is_completed": True}), (0, 0))
        # Completed
        self.assertEqual(g2sql.derive_status({"is_active": True, "is_achieved": True}), (1, 1))
        # Active
        self.assertEqual(g2sql.derive_status({"is_active": True, "is_achieved": False}), (1, 0))

    def test_calc_progress_pct(self):
        # Completed goal
        self.assertEqual(g2sql.calc_progress_pct({}, 1), 100.0)

        # Normal numeric
        goal_num = {"current_value": 15, "target_value": 20}
        self.assertEqual(g2sql.calc_progress_pct(goal_num, 0), 75.0)

        # Scale with min and max
        goal_scale = {"current_value": 30, "target_value": 50, "min_value": 10}
        self.assertEqual(g2sql.calc_progress_pct(goal_scale, 0), 50.0)

        # Boolean
        goal_bool = {"goal_type": "boolean", "current_value": 1}
        self.assertEqual(g2sql.calc_progress_pct(goal_bool, 0), 100.0)

        # Missing target / qualitative
        goal_qual = {"title": "Learn chess"}
        self.assertIsNone(g2sql.calc_progress_pct(goal_qual, 0))

    def test_rows_from_envelopes(self):
        for key in ("goals", "items", "data", "results"):
            wrapped = {key: self.sample_goals}
            src = self.tmp / f"wrapped_{key}.json"
            src.write_text(json.dumps(wrapped), encoding="utf-8")
            rows = g2sql.rows_from(str(src))
            self.assertEqual(len(rows), 3)

        # Single goal dict
        src_single = self.tmp / "single.json"
        src_single.write_text(json.dumps(self.sample_goals[0]), encoding="utf-8")
        rows_single = g2sql.rows_from(str_single := str(src_single))
        self.assertEqual(len(rows_single), 1)

        # Empty or whitespace file
        src_empty = self.tmp / "empty.json"
        src_empty.write_text("   \n\t  ", encoding="utf-8")
        self.assertEqual(len(g2sql.rows_from(str(src_empty))), 0)

        # Non-dict/list raises ValueError
        src_bad = self.tmp / "bad.json"
        src_bad.write_text('"just a string"', encoding="utf-8")
        with self.assertRaises(ValueError):
            g2sql.rows_from(str(src_bad))

    def test_load_schema_and_idempotent_upsert(self):
        f1 = self.tmp / "p1.json"
        f2 = self.tmp / "p2.json"
        db = self.tmp / "goals.sqlite"

        f1.write_text(json.dumps(self.sample_goals[:2]), encoding="utf-8")
        # p2 updates goal_01 progress from 12 to 18
        updated_goal = dict(self.sample_goals[0])
        updated_goal["current_value"] = 18
        f2.write_text(json.dumps([updated_goal, self.sample_goals[2]]), encoding="utf-8")

        loaded, added, total = g2sql.load(str(db), [str(f1), str(f2)])
        self.assertEqual(loaded, 4)
        self.assertEqual(total, 3)

        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()

        # Check indexes exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        self.assertIn("goals_is_active", indexes)
        self.assertIn("goals_is_completed", indexes)
        self.assertIn("goals_goal_type", indexes)
        self.assertIn("goals_created_at", indexes)

        # Verify updated progress on goal_01 (18 / 20 = 90%)
        cursor.execute("SELECT current_value, progress_pct FROM goals WHERE id='goal_01'")
        row = cursor.fetchone()
        self.assertEqual(row[0], 18.0)
        self.assertEqual(row[1], 90.0)

        conn.close()

    def test_main_cli_execution(self):
        src = self.tmp / "cli_input.json"
        db = self.tmp / "cli.sqlite"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        # CLI happy path
        ret = g2sql.main([str(db), str(src)])
        self.assertEqual(ret, 0)
        self.assertTrue(db.exists())

        # CLI missing arguments
        ret_missing = g2sql.main([str(db)])
        self.assertEqual(ret_missing, 1)

        # CLI load error raises SystemExit
        with self.assertRaises(SystemExit) as ctx:
            g2sql.main([str(self.tmp / ".." / "bad.sqlite"), str(src)])
        self.assertIn("SQLite load failed", str(ctx.exception))

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_goals).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            rows = g2sql.rows_from("-")
            self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()
