#!/usr/bin/env python3
"""Unit tests for memories_to_surrealdb converter.

Pins SurrealQL syntax, record ID escaping, schema definition, deduplication,
datetime literal formatting, timestamp fallback resilience, delimiter guards,
stdin piping, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Load memories_to_surrealdb dynamically per repository convention
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_surrealdb.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "surreal_memories_to_surrealdb.py"

spec = importlib.util.spec_from_file_location("memories_to_surrealdb", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2s)

format_memory_for_surreal = m2s.format_memory_for_surreal
generate_surrealql = m2s.generate_surrealql
parse_memories_data = m2s.parse_memories_data
surreal_array_literal = m2s.surreal_array_literal
surreal_datetime_literal = m2s.surreal_datetime_literal
surreal_quote = m2s.surreal_quote
surreal_record_id = m2s.surreal_record_id


class TestMemoriesToSurrealDB(unittest.TestCase):
    def test_surreal_quote(self):
        self.assertEqual(surreal_quote("simple"), "'simple'")
        self.assertEqual(surreal_quote("it's cool"), r"'it\'s cool'")
        self.assertEqual(surreal_quote(r"path\to\file"), r"'path\\to\\file'")
        self.assertEqual(surreal_quote(None), "NONE")
        self.assertEqual(surreal_quote(True), "true")
        self.assertEqual(surreal_quote(False), "false")
        self.assertEqual(surreal_quote(42), "42")

    def test_surreal_quote_escapes_newlines(self):
        # SurrealQL requires literal newlines inside '...' to be escaped as \\n
        raw = "Line 1\nLine 2\r\nLine 3\tTab"
        escaped = surreal_quote(raw)
        self.assertNotIn("\n", escaped)
        self.assertNotIn("\r", escaped)
        self.assertIn(r"\n", escaped)
        self.assertIn(r"\r", escaped)
        self.assertIn(r"\t", escaped)

    def test_surreal_datetime_literal(self):
        self.assertEqual(surreal_datetime_literal(None), "NONE")
        self.assertEqual(surreal_datetime_literal(""), "NONE")
        # Valid ISO datetimes format to d'...'
        self.assertEqual(surreal_datetime_literal("2026-09-25T08:00:00Z"), "d'2026-09-25T08:00:00Z'")
        self.assertEqual(surreal_datetime_literal("'2026-01-01T00:00:00Z'"), "d'2026-01-01T00:00:00Z'")
        self.assertEqual(surreal_datetime_literal("2026-05-12 15:30:00"), "d'2026-05-12 15:30:00'")
        # Unparseable/malformed timestamps fall back to plain quoted string literals
        # so that a single corrupted timestamp does not abort the entire surreal import
        self.assertEqual(surreal_datetime_literal("not-a-timestamp"), "'not-a-timestamp'")
        self.assertEqual(surreal_datetime_literal("2026-99-99T99:99:99"), "'2026-99-99T99:99:99'")

    def test_surreal_array_literal(self):
        self.assertEqual(surreal_array_literal([]), "[]")
        self.assertEqual(surreal_array_literal(["work", "urgent"]), "['work', 'urgent']")
        self.assertEqual(surreal_array_literal(["tag with 'quotes'"]), r"['tag with \'quotes\'']")

    def test_surreal_record_id(self):
        self.assertEqual(surreal_record_id("memory", "12345"), "memory:⟨12345⟩")
        self.assertEqual(surreal_record_id("memories", "mem_abc-def"), "memories:⟨mem_abc-def⟩")
        # Empty id is rejected
        with self.assertRaises(ValueError):
            surreal_record_id("memory", "")
        # Literal ⟩ closing bracket in id is rejected to avoid breaking SurrealQL wrapper
        with self.assertRaises(ValueError):
            surreal_record_id("memory", "mem_brk⟩x")

    def test_parse_memories_data(self):
        self.assertEqual(len(parse_memories_data([{"id": "1"}])), 1)
        self.assertEqual(len(parse_memories_data({"memories": [{"id": "1"}, {"id": "2"}], "total": 2})), 2)
        self.assertEqual(len(parse_memories_data(json.dumps([{"id": "3"}]))), 1)

    def test_format_memory_for_surreal(self):
        raw = {
            "id": "mem_100",
            "content": "User prefers concise responses",
            "category": "preferences",
            "tags": ["ai", "prompting"],
            "created_at": "2026-09-25T08:00:00Z",
        }
        res = format_memory_for_surreal(raw)
        self.assertEqual(res["id"], "mem_100")
        self.assertEqual(res["content"], "User prefers concise responses")
        self.assertEqual(res["tags"], ["ai", "prompting"])

        # Missing ID raises ValueError
        with self.assertRaises(ValueError):
            format_memory_for_surreal({"content": "No id"})

    def test_generate_surrealql(self):
        sample = [
            {"id": "1", "content": "First note", "category": "work", "created_at": "2026-09-20T10:00:00Z"},
            {"id": "2", "content": "Second note\nMulti-line", "tags": ["personal"]},
            {"id": "1", "content": "Duplicate note"},  # Should deduplicate
            {"id": "3", "content": "Malformed timestamp note", "created_at": "not-a-timestamp"},
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(sample, f)
            tpath = f.name

        try:
            sql, count = generate_surrealql([tpath], table_name="memory")
            self.assertEqual(count, 3)
            self.assertIn("OPTION IMPORT;", sql)
            self.assertIn("DEFINE TABLE IF NOT EXISTS memory SCHEMALESS;", sql)
            self.assertIn("UPSERT memory:⟨1⟩ MERGE", sql)
            self.assertIn("UPSERT memory:⟨2⟩ MERGE", sql)
            self.assertIn("UPSERT memory:⟨3⟩ MERGE", sql)
            self.assertIn(r"Second note\nMulti-line", sql)
            # Ensure malformed timestamp falls back to plain quoted string without d'...'
            self.assertIn("created_at: 'not-a-timestamp'", sql)
            self.assertNotIn("d'not-a-timestamp'", sql)
        finally:
            if os.path.exists(tpath):
                os.remove(tpath)

    def test_cli_overwrite_protection(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump([{"id": "1", "content": "Test"}], f)
            tpath = f.name
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".surql", encoding="utf-8") as f:
            f.write("-- Existing")
            outpath = f.name

        try:
            ret = m2s.main([tpath, "-o", outpath])
            self.assertEqual(ret, 1)

            ret_force = m2s.main([tpath, "-o", outpath, "--force"])
            self.assertEqual(ret_force, 0)
        finally:
            for p in (tpath, outpath):
                if os.path.exists(p):
                    os.remove(p)

    def test_cli_stdin(self):
        sample = json.dumps([{"id": "stdin_1", "content": "Piped content"}])
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(sample)
            sys.stdout = io.StringIO()
            ret = m2s.main(["-", "-o", "-"])
            self.assertEqual(ret, 0)
            output = sys.stdout.getvalue()
            self.assertIn("UPSERT memory:⟨stdin_1⟩ MERGE", output)
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
