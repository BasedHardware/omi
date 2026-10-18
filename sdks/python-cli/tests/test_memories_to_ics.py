"""Hermetic tests for examples/memories_to_ics.py (#18987).

Covers: RFC 5545 line folding (75 octets, UTF-8-safe), §3.3.11 escaping,
15-minute event slots, envelope unwrapping, no-created_at skip,
overwrite/path refusal.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import memories_to_ics as m  # noqa: E402

MEM = {
    "id": "m1",
    "content": "Loves espresso, hates meetings",
    "category": "personal",
    "visibility": "public",
    "created_at": "2026-10-17T12:00:00+02:00",
}


class TestRfc5545(unittest.TestCase):
    def test_fold_at_75_octets(self):
        line = "X" * 200
        parts = m.fold(line)
        for p in parts:
            self.assertLessEqual(len(p.encode("utf-8")), 75)

    def test_fold_no_utf8_split(self):
        line = "café " * 30  # é is 2 bytes
        parts = m.fold(line)
        for p in parts:
            p.encode("utf-8")  # decodable = no split mid-char
            self.assertLessEqual(len(p.encode("utf-8")), 75)

    def test_escape_text(self):
        self.assertEqual(m.escape("a;b,c\nd\\e"), "a\\;b\\,c\\nd\\\\e")

    def test_stamp_utc(self):
        dt = datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(m.stamp(dt), "20261017T100000Z")


class TestEvents(unittest.TestCase):
    def test_15_min_slot(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = str(Path(td) / "m.ics")
            n = m.convert([str(src)], out)
            self.assertEqual(n, 1)
            text = Path(out).read_text()
            self.assertIn("DTSTART:20261017T100000Z", text)
            self.assertIn("DTEND:20261017T101500Z", text)
            self.assertIn("UID:omi-memory-m1@omi-cli", text)

    def test_no_created_at_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [{"id": "x", "content": "no date"}]}))
            out = str(Path(td) / "m.ics")
            n = m.convert([str(src)], out)
            self.assertEqual(n, 0)
            self.assertNotIn("BEGIN:VEVENT", Path(out).read_text())

    def test_summary_escaped(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [{**MEM, "content": "a;b,c"}]}))
            out = str(Path(td) / "m.ics")
            m.convert([str(src)], out)
            self.assertIn("SUMMARY:a\\;b\\,c", Path(out).read_text())

    def test_envelope_shapes(self):
        for payload in ({"memories": [MEM]}, {"items": [MEM]}, {"data": [MEM]}, [MEM], MEM):
            self.assertEqual(len(m.extract_memories(payload)), 1)

    def test_id_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM, MEM]}))
            out = str(Path(td) / "m.ics")
            self.assertEqual(m.convert([str(src)], out), 1)

    def test_crlf_output(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = Path(td) / "m.ics"
            m.convert([str(src)], str(out))
            self.assertIn(b"\r\n", out.read_bytes())


class TestSafety(unittest.TestCase):
    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = Path(td) / "m.ics"
            out.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert([str(src)], str(out))
            self.assertEqual(out.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            with self.assertRaises(ValueError):
                m.convert([str(src)], "../escape.ics")


if __name__ == "__main__":
    unittest.main()
