#!/usr/bin/env python3
"""Unit tests for memories_to_surrealdb converter."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memories_to_surrealdb import (
    format_memory_for_surreal,
    generate_surrealql,
    parse_memories_data,
    surreal_array_literal,
    surreal_quote,
    surreal_record_id,
    main,
)


class TestMemoriesToSurrealDB(unittest.TestCase):
    def test_surreal_quote(self):
        self.assertEqual(surreal_quote(None), "NONE")
        self.assertEqual(surreal_quote(True), "true")
        self.assertEqual(surreal_quote(False), "false")
        self.assertEqual(surreal_quote(42), "42")
        self.assertEqual(surreal_quote(3.14), "3.14")
        self.assertEqual(surreal_quote("hello world"), "'hello world'")
        self.assertEqual(surreal_quote("It's a test"), "'It\\'s a test'")

    def test_surreal_array_literal(self):
        self.assertEqual(surreal_array_literal([]), "[]")
        self.assertEqual(surreal_array_literal(["tag1", "tag's"]), "['tag1', 'tag\\'s']")

    def test_surreal_record_id(self):
        self.assertEqual(surreal_record_id("memory", "12345"), "memory:⟨12345⟩")
        self.assertEqual(surreal_record_id("memories", "mem_abc-def"), "memories:⟨mem_abc-def⟩")

    def test_parse_memories_data(self):
        # Raw list
        self.assertEqual(len(parse_memories_data([{"id": "1"}])), 1)
        # Dict with 'memories' key
        self.assertEqual(len(parse_memories_data({"memories": [{"id": "1"}, {"id": "2"}]})), 2)
        # JSON string
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

        # Missing ID raises ValueError
        with self.assertRaises(ValueError):
            format_memory_for_surreal({"content": "no id"})

    def test_generate_surrealql(self):
        sample_data = [
            {
                "id": "mem_1",
                "content": "First memory",
                "category": "ideas",
                "tags": ["brainstorm"],
                "created_at": "2026-09-25T08:00:00Z",
            },
            {
                "id": "mem_1",  # duplicate ID
                "content": "Updated first memory",
                "category": "ideas",
                "tags": ["brainstorm"],
                "created_at": "2026-09-25T08:00:00Z",
            }
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(sample_data, f)
            temp_path = f.name

        try:
            sql, count = generate_surrealql([temp_path], table_name="custom_memory")
            self.assertEqual(count, 1)  # Deduplicated
            self.assertIn("DEFINE TABLE IF NOT EXISTS custom_memory SCHEMALESS;", sql)
            self.assertIn("UPSERT custom_memory:⟨mem_1⟩ SET", sql)
            self.assertIn("type::datetime('2026-09-25T08:00:00Z')", sql)
        finally:
            os.unlink(temp_path)

    def test_cli_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "out.surql"
            out_file.write_text("existing content", encoding="utf-8")

            in_file = Path(tmpdir) / "input.json"
            in_file.write_text(json.dumps([{"id": "1", "content": "test"}]), encoding="utf-8")

            # Calling main without --force should fail
            with patch.object(sys, "argv", ["memories_to_surrealdb.py", str(in_file), "-o", str(out_file)]):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)

            # Calling main with --force should succeed
            with patch.object(sys, "argv", ["memories_to_surrealdb.py", str(in_file), "-o", str(out_file), "--force"]):
                main()
                self.assertIn("UPSERT memory:⟨1⟩ SET", out_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
