"""Tests for the memories -> Atom feed exporter.

Pins the feed shape (Atom 1.0, newest first, one entry per memory), timestamp
normalisation, XML escaping of hostile content, deduplication across exports,
loose field coercion, category terms, and the no-overwrite guarantee.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_atom.py"
spec = importlib.util.spec_from_file_location("memories_to_atom", script_path)
mem2atom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mem2atom)

ATOM = {"atom": "http://www.w3.org/2005/Atom"}


class TestMemoriesToAtom(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, *documents):
        """Write the given documents as exports and convert them."""
        names = []
        for index, document in enumerate(documents):
            name = self.tmp / f"memories-{index}.json"
            name.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            names.append(str(name))
        destination = self.tmp / "memories.xml"
        count = mem2atom.convert(str(destination), names)
        return count, destination.read_text(encoding="utf-8")

    def parsed(self, xml_text):
        return ET.fromstring(xml_text)

    # --- shape ---------------------------------------------------------------

    def test_feed_is_atom_1_0_with_expected_metadata(self):
        count, xml_text = self.export(
            [
                {
                    "id": "mem_1",
                    "category": "work",
                    "visibility": "private",
                    "tags": ["team", "okr"],
                    "content": "Prefers async updates",
                    "created_at": "2026-09-20T10:00:00Z",
                }
            ]
        )
        self.assertEqual(count, 1)
        root = self.parsed(xml_text)
        self.assertEqual(root.tag, "{http://www.w3.org/2005/Atom}feed")
        self.assertEqual(root.find("atom:id", ATOM).text, "urn:omi:memories")
        self.assertEqual(root.find("atom:updated", ATOM).text, "2026-09-20T10:00:00Z")

    def test_one_entry_per_memory_newest_first(self):
        _, xml_text = self.export(
            [
                {"id": "old", "content": "older", "created_at": "2026-01-01T00:00:00Z"},
                {"id": "new", "content": "newer", "created_at": "2026-06-01T00:00:00Z"},
            ]
        )
        root = self.parsed(xml_text)
        titles = [e.find("atom:title", ATOM).text for e in root.findall("atom:entry", ATOM)]
        self.assertEqual(titles, ["newer", "older"])

    def test_entry_id_is_namespaced_and_percent_encoded(self):
        _, xml_text = self.export([{"id": "a/b c", "content": "x", "created_at": "2026-01-01T00:00:00Z"}])
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:id", ATOM).text, "urn:omi:memory:a%2Fb%20c")

    def test_category_becomes_a_term(self):
        _, xml_text = self.export([{"id": "1", "category": "skills", "content": "x", "created_at": "2026-01-01T00:00:00Z"}])
        category = self.parsed(xml_text).find("atom:entry", ATOM).find("atom:category", ATOM)
        self.assertEqual(category.get("term"), "skills")

    def test_summary_carries_metadata_not_content(self):
        _, xml_text = self.export(
            [
                {
                    "id": "1",
                    "category": "health",
                    "visibility": "private",
                    "tags": ["sleep"],
                    "content": "SECRET BODY TEXT",
                    "created_at": "2026-02-02T03:04:05Z",
                }
            ]
        )
        summary = self.parsed(xml_text).find("atom:entry", ATOM).find("atom:summary", ATOM).text
        self.assertIn("category: health", summary)
        self.assertIn("visibility: private", summary)
        self.assertIn("tags: sleep", summary)
        self.assertIn("created: 2026-02-02T03:04:05Z", summary)
        self.assertNotIn("SECRET BODY TEXT", summary)

    # --- timestamps ----------------------------------------------------------

    def test_offset_timestamp_is_normalised_to_utc(self):
        _, xml_text = self.export([{"id": "1", "content": "x", "created_at": "2026-05-05T12:00:00+02:00"}])
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:updated", ATOM).text, "2026-05-05T10:00:00Z")

    def test_naive_timestamp_is_treated_as_utc(self):
        _, xml_text = self.export([{"id": "1", "content": "x", "created_at": "2026-05-05T12:00:00"}])
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:updated", ATOM).text, "2026-05-05T12:00:00Z")

    def test_unparsable_timestamp_falls_back_to_epoch(self):
        _, xml_text = self.export([{"id": "1", "content": "x", "created_at": "not-a-date"}])
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:updated", ATOM).text, mem2atom.EPOCH)

    def test_missing_timestamp_falls_back_to_epoch(self):
        _, xml_text = self.export([{"id": "1", "content": "x"}])
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:updated", ATOM).text, mem2atom.EPOCH)

    # --- hostile content -----------------------------------------------------

    def test_xml_special_characters_are_escaped(self):
        _, xml_text = self.export(
            [{"id": "1", "content": "a < b & c > d \"q\" 's'", "created_at": "2026-01-01T00:00:00Z"}]
        )
        # The document must still parse, and the text must round-trip.
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:title", ATOM).text, "a < b & c > d \"q\" 's'")

    def test_control_characters_are_dropped(self):
        _, xml_text = self.export([{"id": "1", "content": "before\x00\x08after", "created_at": "2026-01-01T00:00:00Z"}])
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:title", ATOM).text, "beforeafter")

    def test_invalid_surrogate_is_dropped(self):
        # A lone surrogate cannot be written to a UTF-8 file, so it is encoded as
        # the JSON escape \ud800 and reaches the converter through json.load.
        source = self.tmp / "surrogate.json"
        source.write_text(
            '[{"id": "1", "content": "a\\ud800b", "created_at": "2026-01-01T00:00:00Z"}]',
            encoding="utf-8",
        )
        destination = self.tmp / "out.xml"
        mem2atom.convert(str(destination), [str(source)])
        entry = ET.fromstring(destination.read_text(encoding="utf-8")).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:title", ATOM).text, "ab")

    # --- loose typing --------------------------------------------------------

    def test_non_string_fields_are_coerced(self):
        _, xml_text = self.export([{"id": 7, "category": ["a", "b"], "content": {"k": "v"}, "created_at": "2026-01-01T00:00:00Z"}])
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertIn("7", entry.find("atom:id", ATOM).text)
        self.assertEqual(entry.find("atom:title", ATOM).text, '{"k": "v"}')
        self.assertEqual(entry.find("atom:category", ATOM).get("term"), '["a", "b"]')

    def test_non_dict_entries_are_skipped(self):
        count, xml_text = self.export(["nope", 42, {"id": "keep", "content": "x", "created_at": "2026-01-01T00:00:00Z"}])
        self.assertEqual(count, 1)
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertTrue(entry.find("atom:id", ATOM).text.endswith("keep"))

    def test_entry_without_id_is_skipped(self):
        count, _ = self.export([{"content": "no id", "created_at": "2026-01-01T00:00:00Z"}])
        self.assertEqual(count, 0)

    def test_entry_without_content_gets_a_placeholder_title(self):
        _, xml_text = self.export([{"id": "1", "created_at": "2026-01-01T00:00:00Z"}])
        entry = self.parsed(xml_text).find("atom:entry", ATOM)
        self.assertEqual(entry.find("atom:title", ATOM).text, "(untitled memory)")

    # --- multiple exports ----------------------------------------------------

    def test_same_id_across_exports_is_included_once(self):
        shared = {"id": "dup", "content": "once", "created_at": "2026-01-01T00:00:00Z"}
        count, xml_text = self.export([shared, {"id": "a", "content": "a", "created_at": "2026-01-01T00:00:00Z"}], [shared])
        self.assertEqual(count, 2)
        self.assertEqual(len(self.parsed(xml_text).findall("atom:entry", ATOM)), 2)

    def test_non_array_document_is_rejected(self):
        with self.assertRaises(ValueError):
            self.export({"id": "1", "content": "x"})

    # --- files ---------------------------------------------------------------

    def test_refuses_to_overwrite(self):
        destination = self.tmp / "feed.xml"
        destination.write_text("existing", encoding="utf-8")
        source = self.tmp / "m.json"
        source.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            mem2atom.convert(str(destination), [str(source)])
        self.assertEqual(destination.read_text(encoding="utf-8"), "existing")

    def test_empty_export_produces_a_valid_empty_feed(self):
        count, xml_text = self.export([])
        self.assertEqual(count, 0)
        root = self.parsed(xml_text)
        self.assertEqual(root.find("atom:updated", ATOM).text, mem2atom.EPOCH)
        self.assertEqual(root.findall("atom:entry", ATOM), [])

    def test_cli_runs_the_converter_and_reports_the_count(self):
        source = self.tmp / "m.json"
        source.write_text(
            '[{"id": "1", "content": "x", "created_at": "2026-01-01T00:00:00Z"}]', encoding="utf-8"
        )
        destination = self.tmp / "feed.xml"
        result = subprocess.run(
            [sys.executable, str(script_path), str(destination), str(source)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 memory written", result.stdout)
        self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
