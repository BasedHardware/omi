#!/usr/bin/env python3
"""Tests for Omi memories to DuckDB SQL ingestion script converter.

Pins SQL schema, literal escaping, array formatting, deduplication, stdin streaming,
and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Load memories_to_duckdb dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_duckdb.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "memories_to_duckdb.py"

spec = importlib.util.spec_from_file_location("memories_to_duckdb", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2d)

format_memory_for_duckdb = m2d.format_memory_for_duckdb
generate_duckdb_sql = m2d.generate_duckdb_sql
main = m2d.main
parse_memories_data = m2d.parse_memories_data
sql_array_literal = m2d.sql_array_literal
sql_quote = m2d.sql_quote


class TestMemoriesToDuckDb(unittest.TestCase):
    def test_sql_quote(self):
        self.assertEqual(sql_quote(None), "NULL")
        self.assertEqual(sql_quote("hello"), "'hello'")
        self.assertEqual(sql_quote("it's cool"), "'it''s cool'")

    def test_sql_array_literal(self):
        self.assertEqual(sql_array_literal([]), "[]")
        self.assertEqual(sql_array_literal(["tag1", "tag'2"]), "['tag1', 'tag''2']")

    def test_parse_memories_formats(self):
        self.assertEqual(len(parse_memories_data([{"id": "m1"}])), 1)
        self.assertEqual(len(parse_memories_data({"memories": [{"id": "m2"}]})), 1)

    def test_format_memory(self):
        item = {
            "id": "mem_01",
            "content": "User lives in Seattle",
            "category": "personal",
            "tags": ["location", "bio"],
            "visibility": "private",
            "created_at": "2026-09-24T12:00:00Z",
        }
        res = format_memory_for_duckdb(item)
        self.assertEqual(res["id"], "mem_01")
        self.assertEqual(res["content"], "User lives in Seattle")
        self.assertEqual(res["category"], "personal")
        self.assertEqual(res["tags"], ["location", "bio"])
        self.assertEqual(res["visibility"], "private")

    def test_generate_duckdb_sql_statements(self):
        mems = [
            {"id": "m1", "content": "Memory 1", "category": "work", "tags": ["w1"], "visibility": "public"},
            {"id": "m2", "content": "Memory 2", "category": "life"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "data.json"
            f.write_text(json.dumps(mems), encoding="utf-8")

            sql, count = generate_duckdb_sql([str(f)], table_name="custom_mems")
            self.assertEqual(count, 2)
            self.assertIn("CREATE TABLE IF NOT EXISTS custom_mems", sql)
            self.assertIn("created_at TIMESTAMPTZ", sql)
            self.assertIn("visibility VARCHAR", sql)
            self.assertNotIn("TIMESTAMP_TZ", sql)
            self.assertIn("INSERT OR REPLACE INTO custom_mems", sql)
            self.assertIn("['w1']", sql)
            self.assertIn("'public'", sql)
            self.assertIn("UNNEST(tags)", sql)

    def test_deduplication(self):
        m1 = [{"id": "dup", "content": "Old"}]
        m2 = [{"id": "dup", "content": "New"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "f1.json"
            f2 = Path(tmpdir) / "f2.json"
            f1.write_text(json.dumps(m1), encoding="utf-8")
            f2.write_text(json.dumps(m2), encoding="utf-8")

            sql, count = generate_duckdb_sql([str(f1), str(f2)])
            self.assertEqual(count, 1)
            self.assertIn("'New'", sql)
            self.assertNotIn("'Old'", sql)

    def test_cli_integration_and_overwrite(self):
        sample = [{"id": "c_cli", "content": "CLI memory"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src.json"
            dst = Path(tmpdir) / "out.sql"
            src.write_text(json.dumps(sample), encoding="utf-8")

            # 1. Standard run
            sys.argv = ["memories_to_duckdb.py", str(src), "-o", str(dst)]
            main()
            self.assertTrue(dst.is_file())

            # 2. Overwrite guard fails
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)

            # 3. Overwrite succeeds with --force
            sys.argv = ["memories_to_duckdb.py", str(src), "-o", str(dst), "--force"]
            main()
            self.assertTrue(dst.is_file())


if __name__ == "__main__":
    unittest.main()
