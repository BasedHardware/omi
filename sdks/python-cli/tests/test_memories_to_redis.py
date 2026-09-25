#!/usr/bin/env python3
"""Unit tests for memories_to_redis converter.

Pins RedisJSON command generation, single-quote escaping without backslash doubling,
deduplication, clean piped command output, stdin piping, and overwrite protection.
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

# Load memories_to_redis dynamically per repository convention
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_redis.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "memories_to_redis.py"

spec = importlib.util.spec_from_file_location("memories_to_redis", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2r)

format_memory_for_redis = m2r.format_memory_for_redis
generate_redis_commands = m2r.generate_redis_commands
parse_memories_data = m2r.parse_memories_data
redis_escape_string = m2r.redis_escape_string
main = m2r.main


class TestMemoriesToRedis(unittest.TestCase):
    def test_redis_escape_string(self):
        self.assertEqual(redis_escape_string("hello"), "'hello'")
        self.assertEqual(redis_escape_string("It's a test"), "'It\\'s a test'")

    def test_redis_escape_string_preserves_backslashes(self):
        # In redis-cli single-quoted strings, backslashes are literal and must not be doubled
        raw_path = r"Path C:\Users\omi"
        escaped = redis_escape_string(raw_path)
        self.assertEqual(escaped, r"'Path C:\Users\omi'")

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
                "content": r"Windows path C:\data",
                "category": "notes",
                "tags": ["test"],
            },
            {
                "id": "mem_1",  # duplicate ID
                "content": "Duplicate memory",
                "category": "notes",
            },
            {
                "id": "mem_2",
                "content": "Second note with 'single quotes'",
                "category": "work",
            },
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(sample_data, f)
            temp_path = f.name

        try:
            content, count = generate_redis_commands([temp_path], key_prefix="omi:mem:")
            self.assertEqual(count, 2)  # Deduplicated from 3 to 2

            # Assert NO comment lines exist that would break piped redis-cli
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            self.assertFalse(any(line.startswith("#") for line in lines))

            # Every line is an executable JSON.SET command
            self.assertTrue(all(line.startswith("JSON.SET ") for line in lines))
            self.assertEqual(len(lines), 2)

            # Check key prefix and escaping
            self.assertIn("JSON.SET omi:mem:mem_1 $", lines[0])
            self.assertIn("JSON.SET omi:mem:mem_2 $", lines[1])
            self.assertIn(r"\'single quotes\'", lines[1])
        finally:
            os.unlink(temp_path)

    def test_cli_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "out.redis"
            out_file.write_text("existing", encoding="utf-8")

            in_file = Path(tmpdir) / "input.json"
            in_file.write_text(json.dumps([{"id": "1", "content": "test"}]), encoding="utf-8")

            # Exits with error code 1 without --force
            code = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code, 1)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "existing")

            # Overwrites cleanly with --force
            code_force = main([str(in_file), "-o", str(out_file), "--force"])
            self.assertEqual(code_force, 0)
            self.assertIn("JSON.SET memory:1 $", out_file.read_text(encoding="utf-8"))

    def test_cli_stdin(self):
        sample = json.dumps([{"id": "stdin_1", "content": "Piped redis"}])
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = Path(tmpdir) / "stdin.redis"
                code = main(["-", "-o", str(out_path)])
                self.assertEqual(code, 0)
                self.assertTrue(out_path.exists())
                self.assertIn("JSON.SET memory:stdin_1 $", out_path.read_text(encoding="utf-8"))
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()
