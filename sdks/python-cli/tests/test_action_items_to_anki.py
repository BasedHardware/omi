"""Tests for action items to Anki deck (.apkg) converter.

Pins note field content, due-date formatting, HTML escaping of untrusted
content, stable GUID/deck-ID derivation across re-exports, and atomic-write
/ overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_anki.py"
spec = importlib.util.spec_from_file_location("action_items_to_anki", script_path)
a2a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2a)


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


class TestActionItemsToAnki(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "ai_001",
                "description": "Send the follow-up email",
                "completed": False,
                "due_at": "2026-09-25T10:00:00Z",
            },
            {
                "id": "ai_002",
                "description": "<b>bold</b> & a\nsecond line",
                "completed": True,
                "due_at": None,
            },
        ]

    def test_conversion_and_html_escaping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            a2a.convert(json_file, apkg_file, deck_name="Test Deck")
            self.assertTrue(apkg_file.is_file())

            notes = _read_notes(apkg_file)
            self.assertEqual(len(notes), 2)
            fields_by_guid = {guid: flds.split("\x1f") for guid, flds in notes}

            front, back = fields_by_guid[a2a.genanki.guid_for("ai_001")]
            self.assertIn("Due 2026-09-25", front)
            self.assertIn("Send the follow-up email", back)
            self.assertIn("Status: Open", back)

            _, back2 = fields_by_guid[a2a.genanki.guid_for("ai_002")]
            self.assertIn("&lt;b&gt;bold&lt;/b&gt;", back2)
            self.assertNotIn("<b>bold</b>", back2)
            self.assertIn("a<br>second line", back2)
            self.assertIn("Status: Done", back2)

    def test_completed_item_hides_due_date_from_front(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            items = [{"id": "ai_003", "description": "Old task", "completed": True, "due_at": "2020-01-01T00:00:00Z"}]
            json_file.write_text(json.dumps(items), encoding="utf-8")

            a2a.convert(json_file, apkg_file)
            ((_, flds),) = _read_notes(apkg_file)
            front, _ = flds.split("\x1f")
            self.assertNotIn("Due", front)

    def test_stable_guid_and_deck_id_across_reexport(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            first = Path(tmpdir) / "first.apkg"
            second = Path(tmpdir) / "second.apkg"
            a2a.convert(json_file, first, deck_name="Same Deck")
            a2a.convert(json_file, second, deck_name="Same Deck")

            self.assertEqual(
                {g for g, _ in _read_notes(first)},
                {g for g, _ in _read_notes(second)},
            )
            self.assertEqual(a2a.deck_id_for("Same Deck"), a2a.deck_id_for("Same Deck"))
            self.assertNotEqual(a2a.deck_id_for("Same Deck"), a2a.deck_id_for("Different Deck"))

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps({"action_items": self.sample_items}), encoding="utf-8")

            a2a.convert(json_file, apkg_file)
            self.assertEqual(len(_read_notes(apkg_file)), 2)

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

            with self.assertRaises(ValueError):
                a2a.convert(json_file, apkg_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            apkg_file.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                a2a.convert(json_file, apkg_file)


if __name__ == "__main__":
    unittest.main()
