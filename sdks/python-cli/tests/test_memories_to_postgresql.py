"""Unit tests for the Omi memories to PostgreSQL export recipe."""

import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

# Load module dynamically using importlib.util matching Omi CLI test conventions
RECIPE_PATH = (
    Path(__file__).resolve().parent.parent / "examples" / "memories_to_postgresql.py"
)
spec = importlib.util.spec_from_file_location("memories_to_postgresql", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {RECIPE_PATH}")
mem_pg = importlib.util.module_from_spec(spec)
sys.modules["memories_to_postgresql"] = mem_pg
spec.loader.exec_module(mem_pg)


class TestMemoriesToPostgreSQL(unittest.TestCase):
    def test_strip_surrogates(self) -> None:
        self.assertIsNone(mem_pg.strip_surrogates(None))
        self.assertEqual(mem_pg.strip_surrogates("hello world"), "hello world")
        # Lone surrogate character
        surrogate_char = "\ud800"
        cleaned = mem_pg.strip_surrogates(f"test{surrogate_char}data")
        self.assertEqual(cleaned, "testdata")

    def test_escape_sql_string(self) -> None:
        self.assertEqual(mem_pg.escape_sql_string(None), "NULL")
        self.assertEqual(mem_pg.escape_sql_string("plain text"), "'plain text'")
        self.assertEqual(mem_pg.escape_sql_string("O'Reilly's book"), "'O''Reilly''s book'")
        # Injection attempt
        injection = "test'; DROP TABLE memories; --"
        escaped = mem_pg.escape_sql_string(injection)
        self.assertEqual(escaped, "'test''; DROP TABLE memories; --'")

    def test_escape_sql_jsonb(self) -> None:
        self.assertEqual(mem_pg.escape_sql_jsonb(None), "'{}'::jsonb")
        data = {"title": "Alice's Key", "count": 10}
        escaped = mem_pg.escape_sql_jsonb(data)
        self.assertTrue(escaped.endswith("::jsonb"))
        self.assertIn("Alice''s Key", escaped)

    def test_normalize_utc_timestamp(self) -> None:
        self.assertIsNone(mem_pg.normalize_utc_timestamp(None))
        self.assertIsNone(mem_pg.normalize_utc_timestamp(""))
        self.assertIsNone(mem_pg.normalize_utc_timestamp("not-a-timestamp"))

        # UTC Z format
        ts_z = mem_pg.normalize_utc_timestamp("2026-10-05T14:30:00Z")
        self.assertEqual(ts_z, "2026-10-05 14:30:00")

        # Numeric offset format (+02:00 -> converts to UTC)
        ts_offset = mem_pg.normalize_utc_timestamp("2026-10-05T16:30:00+02:00")
        self.assertEqual(ts_offset, "2026-10-05 14:30:00")

    def test_serialize_tags(self) -> None:
        self.assertIsNone(mem_pg.serialize_tags(None))
        self.assertEqual(mem_pg.serialize_tags(["python", "database"]), "python, database")
        self.assertEqual(mem_pg.serialize_tags("single-tag"), "single-tag")

    def test_validate_path(self) -> None:
        valid_path = mem_pg.validate_path("memories_export.sql")
        self.assertEqual(str(valid_path), "memories_export.sql")

        with self.assertRaises(ValueError):
            mem_pg.validate_path("../escaped.sql")

    def test_format_memory_upsert_sql_standard(self) -> None:
        sample_item = {
            "id": "mem_101",
            "content": "User prefers Earl Grey tea with milk.",
            "category": "preferences",
            "tags": ["beverage", "tea"],
            "visibility": "private",
            "source": "manual",
            "conversation_id": "conv_99",
            "created_at": "2026-10-05T12:00:00Z",
            "updated_at": "2026-10-05T12:05:00Z",
        }
        sql = mem_pg.format_memory_upsert_sql(sample_item)
        self.assertIn("INSERT INTO memories (", sql)
        self.assertIn("'mem_101'", sql)
        self.assertIn("'User prefers Earl Grey tea with milk.'", sql)
        self.assertIn("'preferences'", sql)
        self.assertIn("'beverage, tea'", sql)
        self.assertIn("'2026-10-05 12:00:00'", sql)
        self.assertIn("ON CONFLICT (id) DO UPDATE SET", sql)
        self.assertIn("EXCLUDED.content", sql)

    def test_format_memory_upsert_missing_id_raises_value_error(self) -> None:
        invalid_item = {"content": "Missing ID entirely"}
        with self.assertRaises(ValueError):
            mem_pg.format_memory_upsert_sql(invalid_item)

    def test_sql_injection_resilience(self) -> None:
        malicious_item = {
            "id": "mem_inject'; DROP TABLE users; --",
            "content": "Secret note '; SELECT * FROM secrets; --",
            "category": "cat' OR '1'='1",
        }
        sql = mem_pg.format_memory_upsert_sql(malicious_item)
        self.assertIn("'mem_inject''; DROP TABLE users; --'", sql)
        self.assertIn("'Secret note ''; SELECT * FROM secrets; --'", sql)
        self.assertIn("'cat'' or ''1''=''1'", sql.lower())

    def test_convert_memories_to_postgresql_full_payload(self) -> None:
        payload = {
            "memories": [
                {
                    "id": "mem_1",
                    "content": "Working on Omi CLI PostgreSQL recipe.",
                    "category": "work",
                    "created_at": "2026-10-05T10:00:00Z",
                },
                {
                    "id": "mem_2",
                    "content": "Verified 10 unit tests hermetically.",
                    "category": "engineering",
                    "created_at": "2026-10-05T11:00:00Z",
                },
            ]
        }
        sql, count = mem_pg.convert_memories_to_postgresql(payload["memories"], with_schema=True)
        self.assertEqual(count, 2)
        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS memories", sql)
        self.assertIn("idx_memories_search ON memories USING gin (search_vector)", sql)
        self.assertIn("'mem_1'", sql)
        self.assertIn("'mem_2'", sql)

    def test_convert_memories_to_postgresql_no_schema(self) -> None:
        payload = [{"id": "mem_ns", "content": "No schema test"}]
        sql, count = mem_pg.convert_memories_to_postgresql(payload, with_schema=False)
        self.assertEqual(count, 1)
        self.assertIn("BEGIN;", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS memories", sql)
        self.assertIn("'mem_ns'", sql)

    def test_write_output_sql_atomic_and_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "output.sql"
            mem_pg.write_output_sql("TEST SQL CONTENT 1", str(out_file), overwrite=False)
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.read_text(encoding="utf-8"), "TEST SQL CONTENT 1")

            # Second write without overwrite must raise FileExistsError
            with self.assertRaises(FileExistsError):
                mem_pg.write_output_sql("TEST SQL CONTENT 2", str(out_file), overwrite=False)

            # Second write with overwrite=True must succeed
            mem_pg.write_output_sql("TEST SQL CONTENT 2", str(out_file), overwrite=True)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "TEST SQL CONTENT 2")

    def test_cli_main_e2e_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "output.sql"

            data = [{"id": "cli_1", "content": "E2E file test content."}]
            in_file.write_text(json.dumps(data), encoding="utf-8")

            exit_code = mem_pg.main(["-i", str(in_file), "-o", str(out_file), "--overwrite"])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("cli_1", content)
            self.assertIn("CREATE TABLE IF NOT EXISTS memories", content)

    def test_cli_main_stdin_stdout(self) -> None:
        data = [{"id": "stdin_1", "content": "Streamed from stdin"}]
        json_str = json.dumps(data)

        with patch("sys.stdin", io.StringIO(json_str)):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = mem_pg.main([])
                self.assertEqual(exit_code, 0)
                output = mock_stdout.getvalue()
                self.assertIn("stdin_1", output)
                self.assertIn("CREATE TABLE IF NOT EXISTS memories", output)

    def test_bom_handling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bom_file = Path(tmp_dir) / "bom.json"
            data = [{"id": "bom_1", "content": "UTF-8 BOM test"}]
            # Write with UTF-8 BOM
            bom_file.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))

            loaded = mem_pg.load_input_json(str(bom_file))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["id"], "bom_1")


if __name__ == "__main__":
    unittest.main()
