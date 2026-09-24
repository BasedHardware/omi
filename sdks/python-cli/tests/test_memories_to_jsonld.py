#!/usr/bin/env python3
"""Tests for memories to W3C schema.org JSON-LD linked data graph converter.

Pins schema.org context, NoteDigitalDocument structure, creator metadata,
filtering, stdin piping, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Load memories_to_jsonld example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_jsonld.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "memories_to_jsonld.py"

spec = importlib.util.spec_from_file_location("memories_to_jsonld", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2j)

extract_memories = m2j.extract_memories
main = m2j.main
parse_iso_datetime = m2j.parse_iso_datetime
transform_to_jsonld = m2j.transform_to_jsonld


class TestMemoriesToJsonLd(unittest.TestCase):
    def test_extract_memories_formats(self):
        self.assertEqual(len(extract_memories([{"id": "1", "content": "A"}])), 1)
        self.assertEqual(len(extract_memories({"memories": [{"id": "2", "content": "B"}]})), 1)

    def test_transform_to_jsonld_structure(self):
        mems = [
            {
                "id": "mem_01",
                "content": "User loves Python and TypeScript",
                "category": "skills",
                "created_at": "2026-09-24T12:00:00Z",
                "updated_at": "2026-09-24T12:30:00Z",
                "tags": ["coding", "languages"],
            }
        ]
        doc = transform_to_jsonld(mems, creator_name="Alex Developer")
        self.assertEqual(doc["@context"], "https://schema.org")
        self.assertEqual(len(doc["@graph"]), 1)

        item = doc["@graph"][0]
        self.assertEqual(item["@type"], "NoteDigitalDocument")
        self.assertEqual(item["@id"], "urn:omi:memory:mem_01")
        self.assertEqual(item["identifier"], "mem_01")
        self.assertEqual(item["text"], "User loves Python and TypeScript")
        self.assertEqual(item["genre"], "skills")
        self.assertEqual(item["dateCreated"], "2026-09-24T12:00:00Z")
        self.assertEqual(item["dateModified"], "2026-09-24T12:30:00Z")
        self.assertEqual(item["keywords"], ["coding", "languages"])
        self.assertEqual(item["creator"]["name"], "Alex Developer")

    def test_transform_to_jsonld_dedup(self):
        mems = [
            {"id": "same", "content": "Version 1"},
            {"id": "same", "content": "Version 2"},
            {"id": "other", "content": "Version 3"},
        ]
        doc = transform_to_jsonld(mems)
        self.assertEqual(len(doc["@graph"]), 2)
        self.assertEqual(doc["@graph"][0]["text"], "Version 1")

    def test_transform_to_jsonld_filtering(self):
        mems = [
            {"id": "m1", "category": "work", "created_at": "2026-09-20T00:00:00Z"},
            {"id": "m2", "category": "hobby", "created_at": "2026-09-24T00:00:00Z"},
        ]
        # Category filter
        doc_cat = transform_to_jsonld(mems, category_filter="work")
        self.assertEqual(len(doc_cat["@graph"]), 1)
        self.assertEqual(doc_cat["@graph"][0]["identifier"], "m1")

        # Date filter
        doc_date = transform_to_jsonld(mems, min_date="2026-09-22T00:00:00Z")
        self.assertEqual(len(doc_date["@graph"]), 1)
        self.assertEqual(doc_date["@graph"][0]["identifier"], "m2")

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "memories.json"
            out_file = tmppath / "graph.jsonld"

            in_file.write_text(json.dumps([{"id": "m1", "content": "Linked data test"}]), encoding="utf-8")
            code = main([str(in_file), "-o", str(out_file), "--creator-name", "Tester"])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())

            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(data["@context"], "https://schema.org")
            self.assertEqual(data["@graph"][0]["creator"]["name"], "Tester")

    def test_cli_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "input.json"
            out_file = tmppath / "output.jsonld"

            in_file.write_text(json.dumps([{"id": "m1", "content": "test"}]), encoding="utf-8")
            out_file.write_text("existing", encoding="utf-8")

            code_fail = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code_fail, 1)

            code_ok = main([str(in_file), "-o", str(out_file), "--force"])
            self.assertEqual(code_ok, 0)

    def test_cli_stdin(self):
        sample = json.dumps([{"id": "stdin_m", "content": "Piped linked data"}])
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(sample)
            sys.stdout = io.StringIO()
            code = main(["-"])
            self.assertEqual(code, 0)
            res = json.loads(sys.stdout.getvalue())
            self.assertEqual(res["@graph"][0]["identifier"], "stdin_m")
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
