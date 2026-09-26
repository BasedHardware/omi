import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_sqlite import (
    SCHEMA,
    boolean_to_int,
    load,
    row_from_goal,
    to_float,
    utc_stamp,
)


class TestGoalsToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_goals.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T10:30:00Z"), "2026-09-20 10:30:00")
        self.assertEqual(utc_stamp("2026-09-20T15:30:00+05:00"), "2026-09-20 10:30:00")
        self.assertEqual(utc_stamp("2026-09-20T06:30:00-04:00"), "2026-09-20 10:30:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp("not-a-valid-date"))

    def test_to_float_coercion(self):
        self.assertEqual(to_float(42), 42.0)
        self.assertEqual(to_float(3.14), 3.14)
        self.assertEqual(to_float("100.5"), 100.5)
        self.assertIsNone(to_float(None))
        self.assertIsNone(to_float("invalid"))

    def test_boolean_to_int(self):
        self.assertEqual(boolean_to_int(True), 1)
        self.assertEqual(boolean_to_int(False), 0)
        self.assertEqual(boolean_to_int("true"), 1)
        self.assertEqual(boolean_to_int("1"), 1)
        self.assertEqual(boolean_to_int("yes"), 1)
        self.assertEqual(boolean_to_int("active"), 1)
        self.assertEqual(boolean_to_int("false"), 0)
        self.assertEqual(boolean_to_int(None), 0)

    def test_load_and_query_idempotency(self):
        sample_goals = [
            {
                "id": "goal_1",
                "title": "Drink 2L water daily",
                "goal_type": "numeric",
                "current_value": 1.5,
                "target_value": 2.0,
                "min_value": 0.0,
                "max_value": 3.0,
                "unit": "liters",
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T12:00:00Z",
            },
            {
                "id": "goal_2",
                "title": "Read 30 mins before sleep",
                "goal_type": "boolean",
                "current_value": 1.0,
                "target_value": 1.0,
                "min_value": 0.0,
                "max_value": 1.0,
                "unit": None,
                "is_active": False,
                "created_at": "2026-09-19T09:00:00Z",
                "updated_at": "2026-09-19T09:30:00Z",
            },
        ]
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(sample_goals), encoding="utf-8")

        loaded, added, total = load(self.db_path, [json_file])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        # Re-run same file: should update 0 new, 2 updated
        loaded_re, added_re, total_re = load(self.db_path, [json_file])
        self.assertEqual(loaded_re, 2)
        self.assertEqual(added_re, 0)
        self.assertEqual(total_re, 2)

        # Verify SQL queries
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT title, current_value, unit FROM goals WHERE id = 'goal_1'").fetchone()
            self.assertEqual(row, ("Drink 2L water daily", 1.5, "liters"))

            active_count = conn.execute("SELECT COUNT(*) FROM goals WHERE is_active = 1").fetchone()[0]
            self.assertEqual(active_count, 1)
        finally:
            conn.close()

    def test_multi_page_dedup_prefers_newer_updated(self):
        page1 = [
            {
                "id": "goal_dup",
                "title": "Old Title",
                "current_value": 5,
                "target_value": 10,
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T09:00:00Z",
            }
        ]
        page2 = [
            {
                "id": "goal_dup",
                "title": "Updated Title",
                "current_value": 8,
                "target_value": 10,
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T11:00:00Z",
            }
        ]
        p1 = self.dir_path / "page1.json"
        p2 = self.dir_path / "page2.json"
        p1.write_text(json.dumps(page1), encoding="utf-8")
        p2.write_text(json.dumps(page2), encoding="utf-8")

        load(self.db_path, [p1, p2])
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT title, current_value FROM goals WHERE id = 'goal_dup'").fetchone()
            self.assertEqual(row, ("Updated Title", 8.0))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
