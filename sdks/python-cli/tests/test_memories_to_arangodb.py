#!/usr/bin/env python3
"""Unit tests for memories_to_arangodb converter.

Pins AQL generation, literal quoting (including newline and quote escaping),
collection scoping, lack of trailing statement semicolons, and overwrite guards.
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

# Load memories_to_arangodb dynamically following repo convention
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_arangodb.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "memories_to_arangodb.py"

spec = importlib.util.spec_from_file_location("memories_to_arangodb", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2a)

aql_array_literal = m2a.aql_array_literal
aql_quote = m2a.aql_quote
format_memory_for_arango = m2a.format_memory_for_arango
generate_aql = m2a.generate_aql
main = m2a.main
parse_memories_data = m2a.parse_memories_data


class TestMemoriesToArangoDB(unittest.TestCase):
    def test_aql_quote(self):
        self.assertEqual(aql_quote(None), "null")
        self.assertEqual(aql_quote(True), "true")
        self.assertEqual(aql_quote(False), "false")
        self.assertEqual(aql_quote(123), "123")
        self.assertEqual(aql_quote(3.14), "3.14")
        self.assertEqual(aql_quote("hello"), "'hello'")
        self.assertEqual(aql_quote("It's a test"), "'It\\'s a test'")

    def test_aql_quote_escapes_newlines_and_tabs(self):
        multiline = "Line 1\r\nLine 2\tTabbed"
        quoted = aql_quote(multiline)
        self.assertEqual(quoted, "'Line 1\\r\\nLine 2\\tTabbed'")
        self.assertNotIn("\n", quoted)
        self.assertNotIn("\r", quoted)
        self.assertNotIn("\t", quoted)

    def test_aql_array_literal(self):
        self.assertEqual(aql_array_literal([]), "[]")
        self.assertEqual(aql_array_literal(["alpha", "beta"]), "['alpha', 'beta']")

    def test_parse_memories_data(self):
        self.assertEqual(len(parse_memories_data([{"id": "1"}])), 1)
        self.assertEqual(len(parse_memories_data({"data": [{"id": "1"}, {"id": "2"}]})), 2)
        json_str = json.dumps({"items": [{"id": "1"}]})
        self.assertEqual(len(parse_memories_data(json_str)), 1)

    def test_format_memory_for_arango(self):
        raw = {
            "id": "mem_arango_01",
            "content": "Graph traversal test",
            "category": "graph",
            "tags": ["graph", "arango"],
            "visibility": "shared",
            "created_at": "2026-09-25T09:00:00Z",
        }
        res = format_memory_for_arango(raw)
        self.assertEqual(res["id"], "mem_arango_01")
        self.assertEqual(res["content"], "Graph traversal test")
        self.assertEqual(res["category"], "graph")
        self.assertEqual(res["tags"], ["graph", "arango"])
        self.assertEqual(res["visibility"], "shared")

        with self.assertRaises(ValueError):
            format_memory_for_arango({"content": "no id"})

    def test_generate_aql_no_trailing_semicolons(self):
        sample = [
            {"id": "1", "content": "Memory one\nwith newline", "category": "work", "tags": ["t1"]},
            {"id": "2", "content": "Memory two", "category": "personal"},
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(sample, f)
            temp_path = f.name

        try:
            aql, count = generate_aql([temp_path], collection_name="user_memories")
            self.assertEqual(count, 2)
            self.assertIn("UPSERT { _key: '1' }", aql)
            self.assertIn("IN user_memories", aql)
            # Verify no statement ends with a semicolon (AQL syntax rule)
            self.assertIn("'Memory one\\nwith newline'", aql)
            for line in aql.splitlines():
                if line.startswith("UPSERT"):
                    self.assertFalse(line.endswith(";"), f"AQL statement must not end with semicolon: {line}")
                    self.assertTrue(line.endswith("IN user_memories"))
        finally:
            os.unlink(temp_path)

    def test_cli_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "out.aql"
            out_file.write_text("pre-existing", encoding="utf-8")

            in_file = Path(tmpdir) / "input.json"
            in_file.write_text(json.dumps([{"id": "1", "content": "test"}]), encoding="utf-8")

            # Fails without --force
            code = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code, 1)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "pre-existing")

            # Succeeds with --force
            code_force = main([str(in_file), "-o", str(out_file), "--force"])
            self.assertEqual(code_force, 0)
            self.assertIn("UPSERT { _key: '1' }", out_file.read_text(encoding="utf-8"))

    def test_cli_stdin(self):
        sample = json.dumps([{"id": "stdin_m", "content": "Piped memory"}])
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = Path(tmpdir) / "stdin.aql"
                code = main(["-", "-o", str(out_path)])
                self.assertEqual(code, 0)
                self.assertTrue(out_path.exists())
                self.assertIn("UPSERT { _key: 'stdin_m' }", out_path.read_text(encoding="utf-8"))
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()
