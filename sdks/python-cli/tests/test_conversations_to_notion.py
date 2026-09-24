"""Tests for Omi conversations to Notion API block payloads export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_notion.py"
spec = importlib.util.spec_from_file_location("conversations_to_notion", script_path)
c2n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2n)


class TestConversationsToNotion(unittest.TestCase):
    def test_text_to_rich_text_chunking(self):
        short_text = "Hello Notion"
        rich = c2n.text_to_rich_text(short_text, bold=True)
        self.assertEqual(len(rich), 1)
        self.assertEqual(rich[0]["text"]["content"], short_text)
        self.assertTrue(rich[0]["annotations"]["bold"])

        # Test chunking over 2000 chars
        long_text = "A" * 3500
        rich_long = c2n.text_to_rich_text(long_text)
        self.assertEqual(len(rich_long), 2)
        self.assertEqual(len(rich_long[0]["text"]["content"]), 2000)
        self.assertEqual(len(rich_long[1]["text"]["content"]), 1500)

    def test_extract_conversations(self):
        raw_list = '[{"id": "conv-1", "title": "Notion Sync"}]'
        raw_wrapped = '{"conversations": [{"id": "conv-2", "title": "Database Setup"}]}'

        res1 = c2n.extract_conversations(raw_list)
        res2 = c2n.extract_conversations(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "conv-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "conv-2")

    def test_conversation_to_notion_payload_structure(self):
        conv = {
            "id": "c-55",
            "structured": {
                "title": "Weekly Strategy",
                "category": "work",
                "overview": "Quarterly planning and review.",
            },
            "transcript_segments": [
                {"speaker": "Alice", "text": "Let's align on Q4 targets."}
            ],
        }
        payload = c2n.conversation_to_notion_payload(conv, parent_id="db-12345")

        self.assertEqual(payload["parent"]["database_id"], "db-12345")
        self.assertEqual(payload["properties"]["Title"]["title"][0]["text"]["content"], "Weekly Strategy")

        children = payload["children"]
        self.assertTrue(any(b["type"] == "callout" for b in children))
        self.assertTrue(any(b["type"] == "heading_2" for b in children))
        self.assertTrue(any(b["type"] == "bulleted_list_item" for b in children))

    def test_convert_conversations_to_notion_output_dir(self):
        conv = {"id": "c-1", "title": "Test Meeting", "transcript": "Meeting content"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "data.json"
            out_dir = tmp / "notion_out"

            f.write_text(json.dumps([conv]), encoding="utf-8")
            count = c2n.convert_conversations_to_notion([f], output_dir=out_dir)

            self.assertEqual(count, 1)
            target = out_dir / "c-1_notion.json"
            self.assertTrue(target.exists())

            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(data["properties"]["Title"]["title"][0]["text"]["content"], "Test Meeting")


if __name__ == "__main__":
    unittest.main()
