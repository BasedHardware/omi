"""Hermetic tests for examples/memories_to_clickhouse.py (#18866).

Covers: ReplacingMergeTree DDL + monthly partition, LowCardinality
encodings, DateTime64 timestamp normalization, dual SQL/JSONEachRow
formats, escaping, envelope unwrapping, output guards.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import memories_to_clickhouse as m  # noqa: E402

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
    def test_replacing_merge_tree(self):
        ddl = m.schema_ddl()
        self.assertIn("ReplacingMergeTree(updated_at)", ddl)
        self.assertIn("PARTITION BY toYYYYMM(created_at)", ddl)
        self.assertIn("ORDER BY id", ddl)

    def test_low_cardinality_encodings(self):
        ddl = m.schema_ddl()
        self.assertIn("LowCardinality(String)", ddl)
        self.assertIn("LowCardinality(String)", ddl)  # category + visibility + app_id
        self.assertIn("DateTime64(3, 'UTC')", ddl)


class TestTypes(unittest.TestCase):
    def test_datetime_to_datetime64(self):
        self.assertEqual(m.ch_datetime("2026-10-17T12:00:00+02:00"), "2026-10-17 10:00:00.000")
        self.assertIsNone(m.ch_datetime(None))
        self.assertIsNone(m.ch_datetime("bad"))

    def test_sql_escaping(self):
        self.assertEqual(m.ch_str("O'Reilly"), "'O\\'Reilly'")
        self.assertEqual(m.ch_str("a\\b"), "'a\\\\b'")

    def test_bools(self):
        self.assertEqual(m.ch_bool(True), 1)
        self.assertEqual(m.ch_bool("yes"), 1)
        self.assertEqual(m.ch_bool(None), 0)


class TestGenerate(unittest.TestCase):
    def test_sql_format(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = m.generate([str(src)], "sql")
            self.assertIn("ReplacingMergeTree", out)
            self.assertIn("INSERT INTO memories", out)
            self.assertIn("['style', 'meetings']", out)

    def test_jsoneachrow_format(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = m.generate([str(src)], "jsoneachrow")
            row = json.loads(out.strip())
            self.assertEqual(row["id"], "m1")
            self.assertEqual(row["manually_added"], 1)
            self.assertEqual(row["reviewed"], 0)
            self.assertEqual(row["created_at"], "2026-10-17 10:00:00.000")
            self.assertNotIn("CREATE TABLE", out)

    def test_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM, MEM]}))
            self.assertEqual(m.generate([str(src)], "sql").count("INSERT INTO"), 1)

    def test_envelope_shapes(self):
        for payload in ({"memories": [MEM]}, {"items": [MEM]}, {"data": [MEM]}, [MEM], MEM):
            self.assertEqual(len(m.extract_memories(payload)), 1)


class TestCli(unittest.TestCase):
    def test_exclusive_write(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = Path(td) / "o.sql"
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


if __name__ == "__main__":
    unittest.main()
