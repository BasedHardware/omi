import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_sqlite import (
    boolean_to_int,
    compute_progress_pct,
    load,
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

    def test_converters(self):
        self.assertEqual(to_float(42), 42.0)
        self.assertEqual(to_float("12.5"), 12.5)
        self.assertIsNone(to_float("abc"))
        self.assertIsNone(to_float(None))

        self.assertEqual(compute_progress_pct(5, 10), 50.0)
        self.assertIsNone(compute_progress_pct(5, 0))

        self.assertEqual(boolean_to_int(True), 1)
        self.assertEqual(boolean_to_int(False), 0)
        self.assertEqual(boolean_to_int("true"), 1)
        self.assertEqual(boolean_to_int("false"), 0)

        self.assertEqual(utc_stamp("2026-09-20T10:00:00Z"), "2026-09-20 10:00:00")
        self.assertIsNone(utc_stamp(None))

    def test_load_and_query(self):
        goals = [
            {
                "id": "g_1",
                "title": "Cycle 100km",
                "goal_type": "numeric",
                "current_value": 75,
                "target_value": 100,
                "unit": "km",
                "min_value": 0,
                "max_value": 100,
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
            },
            {
                "id": "g_2",
                "title": "Learn Rust",
                "goal_type": "scale",
                "current_value": 3,
                "target_value": 10,
                "unit": "level",
                "min_value": 1,
                "max_value": 10,
                "is_active": False,
                "created_at": "2026-09-18T08:00:00Z",
                "updated_at": "2026-09-19T08:00:00Z",
            },
        ]
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(goals), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Query active goals
        cursor.execute("SELECT progress_pct FROM goals WHERE is_active = 1")
        self.assertEqual(cursor.fetchone()[0], 75.0)

        # Raw json extraction
        cursor.execute("SELECT json_extract(raw_json, '$.unit') FROM goals WHERE id = 'g_1'")
        self.assertEqual(cursor.fetchone()[0], "km")

        conn.close()

    def test_idempotence(self):
        batch1 = [{"id": "g_1", "title": "Run", "current_value": 5, "target_value": 10, "is_active": True}]
        batch2 = [
            {"id": "g_1", "title": "Run", "current_value": 10, "target_value": 10, "is_active": False},
            {"id": "g_2", "title": "Swim", "current_value": 2, "target_value": 5, "is_active": True},
        ]
        f1 = self.dir_path / "b1.json"
        f2 = self.dir_path / "b2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 2)
        self.assertEqual(added, 1)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT current_value, is_active FROM goals WHERE id = 'g_1'")
        row = cursor.fetchone()
        self.assertEqual(row[0], 10.0)
        self.assertEqual(row[1], 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
