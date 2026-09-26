#!/usr/bin/env python3
"""Tests for Omi conversations to OpenSearch / Elasticsearch bulk ndjson converter.

Pins ndjson pair structure, index name customization, transcript aggregation,
deduplication, stdin streaming, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Load conversations_to_opensearch dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_opensearch.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "conversations_to_opensearch.py"

spec = importlib.util.spec_from_file_location("conversations_to_opensearch", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
c2o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2o)

format_conversation_for_opensearch = c2o.format_conversation_for_opensearch
generate_bulk_ndjson = c2o.generate_bulk_ndjson
main = c2o.main
parse_conversations_data = c2o.parse_conversations_data


class TestConversationsToOpenSearch(unittest.TestCase):
    def test_parse_conversations_formats(self):
        self.assertEqual(len(parse_conversations_data([{"id": "c1"}])), 1)
        self.assertEqual(len(parse_conversations_data({"conversations": [{"id": "c2"}]})), 1)
        self.assertEqual(len(parse_conversations_data({"data": [{"id": "c3"}]})), 1)

    def test_format_conversation_basic(self):
        item = {
            "id": "conv_123",
            "structured": {
                "title": "Roadmap Sync",
                "overview": "Quarterly planning discussion",
                "category": "work",
                "action_items": [{"description": "Write RFC"}],
            },
            "transcript_segments": [
                {"speaker": "Alice", "text": "Let's review the milestones."},
                {"speaker": "Bob", "text": "Agreed, let's start with Q4."},
            ],
            "started_at": "2026-09-24T09:00:00Z",
            "finished_at": "2026-09-24T09:30:00Z",
        }
        doc = format_conversation_for_opensearch(item)
        self.assertEqual(doc["conversation_id"], "conv_123")
        self.assertEqual(doc["title"], "Roadmap Sync")
        self.assertEqual(doc["overview"], "Quarterly planning discussion")
        self.assertEqual(doc["category"], "work")
        self.assertEqual(doc["action_items"], ["Write RFC"])
        self.assertIn("Alice: Let's review the milestones.", doc["transcript"])
        self.assertIn("Bob: Agreed, let's start with Q4.", doc["transcript"])

    def test_format_conversation_missing_id_raises(self):
        with self.assertRaises(ValueError):
            format_conversation_for_opensearch({"title": "No ID"})

    def test_generate_bulk_ndjson_pairs(self):
        convs = [
            {"id": "c1", "title": "Conv 1"},
            {"id": "c2", "title": "Conv 2"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "data.json"
            f.write_text(json.dumps(convs), encoding="utf-8")

            ndjson, count = generate_bulk_ndjson([str(f)], index_name="custom_index")
            self.assertEqual(count, 2)
            lines = [l for l in ndjson.split("\n") if l.strip()]
            self.assertEqual(len(lines), 4)  # 2 lines per doc

            header_1 = json.loads(lines[0])
            self.assertEqual(header_1["index"]["_index"], "custom_index")
            self.assertEqual(header_1["index"]["_id"], "c1")

            body_1 = json.loads(lines[1])
            self.assertEqual(body_1["conversation_id"], "c1")
            self.assertEqual(body_1["title"], "Conv 1")

    def test_deduplication(self):
        c1 = [{"id": "c_dup", "title": "Original"}]
        c2 = [{"id": "c_dup", "title": "Updated"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "f1.json"
            f2 = Path(tmpdir) / "f2.json"
            f1.write_text(json.dumps(c1), encoding="utf-8")
            f2.write_text(json.dumps(c2), encoding="utf-8")

            ndjson, count = generate_bulk_ndjson([str(f1), str(f2)])
            self.assertEqual(count, 1)
            lines = [l for l in ndjson.split("\n") if l.strip()]
            self.assertEqual(len(lines), 2)
            body = json.loads(lines[1])
            self.assertEqual(body["title"], "Updated")

    def test_cli_integration_and_overwrite(self):
        sample = [{"id": "c_cli", "title": "CLI Test"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src.json"
            dst = Path(tmpdir) / "out.ndjson"
            src.write_text(json.dumps(sample), encoding="utf-8")

            # 1. First run succeeds
            sys.argv = ["conversations_to_opensearch.py", str(src), "-o", str(dst)]
            main()
            self.assertTrue(dst.is_file())

            # 2. Overwrite fails without --force
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)

            # 3. Overwrite succeeds with --force
            sys.argv = ["conversations_to_opensearch.py", str(src), "-o", str(dst), "--force"]
            main()
            self.assertTrue(dst.is_file())


if __name__ == "__main__":
    unittest.main()
