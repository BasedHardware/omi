import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

recipe_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_sqlite.py"
spec = importlib.util.spec_from_file_location("memories_to_sqlite", recipe_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

import_memories = module.import_memories
validate_db_path = module.validate_db_path
strip_surrogates = module.strip_surrogates
utc_stamp = module.utc_stamp
format_tags = module.format_tags
parse_memory = module.parse_memory


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_strip_surrogates(self):
        self.assertEqual(strip_surrogates("Clean text"), "Clean text")
        self.assertEqual(strip_surrogates("Bad\ud800Text\udfff"), "BadText")

    def test_utc_stamp(self):
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))
        self.assertEqual(utc_stamp("2026-09-14T15:30:00Z"), "2026-09-14 15:30:00")
        self.assertEqual(utc_stamp("2026-09-14T17:30:00+02:00"), "2026-09-14 15:30:00")

    def test_format_tags(self):
        self.assertIsNone(format_tags(None))
        self.assertEqual(format_tags(["work", "urgent"]), "work, urgent")
        self.assertEqual(format_tags("single-tag"), "single-tag")

    def test_basic_import_and_schema(self):
        sample = [
            {
                "id": "mem-1",
                "content": "Prefers coffee with oat milk",
                "category": "lifestyle",
                "visibility": "private",
                "tags": ["habits", "coffee"],
                "created_at": "2026-09-14T08:00:00Z",
                "updated_at": "2026-09-14T08:05:00Z",
            },
            {
                "id": "mem-2",
                "content": "Working on Omi SDK refactoring",
                "category": "work",
                "tags": ["coding"],
                "created_at": "2026-09-14T10:00:00Z",
            },
        ]
        json_file = self.tmp / "memories.json"
        json_file.write_text(json.dumps(sample), encoding="utf-8")

        db_file = self.tmp / "memories.db"
        count = import_memories([str(json_file)], str(db_file))
        self.assertEqual(count, 2)

        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()

        # Verify rows
        cur.execute("SELECT id, content, category, visibility, tags, created_at FROM memories ORDER BY id")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[0],
            ("mem-1", "Prefers coffee with oat milk", "lifestyle", "private", "habits, coffee", "2026-09-14 08:00:00"),
        )
        self.assertEqual(
            rows[1],
            ("mem-2", "Working on Omi SDK refactoring", "work", None, "coding", "2026-09-14 10:00:00"),
        )

        # Verify indices exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indices = {r[0] for r in cur.fetchall()}
        self.assertIn("memories_category", indices)
        self.assertIn("memories_created_at", indices)

        conn.close()

    def test_idempotency_upsert(self):
        initial = [{"id": "m1", "content": "Initial note", "category": "notes"}]
        updated = [{"id": "m1", "content": "Updated note", "category": "notes_revised"}]

        f1 = self.tmp / "f1.json"
        f2 = self.tmp / "f2.json"
        f1.write_text(json.dumps(initial), encoding="utf-8")
        f2.write_text(json.dumps(updated), encoding="utf-8")

        db_file = self.tmp / "test.db"
        import_memories([str(f1)], str(db_file))
        import_memories([str(f2)], str(db_file))

        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()
        cur.execute("SELECT content, category FROM memories WHERE id = 'm1'")
        row = cur.fetchone()
        conn.close()

        self.assertEqual(row, ("Updated note", "notes_revised"))

    def test_envelope_unwrapping(self):
        payload = {
            "memories": [
                {"id": "env-1", "content": "Envelope memory"}
            ]
        }
        f = self.tmp / "env.json"
        f.write_text(json.dumps(payload), encoding="utf-8")

        db_file = self.tmp / "env.db"
        count = import_memories([str(f)], str(db_file))
        self.assertEqual(count, 1)

    def test_validate_path_security(self):
        # Traversal check
        with self.assertRaises(ValueError):
            validate_db_path("../unsafe.db")

        # Non-sqlite file
        bad_file = self.tmp / "fake.db"
        bad_file.write_text("not a sqlite file", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_db_path(str(bad_file))

    def test_cli_subprocess(self):
        data = [{"id": "cli-1", "content": "CLI test memory"}]
        src = self.tmp / "cli.json"
        src.write_text(json.dumps(data), encoding="utf-8")
        dest = self.tmp / "cli.db"

        proc = subprocess.run(
            [sys.executable, str(recipe_path), str(src), "-o", str(dest)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Imported 1 memory", proc.stdout)
        self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main()
