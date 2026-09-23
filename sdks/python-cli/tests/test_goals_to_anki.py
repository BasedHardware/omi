"""Tests for goals to Anki deck (.apkg) converter.

Pins progress-percentage computation, note field content, HTML escaping of
untrusted content, stable GUID/deck-ID derivation across re-exports, and
atomic-write / overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_anki.py"
spec = importlib.util.spec_from_file_location("goals_to_anki", script_path)
g2a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2a)


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


class TestGoalsToAnki(unittest.TestCase):
    def setUp(self):
        self.sample_goals = [
            {
                "id": "g1",
                "title": "Read 20 books",
                "current_value": 12,
                "target_value": 20,
                "min_value": 0,
                "max_value": 20,
                "unit": "books",
                "is_active": True,
            },
            {
                "id": "g2",
                "title": "<b>bold</b> & goal",
                "current_value": 1,
                "target_value": 1,
                "min_value": 0,
                "max_value": 1,
                "unit": "",
                "is_active": False,
            },
        ]

    def test_progress_pct(self):
        self.assertAlmostEqual(g2a.progress_pct(12, 20, 0, 20), 0.6)
        self.assertAlmostEqual(g2a.progress_pct(5, 0, 0, 10), 0.5)
        self.assertEqual(g2a.progress_pct("n/a", 10, 0, 10), 0.0)

    def test_conversion_and_html_escaping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            g2a.convert(json_file, apkg_file, deck_name="Test Deck")
            self.assertTrue(apkg_file.is_file())

            notes = _read_notes(apkg_file)
            self.assertEqual(len(notes), 2)
            fields_by_guid = {guid: flds.split("\x1f") for guid, flds in notes}

            front, back = fields_by_guid[g2a.genanki.guid_for("g1")]
            self.assertIn("Read 20 books", front)
            self.assertIn("12 / 20 books", back)
            self.assertIn("60%", back)
            self.assertIn("Active", back)

            front2, back2 = fields_by_guid[g2a.genanki.guid_for("g2")]
            self.assertIn("&lt;b&gt;bold&lt;/b&gt;", front2)
            self.assertNotIn("<b>bold</b>", front2)
            self.assertIn("Completed / Inactive", back2)

    def test_stable_guid_and_deck_id_across_reexport(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            first = Path(tmpdir) / "first.apkg"
            second = Path(tmpdir) / "second.apkg"
            g2a.convert(json_file, first, deck_name="Same Deck")
            g2a.convert(json_file, second, deck_name="Same Deck")

            self.assertEqual(
                {g for g, _ in _read_notes(first)},
                {g for g, _ in _read_notes(second)},
            )
            self.assertEqual(g2a.deck_id_for("Same Deck"), g2a.deck_id_for("Same Deck"))
            self.assertNotEqual(g2a.deck_id_for("Same Deck"), g2a.deck_id_for("Different Deck"))

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps({"goals": self.sample_goals}), encoding="utf-8")

            g2a.convert(json_file, apkg_file)
            self.assertEqual(len(_read_notes(apkg_file)), 2)

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

            with self.assertRaises(ValueError):
                g2a.convert(json_file, apkg_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            apkg_file = Path(tmpdir) / "output.apkg"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")
            apkg_file.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2a.convert(json_file, apkg_file)


if __name__ == "__main__":
    unittest.main()
