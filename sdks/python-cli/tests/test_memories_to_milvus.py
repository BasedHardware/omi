#!/usr/bin/env python3
"""Tests for memories to Milvus / Zilliz entity batch converter.

Pins collection schema payload structure, deduplication, category and date filtering,
stdin piping, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Load memories_to_milvus example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_milvus.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "memories_to_milvus.py"

spec = importlib.util.spec_from_file_location("memories_to_milvus", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2m)

extract_memories = m2m.extract_memories
main = m2m.main
parse_iso_datetime = m2m.parse_iso_datetime
transform_to_milvus = m2m.transform_to_milvus


class TestMemoriesToMilvus(unittest.TestCase):
    def test_extract_memories_list(self):
        data = [{"id": "m1", "content": "Entity 1"}, {"id": "m2", "content": "Entity 2"}]
        res = extract_memories(data)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["id"], "m1")

    def test_extract_memories_dict(self):
        data = {"memories": [{"id": "m1", "content": "Entity 1"}]}
        res = extract_memories(data)
        self.assertEqual(len(res), 1)

    def test_extract_memories_invalid_json(self):
        with self.assertRaises(ValueError):
            extract_memories("{bad json")

    def test_parse_iso_datetime(self):
        dt = parse_iso_datetime("2026-09-24T12:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertIsNone(parse_iso_datetime("invalid"))

    def test_transform_to_milvus_basic(self):
        mems = [
            {
                "id": "mem_42",
                "content": "User prefers Vim keybindings in VS Code",
                "category": "preferences",
                "created_at": "2026-09-24T10:00:00Z",
                "updated_at": "2026-09-24T10:30:00Z",
                "manually_added": True,
                "tags": ["editor", "vim"],
            }
        ]
        payload = transform_to_milvus(mems, collection_name="developer_memories")
        self.assertEqual(payload["collectionName"], "developer_memories")
        self.assertEqual(len(payload["data"]), 1)

        ent = payload["data"][0]
        self.assertEqual(ent["id"], "mem_42")
        self.assertEqual(ent["text"], "User prefers Vim keybindings in VS Code")
        self.assertEqual(ent["category"], "preferences")
        self.assertEqual(ent["created_at"], "2026-09-24T10:00:00Z")
        self.assertEqual(ent["updated_at"], "2026-09-24T10:30:00Z")
        self.assertTrue(ent["manually_added"])
        self.assertEqual(ent["tags"], ["editor", "vim"])

    def test_transform_to_milvus_dedup(self):
        mems = [
            {"id": "duplicate_id", "content": "First"},
            {"id": "duplicate_id", "content": "Second"},
            {"id": "unique_id", "content": "Third"},
        ]
        payload = transform_to_milvus(mems)
        self.assertEqual(len(payload["data"]), 2)
        self.assertEqual(payload["data"][0]["text"], "First")

    def test_transform_to_milvus_category_filter(self):
        mems = [
            {"id": "m1", "content": "Work item", "category": "work"},
            {"id": "m2", "content": "Life item", "category": "personal"},
        ]
        payload = transform_to_milvus(mems, category_filter="work")
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["id"], "m1")

    def test_transform_to_milvus_min_date_filter(self):
        mems = [
            {"id": "m1", "content": "Old", "created_at": "2026-08-01T00:00:00Z"},
            {"id": "m2", "content": "Recent", "created_at": "2026-09-24T00:00:00Z"},
        ]
        payload = transform_to_milvus(mems, min_date="2026-09-01T00:00:00Z")
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["id"], "m2")

    def test_cli_end_to_end_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "memories.json"
            out_file = tmppath / "milvus_batch.json"

            sample_data = [
                {"id": "mem_x1", "content": "Note 1", "category": "tech"},
                {"id": "mem_x2", "content": "Note 2", "category": "infra"},
            ]
            in_file.write_text(json.dumps(sample_data), encoding="utf-8")

            code = main([str(in_file), "-o", str(out_file), "-c", "custom_collection"])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())

            result = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(result["collectionName"], "custom_collection")
            self.assertEqual(len(result["data"]), 2)

    def test_cli_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "input.json"
            out_file = tmppath / "output.json"

            in_file.write_text(json.dumps([{"id": "1", "content": "test"}]), encoding="utf-8")
            out_file.write_text("existing content", encoding="utf-8")

            code_fail = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code_fail, 1)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "existing content")

            code_ok = main([str(in_file), "-o", str(out_file), "--force"])
            self.assertEqual(code_ok, 0)
            result = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(result["data"]), 1)

    def test_cli_stdin_to_stdout(self):
        sample = json.dumps([{"id": "stdin_1", "content": "Streaming memory"}])
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(sample)
            sys.stdout = io.StringIO()
            code = main(["-"])
            self.assertEqual(code, 0)
            output = sys.stdout.getvalue()
            result = json.loads(output)
            self.assertEqual(len(result["data"]), 1)
            self.assertEqual(result["data"][0]["id"], "stdin_1")
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
