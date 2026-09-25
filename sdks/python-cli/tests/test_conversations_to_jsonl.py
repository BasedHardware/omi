import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conversations_to_jsonl import (
    convert_conversations,
    format_chat_entry,
    format_transcript_entry,
    normalize_conversation,
    DEFAULT_SYSTEM_PROMPT,
)


class TestConversationsToJsonl(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.output_file = self.dir_path / "conversations.jsonl"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_valid_conversation(self):
        raw = {
            "id": "conv_01",
            "structured": {
                "title": "Roadmap Planning",
                "overview": "Discussed Q4 deliverables and team hiring targets.",
                "category": "product",
            },
            "started_at": "2026-09-24T10:00:00Z",
            "source": "omi_wearable",
            "transcript_segments": [
                {"speaker": "Alice", "is_user": True, "text": "What are our Q4 goals?"},
                {"speaker": "Bob", "is_user": False, "text": "Launch mobile app and SDK v1."},
            ],
        }
        res = normalize_conversation(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "conv_01")
        self.assertEqual(res["title"], "Roadmap Planning")
        self.assertEqual(len(res["segments"]), 2)

    def test_normalize_invalid_or_empty(self):
        self.assertIsNone(normalize_conversation({"id": "no-content"}))
        self.assertIsNone(normalize_conversation({"structured": {"title": "no id"}}))
        self.assertIsNone(normalize_conversation("not-a-dict"))

    def test_format_chat_with_segments(self):
        item = {
            "id": "c1",
            "title": "Sprint Sync",
            "overview": "Summary of sync",
            "segments": [
                {"speaker": "Me", "is_user": True, "text": "Are we ready to deploy?"},
                {"speaker": "Dev", "is_user": False, "text": "Yes, all integration tests passed."},
            ],
        }
        chat = format_chat_entry(item, DEFAULT_SYSTEM_PROMPT)
        self.assertEqual(chat["id"], "c1")
        msgs = chat["messages"]
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")
        self.assertEqual(msgs[1]["content"], "Are we ready to deploy?")
        self.assertEqual(msgs[2]["role"], "assistant")
        self.assertIn("Yes, all integration tests passed.", msgs[2]["content"])

    def test_format_chat_overview_fallback(self):
        item = {
            "id": "c2",
            "title": "Quick Strategy Call",
            "overview": "Decided to expand customer onboarding pipeline.",
            "segments": [],
        }
        chat = format_chat_entry(item, DEFAULT_SYSTEM_PROMPT)
        msgs = chat["messages"]
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")
        self.assertIn("Quick Strategy Call", msgs[1]["content"])
        self.assertEqual(msgs[2]["role"], "assistant")
        self.assertEqual(msgs[2]["content"], "Decided to expand customer onboarding pipeline.")

    def test_format_transcript_entry(self):
        item = {
            "id": "c3",
            "title": "Tech Talk",
            "category": "education",
            "overview": "Overview text",
            "started_at": "2026-09-24T12:00:00Z",
            "source": "mic",
            "segments": [
                {"speaker": "Host", "text": "Welcome everyone"},
                {"speaker": "Guest", "text": "Glad to be here"},
            ],
        }
        t = format_transcript_entry(item)
        self.assertEqual(t["id"], "c3")
        self.assertIn("Host: Welcome everyone\nGuest: Glad to be here", t["transcript"])
        self.assertEqual(t["metadata"]["segment_count"], 2)

    def test_convert_conversations_and_deduplication(self):
        data1 = [
            {"id": "c1", "title": "Conv 1", "overview": "Overview 1"},
            {"id": "c2", "title": "Conv 2", "overview": "Overview 2"},
        ]
        data2 = [
            {"id": "c2", "title": "Conv 2 Duplicate", "overview": "Overview 2 Duplicate"},
            {"id": "c3", "title": "Conv 3", "overview": "Overview 3"},
        ]

        f1 = self.dir_path / "page1.json"
        f2 = self.dir_path / "page2.json"
        f1.write_text(json.dumps(data1), encoding="utf-8")
        f2.write_text(json.dumps(data2), encoding="utf-8")

        total, written = convert_conversations([f1, f2], self.output_file)
        self.assertEqual(total, 4)
        self.assertEqual(written, 3)

        lines = self.output_file.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 3)
        ids = [json.loads(l)["id"] for l in lines]
        self.assertEqual(ids, ["c1", "c2", "c3"])

    def test_overwrite_safety(self):
        self.output_file.write_text("existing", encoding="utf-8")
        f = self.dir_path / "data.json"
        f.write_text(json.dumps([{"id": "c1", "overview": "note"}]), encoding="utf-8")

        with self.assertRaises(FileExistsError):
            convert_conversations([f], self.output_file, force=False)

        convert_conversations([f], self.output_file, force=True)
        self.assertIn("c1", self.output_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
