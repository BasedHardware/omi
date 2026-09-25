#!/usr/bin/env python3
"""Unit tests for memories_to_surrealdb converter.

Pins SurrealQL syntax, record ID escaping, schema definition, deduplication,
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
    script_path = Path(__file__).resolve().parent / "memories_to_surrealdb.py"

spec = importlib.util.spec_from_file_location("memories_to_surrealdb", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2s)

format_memory_for_surreal = m2s.format_memory_for_surreal
generate_surrealql = m2s.generate_surrealql
parse_memories_data = m2s.parse_memories_data
surreal_array_literal = m2s.surreal_array_literal
surreal_quote = m2s.surreal_quote
surreal_record_id = m2s.surreal_record_id
main = m2s.main


class TestMemoriesToSurrealDB(unittest.TestCase):
    def test_surreal_quote(self):
        self.assertEqual(surreal_quote(None), "NONE")
        self.assertEqual(surreal_quote(True), "true")
        self.assertEqual(surreal_quote(False), "false")
        self.assertEqual(surreal_quote(42), "42")
        self.assertEqual(surreal_quote(3.14), "3.14")
        self.assertEqual(surreal_quote("hello world"), "'hello world'")
        self.assertEqual(surreal_quote("It's a test"), "'It\\'s a test'")

    def test_surreal_quote_escapes_newlines(self):
        quoted = surreal_quote("Line 1\nLine 2")
        self.assertEqual(quoted, "'Line 1\\nLine 2'")

    def test_surreal_array_literal(self):
        self.assertEqual(surreal_array_literal([]), "[]")
        self.assertEqual(surreal_array_literal(["tag1", "tag's"]), "['tag1', 'tag\\'s']")

    def test_surreal_record_id(self):
        self.assertEqual(surreal_record_id("memory", "12345"), "memory:⟨12345⟩")
        self.assertEqual(surreal_record_id("memories", "mem_abc-def"), "memories:⟨mem_abc-def⟩")

    def test_parse_memories_data(self):
        self.assertEqual(len(parse_memories_data([{"id": "1"}])), 1)
        self.assertEqual(len(parse_memories_data({"memories": [{"id": "1"}, {"id": "2"}]})), 2)
        json_str = json.dumps({"items": [{"id": "1"}]})
        self.assertEqual(len(parse_memories_data(json_str)), 1)

    def test_format_memory_for_surreal(self):
        raw = {
            "id": "mem_001",
            "content": "Discussed AI agent architecture",
            "category": "work",
            "tags": ["ai", "architecture"],
            "visibility": "private",
            "created_at": "2026-09-25T08:00:00Z",
            "updated_at": "2026-09-25T08:30:00Z",
        }
        res = format_memory_for_surreal(raw)
        self.assertEqual(res["id"], "mem_001")
        self.assertEqual(res["content"], "Discussed AI agent architecture")
        self.assertEqual(res["category"], "work")
        self.assertEqual(res["tags"], ["ai", "architecture"])
        self.assertEqual(res["visibility"], "private")

        with self.assertRaises(ValueError):
            format_memory_for_surreal({"content": "missing id"})

    def test_generate_surrealql(self):
        sample_data = [
            {
                "id": "mem_1",
                "content": "First memory",
                "category": "work",
                "tags": ["alpha"],
            },
            {
                "id": "mem_1",  # duplicate ID
                "content": "Updated memory",
                "category": "work",
            },
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(sample_data, f)
            temp_path = f.name

        try:
            sql, count = generate_surrealql([temp_path], table_name="custom_mem")
            self.assertEqual(count, 1)  # Deduplicated
            self.assertIn("DEFINE TABLE IF NOT EXISTS custom_mem SCHEMALESS;", sql)
            self.assertIn("UPSERT custom_mem:⟨mem_1⟩ MERGE", sql)
        finally:
            os.unlink(temp_path)

    def test_cli_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "out.surql"
            out_file.write_text("existing content", encoding="utf-8")

            in_file = Path(tmpdir) / "input.json"
            in_file.write_text(json.dumps([{"id": "1", "content": "test"}]), encoding="utf-8")

            # Exits with 1 without --force
            code = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code, 1)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "existing content")

            # Succeeds with --force
            code_force = main([str(in_file), "-o", str(out_file), "--force"])
            self.assertEqual(code_force, 0)
            self.assertIn("UPSERT memory:⟨1⟩ MERGE", out_file.read_text(encoding="utf-8"))

    def test_cli_stdin(self):
        sample = json.dumps([{"id": "stdin_1", "content": "Piped surreal memory"}])
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = Path(tmpdir) / "stdin.surql"
                code = main(["-", "-o", str(out_path)])
                self.assertEqual(code, 0)
                self.assertTrue(out_path.exists())
                self.assertIn("UPSERT memory:⟨stdin_1⟩ MERGE", out_path.read_text(encoding="utf-8"))
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()
