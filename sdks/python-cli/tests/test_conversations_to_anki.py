"""Tests for conversations to Anki deck (.apkg) converter.

Pins note field content, date/category formatting from the `structured`
object, HTML escaping of untrusted content, stable GUID/deck-ID derivation
across re-exports, and atomic-write / overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_anki.py"
spec = importlib.util.spec_from_file_location("conversations_to_anki", script_path)
c2a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2a)


def _read_notes(apkg_path):
    with zipfile.ZipFile(apkg_path) as z:
        with tempfile.NamedTemporaryFile(suffix=".anki2", delete=False) as tmp:
            tmp.write(z.read("collection.anki2"))
            db_path = tmp.name
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT guid, flds FROM notes")
        return cur.fetchall()
    finally:
        conn.close()


class TestConversationsToAnki(unittest.TestCase):
    def setUp(self):
        self.sample_conversations = [
            {
                "id": "conv_001",
                "started_at": "2026-09-18T10:00:00Z",
                "structured": {
                    "title": "Sprint planning",
                    "category": "work",
                    "overview": "Discussed the Q4 roadmap and assigned owners.",
                },
            },
            {
                "id": "conv_002",
                "started_at": "2026-09-19T14:15:00Z",
                "structured": {
                    "title": "<b>bold</b> & a\nsecond line",
                    "category": "personal",
                    "overview": "",
                },
            },
        ]

    def test_conversion_and_html_escaping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps(self.sample_conversations), encoding="utf-8")

            c2a.convert(json_file, apkg_file, deck_name="Test Deck")
            self.assertTrue(apkg_file.is_file())

            notes = _read_notes(apkg_file)
            self.assertEqual(len(notes), 2)
            fields_by_guid = {guid: flds.split("\x1f") for guid, flds in notes}

            front, back = fields_by_guid[c2a.genanki.guid_for("conv_001")]
            self.assertIn("2026-09-18", front)
            self.assertIn("work", front)
            self.assertIn("Sprint planning", back)
            self.assertIn("Q4 roadmap", back)

            _, back2 = fields_by_guid[c2a.genanki.guid_for("conv_002")]
            self.assertIn("&lt;b&gt;bold&lt;/b&gt;", back2)
            self.assertNotIn("<b>bold</b>", back2)
            self.assertIn("a<br>second line", back2)

    def test_missing_structured_falls_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            items = [{"id": "conv_003", "started_at": "2026-01-01T00:00:00Z"}]
            json_file.write_text(json.dumps(items), encoding="utf-8")

            c2a.convert(json_file, apkg_file)
            ((_, flds),) = _read_notes(apkg_file)
            _, back = flds.split("\x1f")
            self.assertIn("Untitled conversation", back)

    def test_stable_guid_and_deck_id_across_reexport(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            json_file.write_text(json.dumps(self.sample_conversations), encoding="utf-8")

            first = Path(tmpdir) / "first.apkg"
            second = Path(tmpdir) / "second.apkg"
            c2a.convert(json_file, first, deck_name="Same Deck")
            c2a.convert(json_file, second, deck_name="Same Deck")

            self.assertEqual(
                {g for g, _ in _read_notes(first)},
                {g for g, _ in _read_notes(second)},
            )
            self.assertEqual(c2a.deck_id_for("Same Deck"), c2a.deck_id_for("Same Deck"))
            self.assertNotEqual(c2a.deck_id_for("Same Deck"), c2a.deck_id_for("Different Deck"))

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps({"conversations": self.sample_conversations}), encoding="utf-8")

            c2a.convert(json_file, apkg_file)
            self.assertEqual(len(_read_notes(apkg_file)), 2)

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

            with self.assertRaises(ValueError):
                c2a.convert(json_file, apkg_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps(self.sample_conversations), encoding="utf-8")
            apkg_file.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                c2a.convert(json_file, apkg_file)

    def test_distinct_model_id_from_sibling_recipes(self):
        memories_script = Path(__file__).resolve().parent.parent / "examples" / "memories_to_anki.py"
        action_items_script = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_anki.py"
        if not memories_script.exists() or not action_items_script.exists():
            self.skipTest("sibling recipe not present on this branch")
        for path in (memories_script, action_items_script):
            spec2 = importlib.util.spec_from_file_location(path.stem, path)
            mod = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(mod)
            self.assertNotEqual(c2a.MODEL_ID, mod.MODEL_ID)


if __name__ == "__main__":
    unittest.main()
