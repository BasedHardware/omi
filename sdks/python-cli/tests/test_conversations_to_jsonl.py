"""Tests for Omi conversations to JSONL export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_jsonl.py"
spec = importlib.util.spec_from_file_location("conversations_to_jsonl", script_path)
c2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2j)


class TestConversationsToJsonl(unittest.TestCase):
    def test_utc_stamp_normalization(self):
        self.assertEqual(c2j.utc_stamp("2026-09-24T08:30:00Z"), "2026-09-24 08:30:00")
        self.assertIsNone(c2j.utc_stamp(None))
        self.assertEqual(c2j.utc_stamp("invalid-date"), "invalid-date")

    def test_extract_conversations_array_and_wrapped(self):
        raw_list = '[{"id": "conv-1", "title": "Chat 1"}]'
        raw_wrapped = '{"conversations": [{"id": "conv-2", "title": "Chat 2"}]}'

        res1 = c2j.extract_conversations(raw_list)
        res2 = c2j.extract_conversations(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "conv-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "conv-2")

    def test_extract_conversations_validation_errors(self):
        with self.assertRaises(ValueError):
            c2j.extract_conversations('{"items": "not-a-list"}')
        with self.assertRaises(ValueError):
            c2j.extract_conversations('[{"no_id": "test"}]')

    def test_normalize_record_fields(self):
        sample = {
            "id": "c-100",
            "structured": {
                "title": "Strategy Sync",
                "category": "work",
                "overview": "Quarterly planning discussion",
            },
            "started_at": "2026-09-24T10:00:00Z",
            "finished_at": "2026-09-24T10:30:00Z",
            "created_at": "2026-09-24T10:35:00Z",
            "transcript_segments": [
                {"text": "Hello world", "speaker": "SPEAKER_00"}
            ],
        }
        rec = c2j.normalize_record(sample)
        self.assertEqual(rec["id"], "c-100")
        self.assertEqual(rec["title"], "Strategy Sync")
        self.assertEqual(rec["category"], "work")
        self.assertEqual(rec["turns_count"], 1)
        self.assertEqual(rec["started_at"], "2026-09-24 10:00:00")
        self.assertEqual(rec["transcript_segments"], sample["transcript_segments"])

    def test_convert_paths_to_jsonl_and_deduplication(self):
        item1 = {"id": "c-1", "title": "First", "created_at": "2026-09-24T01:00:00Z"}
        item2 = {"id": "c-2", "title": "Second", "created_at": "2026-09-24T02:00:00Z"}
        item1_duplicate = {"id": "c-1", "title": "First duplicate", "created_at": "2026-09-24T01:00:00Z"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f1 = tmp / "data1.json"
            f2 = tmp / "data2.json"
            out_file = tmp / "output.jsonl"

            f1.write_text(json.dumps([item1, item2]), encoding="utf-8")
            f2.write_text(json.dumps([item1_duplicate]), encoding="utf-8")

            count = c2j.convert_paths_to_jsonl([f1, f2], out_file)
            self.assertEqual(count, 2)

            lines = out_file.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 2)

            parsed1 = json.loads(lines[0])
            parsed2 = json.loads(lines[1])
            self.assertEqual(parsed1["id"], "c-1")
            self.assertEqual(parsed2["id"], "c-2")


if __name__ == "__main__":
    unittest.main()
