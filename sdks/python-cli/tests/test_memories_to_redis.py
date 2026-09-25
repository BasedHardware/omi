#!/usr/bin/env python3
"""Unit tests for memories_to_redis converter."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memories_to_redis import (
    format_memory_for_redis,
    generate_redis_commands,
    parse_memories_data,
    redis_escape_string,
    main,
)


class TestMemoriesToRedis(unittest.TestCase):
    def test_redis_escape_string(self):
        self.assertEqual(redis_escape_string("hello"), "'hello'")
        self.assertEqual(redis_escape_string("It's a test"), "'It\\'s a test'")
        self.assertEqual(redis_escape_string("back\\slash"), "'back\\\\slash'")

    def test_parse_memories_data(self):
        self.assertEqual(len(parse_memories_data([{"id": "1"}])), 1)
        self.assertEqual(len(parse_memories_data({"memories": [{"id": "1"}, {"id": "2"}]})), 2)
        json_str = json.dumps({"items": [{"id": "1"}]})
        self.assertEqual(len(parse_memories_data(json_str)), 1)

    def test_format_memory_for_redis(self):
        raw = {
            "id": "mem_100",
            "content": "Redis Stack fast indexing",
            "category": "database",
            "tags": ["redis", "nosql"],
            "visibility": "public",
            "created_at": "2026-09-25T08:00:00Z",
        }
        res = format_memory_for_redis(raw)
        self.assertEqual(res["id"], "mem_100")
        self.assertEqual(res["content"], "Redis Stack fast indexing")
        self.assertEqual(res["category"], "database")
        self.assertEqual(res["tags"], ["redis", "nosql"])
        self.assertEqual(res["visibility"], "public")

        with self.assertRaises(ValueError):
            format_memory_for_redis({"content": "no id"})

    def test_generate_redis_commands(self):
        sample_data = [
            {
                "id": "mem_1",
                "content": "First Redis memory",
                "category": "notes",
                "tags": ["test"],
            },
            {
                "id": "mem_1",  # duplicate ID
                "content": "Duplicate memory",
                "category": "notes",
            }
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(sample_data, f)
            temp_path = f.name

        try:
            content, count = generate_redis_commands([temp_path], key_prefix="omi:mem:", index_name="idx:omi_mem")
            self.assertEqual(count, 1)  # Deduplicated
            self.assertIn("JSON.SET omi:mem:mem_1 $", content)
            self.assertIn("FT.CREATE idx:omi_mem", content)
        finally:
            os.unlink(temp_path)

    def test_cli_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "out.redis"
            out_file.write_text("existing", encoding="utf-8")

            in_file = Path(tmpdir) / "input.json"
            in_file.write_text(json.dumps([{"id": "1", "content": "test"}]), encoding="utf-8")

            with patch.object(sys, "argv", ["memories_to_redis.py", str(in_file), "-o", str(out_file)]):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)

            with patch.object(sys, "argv", ["memories_to_redis.py", str(in_file), "-o", str(out_file), "--force"]):
                main()
                self.assertIn("JSON.SET memory:1 $", out_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
