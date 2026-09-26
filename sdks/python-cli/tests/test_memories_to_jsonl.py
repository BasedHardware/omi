import json
import tempfile
import unittest
from pathlib import Path

from memories_to_jsonl import (
    clean_text,
    parse_time,
    load_memories,
    format_record,
    convert
)

class TestMemoriesToJsonl(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  remember   to buy milk  "), "remember to buy milk")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text(42), "42")

    def test_parse_time(self):
        t = parse_time("2026-09-26T14:00:00Z")
        self.assertEqual(t, "2026-09-26T14:00:00+00:00")
        self.assertIsNone(parse_time("invalid"))
        self.assertIsNone(parse_time(None))

    def test_load_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "m1.json"
            f2 = Path(tmpdir) / "m2.json"
            f1.write_text(json.dumps([
                {"id": "mem-1", "content": "Favorite coffee is espresso", "category": "preference"},
                {"id": "mem-2", "content": "Doctor appointment next Monday", "category": "health"}
            ]))
            f2.write_text(json.dumps([
                {"id": "mem-1", "content": "Favorite coffee is double espresso", "category": "preference"},
                {"id": "mem-3", "content": "Flight at 6 PM", "category": "travel"}
            ]))
            loaded = load_memories([str(f1), str(f2)])
            self.assertEqual(len(loaded), 3)
            self.assertEqual(loaded[0]["id"], "mem-1")
            self.assertEqual(loaded[0]["content"], "Favorite coffee is double espresso")

    def test_format_record_modes(self):
        raw = {
            "id": "mem-100",
            "content": "Prefers dark mode in code editors",
            "category": "preferences",
            "created_at": "2026-09-26T10:00:00Z",
            "tags": ["code", "ui"]
        }
        # standard
        rec_std = format_record(raw, mode="standard")
        self.assertEqual(rec_std["id"], "mem-100")
        self.assertEqual(rec_std["category"], "preferences")
        self.assertEqual(rec_std["tags"], ["code", "ui"])

        # chat / fine-tuning
        rec_chat = format_record(raw, mode="chat")
        self.assertIn("messages", rec_chat)
        self.assertEqual(len(rec_chat["messages"]), 3)
        self.assertEqual(rec_chat["messages"][2]["content"], "Prefers dark mode in code editors")

        # completion
        rec_comp = format_record(raw, mode="completion")
        self.assertIn("prompt", rec_comp)
        self.assertIn("completion", rec_comp)

    def test_convert_and_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "m.json"
            out = Path(tmpdir) / "out.jsonl"
            src.write_text(json.dumps([
                {"id": "1", "content": "work project", "category": "work"},
                {"id": "2", "content": "personal hobby", "category": "personal"}
            ]))

            # Category filter
            cnt = convert([str(src)], str(out), category_filter="work")
            self.assertEqual(cnt, 1)
            lines = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            item = json.loads(lines[0])
            self.assertEqual(item["category"], "work")

            # Protection against overwrite
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(out))

if __name__ == '__main__':
    unittest.main()
