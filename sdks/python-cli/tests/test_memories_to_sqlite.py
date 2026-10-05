import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add examples and tests directory to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import (
    _SQLITE_MAGIC,
    SCHEMA,
    import_memories_to_sqlite,
    load_input_json,
    normalize_utc_timestamp,
    prepare_memory_record,
    serialize_tags,
    strip_surrogates,
    validate_db_path,
)


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_memories.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_strip_surrogates(self):
        self.assertEqual(strip_surrogates("Regular text"), "Regular text")
        self.assertEqual(strip_surrogates(None), None)
        # Test surrogate character (\ud800)
        bad_text = "Hello \ud800 World"
        cleaned = strip_surrogates(bad_text)
        self.assertNotIn("\ud800", cleaned)
        self.assertTrue(cleaned.startswith("Hello"))

    def test_normalize_utc_timestamp(self):
        self.assertEqual(normalize_utc_timestamp("2026-10-04T12:00:00Z"), "2026-10-04 12:00:00")
        self.assertEqual(normalize_utc_timestamp("2026-10-04T15:00:00+03:00"), "2026-10-04 12:00:00")
        self.assertIsNone(normalize_utc_timestamp(None))
        self.assertIsNone(normalize_utc_timestamp("invalid-date"))

    def test_serialize_tags(self):
        self.assertEqual(serialize_tags(["ai", "python", "fastapi"]), "ai, python, fastapi")
        self.assertEqual(serialize_tags("single-tag"), "single-tag")
        self.assertIsNone(serialize_tags(None))
        self.assertIsNone(serialize_tags([]))

    def test_validate_db_path(self):
        valid = self.dir_path / "test.sqlite"
        self.assertEqual(validate_db_path(str(valid)), valid)

        with self.assertRaises(ValueError):
            validate_db_path("../escape.sqlite")

        # File shorter than 16 bytes
        tiny = self.dir_path / "tiny.sqlite"
        tiny.write_bytes(b"short")
        with self.assertRaises(ValueError):
            validate_db_path(str(tiny))

        # Corrupt file with invalid header
        corrupt = self.dir_path / "corrupt.sqlite"
        corrupt.write_bytes(b"INVALID_HEADER_DATA_1234567")
        with self.assertRaises(ValueError):
            validate_db_path(str(corrupt))

    def test_import_and_query_memories(self):
        items = [
            {
                "id": "mem_01",
                "content": "User prefers TypeScript and React for web applications",
                "category": "work",
                "tags": ["frontend", "tech"],
                "created_at": "2026-10-01T10:00:00Z",
            },
            {
                "id": "mem_02",
                "content": "Favorite coffee roast is light Ethiopian Yirgacheffe",
                "category": "habits",
                "tags": ["coffee", "personal"],
                "created_at": "2026-10-02T08:30:00Z",
            },
        ]

        count = import_memories_to_sqlite(items, str(self.db_path))
        self.assertEqual(count, 2)
        self.assertTrue(self.db_path.exists())

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, category, tags FROM memories ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "mem_01")
        self.assertEqual(rows[0][1], "User prefers TypeScript and React for web applications")
        self.assertEqual(rows[0][2], "work")
        self.assertEqual(rows[0][3], "frontend, tech")

    def test_fts5_search(self):
        test_conn = sqlite3.connect(":memory:")
        fts5_supported = True
        try:
            test_conn.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        except sqlite3.OperationalError:
            fts5_supported = False
        finally:
            test_conn.close()

        if not fts5_supported:
            self.skipTest("SQLite build does not support FTS5")

        items = [
            {
                "id": "mem_fts_1",
                "content": "Architecture meeting regarding microservices latency",
                "category": "work",
                "created_at": "2026-10-01T10:00:00Z",
            },
            {
                "id": "mem_fts_2",
                "content": "Grocery list: bananas, almond milk, and oats",
                "category": "lifestyle",
                "created_at": "2026-10-02T10:00:00Z",
            },
        ]

        import_memories_to_sqlite(items, str(self.db_path))

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.id FROM memories m
            JOIN memories_fts f ON m.rowid = f.rowid
            WHERE memories_fts MATCH 'latency'
            """
        )
        results = cursor.fetchall()
        conn.close()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "mem_fts_1")

    def test_fts_updated_on_reimport(self):
        test_conn = sqlite3.connect(":memory:")
        fts5_supported = True
        try:
            test_conn.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        except sqlite3.OperationalError:
            fts5_supported = False
        finally:
            test_conn.close()

        if not fts5_supported:
            self.skipTest("SQLite build does not support FTS5")

        import_memories_to_sqlite(
            [{"id": "mem_upd", "content": "Initial draft about Kubernetes"}],
            str(self.db_path),
        )
        import_memories_to_sqlite(
            [{"id": "mem_upd", "content": "Revised draft about Docker"}],
            str(self.db_path),
        )

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT m.id FROM memories m JOIN memories_fts f ON m.rowid = f.rowid WHERE memories_fts MATCH 'Docker'")
        docker_results = cursor.fetchall()
        cursor.execute("SELECT m.id FROM memories m JOIN memories_fts f ON m.rowid = f.rowid WHERE memories_fts MATCH 'Kubernetes'")
        k8s_results = cursor.fetchall()
        conn.close()

        self.assertEqual(len(docker_results), 1)
        self.assertEqual(len(k8s_results), 0)

    def test_idempotent_merge(self):
        items_v1 = [
            {"id": "mem_sync", "content": "Initial thought", "category": "notes"}
        ]
        items_v2 = [
            {"id": "mem_sync", "content": "Updated refined thought", "category": "notes"}
        ]

        import_memories_to_sqlite(items_v1, str(self.db_path))
        import_memories_to_sqlite(items_v2, str(self.db_path))

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM memories WHERE id = 'mem_sync'")
        rows = cursor.fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "Updated refined thought")

    def test_load_input_json(self):
        file_path = self.dir_path / "wrapped.json"
        file_path.write_text('{"memories": [{"id": "m1", "content": "test"}]}', encoding="utf-8")
        data = load_input_json(str(file_path))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "m1")


if __name__ == "__main__":
    unittest.main()
