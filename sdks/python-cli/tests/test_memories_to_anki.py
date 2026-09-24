"""Tests for Omi memories to Anki flashcards export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_anki.py"
spec = importlib.util.spec_from_file_location("memories_to_anki", script_path)
m2a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2a)


class TestMemoriesToAnki(unittest.TestCase):
    def test_clean_card_text(self):
        self.assertEqual(m2a.clean_card_text("Hello\tworld\nSecond line"), "Hello world<br>Second line")
        self.assertEqual(m2a.clean_card_text(""), "")

    def test_make_card_structure_and_tags(self):
        mem = {
            "id": "m-1",
            "content": "Python is interpreted and dynamically typed.",
            "category": "skills",
            "tags": ["python", "programming"],
        }
        card = m2a.make_card(mem, deck_prefix="Omi::Memories")
        self.assertIsNotNone(card)
        self.assertEqual(len(card), 4)
        self.assertIn("Skills Recall", card[0])
        self.assertEqual(card[1], "Python is interpreted and dynamically typed.")
        self.assertEqual(card[2], "Omi::Memories::Skills")
        self.assertIn("omi", card[3])
        self.assertIn("python", card[3])

    def test_convert_to_anki_output_and_headers(self):
        mem1 = {"id": "m-1", "content": "Fact 1", "category": "work"}
        mem2 = {"id": "m-2", "content": "Fact 2", "category": "personal"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "data.json"
            out = tmp / "deck.tsv"

            f.write_text(json.dumps([mem1, mem2]), encoding="utf-8")
            count = m2a.convert_to_anki([f], out)

            self.assertEqual(count, 2)
            content = out.read_text(encoding="utf-8")
            self.assertIn("#separator:tab", content)
            self.assertIn("#html:true", content)
            self.assertIn("Fact 1", content)
            self.assertIn("Fact 2", content)


if __name__ == "__main__":
    unittest.main()
