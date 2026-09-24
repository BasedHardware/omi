#!/usr/bin/env python3
"""Tests for memories to Weaviate vector database batch converter.

Pins Weaviate v3/v4 batch payload structure, RFC 4122 deterministic UUID generation,
memory deduplication, category/date filtering, streaming stdin, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

# Load memories_to_weaviate example script dynamically per sibling test convention
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_weaviate.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "memories_to_weaviate.py"

spec = importlib.util.spec_from_file_location("memories_to_weaviate", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2w)

deterministic_uuid = m2w.deterministic_uuid
extract_memories = m2w.extract_memories
load_input_sources = m2w.load_input_sources
main = m2w.main
parse_iso_datetime = m2w.parse_iso_datetime
transform_to_weaviate = m2w.transform_to_weaviate


class TestMemoriesToWeaviate(unittest.TestCase):
    def test_deterministic_uuid_valid_uuid(self):
        sample_uuid = "12345678-1234-5678-1234-567812345678"
        res = deterministic_uuid(sample_uuid)
        self.assertEqual(res, sample_uuid)

    def test_deterministic_uuid_arbitrary_string(self):
        raw_id = "memory_user_preference_99"
        res1 = deterministic_uuid(raw_id)
        res2 = deterministic_uuid(raw_id)
        # Must be strictly deterministic across calls
        self.assertEqual(res1, res2)
        # Must parse as valid RFC 4122 UUID
        parsed = uuid.UUID(res1)
        self.assertEqual(str(parsed), res1)

    def test_deterministic_uuid_empty_or_none(self):
        res = deterministic_uuid(None)
        self.assertTrue(uuid.UUID(res))

    def test_extract_memories_from_list(self):
        data = [{"id": "m1", "content": "Knowledge 1"}, {"id": "m2", "content": "Knowledge 2"}]
        res = extract_memories(data)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["id"], "m1")

    def test_extract_memories_from_json_string(self):
        json_str = json.dumps({"memories": [{"id": "m1", "content": "Learning from Omi"}]})
        res = extract_memories(json_str)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["content"], "Learning from Omi")

    def test_extract_memories_single_dict(self):
        single = {"id": "m1", "content": "Lone memory"}
        res = extract_memories(single)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "m1")

    def test_extract_memories_invalid_json(self):
        with self.assertRaises(ValueError):
            extract_memories("{bad json")

    def test_extract_memories_invalid_item_type(self):
        with self.assertRaises(ValueError):
            extract_memories([123, "not a dict"])

    def test_parse_iso_datetime(self):
        dt = parse_iso_datetime("2026-09-24T12:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertIsNone(parse_iso_datetime("invalid-date"))
        self.assertIsNone(parse_iso_datetime(""))

    def test_transform_to_weaviate_basic(self):
        mems = [
            {
                "id": "mem_01",
                "content": "User prefers dark mode in all IDEs",
                "category": "preferences",
                "created_at": "2026-09-24T10:00:00Z",
                "updated_at": "2026-09-24T10:30:00Z",
                "manually_added": True,
                "tags": ["ui", "editor"],
            }
        ]
        payload = transform_to_weaviate(mems, collection="DeveloperProfile")
        self.assertIn("objects", payload)
        self.assertEqual(len(payload["objects"]), 1)

        obj = payload["objects"][0]
        self.assertEqual(obj["class"], "DeveloperProfile")
        self.assertTrue(uuid.UUID(obj["id"]))
        props = obj["properties"]
        self.assertEqual(props["content"], "User prefers dark mode in all IDEs")
        self.assertEqual(props["category"], "preferences")
        self.assertEqual(props["memory_id"], "mem_01")
        self.assertEqual(props["created_at"], "2026-09-24T10:00:00Z")
        self.assertEqual(props["updated_at"], "2026-09-24T10:30:00Z")
        self.assertTrue(props["manually_added"])
        self.assertEqual(props["tags"], ["ui", "editor"])

    def test_transform_to_weaviate_dedup(self):
        mems = [
            {"id": "duplicate_id", "content": "First version"},
            {"id": "duplicate_id", "content": "Second version"},
            {"id": "unique_id", "content": "Other item"},
        ]
        payload = transform_to_weaviate(mems)
        self.assertEqual(len(payload["objects"]), 2)
        self.assertEqual(payload["objects"][0]["properties"]["content"], "First version")

    def test_transform_to_weaviate_category_filter(self):
        mems = [
            {"id": "m1", "content": "Project roadmap", "category": "work"},
            {"id": "m2", "content": "Went biking today", "category": "fitness"},
        ]
        payload = transform_to_weaviate(mems, category_filter="work")
        self.assertEqual(len(payload["objects"]), 1)
        self.assertEqual(payload["objects"][0]["properties"]["category"], "work")

    def test_transform_to_weaviate_min_date_filter(self):
        mems = [
            {"id": "m1", "content": "Old memory", "created_at": "2026-08-01T00:00:00Z"},
            {"id": "m2", "content": "Recent memory", "created_at": "2026-09-20T00:00:00Z"},
        ]
        payload = transform_to_weaviate(mems, min_date="2026-09-01T00:00:00Z")
        self.assertEqual(len(payload["objects"]), 1)
        self.assertEqual(payload["objects"][0]["properties"]["memory_id"], "m2")

    def test_cli_end_to_end_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "memories.json"
            out_file = tmppath / "batch.json"

            sample_data = [
                {"id": "mem_x1", "content": "Remember to submit PR", "category": "task"},
                {"id": "mem_x2", "content": "Check CI gates", "category": "dev"},
            ]
            in_file.write_text(json.dumps(sample_data), encoding="utf-8")

            # Run CLI
            code = main([str(in_file), "-o", str(out_file), "-c", "CustomMemory"])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())

            result = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(result["objects"]), 2)
            self.assertEqual(result["objects"][0]["class"], "CustomMemory")

    def test_cli_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "input.json"
            out_file = tmppath / "output.json"

            in_file.write_text(json.dumps([{"id": "1", "content": "test"}]), encoding="utf-8")
            out_file.write_text("existing content", encoding="utf-8")

            # Without --force, should exit with code 1
            code_fail = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code_fail, 1)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "existing content")

            # With --force, should succeed and overwrite
            code_ok = main([str(in_file), "-o", str(out_file), "--force"])
            self.assertEqual(code_ok, 0)
            result = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(result["objects"]), 1)

    def test_cli_stdin_to_stdout(self):
        sample = json.dumps([{"id": "stdin_1", "content": "Streaming input"}])
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(sample)
            sys.stdout = io.StringIO()
            code = main(["-"])
            self.assertEqual(code, 0)
            output = sys.stdout.getvalue()
            result = json.loads(output)
            self.assertEqual(len(result["objects"]), 1)
            self.assertEqual(result["objects"][0]["properties"]["memory_id"], "stdin_1")
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
