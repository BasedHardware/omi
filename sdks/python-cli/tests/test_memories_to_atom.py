"""Hermetic tests for examples/memories_to_atom.py (#19223).

Covers: RFC 3339 timestamps, metadata-only summary (content excluded),
XML escaping + illegal-char dropping, newest-first sort, ID dedupe,
envelope unwrapping, overwrite/path refusal.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import memories_to_atom as m  # noqa: E402

MEM = {
    "id": "m1",
    "content": "Loves espresso & hates meetings",
    "category": "personal",
    "visibility": "public",
    "tags": ["coffee", "work"],
    "created_at": "2026-10-17T12:00:00+02:00",
    "updated_at": "2026-10-17T14:00:00Z",
}


class TestTextClean(unittest.TestCase):
    def test_illegal_chars_dropped(self):
        self.assertEqual(m.clean_text("a\x00b\ud800c"), "abc")
        self.assertEqual(m.clean_text("a\x01b"), "ab")

    def test_non_string_coerced(self):
        self.assertEqual(m.clean_text({"a": 1}), '{"a": 1}')


class TestSummary(unittest.TestCase):
    def test_metadata_only_no_content(self):
        s = m.summary_of(MEM)
        self.assertIn("Category: personal", s)
        self.assertIn("Visibility: public", s)
        self.assertIn("Tags: coffee, work", s)
        self.assertNotIn("espresso", s)  # content never leaks into summary

    def test_no_metadata_fallback(self):
        self.assertEqual(m.summary_of({"id": "x"}), "Omi memory")


class TestEntries(unittest.TestCase):
    def test_newest_first(self):
        rows = m.entries(
            {
                "old": {"id": "old", "content": "o", "created_at": "2026-01-01T00:00:00Z"},
                "new": {"id": "new", "content": "n", "created_at": "2026-10-17T10:00:00Z"},
            }
        )
        self.assertEqual(rows[0]["id"], "new")

    def test_published_updated_from_created(self):
        rows = m.entries({"m1": MEM})
        self.assertEqual(rows[0]["published"].hour, 10)  # 12+02:00 → 10Z
        self.assertEqual(rows[0]["updated"].hour, 14)


class TestFeed(unittest.TestCase):
    def test_valid_atom_shape(self):
        rows = m.entries({"m1": MEM})
        xml = m.feed(rows)
        self.assertIn('<feed xmlns="http://www.w3.org/2005/Atom">', xml)
        self.assertIn("urn:omi:memory:m1", xml)
        self.assertIn("<published>2026-10-17T10:00:00Z</published>", xml)
        self.assertIn("Category: personal", xml)

    def test_escaping(self):
        rows = m.entries({"m1": {**MEM, "content": "a<b>&\"c\""}})
        xml = m.feed(rows)
        self.assertNotIn("a<b>", xml)
        self.assertIn("a&lt;b&gt;", xml)


class TestConvert(unittest.TestCase):
    def test_writes_feed(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = str(Path(td) / "feed.xml")
            n = m.convert([str(src)], out)
            self.assertEqual(n, 1)
            self.assertIn("<entry>", Path(out).read_text())

    def test_id_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM, MEM]}))
            out = str(Path(td) / "feed.xml")
            self.assertEqual(m.convert([str(src)], out), 1)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = Path(td) / "feed.xml"
            out.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert([str(src)], str(out))
            self.assertEqual(out.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            with self.assertRaises(ValueError):
                m.convert([str(src)], "../escape.xml")


if __name__ == "__main__":
    unittest.main()
