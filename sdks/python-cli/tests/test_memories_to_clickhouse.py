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
        escape_clickhouse_array,
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
        escape_clickhouse_array,
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

    def test_escape_clickhouse_array(self):
        self.assertEqual(escape_clickhouse_array(None), "[]")
        self.assertEqual(escape_clickhouse_array([]), "[]")
        self.assertEqual(
            escape_clickhouse_array(["coffee", "tea"]), "['coffee', 'tea']"
        )
        self.assertEqual(escape_clickhouse_array(["it's hot"]), "['it\\'s hot']")

    def test_parse_clickhouse_datetime(self):
        res = parse_clickhouse_datetime("2024-06-15T08:30:00Z")
        self.assertEqual(res, "2024-06-15 08:30:00.000")

        res_tz = parse_clickhouse_datetime("2024-06-15T10:30:00+02:00")
        self.assertEqual(res_tz, "2024-06-15 08:30:00.000")

    def test_generate_clickhouse_schema(self):
        ddl = generate_clickhouse_schema()
        self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", ddl)
        self.assertIn("ReplacingMergeTree(updated_at)", ddl)
        # Verify valid prefix alignment constraint
        self.assertIn("PRIMARY KEY (id)", ddl)
        self.assertIn("ORDER BY (id, category)", ddl)
        self.assertIn("PARTITION BY toYYYYMM(created_at)", ddl)
        self.assertIn("LowCardinality(String)", ddl)
        self.assertIn("tags Array(String)", ddl)

    def test_format_memory_for_clickhouse_realistic_cli_fixture(self):
        # Fixture captured from `omi --json memory list` export contract
        cli_fixture = {
            "id": "mem_01hqxyz123456789abcdef01",
            "category": "preferences",
            "visibility": "private",
            "content": "Prefers oat milk in cappuccino.",
            "tags": ["coffee", "drinks"],
            "created_at": "2024-06-01T12:00:00.000000Z",
            "updated_at": "2024-06-01T12:05:00.000000Z",
            "manually_added": True,
        }
        rec = format_memory_for_clickhouse(cli_fixture)
        self.assertEqual(rec["id"], "mem_01hqxyz123456789abcdef01")
        self.assertEqual(rec["category"], "preferences")
        self.assertEqual(rec["visibility"], "private")
        self.assertEqual(rec["manually_added"], 1)
        self.assertEqual(rec["tags"], ["coffee", "drinks"])
        self.assertEqual(rec["created_at"], "2024-06-01 12:00:00.000")
        self.assertEqual(rec["updated_at"], "2024-06-01 12:05:00.000")

    def test_format_sql_insert(self):
        rec = {
            "id": "ck-102",
            "content": "Discussed Q3 roadmaps.",
            "category": "work",
            "visibility": "private",
            "created_at": "2024-06-01 12:00:00.000",
            "updated_at": "2024-06-01 12:00:00.000",
            "manually_added": 0,
            "tags": ["roadmap", "planning"],
            "metadata_json": "{}",
        }
        sql = format_sql_insert(rec)
        self.assertIn("INSERT INTO omi_memories", sql)
        self.assertIn("'ck-102'", sql)
        self.assertIn("'Discussed Q3 roadmaps.'", sql)
        self.assertIn("['roadmap', 'planning']", sql)

    def test_convert_memories_to_clickhouse_jsonl(self):
        payload = [
            {"id": "m1", "content": "Memory one", "category": "cat1"},
            {"id": "m2", "content": "Memory two", "category": "cat2"},
        ]
        jsonl = convert_memories_to_clickhouse(payload, format_mode="jsonl")
        lines = [line for line in jsonl.split("\n") if line.strip()]
        self.assertEqual(len(lines), 2)
        parsed = [json.loads(line) for line in lines]
        self.assertEqual(parsed[0]["id"], "m1")
        self.assertEqual(parsed[1]["id"], "m2")

    def test_convert_memories_to_clickhouse_sql(self):
        payload = {"items": [{"id": "m3", "content": "Memory three"}]}
        sql = convert_memories_to_clickhouse(
            payload, format_mode="sql", with_schema=True
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", sql)
        self.assertIn("INSERT INTO omi_memories", sql)
        self.assertIn("'m3'", sql)

    def test_main_cli_schema_only(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = main(["--schema-only"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", output)
            self.assertIn("ORDER BY (id, category)", output)

    def test_main_cli_file_io(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            in_file = tmp_path / "test.json"
            out_file = tmp_path / "test.jsonl"
            in_file.write_text(
                json.dumps([{"id": "cli-1", "content": "Test"}]), encoding="utf-8"
            )

            exit_code = main(
                ["-i", str(in_file), "-o", str(out_file), "--format", "jsonl"]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("cli-1", content)


if __name__ == "__main__":
    unittest.main()
