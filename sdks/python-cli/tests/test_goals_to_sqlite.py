import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add parent directories to import path if needed
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goals_to_sqlite import load, SCHEMA, boolean_to_int, float_val, utc_stamp


class TestGoalsToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_goals.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T10:30:00Z"), "2026-09-20 10:30:00")
        self.assertEqual(utc_stamp("2026-09-20T12:30:00+02:00"), "2026-09-20 10:30:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp("invalid-date"))

    def test_boolean_to_int(self):
        self.assertEqual(boolean_to_int(True), 1)
        self.assertEqual(boolean_to_int(False), 0)
        self.assertEqual(boolean_to_int("true"), 1)
        self.assertEqual(boolean_to_int("1"), 1)
        self.assertEqual(boolean_to_int("false"), 0)
        self.assertEqual(boolean_to_int(None, default=1), 1)

    def test_float_val(self):
        self.assertEqual(float_val(10.5), 10.5)
        self.assertEqual(float_val("42"), 42.0)
        self.assertEqual(float_val(None, default=5.0), 5.0)
        self.assertEqual(float_val("invalid", default=0.0), 0.0)

    def test_load_and_query(self):
        sample_goals = [
            {
                "id": "goal_1",
                "title": "Read 20 books this year",
                "goal_type": "numeric",
                "target_value": 20.0,
                "current_value": 8.0,
                "min_value": 0.0,
                "max_value": 50.0,
                "unit": "books",
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
            },
            {
                "id": "goal_2",
                "title": "Daily Meditation",
                "goal_type": "boolean",
                "target_value": 1.0,
                "current_value": 1.0,
                "min_value": 0.0,
                "max_value": 1.0,
                "unit": None,
                "is_active": True,
                "created_at": "2026-09-20T09:00:00Z",
                "updated_at": "2026-09-20T09:30:00Z",
            },
            {
                "id": "goal_3",
                "title": "Old Archive Goal",
                "goal_type": "scale",
                "target_value": 10.0,
                "current_value": 10.0,
                "min_value": 0.0,
                "max_value": 10.0,
                "unit": "pts",
                "is_active": False,
                "created_at": "2026-09-19T09:00:00Z",
                "updated_at": "2026-09-19T09:30:00Z",
            }
        ]
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(sample_goals), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 3)
        self.assertEqual(added, 3)
        self.assertEqual(total, 3)

        # Verify in SQLite
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Check count of active goals
        cursor.execute("SELECT COUNT(*) FROM goals WHERE is_active = 1")
        self.assertEqual(cursor.fetchone()[0], 2)

        # Check numeric progress
        cursor.execute("SELECT current_value, target_value, unit FROM goals WHERE id = 'goal_1'")
        row = cursor.fetchone()
        self.assertEqual(row[0], 8.0)
        self.assertEqual(row[1], 20.0)
        self.assertEqual(row[2], "books")

        # Check raw json extraction
        cursor.execute("SELECT json_extract(raw_json, '$.title') FROM goals WHERE id = 'goal_1'")
        self.assertEqual(cursor.fetchone()[0], "Read 20 books this year")

        conn.close()

    def test_idempotence_and_replacement(self):
        batch1 = [
            {
                "id": "goal_1",
                "title": "Run 100km",
                "goal_type": "numeric",
                "target_value": 100.0,
                "current_value": 25.0,
                "min_value": 0.0,
                "max_value": 100.0,
                "unit": "km",
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
            }
        ]
        batch2 = [
            {
                "id": "goal_1",
                "title": "Run 100km",
                "goal_type": "numeric",
                "target_value": 100.0,
                "current_value": 50.0,
                "min_value": 0.0,
                "max_value": 100.0,
                "unit": "km",
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
            },
            {
                "id": "goal_2",
                "title": "Sleep 8 hours",
                "goal_type": "scale",
                "target_value": 8.0,
                "current_value": 7.0,
                "min_value": 0.0,
                "max_value": 10.0,
                "unit": "hours",
                "is_active": True,
                "created_at": "2026-09-20T10:00:00Z",
            }
        ]
        f1 = self.dir_path / "b1.json"
        f2 = self.dir_path / "b2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 2)
        self.assertEqual(added, 1)  # Only goal_2 is new
        self.assertEqual(total, 2)

        # Check that goal_1 updated current_value to 50.0
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT current_value FROM goals WHERE id = 'goal_1'")
        self.assertEqual(cursor.fetchone()[0], 50.0)
        conn.close()

    def test_missing_id_raises(self):
        invalid_data = [{"title": "No ID goal", "goal_type": "scale"}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(invalid_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])


if __name__ == "__main__":
    unittest.main()
