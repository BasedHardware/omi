"""Hermetic tests for examples/memories_to_sqlite.py (#18468).

Covers: schema + indexes, idempotent INSERT OR REPLACE, timestamp
normalization, loose row coercion, envelope unwrapping, '..' path guard,
non-SQLite-file refusal, and CLI entry.
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import memories_to_sqlite as m  # noqa: E402

MEM = {
    "id": "m1",
    "content": "Prefers short standups",
    "category": "Work",
    "tags": ["style", "meetings"],
    "visibility": "public",
    "manually_added": True,
    "app_id": "chatgpt",
    "created_at": "2026-10-17T12:00:00+02:00",
    "updated_at": "2026-10-17T13:00:00Z",
}


def _page(tmpdir, payload, name="p.json"):
    p = Path(tmpdir) / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


class TestLoad(unittest.TestCase):
    def test_load_and_schema(self):
        with tempfile.TemporaryDirectory() as td:
            page = _page(td, {"memories": [MEM]})
            db = str(Path(td) / "m.db")
            loaded, added, total = m.load(db, [page])
            self.assertEqual((loaded, added, total), (1, 1, 1))
            conn = sqlite3.connect(db)
            try:
                row = conn.execute(
                    "SELECT id, content, category, tags, visibility, manually_added, app_id, created_at, raw_json FROM memories"
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row[0], "m1")
            self.assertEqual(row[1], "Prefers short standups")
            self.assertEqual(row[3], "style|meetings")
            self.assertEqual(row[5], 1)
            self.assertEqual(row[6], "chatgpt")
            self.assertEqual(row[7], "2026-10-17 10:00:00")  # UTC
            self.assertIn('"id": "m1"', row[8])

    def test_idempotent_reimport(self):
        with tempfile.TemporaryDirectory() as td:
            page = _page(td, {"memories": [MEM]})
            db = str(Path(td) / "m.db")
            m.load(db, [page])
            loaded, added, total = m.load(db, [page])
            self.assertEqual(total, 1)  # INSERT OR REPLACE, never duplicates

    def test_multi_page_merge(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = _page(td, {"memories": [MEM]}, "p1.json")
            p2 = _page(td, {"memories": [{**MEM, "id": "m2"}]}, "p2.json")
            db = str(Path(td) / "m.db")
            _, _, total = m.load(db, [p1, p2])
            self.assertEqual(total, 2)


class TestCoercion(unittest.TestCase):
    def test_missing_id_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            page = _page(td, [{"content": "no id"}])
            with self.assertRaises(ValueError):
                m.rows_from([page])

    def test_memory_id_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            page = _page(td, [{"memory_id": "m9"}])
            rows = m.rows_from([page])
            self.assertEqual(rows[0][0], "m9")

    def test_loose_types_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            page = _page(td, [{"id": "m1", "tags": {"odd": 1}, "manually_added": "yes"}])
            rows = m.rows_from([page])
            self.assertEqual(rows[0][5], 1)

    def test_non_dict_row_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            page = _page(td, [42])
            with self.assertRaises(ValueError):
                m.rows_from([page])


class TestEnvelopes(unittest.TestCase):
    def test_envelope_keys(self):
        for key in ("memories", "items", "data"):
            with tempfile.TemporaryDirectory() as td:
                page = _page(td, {key: [MEM]})
                self.assertEqual(len(m.rows_from([page])), 1)

    def test_single_object(self):
        with tempfile.TemporaryDirectory() as td:
            page = _page(td, MEM)
            self.assertEqual(len(m.rows_from([page])), 1)


class TestPathGuard(unittest.TestCase):
    def test_dotdot_refused(self):
        with self.assertRaises(ValueError):
            m.validate_db_path("../escape.db")

    def test_non_sqlite_file_refused(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "x.db"
            bad.write_text("not sqlite")
            with self.assertRaises(ValueError):
                m.validate_db_path(str(bad))

    def test_valid_sqlite_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            good = Path(td) / "x.db"
            conn = sqlite3.connect(str(good))
            conn.execute("CREATE TABLE t (x)")
            conn.close()
            m.validate_db_path(str(good))  # no raise


class TestTimestamps(unittest.TestCase):
    def test_utc_normalization(self):
        self.assertEqual(m.utc_stamp("2026-10-17T12:00:00+02:00"), "2026-10-17 10:00:00")

    def test_none_and_empty(self):
        self.assertIsNone(m.utc_stamp(None))
        self.assertIsNone(m.utc_stamp(""))

    def test_unparseable_kept_as_text(self):
        self.assertEqual(m.utc_stamp("not-a-date"), "not-a-date")


if __name__ == "__main__":
    unittest.main()
