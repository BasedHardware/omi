import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import load, SCHEMA, boolean_to_int, utc_stamp


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_memories.sqlite"

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
        self.assertEqual(boolean_to_int(None), 0)

    def test_load_and_query(self):
        sample_memories = [
            {
                "id": "mem_1",
                "content": "User prefers dark mode and Python over TypeScript",
                "category": "preferences",
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
                "deleted": False,
                "conversation_id": "conv_101",
            },
            {
                "id": "mem_2",
                "content": "Deploying smart contract on Base mainnet",
                "category": "work",
                "created_at": "2026-09-21T09:00:00Z",
                "updated_at": "2026-09-21T09:00:00Z",
                "deleted": False,
                "conversation_id": "conv_102",
            },
        ]

        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(sample_memories), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        rows = cur.execute("SELECT id, content, category, deleted FROM memories ORDER BY id").fetchall()
        conn.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "mem_1")
        self.assertEqual(rows[0][1], "User prefers dark mode and Python over TypeScript")
        self.assertEqual(rows[0][2], "preferences")
        self.assertEqual(rows[0][3], 0)

    def test_idempotent_upsert(self):
        initial = [{"id": "mem_1", "content": "Initial note", "category": "general"}]
        updated = [{"id": "mem_1", "content": "Updated note", "category": "work"}]

        f1 = self.dir_path / "f1.json"
        f2 = self.dir_path / "f2.json"
        f1.write_text(json.dumps(initial), encoding="utf-8")
        f2.write_text(json.dumps(updated), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 1)
        self.assertEqual(added, 0)
        self.assertEqual(total, 1)

        conn = sqlite3.connect(self.db_path)
        content, category = conn.execute("SELECT content, category FROM memories WHERE id = 'mem_1'").fetchone()
        conn.close()
        self.assertEqual(content, "Updated note")
        self.assertEqual(category, "work")

    def test_invalid_input_missing_id(self):
        invalid = [{"content": "No ID here"}]
        f = self.dir_path / "invalid.json"
        f.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(f)])


if __name__ == "__main__":
    unittest.main()
