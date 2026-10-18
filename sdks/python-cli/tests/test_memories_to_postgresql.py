"""Hermetic tests for examples/memories_to_postgresql.py (#18864).

Covers: idempotent DDL + GIN/tsvector + optional pgvector, SQL literal
escaping, upsert ON CONFLICT, tags array, envelope unwrapping, output paths.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import memories_to_postgresql as m  # noqa: E402

MEM = {
    "id": "m1",
    "content": "Prefers short standups",
    "category": "Work",
    "tags": ["style", "meetings"],
    "visibility": "public",
    "manually_added": True,
    "reviewed": False,
    "app_id": "chatgpt",
    "created_at": "2026-10-17T12:00:00+02:00",
    "updated_at": "2026-10-17T13:00:00Z",
}


class TestDdl(unittest.TestCase):
    def test_idempotent_schema(self):
        ddl = m.schema_ddl()
        self.assertIn("CREATE TABLE IF NOT EXISTS memories", ddl)
        self.assertIn("PRIMARY KEY", ddl)
        self.assertIn("idx_memories_category", ddl)
        self.assertIn("idx_memories_created_at", ddl)

    def test_fulltext_tsvector_gin(self):
        ddl = m.schema_ddl()
        self.assertIn("tsvector", ddl)
        self.assertIn("USING GIN(search_vector)", ddl)

    def test_pgvector_optional(self):
        self.assertNotIn("embedding", m.schema_ddl())
        self.assertNotIn("ivfflat", m.schema_ddl())
        pg = m.schema_ddl(with_pgvector=True)
        self.assertIn("embedding     vector(1536)", pg)
        self.assertIn("ivfflat", pg)


class TestLiterals(unittest.TestCase):
    def test_sql_literal_types(self):
        self.assertEqual(m.sql_literal(None), "NULL")
        self.assertEqual(m.sql_literal(True), "TRUE")
        self.assertEqual(m.sql_literal(3), "3")
        self.assertEqual(m.sql_literal("O'Reilly"), "'O''Reilly'")

    def test_tags_to_text_array(self):
        self.assertEqual(m.tags_array(["a", "b"]), "ARRAY['a', 'b']::text[]")
        self.assertEqual(m.tags_array("solo"), "ARRAY['solo']::text[]")
        self.assertEqual(m.tags_array(None), "NULL")

    def test_timestamp_literal(self):
        self.assertEqual(m.ts_literal("2026-10-17T12:00:00Z"), "'2026-10-17T12:00:00Z'")
        self.assertEqual(m.ts_literal(None), "NULL")
        self.assertEqual(m.ts_literal(42), "NULL")


class TestGenerate(unittest.TestCase):
    def test_upsert_shape(self):
        sql = m.row_sql(MEM)
        self.assertIn("INSERT INTO memories", sql)
        self.assertIn("ON CONFLICT (id) DO UPDATE SET", sql)
        self.assertIn("'m1'", sql)
        self.assertIn("ARRAY['style', 'meetings']::text[]", sql)
        self.assertIn("TRUE", sql)  # manually_added
        self.assertIn("FALSE", sql)  # reviewed

    def test_sql_injection_escaped(self):
        sql = m.row_sql({"id": "x", "content": "'; DROP TABLE memories; --"})
        self.assertNotIn("DROP TABLE memories; --\n", sql)
        self.assertIn("''; DROP TABLE memories; --'", sql)

    def test_multi_page_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.json"
            p1.write_text(json.dumps({"memories": [MEM, {**MEM, "id": "m2"}]}))
            p2 = Path(td) / "b.json"
            p2.write_text(json.dumps({"memories": [MEM]}))  # m1 dupes
            sql = m.generate([str(p1), str(p2)])
            self.assertEqual(sql.count("INSERT INTO memories"), 2)

    def test_envelope_shapes(self):
        for payload in ({"memories": [MEM]}, {"items": [MEM]}, {"data": [MEM]}, [MEM], MEM):
            self.assertEqual(len(m.extract_memories(payload)), 1)


class TestCli(unittest.TestCase):
    def test_exclusive_write(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = Path(td) / "m.sql"
            out.write_text("keep")
            buf = io.StringIO()
            old = sys.stderr
            sys.stderr = buf
            try:
                rc = m.main([str(src), "-o", str(out)])
            finally:
                sys.stderr = old
            self.assertEqual(rc, 2)
            self.assertEqual(out.read_text(), "keep")

    def test_schema_only_stdout(self):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = m.main(["--schema-only", "--with-pgvector"])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        self.assertIn("vector(1536)", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
