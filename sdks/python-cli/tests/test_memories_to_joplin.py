#!/usr/bin/env python3
"""Unit tests for memories_to_joplin converter."""

import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memories_to_joplin import (
    format_memory_for_joplin,
    parse_memories_data,
    process_memories_to_joplin,
    render_joplin_markdown,
    sanitize_filename,
    main,
)


class TestMemoriesToJoplin(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("valid_name"), "valid_name")
        self.assertEqual(sanitize_filename("illegal/path:name?"), "illegalpathname")
        self.assertEqual(sanitize_filename("multiple   spaces"), "multiple_spaces")

    def test_parse_memories_data(self):
        self.assertEqual(len(parse_memories_data([{"id": "1"}])), 1)
        self.assertEqual(len(parse_memories_data({"memories": [{"id": "1"}, {"id": "2"}]})), 2)
        json_str = json.dumps({"items": [{"id": "1"}]})
        self.assertEqual(len(parse_memories_data(json_str)), 1)

    def test_format_memory_for_joplin(self):
        raw = {
            "id": "mem_joplin_01",
            "content": "Discussed wearable memory indexing",
            "structured": {
                "title": "Wearable Indexing Architecture",
                "category": "engineering",
            },
            "tags": ["joplin", "offline"],
            "visibility": "private",
            "created_at": "2026-09-25T09:00:00Z",
        }
        res = format_memory_for_joplin(raw)
        self.assertEqual(res["id"], "mem_joplin_01")
        self.assertEqual(res["title"], "Wearable Indexing Architecture")
        self.assertEqual(res["category"], "engineering")
        self.assertEqual(res["tags"], ["joplin", "offline"])

        with self.assertRaises(ValueError):
            format_memory_for_joplin({"content": "missing id"})

    def test_render_joplin_markdown(self):
        rec = {
            "id": "mem_01",
            "title": "Project Kickoff",
            "content": "Detailed meeting notes",
            "category": "work",
            "tags": ["kickoff", "q4"],
            "created_at": "2026-09-25T09:00:00Z",
            "updated_at": "2026-09-25T09:30:00Z",
        }
        md = render_joplin_markdown(rec, notebook="Work Notebook")
        self.assertIn("---", md)
        self.assertIn('notebook: "Work Notebook"', md)
        self.assertIn("- \"kickoff\"", md)
        self.assertIn("# Project Kickoff", md)
        self.assertIn("Detailed meeting notes", md)

    def test_process_memories_to_joplin(self):
        sample = [
            {"id": "1", "content": "First note", "tags": ["tag1"]},
            {"id": "1", "content": "Duplicate note"},
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(sample, f)
            temp_path = f.name

        try:
            notes, count = process_memories_to_joplin([temp_path])
            self.assertEqual(count, 1)  # Deduplicated
            self.assertEqual(len(notes), 1)
            filename, content = notes[0]
            self.assertTrue(filename.endswith(".md"))
            self.assertIn("First note", content)
        finally:
            os.unlink(temp_path)

    def test_cli_jex_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            in_file = Path(tmpdir) / "in.json"
            in_file.write_text(json.dumps([{"id": "1", "content": "JEX test"}]), encoding="utf-8")
            out_jex = Path(tmpdir) / "archive.jex"

            with patch.object(sys, "argv", ["memories_to_joplin.py", str(in_file), "-o", str(out_jex)]):
                main()

            self.assertTrue(out_jex.exists())
            with tarfile.open(out_jex, "r") as tar:
                members = tar.getmembers()
                self.assertEqual(len(members), 1)
                self.assertTrue(members[0].name.endswith(".md"))


if __name__ == "__main__":
    unittest.main()
