import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add parent directories to import path if needed
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import load, SCHEMA, boolean_to_int, utc_stamp, tags_to_text


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
        self.assertEqual(boolean_to_int("yes"), 1)
        self.assertEqual(boolean_to_int("false"), 0)
        self.assertEqual(boolean_to_int(None), 0)

    def test_tags_to_text(self):
        self.assertEqual(tags_to_text(["python", "sqlite"]), '["python", "sqlite"]')
        self.assertEqual(tags_to_text('["ai", "omi"]'), '["ai", "omi"]')
        self.assertEqual(tags_to_text("work, productivity"), '["work", "productivity"]')
        self.assertEqual(tags_to_text(None), "[]")
        self.assertEqual(tags_to_text([]), "[]")

    def test_load_and_query(self):
        sample_memories = [
            {
                "id": "mem_1",
                "content": "Prefers dark mode in code editors",
                "category": "preferences",
                "visibility": "private",
                "tags": ["ui", "editor"],
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
                "manually_added": True,
                "reviewed": False,
                "edited": False,
            },
            {
                "id": "mem_2",
                "content": "Worked on Omi firmware Bluetooth LE stack",
                "category": "work",
                "visibility": "public",
                "tags": ["ble", "firmware"],
                "created_at": "2026-09-20T09:00:00Z",
                "updated_at": "2026-09-20T09:30:00Z",
                "manually_added": False,
                "reviewed": True,
                "edited": True,
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

        # Check category filtering
        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'work'")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Check reviewed status
        cursor.execute("SELECT COUNT(*) FROM memories WHERE reviewed = 1")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Check raw json extraction
        cursor.execute("SELECT json_extract(raw_json, '$.content') FROM memories WHERE id = 'mem_1'")
        self.assertEqual(cursor.fetchone()[0], "Prefers dark mode in code editors")

        # Check json_each expansion on tags
        cursor.execute(
            "SELECT m.id FROM memories m, json_each(m.tags) tag WHERE tag.value = 'ble'"
        )
        self.assertEqual(cursor.fetchone()[0], "mem_2")

        conn.close()

    def test_idempotence_and_replacement(self):
        batch1 = [
            {"id": "mem_1", "content": "Initial fact", "category": "general", "created_at": "2026-09-20T08:00:00Z"}
        ]
        batch2 = [
            {"id": "mem_1", "content": "Updated fact", "category": "general", "edited": True, "created_at": "2026-09-20T08:00:00Z"},
            {"id": "mem_2", "content": "Another fact", "category": "skills", "created_at": "2026-09-20T10:00:00Z"}
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

        # Check that mem_1 is updated
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT content, edited FROM memories WHERE id = 'mem_1'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "Updated fact")
        self.assertEqual(row[1], 1)
        conn.close()

    def test_wrapped_dict_formats(self):
        sample = [{"id": "mem_wrap", "content": "Wrapped item", "category": "notes"}]
        for wrapper_key in ("memories", "items", "data"):
            file_path = self.dir_path / f"wrap_{wrapper_key}.json"
            file_path.write_text(json.dumps({wrapper_key: sample}), encoding="utf-8")
            loaded, added, total = load(str(self.db_path), [str(file_path)])
            self.assertEqual(loaded, 1)

    def test_utf8_bom_handling(self):
        sample = [{"id": "mem_bom", "content": "BOM fact", "category": "notes"}]
        bom_payload = "\ufeff" + json.dumps(sample)
        bom_file = self.dir_path / "bom.json"
        bom_file.write_bytes(bom_payload.encode("utf-8"))

        loaded, added, total = load(str(self.db_path), [str(bom_file)])
        self.assertEqual(loaded, 1)

    def test_missing_id_raises(self):
        invalid_data = [{"content": "No ID memory", "category": "general"}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(invalid_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])


if __name__ == "__main__":
    unittest.main()
