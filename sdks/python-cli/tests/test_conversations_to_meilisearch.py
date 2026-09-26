#!/usr/bin/env python3
"""Tests for conversations to Meilisearch document batch converter.

Pins primary key sanitization, transcript flattening, speaker extraction,
filtering (category, date, duration), stdin piping, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Load conversations_to_meilisearch example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_meilisearch.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "conversations_to_meilisearch.py"

spec = importlib.util.spec_from_file_location("conversations_to_meilisearch", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
c2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2m)

extract_conversations = c2m.extract_conversations
extract_speakers = c2m.extract_speakers
extract_transcript_text = c2m.extract_transcript_text
main = c2m.main
parse_iso_datetime = c2m.parse_iso_datetime
sanitize_meili_id = c2m.sanitize_meili_id
transform_to_meilisearch = c2m.transform_to_meilisearch


class TestConversationsToMeilisearch(unittest.TestCase):
    def test_sanitize_meili_id_clean(self):
        self.assertEqual(sanitize_meili_id("conv_123-abc"), "conv_123-abc")

    def test_sanitize_meili_id_special_chars(self):
        raw = "conv:2026/09/24@10:00#meeting!"
        cleaned = sanitize_meili_id(raw)
        self.assertEqual(cleaned, "conv-2026-09-24-10-00-meeting")

    def test_sanitize_meili_id_empty(self):
        self.assertEqual(sanitize_meili_id(""), "unknown_doc")
        self.assertEqual(sanitize_meili_id(None), "unknown_doc")

    def test_extract_transcript_from_string(self):
        conv = {"transcript": "Hello world from meeting"}
        self.assertEqual(extract_transcript_text(conv), "Hello world from meeting")

    def test_extract_transcript_from_segments(self):
        conv = {
            "transcript_segments": [
                {"speaker": "Alice", "text": "Good morning"},
                {"speaker": "Bob", "text": "Hi Alice"},
            ]
        }
        res = extract_transcript_text(conv)
        self.assertIn("Alice: Good morning", res)
        self.assertIn("Bob: Hi Alice", res)

    def test_extract_speakers(self):
        conv = {
            "transcript_segments": [
                {"speaker": "Alice", "text": "1"},
                {"speaker": "Bob", "text": "2"},
                {"speaker": "Alice", "text": "3"},
            ]
        }
        speakers = extract_speakers(conv)
        self.assertEqual(speakers, ["Alice", "Bob"])

    def test_extract_conversations_formats(self):
        data_list = [{"id": "c1", "title": "Conv 1"}]
        self.assertEqual(len(extract_conversations(data_list)), 1)

        data_dict = {"conversations": [{"id": "c1", "title": "Conv 1"}]}
        self.assertEqual(len(extract_conversations(data_dict)), 1)

        with self.assertRaises(ValueError):
            extract_conversations("{bad json")

    def test_transform_to_meilisearch_basic(self):
        convs = [
            {
                "id": "c_001",
                "title": "Design Review",
                "category": "work",
                "created_at": "2026-09-24T14:00:00Z",
                "duration": 1800,
                "summary": "Reviewed mockups",
                "transcript": "Looks good",
                "speakers": ["Alice"],
            }
        ]
        docs = transform_to_meilisearch(convs)
        self.assertEqual(len(docs), 1)
        doc = docs[0]
        self.assertEqual(doc["id"], "c_001")
        self.assertEqual(doc["title"], "Design Review")
        self.assertEqual(doc["category"], "work")
        self.assertEqual(doc["duration_seconds"], 1800)
        self.assertEqual(doc["summary"], "Reviewed mockups")
        self.assertEqual(doc["transcript"], "Looks good")
        self.assertEqual(doc["speakers"], ["Alice"])

    def test_transform_to_meilisearch_dedup(self):
        convs = [
            {"id": "c1", "title": "Version 1"},
            {"id": "c1", "title": "Version 2"},
            {"id": "c2", "title": "Version 3"},
        ]
        docs = transform_to_meilisearch(convs)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0]["title"], "Version 1")

    def test_transform_to_meilisearch_filters(self):
        convs = [
            {"id": "c1", "category": "work", "created_at": "2026-09-20T00:00:00Z", "duration": 300},
            {"id": "c2", "category": "social", "created_at": "2026-09-22T00:00:00Z", "duration": 1200},
            {"id": "c3", "category": "work", "created_at": "2026-09-24T00:00:00Z", "duration": 1800},
        ]
        # Filter by category
        res_cat = transform_to_meilisearch(convs, category_filter="work")
        self.assertEqual(len(res_cat), 2)

        # Filter by min_duration
        res_dur = transform_to_meilisearch(convs, min_duration=1000)
        self.assertEqual(len(res_dur), 2)
        self.assertEqual({d["id"] for d in res_dur}, {"c2", "c3"})

        # Filter by min_date
        res_date = transform_to_meilisearch(convs, min_date="2026-09-23T00:00:00Z")
        self.assertEqual(len(res_date), 1)
        self.assertEqual(res_date[0]["id"], "c3")

    def test_transform_from_structured_cli_format(self):
        real_fixture = [
            {
                "id": "conv-real-999",
                "structured": {
                    "title": "Weekly Engineering Sync",
                    "category": "work",
                    "overview": "Discussed release milestone and roadmap."
                },
                "started_at": "2026-09-24T10:00:00Z",
                "finished_at": "2026-09-24T10:30:00Z",
                "transcript_segments": [
                    {"speaker": "David", "text": "Let's review the sprint board."},
                    {"speaker": "Sarah", "text": "Backend PRs are all green."}
                ]
            }
        ]
        docs = transform_to_meilisearch(real_fixture)
        self.assertEqual(len(docs), 1)
        doc = docs[0]
        self.assertEqual(doc["title"], "Weekly Engineering Sync")
        self.assertEqual(doc["category"], "work")
        self.assertEqual(doc["summary"], "Discussed release milestone and roadmap.")
        self.assertEqual(doc["duration_seconds"], 1800)
        self.assertEqual(doc["created_at"], "2026-09-24T10:00:00Z")
        self.assertEqual(doc["started_at"], "2026-09-24T10:00:00Z")
        self.assertIn("David: Let's review the sprint board.", doc["transcript"])
        self.assertIn("Sarah: Backend PRs are all green.", doc["transcript"])
        self.assertEqual(doc["speakers"], ["David", "Sarah"])

    def test_timestamp_fallback_and_duration_calc(self):
        item = {
            "id": "c_fallback",
            "started_at": "2026-09-24T08:00:00Z",
            "finished_at": "2026-09-24T08:15:00Z",
        }
        docs = transform_to_meilisearch([item])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["created_at"], "2026-09-24T08:00:00Z")
        self.assertEqual(docs[0]["duration_seconds"], 900)

    def test_cli_end_to_end_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "conversations.json"
            out_file = tmppath / "meili_docs.json"

            sample_data = [
                {"id": "c1", "title": "Weekly Planning", "category": "work"},
                {"id": "c2", "title": "Quick Coffee Chat", "category": "personal"},
            ]
            in_file.write_text(json.dumps(sample_data), encoding="utf-8")

            code = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())

            result = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["id"], "c1")

    def test_cli_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "input.json"
            out_file = tmppath / "output.json"

            in_file.write_text(json.dumps([{"id": "c1", "title": "test"}]), encoding="utf-8")
            out_file.write_text("existing content", encoding="utf-8")

            code_fail = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code_fail, 1)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "existing content")

            code_ok = main([str(in_file), "-o", str(out_file), "--force"])
            self.assertEqual(code_ok, 0)
            result = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(result), 1)

    def test_cli_stdin_to_stdout(self):
        sample = json.dumps([{"id": "stdin_conv", "title": "Piped Conversation"}])
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(sample)
            sys.stdout = io.StringIO()
            code = main(["-"])
            self.assertEqual(code, 0)
            output = sys.stdout.getvalue()
            result = json.loads(output)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["id"], "stdin_conv")
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
