from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

# Allow importing local script
SCRATCH_DIR = Path(__file__).resolve().parent
if str(SCRATCH_DIR) not in sys.path:
    sys.path.insert(0, str(SCRATCH_DIR))

# Also allow importing when placed in sdks/python-cli/tests
REPO_SDK_EXAMPLES = SCRATCH_DIR.parents[0] / "examples"
if str(REPO_SDK_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(REPO_SDK_EXAMPLES))

try:
    from memories_to_postgresql import (
        convert_memories_to_postgresql,
        escape_sql_json,
        escape_sql_string,
        format_memory_sql_row,
        generate_schema_sql,
        main,
        parse_iso_datetime,
    )
except ImportError:
    from sdks.python_cli.examples.memories_to_postgresql import (  # type: ignore
        convert_memories_to_postgresql,
        escape_sql_json,
        escape_sql_string,
        format_memory_sql_row,
        generate_schema_sql,
        main,
        parse_iso_datetime,
    )


class MemoriesToPostgreSqlTests(unittest.TestCase):
    def test_escape_sql_string(self):
        self.assertEqual(escape_sql_string(None), "NULL")
        self.assertEqual(escape_sql_string("hello"), "'hello'")
        self.assertEqual(escape_sql_string("it's a test"), "'it''s a test'")
        self.assertEqual(escape_sql_string("semi; colon ' quote"), "'semi; colon '' quote'")

    def test_escape_sql_json(self):
        self.assertEqual(escape_sql_json(None), "NULL")
        obj = {"key": "it's value", "number": 42}
        sql_json = escape_sql_json(obj)
        self.assertTrue(sql_json.endswith("::jsonb"))
        self.assertIn("it''s value", sql_json)

    def test_parse_iso_datetime(self):
        self.assertIsNone(parse_iso_datetime(None))
        self.assertIsNone(parse_iso_datetime(""))
        self.assertIsNone(parse_iso_datetime("not-a-date"))

        ts = parse_iso_datetime("2024-05-01T12:00:00Z")
        self.assertIsNotNone(ts)
        self.assertTrue(ts.startswith("2024-05-01 12:00:00"))

        ts2 = parse_iso_datetime("2024-05-01T14:30:00.123456+02:00")
        self.assertIsNotNone(ts2)
        # Should be converted to UTC: 14:30 +02:00 -> 12:30 UTC
        self.assertTrue(ts2.startswith("2024-05-01 12:30:00"))

    def test_generate_schema_sql(self):
        schema_default = generate_schema_sql(with_pgvector=False)
        self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", schema_default)
        self.assertIn("search_vector tsvector GENERATED ALWAYS", schema_default)
        self.assertNotIn("CREATE EXTENSION IF NOT EXISTS \"vector\"", schema_default)
        self.assertNotIn("embedding vector", schema_default)

        schema_vector = generate_schema_sql(with_pgvector=True, vector_dim=768)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS \"vector\"", schema_vector)
        self.assertIn("embedding vector(768)", schema_vector)
        self.assertIn("idx_omi_memories_embedding", schema_vector)

    def test_format_memory_sql_row_standard(self):
        mem = {
            "id": "mem-101",
            "content": "User prefers Earl Grey tea with milk.",
            "category": "preferences",
            "created_at": "2024-05-01T08:00:00Z",
            "manually_added": True,
            "deleted": False,
            "score": 5,
            "metadata": {"source": "voice_recording"},
        }
        sql = format_memory_sql_row(mem, with_pgvector=False)
        self.assertIn("INSERT INTO omi_memories", sql)
        self.assertIn("'mem-101'", sql)
        self.assertIn("'User prefers Earl Grey tea with milk.'", sql)
        self.assertIn("'preferences'", sql)
        self.assertIn("ON CONFLICT (id) DO UPDATE SET", sql)
        self.assertIn("TRUE", sql)

    def test_format_memory_sql_row_with_pgvector(self):
        mem = {
            "id": "mem-102",
            "content": "Meeting with Sarah scheduled for Friday.",
            "category": "work",
            "embedding": [0.123, -0.456, 0.789],
        }
        sql = format_memory_sql_row(mem, with_pgvector=True)
        self.assertIn("embedding", sql)
        self.assertIn("'[0.123,-0.456,0.789]'::vector", sql)

    def test_sql_injection_resilience(self):
        malicious_mem = {
            "id": "mal-001'; DROP TABLE omi_memories; --",
            "content": "Testing '; DELETE FROM users; /* comment */",
            "category": "inject' OR '1'='1",
        }
        sql = format_memory_sql_row(malicious_mem)
        # Verify that single quotes are doubled and cannot break out of literals
        self.assertIn("'mal-001''; DROP TABLE omi_memories; --'", sql)
        self.assertIn("'Testing ''; DELETE FROM users; /* comment */'", sql)
        self.assertIn("'inject'' OR ''1''=''1'", sql)

    def test_convert_memories_to_postgresql_full_payload(self):
        payload = {
            "items": [
                {
                    "id": "mem-1",
                    "content": "User likes Python programming.",
                    "category": "skills",
                    "created_at": "2024-05-01T10:00:00Z",
                },
                {
                    "id": "mem-2",
                    "content": "Favorite editor is VS Code.",
                    "category": "tools",
                    "created_at": "2024-05-02T11:00:00Z",
                },
            ]
        }
        script = convert_memories_to_postgresql(payload, with_schema=True)
        self.assertIn("BEGIN;", script)
        self.assertIn("COMMIT;", script)
        self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", script)
        self.assertIn("INSERT INTO omi_memories", script)
        self.assertIn("mem-1", script)
        self.assertIn("mem-2", script)
        self.assertIn("-- Transformed 2 memories successfully.", script)

    def test_convert_memories_to_postgresql_skips_invalid(self):
        payload = [
            {"id": "valid-1", "content": "Valid memory."},
            {"no_id_here": "Invalid record."},
            "not even a dict",
        ]
        script = convert_memories_to_postgresql(payload, with_schema=False)
        self.assertIn("valid-1", script)
        self.assertIn("Skipped invalid record", script)
        self.assertIn("-- Transformed 1 memories successfully.", script)

    def test_main_cli_file_io(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            in_file = tmp_path / "memories.json"
            out_file = tmp_path / "output.sql"

            data = [{"id": "cli-1", "content": "Created via CLI test."}]
            in_file.write_text(json.dumps(data), encoding="utf-8")

            exit_code = main(["-i", str(in_file), "-o", str(out_file), "--with-pgvector"])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())
            sql = out_file.read_text(encoding="utf-8")
            self.assertIn("cli-1", sql)
            self.assertIn("vector", sql)

    def test_main_cli_stdin_stdout(self):
        data = [{"id": "stdin-1", "content": "From STDIN."}]
        json_input = json.dumps(data)

        with patch("sys.stdin", io.StringIO(json_input)):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = main([])
                self.assertEqual(exit_code, 0)
                output = mock_stdout.getvalue()
                self.assertIn("stdin-1", output)
                self.assertIn("CREATE TABLE IF NOT EXISTS omi_memories", output)


if __name__ == "__main__":
    unittest.main()
