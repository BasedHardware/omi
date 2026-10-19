import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import load, SCHEMA, boolean_to_int, utc_stamp, format_tags


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

    def test_format_tags(self):
        self.assertEqual(format_tags(["work", "ai", "project"]), "work, ai, project")
        self.assertEqual(format_tags("solo-tag"), "solo-tag")
        self.assertIsNone(format_tags(None))
        self.assertEqual(format_tags([]), "")

    def test_load_and_query(self):
        sample_memories = [
            {
                "id": "mem_1",
                "content": "User prefers concise answers with Python examples.",
                "category": "Interests",
                "tags": ["coding", "python"],
                "visibility": "private",
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
                "is_user_created": True,
            },
            {
                "id": "mem_2",
                "content": "Working on decentralized protocol bounties.",
                "category": "work",
                "tags": ["bounties", "web3"],
                "visibility": "public",
                "created_at": "2026-09-20T09:00:00Z",
                "updated_at": "2026-09-20T09:30:00Z",
                "is_user_created": False,
            },
        ]
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(sample_memories), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        # Verify in SQLite
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Check category query (case normalized to lowercase)
        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'interests'")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Check tags filter with LIKE
        cursor.execute("SELECT content FROM memories WHERE tags LIKE '%python%'")
        self.assertEqual(cursor.fetchone()[0], "User prefers concise answers with Python examples.")

        # Check raw json extraction
        cursor.execute("SELECT json_extract(raw_json, '$.category') FROM memories WHERE id = 'mem_1'")
        self.assertEqual(cursor.fetchone()[0], "Interests")

        conn.close()

    def test_envelope_unwrapping(self):
        envelope = {
            "memories": [
                {
                    "id": "mem_env_1",
                    "content": "Learned about SQLite indexing strategies.",
                    "category": "learnings",
                    "created_at": "2026-09-21T10:00:00Z",
                }
            ]
        }
        json_file = self.dir_path / "envelope.json"
        json_file.write_text(json.dumps(envelope), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(added, 1)
        self.assertEqual(total, 1)

    def test_empty_wrappers(self):
        for wrapper_key in ("memories", "items", "data"):
            file_path = self.dir_path / f"empty_{wrapper_key}.json"
            file_path.write_text(json.dumps({wrapper_key: []}), encoding="utf-8")
            loaded, added, total = load(str(self.db_path), [str(file_path)])
            self.assertEqual((loaded, added, total), (0, 0, 0))

        bare_path = self.dir_path / "empty_bare.json"
        bare_path.write_text(json.dumps([]), encoding="utf-8")
        loaded, added, total = load(str(self.db_path), [str(bare_path)])
        self.assertEqual((loaded, added, total), (0, 0, 0))

    def test_single_object_input(self):
        single_obj = {
            "id": "single_mem",
            "content": "Solo memory object import",
            "category": "notes",
            "created_at": "2026-09-22T10:00:00Z",
        }
        f = self.dir_path / "single.json"
        f.write_text(json.dumps(single_obj), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(f)])
        self.assertEqual(loaded, 1)
        self.assertEqual(added, 1)
        self.assertEqual(total, 1)

    def test_idempotence_and_replacement(self):
        batch1 = [
            {"id": "mem_1", "content": "Initial thought", "category": "notes", "created_at": "2026-09-20T08:00:00Z"}
        ]
        batch2 = [
            {
                "id": "mem_1",
                "content": "Updated refined thought",
                "category": "learnings",
                "created_at": "2026-09-20T08:00:00Z",
            },
            {"id": "mem_2", "content": "Second thought", "category": "work", "created_at": "2026-09-20T10:00:00Z"},
        ]
        f1 = self.dir_path / "b1.json"
        f2 = self.dir_path / "b2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 2)
        self.assertEqual(added, 1)  # Only mem_2 is new
        self.assertEqual(total, 2)

        # Check that mem_1 content is updated
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT content, category FROM memories WHERE id = 'mem_1'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "Updated refined thought")
        self.assertEqual(row[1], "learnings")
        conn.close()

    def test_missing_id_raises(self):
        invalid_data = [{"content": "No ID memory", "category": "misc"}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(invalid_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])


if __name__ == "__main__":
    unittest.main()
