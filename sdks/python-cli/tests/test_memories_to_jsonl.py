import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_jsonl import (
    convert_memories,
    format_chat_entry,
    format_knowledge_entry,
    validate_and_normalize_record,
    DEFAULT_SYSTEM_PROMPT,
)


class TestMemoriesToJsonl(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.output_file = self.dir_path / "dataset.jsonl"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validate_and_normalize_valid_record(self):
        raw = {
            "id": "mem_01",
            "content": "Prefers Rust and Go for systems programming",
            "category": "preferences",
            "created_at": "2026-09-21T10:00:00Z",
            "updated_at": "2026-09-21T10:00:00Z",
            "conversation_id": "conv_123",
            "deleted": False,
        }
        res = validate_and_normalize_record(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "mem_01")
        self.assertEqual(res["content"], "Prefers Rust and Go for systems programming")
        self.assertEqual(res["category"], "preferences")

    def test_validate_and_normalize_invalid_or_deleted(self):
        # Deleted flag
        self.assertIsNone(validate_and_normalize_record({"id": "1", "content": "hello", "deleted": True}))
        self.assertIsNone(validate_and_normalize_record({"id": "1", "content": "hello", "deleted": "true"}))
        # Missing id
        self.assertIsNone(validate_and_normalize_record({"content": "hello"}))
        # Empty/whitespace content
        self.assertIsNone(validate_and_normalize_record({"id": "1", "content": "   "}))
        # Not a dict
        self.assertIsNone(validate_and_normalize_record("not-a-dict"))

    def test_format_chat_entry(self):
        item = {
            "id": "mem_02",
            "content": "Works on Arch Linux with Hyprland",
            "category": "environment",
        }
        chat = format_chat_entry(item, DEFAULT_SYSTEM_PROMPT)
        self.assertEqual(chat["id"], "mem_02")
        self.assertEqual(len(chat["messages"]), 3)
        self.assertEqual(chat["messages"][0]["role"], "system")
        self.assertEqual(chat["messages"][0]["content"], DEFAULT_SYSTEM_PROMPT)
        self.assertEqual(chat["messages"][1]["role"], "user")
        self.assertIn("environment", chat["messages"][1]["content"])
        self.assertEqual(chat["messages"][2]["role"], "assistant")
        self.assertEqual(chat["messages"][2]["content"], "Works on Arch Linux with Hyprland")

    def test_format_knowledge_entry(self):
        item = {
            "id": "mem_03",
            "content": "Favorite editor is Neovim",
            "category": "preferences",
            "created_at": "2026-09-22T14:00:00Z",
            "updated_at": "2026-09-22T14:30:00Z",
            "conversation_id": "conv_99",
        }
        k = format_knowledge_entry(item)
        self.assertEqual(k["id"], "mem_03")
        self.assertEqual(k["text"], "Favorite editor is Neovim")
        self.assertEqual(k["category"], "preferences")
        self.assertEqual(k["metadata"]["conversation_id"], "conv_99")
        self.assertEqual(k["metadata"]["updated_at"], "2026-09-22T14:30:00Z")

    def test_convert_memories_chat_and_deduplication(self):
        data1 = [
            {"id": "m1", "content": "First memory", "category": "work"},
            {"id": "m2", "content": "Second memory", "category": "personal"},
        ]
        data2 = [
            {"id": "m2", "content": "Duplicate second memory", "category": "personal"},
            {"id": "m3", "content": "Third memory", "category": "general"},
            {"id": "m4", "content": "   ", "category": "invalid"},
            {"id": "m5", "content": "Deleted note", "deleted": True},
        ]

        f1 = self.dir_path / "page1.json"
        f2 = self.dir_path / "page2.json"
        f1.write_text(json.dumps(data1), encoding="utf-8")
        f2.write_text(json.dumps(data2), encoding="utf-8")

        total_processed, unique_written = convert_memories(
            sources=[f1, f2],
            destination=self.output_file,
            output_format="chat",
        )

        self.assertEqual(total_processed, 6)
        self.assertEqual(unique_written, 3)

        lines = self.output_file.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 3)

        entries = [json.loads(line) for line in lines]
        ids = [e["id"] for e in entries]
        self.assertEqual(ids, ["m1", "m2", "m3"])
        for e in entries:
            self.assertIn("messages", e)

    def test_convert_memories_knowledge_format(self):
        data = [{"id": "m1", "content": "Fact 1", "category": "facts", "created_at": "2026-09-24T00:00:00Z"}]
        f = self.dir_path / "data.json"
        f.write_text(json.dumps(data), encoding="utf-8")

        total, written = convert_memories(
            sources=[f],
            destination=self.output_file,
            output_format="knowledge",
        )
        self.assertEqual(total, 1)
        self.assertEqual(written, 1)

        entry = json.loads(self.output_file.read_text(encoding="utf-8").strip())
        self.assertEqual(entry["text"], "Fact 1")
        self.assertEqual(entry["category"], "facts")
        self.assertEqual(entry["created_at"], "2026-09-24T00:00:00Z")

    def test_overwrite_protection(self):
        self.output_file.write_text("existing content", encoding="utf-8")
        data = [{"id": "m1", "content": "New content"}]
        f = self.dir_path / "data.json"
        f.write_text(json.dumps(data), encoding="utf-8")

        # Refusal without force
        with self.assertRaises(FileExistsError):
            convert_memories(sources=[f], destination=self.output_file, force=False)

        # Successful with force=True
        convert_memories(sources=[f], destination=self.output_file, force=True)
        self.assertIn("New content", self.output_file.read_text(encoding="utf-8"))

    def test_invalid_source_file(self):
        with self.assertRaises(FileNotFoundError):
            convert_memories(sources=[self.dir_path / "non_existent.json"], destination=self.output_file)

        bad_json = self.dir_path / "bad.json"
        bad_json.write_text("invalid json {{{", encoding="utf-8")
        with self.assertRaises(ValueError):
            convert_memories(sources=[bad_json], destination=self.output_file)


if __name__ == "__main__":
    unittest.main()
