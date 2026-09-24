import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goals_to_sqlite import load, compute_progress_pct, boolean_to_int, utc_stamp, float_val


class TestGoalsToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_goals.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compute_progress_pct(self):
        self.assertEqual(compute_progress_pct(50, 100), 50.0)
        self.assertEqual(compute_progress_pct(150, 100), 150.0)
        self.assertEqual(compute_progress_pct(1, 3), 33.33)
        self.assertEqual(compute_progress_pct(0, 100), 0.0)
        self.assertEqual(compute_progress_pct(50, 0), 0.0)
        self.assertEqual(compute_progress_pct(50, -10), 0.0)
        self.assertEqual(compute_progress_pct(None, 100), 0.0)
        self.assertEqual(compute_progress_pct(50, None), 0.0)

    def test_utc_stamp(self):
        self.assertEqual(utc_stamp("2026-09-24T12:00:00Z"), "2026-09-24 12:00:00")
        self.assertEqual(utc_stamp("2026-09-24T14:00:00+02:00"), "2026-09-24 12:00:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp("invalid"))

    def test_boolean_to_int(self):
        self.assertEqual(boolean_to_int(True), 1)
        self.assertEqual(boolean_to_int(False), 0)
        self.assertEqual(boolean_to_int("active"), 1)
        self.assertEqual(boolean_to_int("true"), 1)
        self.assertEqual(boolean_to_int("false"), 0)

    def test_float_val(self):
        self.assertEqual(float_val(10), 10.0)
        self.assertEqual(float_val("25.5"), 25.5)
        self.assertIsNone(float_val(None))
        self.assertIsNone(float_val("abc"))

    def test_load_and_query(self):
        sample_goals = [
            {
                "id": "goal_1",
                "title": "Drink 2L water daily",
                "goal_type": "habit",
                "current_value": 1.5,
                "target_value": 2.0,
                "unit": "liters",
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-24T08:00:00Z"
            },
            {
                "id": "goal_2",
                "title": "Read 12 books",
                "goal_type": "reading",
                "current_value": 12,
                "target_value": 12,
                "unit": "books",
                "is_active": False,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-09-24T09:00:00Z"
            }
        ]
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(sample_goals), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Check progress_pct computed
        cursor.execute("SELECT progress_pct FROM goals WHERE id = 'goal_1'")
        self.assertEqual(cursor.fetchone()[0], 75.0)

        # Check completed goal
        cursor.execute("SELECT progress_pct, is_active FROM goals WHERE id = 'goal_2'")
        row = cursor.fetchone()
        self.assertEqual(row[0], 100.0)
        self.assertEqual(row[1], 0)

        conn.close()

    def test_idempotence_and_replacement(self):
        batch1 = [
            {"id": "goal_1", "title": "Run 50km", "current_value": 10, "target_value": 50}
        ]
        batch2 = [
            {"id": "goal_1", "title": "Run 50km", "current_value": 25, "target_value": 50}
        ]
        f1 = self.dir_path / "b1.json"
        f2 = self.dir_path / "b2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 1)
        self.assertEqual(added, 0)  # existing row updated
        self.assertEqual(total, 1)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT current_value, progress_pct FROM goals WHERE id = 'goal_1'")
        row = cursor.fetchone()
        self.assertEqual(row[0], 25.0)
        self.assertEqual(row[1], 50.0)
        conn.close()

    def test_wrapped_dict_payload(self):
        wrapped = {
            "goals": [
                {"id": "g_wrapped", "title": "Wrapped Goal", "current_value": 5, "target_value": 10}
            ]
        }
        wf = self.dir_path / "wrapped.json"
        wf.write_text(json.dumps(wrapped), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(wf)])
        self.assertEqual(loaded, 1)
        self.assertEqual(total, 1)

    def test_missing_id_raises(self):
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps([{"title": "No ID"}]), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])


if __name__ == "__main__":
    unittest.main()
