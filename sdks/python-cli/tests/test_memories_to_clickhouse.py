"""Tests for the memories -> ClickHouse exporter.

Pins schema validity (PRIMARY KEY prefix of ORDER BY), field mapping from the
omi memory export, SQL/JSONEachRow formatting and escaping, datetime
normalization, schema-only / --no-schema flags, and stdin/file loading.
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_clickhouse.py"
spec = importlib.util.spec_from_file_location("memories_to_clickhouse", script_path)
m2ch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2ch)


class TestMemoriesToClickhouse(unittest.TestCase):
    def sample_memories(self):
        return [
            {
                "id": "mem_01_work",
                "category": "work",
                "visibility": "private",
                "content": "Prefers async standups",
                "tags": ["workflow", "management"],
                "created_at": "2026-09-15T10:30:00Z",
                "updated_at": "2026-09-16T10:30:00Z",
                "manually_added": True,
                "metadata": {"source": "device"},
            },
            {
                "id": "mem_02_skills",
                "category": "skills",
                "visibility": "public",
                "content": "Uses ClickHouse for analytics",
                "tags": [],
                "created_at": "2026-09-16T14:15:00+00:00",
            },
        ]

    def test_schema_uses_valid_primary_key_prefix(self):
        ddl = m2ch.SCHEMA_SQL
        self.assertIn("PRIMARY KEY (id)", ddl)
        self.assertIn("ORDER BY (id, category)", ddl)
        self.assertIn("ENGINE = ReplacingMergeTree(updated_at)", ddl)
        self.assertIn("PARTITION BY toYYYYMM(created_at)", ddl)
        # PRIMARY KEY must be a prefix of ORDER BY.
        self.assertTrue(ddl.index("PRIMARY KEY (id)") < ddl.index("ORDER BY (id, category)"))

    def test_parse_datetime_normalizes_to_utc_clickhouse_text(self):
        self.assertEqual(m2ch.parse_datetime("2026-09-15T10:30:00Z"), "2026-09-15 10:30:00.000")
        self.assertEqual(m2ch.parse_datetime("2026-09-15T12:30:00+02:00"), "2026-09-15 10:30:00.000")
        self.assertEqual(m2ch.parse_datetime("2026-09-15T10:30:00"), "2026-09-15 10:30:00.000")
        self.assertEqual(m2ch.parse_datetime(None), "1970-01-01 00:00:00.000")
        self.assertEqual(m2ch.parse_datetime("not-a-date"), "1970-01-01 00:00:00.000")

    def test_escape_string_and_array(self):
        self.assertEqual(m2ch.escape_string("O'Reilly\\path"), "O\\'Reilly\\\\path")
        self.assertEqual(m2ch.escape_array(["a", "b'c"]), "['a', 'b\\'c']")
        self.assertEqual(m2ch.escape_array(None), "[]")
        self.assertEqual(m2ch.escape_array([""]), "[]")

    def test_normalize_memory_defaults_and_coercion(self):
        record = m2ch.normalize_memory({"id": "m1", "content": 123, "tags": "solo"})
        self.assertEqual(record["id"], "m1")
        self.assertEqual(record["content"], "123")
        self.assertEqual(record["category"], "uncategorized")
        self.assertEqual(record["visibility"], "private")
        self.assertEqual(record["tags"], ["solo"])
        self.assertEqual(record["manually_added"], 0)
        self.assertEqual(record["updated_at"], record["created_at"])

    def test_normalize_memory_requires_id(self):
        with self.assertRaises(ValueError):
            m2ch.normalize_memory({"content": "no id"})
        with self.assertRaises(ValueError):
            m2ch.normalize_memory({"id": "  "})

    def test_sql_insert_round_trip_fields(self):
        record = m2ch.normalize_memory(self.sample_memories()[0])
        sql = m2ch.format_sql_insert(record)
        self.assertTrue(sql.startswith("INSERT INTO omi_memories "))
        self.assertIn("'mem_01_work'", sql)
        self.assertIn("'Prefers async standups'", sql)
        self.assertIn("'2026-09-15 10:30:00.000'", sql)
        self.assertIn("'2026-09-16 10:30:00.000'", sql)
        self.assertIn("['workflow', 'management']", sql)
        self.assertIn(", 1,", sql)
        self.assertTrue(sql.endswith(";"))

    def test_json_each_row_line(self):
        record = m2ch.normalize_memory(self.sample_memories()[0])
        line = m2ch.format_json_each_row(record)
        payload = json.loads(line)
        self.assertEqual(payload["id"], "mem_01_work")
        self.assertEqual(payload["created_at"], "2026-09-15 10:30:00.000")
        self.assertEqual(payload["tags"], ["workflow", "management"])
        self.assertEqual(payload["manually_added"], 1)

    def test_convert_sql_includes_schema_by_default(self):
        text = m2ch.convert(self.sample_memories(), output_format="sql", include_schema=True)
        self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", text)
        self.assertIn("INSERT INTO omi_memories", text)
        self.assertEqual(text.count("INSERT INTO omi_memories"), 2)

    def test_convert_sql_no_schema_and_jsonl(self):
        sql = m2ch.convert(self.sample_memories(), output_format="sql", include_schema=False)
        self.assertNotIn("CREATE TABLE", sql)
        self.assertIn("INSERT INTO omi_memories", sql)

        jsonl = m2ch.convert(self.sample_memories(), output_format="jsonl")
        lines = [line for line in jsonl.splitlines() if line]
        self.assertEqual(len(lines), 2)
        self.assertNotIn("CREATE TABLE", jsonl)

    def test_main_schema_only_and_file_round_trip(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout, stderr
        try:
            code = m2ch.main(["--schema-only"])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        self.assertEqual(code, 0)
        self.assertIn("ORDER BY (id, category)", stdout.getvalue())

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "memories.json"
            dest = Path(tmp) / "out.sql"
            src.write_text(json.dumps(self.sample_memories()), encoding="utf-8")
            code = m2ch.main([str(src), "--no-schema", "-o", str(dest)])
            self.assertEqual(code, 0)
            text = dest.read_text(encoding="utf-8")
            self.assertIn("INSERT INTO omi_memories", text)
            self.assertNotIn("CREATE TABLE", text)

    def test_main_rejects_non_array_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bad.json"
            src.write_text('{"id": "m1"}', encoding="utf-8")
            stderr = io.StringIO()
            old_err = sys.stderr
            sys.stderr = stderr
            try:
                code = m2ch.main([str(src)])
            finally:
                sys.stderr = old_err
            self.assertEqual(code, 1)
            self.assertIn("Expected the JSON array", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
