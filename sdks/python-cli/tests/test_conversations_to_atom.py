"""Tests for the conversations -> Atom feed recipe (#15945).

Covers the shared recipe checks (normal input, CJK, empty output, overwrite
refused, missing id, duplicate id, non-array JSON, non-array item, malformed
JSON with no partial file, no input at all) plus feed-specific behavior.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_atom.py"
spec = importlib.util.spec_from_file_location("conversations_to_atom", script_path)
c2a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2a)

ATOM_NS = "{http://www.w3.org/2005/Atom}"


class TestConversationsToAtom(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_json(self, name, data):
        path = self.dir_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_normal_input_produces_valid_feed(self):
        conv = {
            "id": "conv-1",
            "started_at": "2026-09-17T10:00:00Z",
            "finished_at": "2026-09-17T10:20:00Z",
            "structured": {"title": "Standup", "category": "work"},
            "source": "mobile",
            "language": "en",
        }
        src = self.write_json("in.json", [conv])
        out = self.dir_path / "out.xml"
        c2a.convert([str(src)], str(out))

        tree = ET.fromstring(out.read_text(encoding="utf-8"))
        entries = tree.findall(f"{ATOM_NS}entry")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].find(f"{ATOM_NS}title").text, "Standup")
        self.assertEqual(entries[0].find(f"{ATOM_NS}published").text, "2026-09-17T10:00:00Z")
        self.assertEqual(entries[0].find(f"{ATOM_NS}updated").text, "2026-09-17T10:20:00Z")
        self.assertIn("Duration: 20 min", entries[0].find(f"{ATOM_NS}summary").text)

    def test_cjk_title_round_trips(self):
        conv = {"id": "conv-cjk", "started_at": "2026-09-18T10:00:00Z", "structured": {"title": "会議メモ"}}
        src = self.write_json("cjk.json", [conv])
        out = self.dir_path / "cjk.xml"
        c2a.convert([str(src)], str(out))
        tree = ET.fromstring(out.read_text(encoding="utf-8"))
        self.assertEqual(tree.find(f"{ATOM_NS}entry/{ATOM_NS}title").text, "会議メモ")

    def test_empty_export_is_valid_empty_feed(self):
        src = self.write_json("empty.json", [])
        out = self.dir_path / "empty.xml"
        c2a.convert([str(src)], str(out))
        tree = ET.fromstring(out.read_text(encoding="utf-8"))
        self.assertEqual(tree.findall(f"{ATOM_NS}entry"), [])

    def test_overwrite_refused(self):
        src = self.write_json("in.json", [{"id": "conv-1", "structured": {"title": "A"}}])
        out = self.dir_path / "out.xml"
        c2a.convert([str(src)], str(out))
        with self.assertRaises(FileExistsError):
            c2a.convert([str(src)], str(out))

    def test_missing_id_raises(self):
        src = self.write_json("bad.json", [{"structured": {"title": "No id"}}])
        out = self.dir_path / "bad.xml"
        with self.assertRaises(ValueError):
            c2a.convert([str(src)], str(out))
        self.assertFalse(out.exists())

    def test_duplicate_id_across_pages_appears_once(self):
        page1 = self.write_json("p1.json", [{"id": "dup", "started_at": "2026-09-17T10:00:00Z", "structured": {"title": "First"}}])
        page2 = self.write_json("p2.json", [{"id": "dup", "started_at": "2026-09-18T10:00:00Z", "structured": {"title": "Second"}}])
        out = self.dir_path / "out.xml"
        c2a.convert([str(page1), str(page2)], str(out))
        tree = ET.fromstring(out.read_text(encoding="utf-8"))
        entries = tree.findall(f"{ATOM_NS}entry")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].find(f"{ATOM_NS}title").text, "First")

    def test_non_array_json_raises(self):
        src = self.write_json("obj.json", {"not": "an array"})
        out = self.dir_path / "obj.xml"
        with self.assertRaises(ValueError):
            c2a.convert([str(src)], str(out))
        self.assertFalse(out.exists())

    def test_non_array_item_raises(self):
        src = self.write_json("item.json", ["not an object"])
        out = self.dir_path / "item.xml"
        with self.assertRaises(ValueError):
            c2a.convert([str(src)], str(out))
        self.assertFalse(out.exists())

    def test_malformed_json_leaves_no_partial_file(self):
        src = self.dir_path / "mal.json"
        src.write_text("{not valid json", encoding="utf-8")
        out = self.dir_path / "mal.xml"
        with self.assertRaises(ValueError):
            c2a.convert([str(src)], str(out))
        self.assertFalse(out.exists())

    def test_missing_source_file_leaves_no_partial_file(self):
        out = self.dir_path / "noinput.xml"
        with self.assertRaises(OSError):
            c2a.convert([str(self.dir_path / "does-not-exist.json")], str(out))
        self.assertFalse(out.exists())

    def test_markup_in_title_and_category_is_escaped_not_raw(self):
        conv = {
            "id": "conv-xss",
            "started_at": "2026-09-17T10:00:00Z",
            "structured": {"title": "<script>alert(1)</script>", "category": "<b>cat</b>"},
        }
        src = self.write_json("xss.json", [conv])
        out = self.dir_path / "xss.xml"
        c2a.convert([str(src)], str(out))
        raw = out.read_text(encoding="utf-8")
        self.assertNotIn("<script>", raw)
        self.assertNotIn("<b>cat</b>", raw)
        tree = ET.fromstring(raw)  # must still parse
        entry = tree.find(f"{ATOM_NS}entry")
        self.assertEqual(entry.find(f"{ATOM_NS}title").text, "<script>alert(1)</script>")
        self.assertEqual(entry.find(f"{ATOM_NS}category").get("term"), "<b>cat</b>")

    def test_id_with_special_characters_is_percent_encoded(self):
        conv = {"id": "a b/c?", "started_at": "2026-09-17T10:00:00Z", "structured": {"title": "T"}}
        src = self.write_json("special.json", [conv])
        out = self.dir_path / "special.xml"
        c2a.convert([str(src)], str(out))
        tree = ET.fromstring(out.read_text(encoding="utf-8"))
        entry_id = tree.find(f"{ATOM_NS}entry/{ATOM_NS}id").text
        self.assertNotIn(" ", entry_id)
        self.assertTrue(entry_id.startswith("urn:omi-cli:conversations:a%20b"))

    def test_control_chars_and_lone_surrogate_are_dropped_not_fatal(self):
        conv = {"id": "conv-ctrl", "started_at": "2026-09-17T10:00:00Z",
                "structured": {"title": "Bad\x00\x07Title\ud800End", "category": "Bad\x01Cat\ud800End"}}
        src = self.write_json("ctrl.json", [conv])
        out = self.dir_path / "ctrl.xml"
        c2a.convert([str(src)], str(out))
        tree = ET.fromstring(out.read_text(encoding="utf-8"))  # must still parse
        title = tree.find(f"{ATOM_NS}entry/{ATOM_NS}title").text
        self.assertNotIn("\x00", title)
        self.assertNotIn("\x07", title)
        cat = tree.find(f"{ATOM_NS}entry/{ATOM_NS}category").attrib["term"]
        self.assertNotIn("\x01", cat)
        self.assertEqual(cat, "BadCatEnd")

    def test_end_before_start_gives_zero_duration(self):
        conv = {"id": "conv-neg", "started_at": "2026-09-17T10:20:00Z", "finished_at": "2026-09-17T10:00:00Z",
                "structured": {"title": "T"}}
        src = self.write_json("neg.json", [conv])
        out = self.dir_path / "neg.xml"
        c2a.convert([str(src)], str(out))
        summary = ET.fromstring(out.read_text(encoding="utf-8")).find(f"{ATOM_NS}entry/{ATOM_NS}summary").text
        self.assertIn("Duration: 0 min", summary)

    def test_missing_started_at_sorts_last_with_epoch_updated_and_no_published(self):
        old = {"id": "old", "started_at": "not-a-date", "structured": {"title": "No date"}}
        recent = {"id": "recent", "started_at": "2026-09-17T10:00:00Z", "structured": {"title": "Has date"}}
        src = self.write_json("mixed.json", [old, recent])
        out = self.dir_path / "mixed.xml"
        c2a.convert([str(src)], str(out))
        tree = ET.fromstring(out.read_text(encoding="utf-8"))
        entries = tree.findall(f"{ATOM_NS}entry")
        self.assertEqual([e.find(f"{ATOM_NS}title").text for e in entries], ["Has date", "No date"])
        self.assertIsNone(entries[1].find(f"{ATOM_NS}published"))
        self.assertEqual(entries[1].find(f"{ATOM_NS}updated").text, "1970-01-01T00:00:00Z")

    def test_same_input_twice_is_byte_identical(self):
        conv = {"id": "conv-1", "started_at": "2026-09-17T10:00:00Z", "structured": {"title": "T"}}
        src = self.write_json("in.json", [conv])
        out1 = self.dir_path / "out1.xml"
        out2 = self.dir_path / "out2.xml"
        c2a.convert([str(src)], str(out1))
        c2a.convert([str(src)], str(out2))
        self.assertEqual(out1.read_bytes(), out2.read_bytes())


if __name__ == "__main__":
    unittest.main()
