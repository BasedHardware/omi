import csv
import tempfile
import unittest
from pathlib import Path

from memories_to_anki import (
    clean_text,
    clean_tag,
    parse_time,
    load_memories,
    format_anki_card,
    convert
)

class TestMemoriesToAnki(unittest.TestCase):
    def test_clean_text_and_tags(self):
        self.assertEqual(clean_text("  remember   to drink water  "), "remember to drink water")
        self.assertEqual(clean_tag("deep work"), "deep_work")
        self.assertEqual(clean_tag(None), "")

    def test_parse_time(self):
        t = parse_time("2026-09-27T10:00:00Z")
        self.assertIsNotNone(t)
        self.assertEqual(t.year, 2026)
        self.assertIsNone(parse_time("invalid"))

    def test_format_anki_card(self):
        raw = {
            "id": "mem-1",
            "content": "Quantum entanglement occurs when particles remain connected regardless of distance.",
            "category": "physics",
            "created_at": "2026-09-27T10:00:00Z",
            "tags": ["science", "modern physics"]
        }
        front, back, tags = format_anki_card(raw)
        self.assertIn("Physics", front)
        self.assertIn("Quantum entanglement", back)
        self.assertIn("omi", tags)
        self.assertIn("physics", tags)
        self.assertIn("science", tags)
        self.assertIn("modern_physics", tags)
        self.assertIn("year_2026", tags)

    def test_load_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "m1.json"
            f2 = Path(tmpdir) / "m2.json"
            import json
            f1.write_text(json.dumps([
                {"id": "1", "content": "Fact 1", "category": "math"},
                {"id": "2", "content": "Fact 2", "category": "history"}
            ]))
            f2.write_text(json.dumps([
                {"id": "1", "content": "Fact 1 (updated)", "category": "math"},
                {"id": "3", "content": "Fact 3", "category": "geography"}
            ]))
            loaded = load_memories([str(f1), str(f2)])
            self.assertEqual(len(loaded), 3)
            self.assertEqual(loaded[0]["content"], "Fact 1 (updated)")

    def test_convert_tsv_and_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "m.json"
            out = Path(tmpdir) / "deck.tsv"
            import json
            src.write_text(json.dumps([
                {"id": "1", "content": "Learning 1", "category": "tech"},
                {"id": "2", "content": "Learning 2", "category": "art"}
            ]))

            # Category filter
            cnt = convert([str(src)], str(out), category_filter="tech")
            self.assertEqual(cnt, 1)
            self.assertTrue(out.exists())
            lines = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            parts = lines[0].split("\t")
            self.assertEqual(len(parts), 3)
            self.assertIn("Learning 1", parts[1])

            # Protection against overwrite
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(out))

if __name__ == '__main__':
    unittest.main()
