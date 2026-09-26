"""Tests for Omi goals to SQLite exporter example script."""

from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Load goals_to_sqlite example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_sqlite.py"
spec = importlib.util.spec_from_file_location("goals_to_sqlite", script_path)
g2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2s)


class TestGoalsToSQLite(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_goals.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_export_goals_basic_schema_and_types(self) -> None:
        goals = [
            {
                "id": "goal-1",
                "title": "Drink Water",
                "goal_type": "numeric",
                "target_value": 3.5,
                "current_value": 1.5,
                "min_value": 0,
                "max_value": 5,
                "unit": "liters",
                "is_active": True,
                "created_at": "2026-04-20T10:30:00Z",
                "updated_at": "2026-04-20T12:00:00Z",
            }
        ]

        count = g2s.export_goals_to_sqlite(goals, self.db_path)
        self.assertEqual(count, 1)

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        row = cursor.execute("SELECT * FROM goals WHERE id = 'goal-1'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["title"], "Drink Water")
        self.assertEqual(row["goal_type"], "numeric")
        self.assertEqual(row["target_value"], 3.5)
        self.assertEqual(row["current_value"], 1.5)
        self.assertEqual(row["unit"], "liters")
        self.assertEqual(row["is_active"], 1)
        self.assertEqual(row["created_at"], "2026-04-20 10:30:00")
        self.assertEqual(row["updated_at"], "2026-04-20 12:00:00")

        # Verify index creation
        indices = [r[1] for r in cursor.execute("PRAGMA index_list('goals')").fetchall()]
        self.assertIn("idx_goals_is_active", indices)
        self.assertIn("idx_goals_goal_type", indices)

        conn.close()

    def test_timestamp_normalization(self) -> None:
        self.assertEqual(
            g2s.normalize_timestamp("2026-05-15T08:00:00Z"),
            "2026-05-15 08:00:00",
        )
        self.assertEqual(
            g2s.normalize_timestamp("2026-05-15T13:30:00+05:30"),
            "2026-05-15 08:00:00",
        )
        self.assertIsNone(g2s.normalize_timestamp(None))

    def test_deduplication_and_upsert(self) -> None:
        goal_v1 = [
            {
                "id": "goal-dupe",
                "title": "Read 20 pages",
                "goal_type": "numeric",
                "target_value": 20,
                "current_value": 5,
                "is_active": True,
            }
        ]
        goal_v2 = [
            {
                "id": "goal-dupe",
                "title": "Read 20 pages (Updated)",
                "goal_type": "numeric",
                "target_value": 20,
                "current_value": 15,
                "is_active": True,
            }
        ]

        g2s.export_goals_to_sqlite(goal_v1, self.db_path)
        g2s.export_goals_to_sqlite(goal_v2, self.db_path)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        rows = cursor.execute("SELECT title, current_value FROM goals WHERE id = 'goal-dupe'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "Read 20 pages (Updated)")
        self.assertEqual(rows[0][1], 15.0)
        conn.close()

    def test_qualitative_goals_with_null_metrics(self) -> None:
        goals = [
            {
                "id": "goal-qual",
                "title": "Meditate daily",
                "goal_type": None,
                "target_value": None,
                "current_value": None,
                "is_active": False,
            }
        ]

        g2s.export_goals_to_sqlite(goals, self.db_path)

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.cursor().execute("SELECT * FROM goals WHERE id = 'goal-qual'").fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row["goal_type"])
        self.assertIsNone(row["target_value"])
        self.assertIsNone(row["current_value"])
        self.assertEqual(row["is_active"], 0)
        conn.close()

    def test_raw_json_preservation_and_json_extract(self) -> None:
        goal = {
            "id": "goal-raw",
            "title": "Learn Rust",
            "custom_metadata": {"difficulty": "hard", "priority": 1},
        }

        g2s.export_goals_to_sqlite([goal], self.db_path)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        val = cursor.execute(
            "SELECT json_extract(raw_json, '$.custom_metadata.difficulty') FROM goals WHERE id = 'goal-raw'"
        ).fetchone()
        self.assertEqual(val[0], "hard")
        conn.close()

    def test_file_input_and_stdin_input(self) -> None:
        goals = [{"id": "g-file", "title": "From File", "is_active": True}]
        json_file = Path(self.temp_dir.name) / "goals.json"
        json_file.write_text(json.dumps(goals), encoding="utf-8")

        # Test from file
        count_file = g2s.export_goals_to_sqlite(str(json_file), self.db_path)
        self.assertEqual(count_file, 1)

        # Test from stdin
        stdin_goals = [{"id": "g-stdin", "title": "From Stdin", "is_active": True}]
        with patch("sys.stdin", io.StringIO(json.dumps(stdin_goals))):
            count_stdin = g2s.export_goals_to_sqlite("-", self.db_path)
            self.assertEqual(count_stdin, 1)

        conn = sqlite3.connect(str(self.db_path))
        ids = [r[0] for r in conn.cursor().execute("SELECT id FROM goals ORDER BY id").fetchall()]
        self.assertEqual(ids, ["g-file", "g-stdin"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
