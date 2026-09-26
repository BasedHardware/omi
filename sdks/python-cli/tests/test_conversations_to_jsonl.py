import json
import tempfile
import unittest
from pathlib import Path

from conversations_to_jsonl import (
    clean_text,
    parse_time,
    load_conversations,
    format_conversation_record,
    convert
)

class TestConversationsToJsonl(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  meeting   notes  "), "meeting notes")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text(999), "999")

    def test_parse_time(self):
        t = parse_time("2026-09-26T15:00:00Z")
        self.assertIsNotNone(t)
        self.assertEqual(t.hour, 15)
        self.assertIsNone(parse_time("invalid"))
        self.assertIsNone(parse_time(None))

    def test_load_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "c1.json"
            f2 = Path(tmpdir) / "c2.json"
            f1.write_text(json.dumps([
                {"id": "conv-1", "started_at": "2026-09-26T10:00:00Z", "structured": {"title": "Team Standup", "category": "work"}},
                {"id": "conv-2", "started_at": "2026-09-26T11:00:00Z", "structured": {"title": "Coffee Chat", "category": "social"}}
            ]))
            f2.write_text(json.dumps([
                {"id": "conv-1", "started_at": "2026-09-26T10:00:00Z", "structured": {"title": "Team Standup (Synced)", "category": "work"}},
                {"id": "conv-3", "started_at": "2026-09-26T12:00:00Z", "structured": {"title": "Architecture Review", "category": "work"}}
            ]))
            loaded = load_conversations([str(f1), str(f2)])
            self.assertEqual(len(loaded), 3)
            self.assertEqual(loaded[0]["id"], "conv-1")
            self.assertEqual(loaded[0]["structured"]["title"], "Team Standup (Synced)")

    def test_format_modes(self):
        raw = {
            "id": "c-123",
            "started_at": "2026-09-26T10:00:00Z",
            "finished_at": "2026-09-26T10:15:00Z",
            "language": "en",
            "structured": {
                "title": "Quarterly Planning",
                "category": "business",
                "overview": "Reviewed quarterly OKRs and timeline.",
                "action_items": ["Finalize budget", "Send invites"]
            }
        }
        # standard mode
        rec_std = format_conversation_record(raw, mode="standard")
        self.assertEqual(rec_std["id"], "c-123")
        self.assertEqual(rec_std["duration_seconds"], 900)
        self.assertEqual(len(rec_std["action_items"]), 2)

        # chat mode
        rec_chat = format_conversation_record(raw, mode="chat")
        self.assertIn("messages", rec_chat)
        self.assertEqual(len(rec_chat["messages"]), 3)
        self.assertIn("Reviewed quarterly OKRs", rec_chat["messages"][2]["content"])

        # rag mode
        rec_rag = format_conversation_record(raw, mode="rag")
        self.assertIn("text", rec_rag)
        self.assertIn("Quarterly Planning", rec_rag["text"])
        self.assertEqual(rec_rag["metadata"]["duration_seconds"], 900)

    def test_convert_filter_and_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "convs.json"
            out = Path(tmpdir) / "out.jsonl"
            src.write_text(json.dumps([
                {"id": "1", "structured": {"title": "Work Talk", "category": "work"}},
                {"id": "2", "structured": {"title": "Gaming Chat", "category": "gaming"}}
            ]))

            # Filter by category
            count = convert([str(src)], str(out), category_filter="work")
            self.assertEqual(count, 1)
            lines = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            data = json.loads(lines[0])
            self.assertEqual(data["category"], "work")

            # Protection against overwrite
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(out))

if __name__ == '__main__':
    unittest.main()
