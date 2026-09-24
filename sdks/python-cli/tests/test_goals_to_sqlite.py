#!/usr/bin/env python3
"""
Unit tests for sdks/python-cli/examples/goals_to_sqlite.py
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goals_to_sqlite import (
    compute_progress,
    load,
    normalize_status,
    rows_from,
    text,
    utc_stamp,
)


class TestGoalsToSqlite(unittest.TestCase):

    def test_text_helper(self):
        self.assertIsNone(text(None))
        self.assertEqual(text("  learn   rust \n"), "learn rust")
        self.assertEqual(text(42), "42")
        self.assertEqual(text(["reading", "books"]), '["reading", "books"]')
        self.assertEqual(text({"key": "value"}), '{"key": "value"}')

    def test_utc_stamp(self):
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))
        self.assertIsNone(utc_stamp("not-a-date"))

        # UTC format
        ts = utc_stamp("2026-09-20T14:30:00Z")
        self.assertEqual(ts, "2026-09-20 14:30:00")

        # Offset timezone converted to UTC
        ts_offset = utc_stamp("2026-09-20T22:30:00+08:00")
        self.assertEqual(ts_offset, "2026-09-20 14:30:00")

    def test_normalize_status(self):
        self.assertEqual(normalize_status({"status": "Active"}), "active")
        self.assertEqual(normalize_status({"status": "COMPLETED"}), "completed")
        self.assertEqual(normalize_status({"is_active": True}), "active")
        self.assertEqual(normalize_status({"is_active": False}), "completed")
        self.assertEqual(normalize_status({}), "active")

    def test_compute_progress(self):
        # Completed status overrides
        self.assertEqual(compute_progress({"goal_type": "numeric", "current_value": 2, "target_value": 10}, "completed"), 100.0)

        # Qualitative
        self.assertIsNone(compute_progress({"goal_type": "qualitative"}, "active"))

        # Boolean
        self.assertEqual(compute_progress({"goal_type": "boolean", "current_value": 0, "target_value": 1}, "active"), 0.0)
        self.assertEqual(compute_progress({"goal_type": "boolean", "current_value": 1, "target_value": 1}, "active"), 100.0)

        # Numeric standard
        self.assertEqual(compute_progress({"goal_type": "numeric", "current_value": 5, "target_value": 10, "min_value": 0}, "active"), 50.0)
        self.assertEqual(compute_progress({"goal_type": "scale", "current_value": 7, "target_value": 10, "min_value": 0}, "active"), 70.0)

        # Bounds (capped at 0 - 100)
        self.assertEqual(compute_progress({"goal_type": "numeric", "current_value": 15, "target_value": 10}, "active"), 100.0)
        self.assertEqual(compute_progress({"goal_type": "numeric", "current_value": -5, "target_value": 10, "min_value": 0}, "active"), 0.0)

    def test_load_and_deduplicate(self):
        f1_data = [
            {"id": "g1", "title": "Read 25 books", "goal_type": "numeric", "current_value": 5, "target_value": 25, "unit": "books", "status": "active"},
            {"id": "g2", "title": "Learn Rust", "goal_type": "qualitative", "status": "active"}
        ]
        f2_data = [
            {"id": "g2", "title": "Learn Rust and Axum", "goal_type": "qualitative", "status": "completed"},
            {"id": "g3", "title": "Run 100km", "goal_type": "numeric", "current_value": 20, "target_value": 100, "unit": "km", "status": "active"}
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_goals.sqlite")
            p1 = Path(tmpdir) / "p1.json"
            p2 = Path(tmpdir) / "p2.json"
            p1.write_text(json.dumps(f1_data), encoding="utf-8")
            p2.write_text(json.dumps(f2_data), encoding="utf-8")

            loaded, added, total = load(db_path, [str(p1), str(p2)])
            self.assertEqual(loaded, 4)
            self.assertEqual(added, 3)
            self.assertEqual(total, 3)

            # Query database to confirm replacement
            conn = sqlite3.connect(db_path)
            row_g2 = conn.execute("SELECT title, status, progress_percentage FROM goals WHERE id = 'g2'").fetchone()
            self.assertEqual(row_g2[0], "Learn Rust and Axum")
            self.assertEqual(row_g2[1], "completed")
            self.assertEqual(row_g2[2], 100.0)

            # Verify idempotence on reloading same file
            loaded2, added2, total2 = load(db_path, [str(p1)])
            self.assertEqual(loaded2, 2)
            self.assertEqual(added2, 0)
            self.assertEqual(total2, 3)
            conn.close()

    def test_load_stdin(self):
        data = [{"id": "g_stdin", "title": "Piped goal", "status": "active"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "stdin.sqlite")
            with patch("sys.stdin", io.StringIO(json.dumps(data))):
                loaded, added, total = load(db_path, ["-"])
                self.assertEqual(loaded, 1)
                self.assertEqual(added, 1)
                self.assertEqual(total, 1)

    def test_schema_and_indexes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "schema_check.sqlite")
            load(db_path, [])
            conn = sqlite3.connect(db_path)

            # Check table exists
            table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='goals'").fetchone()
            self.assertIsNotNone(table)

            # Check column names
            cols = [info[1] for info in conn.execute("PRAGMA table_info(goals)").fetchall()]
            expected_cols = [
                "id", "title", "status", "goal_type", "current_value",
                "target_value", "min_value", "unit", "progress_percentage",
                "created_at", "updated_at", "raw_json"
            ]
            self.assertEqual(cols, expected_cols)

            # Check indexes
            indexes = [info[1] for info in conn.execute("PRAGMA index_list(goals)").fetchall()]
            self.assertIn("idx_goals_status", indexes)
            self.assertIn("idx_goals_type", indexes)
            self.assertIn("idx_goals_created_at", indexes)
            conn.close()

    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "invalid.sqlite")

            # Missing file
            with self.assertRaises(FileNotFoundError):
                load(db_path, [str(Path(tmpdir) / "nonexistent.json")])

            # Corrupted JSON
            p_bad = Path(tmpdir) / "bad.json"
            p_bad.write_text("{bad", encoding="utf-8")
            with self.assertRaises(ValueError):
                load(db_path, [str(p_bad)])

            # Missing ID
            p_noid = Path(tmpdir) / "no_id.json"
            p_noid.write_text('[{"title": "No ID goal"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load(db_path, [str(p_noid)])

            # Non-dict item
            p_nondict = Path(tmpdir) / "non_dict.json"
            p_nondict.write_text('["just a string"]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load(db_path, [str(p_nondict)])

    def test_sql_analytical_queries(self):
        sample_goals = [
            {"id": "g1", "title": "Gym visits", "goal_type": "numeric", "current_value": 15, "target_value": 30, "unit": "sessions", "status": "active", "created_at": "2026-09-01T10:00:00Z"},
            {"id": "g2", "title": "Complete course", "goal_type": "numeric", "current_value": 100, "target_value": 100, "unit": "%", "status": "completed", "created_at": "2026-09-02T10:00:00Z"},
            {"id": "g3", "title": "Daily meditation", "goal_type": "boolean", "current_value": 1, "target_value": 1, "status": "active", "created_at": "2026-09-03T10:00:00Z"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "query_test.sqlite")
            p = Path(tmpdir) / "goals.json"
            p.write_text(json.dumps(sample_goals), encoding="utf-8")
            load(db_path, [str(p)])

            conn = sqlite3.connect(db_path)

            # Test GROUP BY status
            res_status = dict(conn.execute("SELECT status, COUNT(*) FROM goals GROUP BY status").fetchall())
            self.assertEqual(res_status["active"], 2)
            self.assertEqual(res_status["completed"], 1)

            # Test AVG progress for active goals
            avg_progress = conn.execute("SELECT AVG(progress_percentage) FROM goals WHERE status = 'active'").fetchone()[0]
            # g1 is 50.0%, g3 is 100.0% -> avg is 75.0%
            self.assertAlmostEqual(avg_progress, 75.0)

            # Test JSON extraction
            unit_val = conn.execute("SELECT json_extract(raw_json, '$.unit') FROM goals WHERE id = 'g1'").fetchone()[0]
            self.assertEqual(unit_val, "sessions")

            conn.close()


if __name__ == "__main__":
    unittest.main()
