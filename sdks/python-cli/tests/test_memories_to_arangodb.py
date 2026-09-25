#!/usr/bin/env python3
"""Unit tests for memories_to_arangodb converter."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memories_to_arangodb import (
    aql_array_literal,
    aql_quote,
    format_memory_for_arango,
    generate_aql,
    parse_memories_data,
    main,
)


class TestMemoriesToArangoDB(unittest.TestCase):
    def test_aql_quote(self):
        self.assertEqual(aql_quote(None), "null")
        self.assertEqual(aql_quote(True), "true")
        self.assertEqual(aql_quote(False), "false")
        self.assertEqual(aql_quote(123), "123")
        self.assertEqual(aql_quote(3.14), "3.14")
        self.assertEqual(aql_quote("hello"), "'hello'")
        self.assertEqual(aql_quote("It's a test"), "'It\\'s a test'")

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

    def test_generate_aql(self):
        sample = [
            {"id": "1", "content": "Memory one", "category": "work", "tags": ["t1"]},
            {"id": "1", "content": "Duplicate", "category": "work"},
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(sample, f)
            temp_path = f.name

        try:
            aql, count = generate_aql([temp_path], collection_name="user_memories")
            self.assertEqual(count, 1)
            self.assertIn("UPSERT { _key: '1' }", aql)
            self.assertIn("IN user_memories;", aql)
        finally:
            os.unlink(temp_path)

    def test_cli_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "out.aql"
            out_file.write_text("pre-existing", encoding="utf-8")

            in_file = Path(tmpdir) / "input.json"
            in_file.write_text(json.dumps([{"id": "1", "content": "test"}]), encoding="utf-8")

            with patch.object(sys, "argv", ["memories_to_arangodb.py", str(in_file), "-o", str(out_file)]):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)

            with patch.object(sys, "argv", ["memories_to_arangodb.py", str(in_file), "-o", str(out_file), "--force"]):
                main()
                self.assertIn("UPSERT { _key: '1' }", out_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
