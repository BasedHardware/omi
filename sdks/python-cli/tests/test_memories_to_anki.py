"""Tests for memories to Anki deck (.apkg) converter.

Pins note field content, HTML escaping of untrusted memory content, stable
GUID/deck-ID derivation across re-exports, and atomic-write / overwrite
refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_anki.py"
spec = importlib.util.spec_from_file_location("memories_to_anki", script_path)
m2a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2a)


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


class TestMemoriesToAnki(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "mem_001",
                "category": "work",
                "content": "Prefers async standups over live meetings",
                "tags": ["workflow", "remote"],
                "created_at": "2026-09-18T10:00:00Z",
            },
            {
                "id": "mem_002",
                "category": "interesting",
                "content": "<b>bold</b> & a\nsecond line",
                "tags": [],
                "created_at": "2026-09-19T14:15:00Z",
            },
        ]

    def test_conversion_and_html_escaping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2a.convert(json_file, apkg_file, deck_name="Test Deck")
            self.assertTrue(apkg_file.is_file())

            notes = _read_notes(apkg_file)
            self.assertEqual(len(notes), 2)

            fields_by_guid = {guid: flds.split("\x1f") for guid, flds in notes}
            front, back = fields_by_guid[m2a.genanki.guid_for("mem_001")]
            self.assertIn("Work", front)
            self.assertIn("workflow, remote", front)
            self.assertIn("Prefers async standups", back)

            # HTML-unsafe content must be escaped, and newlines turned into <br>.
            _, back2 = fields_by_guid[m2a.genanki.guid_for("mem_002")]
            self.assertIn("&lt;b&gt;bold&lt;/b&gt;", back2)
            self.assertNotIn("<b>bold</b>", back2)
            self.assertIn("a<br>second line", back2)

    def test_stable_guid_and_deck_id_across_reexport(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            first = Path(tmpdir) / "first.apkg"
            second = Path(tmpdir) / "second.apkg"
            m2a.convert(json_file, first, deck_name="Same Deck")
            m2a.convert(json_file, second, deck_name="Same Deck")

            guids_first = {guid for guid, _ in _read_notes(first)}
            guids_second = {guid for guid, _ in _read_notes(second)}
            self.assertEqual(guids_first, guids_second)

            self.assertEqual(
                m2a.deck_id_for("Same Deck"),
                m2a.deck_id_for("Same Deck"),
            )
            self.assertNotEqual(
                m2a.deck_id_for("Same Deck"),
                m2a.deck_id_for("Different Deck"),
            )

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps({"memories": self.sample_memories}), encoding="utf-8")

            m2a.convert(json_file, apkg_file)
            self.assertEqual(len(_read_notes(apkg_file)), 2)

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

            with self.assertRaises(ValueError):
                m2a.convert(json_file, apkg_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")
            apkg_file.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                m2a.convert(json_file, apkg_file)


if __name__ == "__main__":
    unittest.main()
