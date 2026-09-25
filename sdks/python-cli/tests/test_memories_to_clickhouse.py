from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRATCH_DIR = Path(__file__).resolve().parent
if str(SCRATCH_DIR) not in sys.path:
    sys.path.insert(0, str(SCRATCH_DIR))

REPO_SDK_EXAMPLES = SCRATCH_DIR.parents[0] / "examples"
if str(REPO_SDK_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(REPO_SDK_EXAMPLES))

try:
    from memories_to_clickhouse import (
        convert_memories_to_clickhouse,
        escape_clickhouse_string,
        format_memory_for_clickhouse,
        format_sql_insert,
        generate_clickhouse_schema,
        main,
        parse_clickhouse_datetime,
    )
except ImportError:
    from sdks.python_cli.examples.memories_to_clickhouse import (  # type: ignore
        convert_memories_to_clickhouse,
        escape_clickhouse_string,
        format_memory_for_clickhouse,
        format_sql_insert,
        generate_clickhouse_schema,
        main,
        parse_clickhouse_datetime,
    )


class MemoriesToClickHouseTests(unittest.TestCase):
    def test_escape_clickhouse_string(self):
        self.assertEqual(escape_clickhouse_string(None), "''")
        self.assertEqual(escape_clickhouse_string("normal"), "'normal'")
        self.assertEqual(escape_clickhouse_string("it's cool"), "'it\\'s cool'")
        self.assertEqual(escape_clickhouse_string("path\\name"), "'path\\\\name'")

    def test_parse_clickhouse_datetime(self):
        res = parse_clickhouse_datetime("2024-06-15T08:30:00Z")
        self.assertEqual(res, "2024-06-15 08:30:00.000")

        res_tz = parse_clickhouse_datetime("2024-06-15T10:30:00+02:00")
        self.assertEqual(res_tz, "2024-06-15 08:30:00.000")

    def test_generate_clickhouse_schema(self):
        ddl = generate_clickhouse_schema()
        self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", ddl)
        self.assertIn("ReplacingMergeTree(updated_at)", ddl)
        self.assertIn("PARTITION BY toYYYYMM(created_at)", ddl)
        self.assertIn("LowCardinality(String)", ddl)

    def test_format_memory_for_clickhouse(self):
        mem = {
            "id": "ck-101",
            "content": "User ordered espresso.",
            "category": "preferences",
            "created_at": "2024-06-01T12:00:00Z",
            "manually_added": True,
            "deleted": False,
            "score": 10,
            "metadata": {"venue": "Cafe Nero"},
        }
        rec = format_memory_for_clickhouse(mem)
        self.assertEqual(rec["id"], "ck-101")
        self.assertEqual(rec["category"], "preferences")
        self.assertEqual(rec["manually_added"], 1)
        self.assertEqual(rec["deleted"], 0)
        self.assertEqual(rec["score"], 10)
        self.assertIn("Cafe Nero", rec["metadata_json"])

    def test_format_sql_insert(self):
        rec = {
            "id": "ck-102",
            "content": "Discussed Q3 roadmaps.",
            "category": "work",
            "created_at": "2024-06-01 12:00:00.000",
            "updated_at": "2024-06-01 12:00:00.000",
            "manually_added": 0,
            "deleted": 0,
            "score": 0,
            "metadata_json": "{}",
        }
        sql = format_sql_insert(rec)
        self.assertIn("INSERT INTO omi_memories", sql)
        self.assertIn("'ck-102'", sql)
        self.assertIn("'Discussed Q3 roadmaps.'", sql)

    def test_convert_memories_to_clickhouse_jsonl(self):
        payload = [
            {"id": "m1", "content": "Memory one", "category": "cat1"},
            {"id": "m2", "content": "Memory two", "category": "cat2"},
        ]
        jsonl = convert_memories_to_clickhouse(payload, format_mode="jsonl")
        lines = [line for line in jsonl.strip().split("\n") if line]
        self.assertEqual(len(lines), 2)
        d1 = json.loads(lines[0])
        self.assertEqual(d1["id"], "m1")
        self.assertEqual(d1["content"], "Memory one")

    def test_convert_memories_to_clickhouse_sql(self):
        payload = {"items": [{"id": "m1", "content": "Memory one"}]}
        sql = convert_memories_to_clickhouse(payload, format_mode="sql", with_schema=True)
        self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", sql)
        self.assertIn("INSERT INTO omi_memories", sql)
        self.assertIn("'m1'", sql)
        self.assertIn("-- Transformed 1 memories for ClickHouse successfully.", sql)

    def test_main_cli_file_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            in_file = tmp / "memories.json"
            out_file = tmp / "output.jsonl"

            in_file.write_text(json.dumps([{"id": "cli-ck-1", "content": "Test CLI"}]), encoding="utf-8")
            exit_code = main(["-i", str(in_file), "-o", str(out_file), "--format", "jsonl"])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("cli-ck-1", content)


if __name__ == "__main__":
    unittest.main()
