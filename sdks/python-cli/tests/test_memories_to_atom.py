"""Tests for the local Omi memories-to-Atom example."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ATOM = "http://www.w3.org/2005/Atom"
SCRIPT = Path(__file__).resolve().parent.parent / "examples" / "memories_to_atom.py"
SPEC = importlib.util.spec_from_file_location("memories_to_atom", SCRIPT)
memories_to_atom = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(memories_to_atom)


def atom(name: str) -> str:
    return f"{{{ATOM}}}{name}"


def parsed_rows(rows):
    return ET.fromstring(ET.tostring(memories_to_atom.build_feed(rows), encoding="utf-8"))


class TestMemoriesToAtom(unittest.TestCase):
    def setUp(self):
        self.memories = [
            {
                "id": "mem_old",
                "content": "Older fact",
                "category": "work",
                "visibility": "private",
                "tags": ["planning", "team"],
                "created_at": "2026-09-15T10:00:00Z",
            },
            {
                "id": "mem_new",
                "content": "Newer fact",
                "category": "learnings",
                "visibility": "public",
                "tags": ["python"],
                "created_at": "2026-09-16T12:30:00+02:00",
            },
        ]

    def test_feed_uses_atom_10_namespace_and_metadata(self):
        root = parsed_rows(memories_to_atom.entries(self.memories))
        self.assertEqual(root.tag, atom("feed"))
        self.assertEqual(root.findtext(atom("title")), "Omi memories")
        self.assertEqual(root.findtext(atom("id")), "urn:omi:memories")
        self.assertEqual(root.findtext(f"{atom('author')}/{atom('name')}"), "Omi")

    def test_empty_feed_uses_epoch_as_updated(self):
        root = parsed_rows([])
        self.assertEqual(root.findtext(atom("updated")), memories_to_atom.rfc3339(memories_to_atom.EPOCH))
        self.assertEqual(root.findall(atom("entry")), [])

    def test_feed_updated_is_newest_entry_timestamp(self):
        root = parsed_rows(memories_to_atom.entries(self.memories))
        self.assertEqual(root.findtext(atom("updated")), "2026-09-16T10:30:00Z")

    def test_entries_are_newest_first(self):
        root = parsed_rows(memories_to_atom.entries(self.memories))
        self.assertEqual(
            [entry.findtext(atom("id")) for entry in root.findall(atom("entry"))],
            ["urn:omi:memory:mem_new", "urn:omi:memory:mem_old"],
        )

    def test_timestamp_offset_is_normalized_to_utc(self):
        row = memories_to_atom.entries([self.memories[1]])[0]
        self.assertEqual(row["published"], row["updated"])
        self.assertEqual(memories_to_atom.rfc3339(row["published"]), "2026-09-16T10:30:00Z")

    def test_naive_timestamp_is_treated_as_utc(self):
        self.assertEqual(
            memories_to_atom.rfc3339(memories_to_atom.parse_time("2026-09-17T03:04:05")),
            "2026-09-17T03:04:05Z",
        )

    def test_fractional_seconds_are_preserved(self):
        moment = memories_to_atom.parse_time("2026-09-17T03:04:05.125+00:00")
        self.assertEqual(memories_to_atom.rfc3339(moment), "2026-09-17T03:04:05.125Z")

    def test_invalid_timestamp_falls_back_to_epoch(self):
        row = memories_to_atom.entries([{"id": "bad-time", "created_at": "not a date"}])[0]
        self.assertEqual(row["published"], memories_to_atom.EPOCH)
        self.assertEqual(row["updated"], memories_to_atom.EPOCH)

    def test_missing_timestamp_falls_back_to_epoch(self):
        row = memories_to_atom.entries([{"id": "undated"}])[0]
        self.assertEqual(row["published"], memories_to_atom.EPOCH)

    def test_content_is_title_and_summary_contains_metadata_only(self):
        row = memories_to_atom.entries(self.memories)[0]
        self.assertEqual(row["title"], "Newer fact")
        self.assertNotIn("Newer fact", row["summary"])

    def test_summary_contains_category_visibility_tags_and_creation_time(self):
        row = memories_to_atom.entries(self.memories)[1]
        self.assertEqual(
            row["summary"],
            "Category: work - Visibility: private - Tags: planning, team - Created: 2026-09-15T10:00:00Z",
        )

    def test_category_is_emitted_as_atom_term(self):
        root = parsed_rows(memories_to_atom.entries([self.memories[0]]))
        category = root.find(f"{atom('entry')}/{atom('category')}")
        self.assertEqual(category.attrib["term"], "work")

    def test_entry_id_is_percent_encoded(self):
        row = memories_to_atom.entries([{"id": "id with/slash?&"}])
        root = parsed_rows(row)
        self.assertEqual(
            root.findtext(f"{atom('entry')}/{atom('id')}"),
            "urn:omi:memory:id%20with%2Fslash%3F%26",
        )

    def test_markup_is_escaped_and_round_trips(self):
        text = "A < B & C > D"
        row = memories_to_atom.entries([{"id": "m1", "content": text, "category": "R&D"}])
        xml = ET.tostring(memories_to_atom.build_feed(row), encoding="unicode")
        self.assertIn("&lt;", xml)
        self.assertIn("&amp;", xml)
        root = ET.fromstring(xml)
        self.assertEqual(root.findtext(f"{atom('entry')}/{atom('title')}"), text)

    def test_xml_controls_are_removed(self):
        row = memories_to_atom.entries([{"id": "m1", "content": "before\x00\x01after"}])
        root = parsed_rows(row)
        self.assertEqual(root.findtext(f"{atom('entry')}/{atom('title')}"), "beforeafter")

    def test_lone_surrogates_are_removed(self):
        row = memories_to_atom.entries([{"id": "m1", "content": "left\ud800right"}])
        payload = ET.tostring(memories_to_atom.build_feed(row), encoding="utf-8")
        self.assertIn(b"leftright", payload)
        ET.fromstring(payload)

    def test_bmp_and_supplementary_noncharacters_are_removed(self):
        value = "a\ufdd0b\ufffec\U0001fffed\U0010ffffe"
        row = memories_to_atom.entries([{"id": "m1", "content": value}])
        self.assertEqual(row[0]["title"], "abcde")
        ET.fromstring(ET.tostring(memories_to_atom.build_feed(row), encoding="utf-8"))

    def test_non_string_fields_are_coerced(self):
        row = memories_to_atom.entries(
            [{"id": 7, "content": 42, "category": False, "visibility": 3, "tags": ["x", 8]}]
        )[0]
        self.assertEqual(row["id"], "7")
        self.assertEqual(row["title"], "42")
        self.assertEqual(row["category"], "False")
        self.assertIn("Visibility: 3", row["summary"])
        self.assertIn("Tags: x, 8", row["summary"])

    def test_list_and_dict_content_are_rendered_as_json(self):
        row = memories_to_atom.entries([{"id": "m1", "content": {"b": 2, "a": 1}}])[0]
        self.assertEqual(row["title"], '{"a": 1, "b": 2}')

    def test_non_objects_and_rows_without_ids_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "mixed.json"
            source.write_text(json.dumps([None, "row", {}, {"id": ""}]), encoding="utf-8")
            self.assertEqual(memories_to_atom.load_memories([str(source)]), [])

    def test_numeric_zero_id_is_preserved(self):
        rows = memories_to_atom.entries([{"id": 0, "content": "zero id"}])
        self.assertEqual(rows[0]["id"], "0")

    def test_duplicate_ids_across_exports_use_later_input(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            first.write_text(json.dumps([{"id": "same", "content": "old"}]), encoding="utf-8")
            second.write_text(json.dumps([{"id": "same", "content": "new"}]), encoding="utf-8")
            rows = memories_to_atom.entries(memories_to_atom.load_memories([str(first), str(second)]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "new")

    def test_invalid_json_is_reported_with_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.json"
            source.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bad.json: invalid JSON"):
                memories_to_atom.load_memories([str(source)])

    def test_non_array_document_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "object.json"
            source.write_text('{"memories": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected the JSON array"):
                memories_to_atom.load_memories([str(source)])

    def test_utf8_bom_export_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bom.json"
            source.write_text(json.dumps([{"id": "m1"}]), encoding="utf-8-sig")
            self.assertEqual(len(memories_to_atom.load_memories([str(source)])), 1)

    def test_convert_writes_parseable_feed_and_returns_count(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "memories.json"
            output = Path(directory) / "memories.xml"
            source.write_text(json.dumps(self.memories), encoding="utf-8")
            self.assertEqual(memories_to_atom.convert([str(source)], str(output)), 2)
            root = ET.parse(output).getroot()
        self.assertEqual(len(root.findall(atom("entry"))), 2)

    @unittest.skipIf(os.name == "nt", "POSIX file modes are not available on Windows")
    def test_created_feed_is_owner_readable_only(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "memories.json"
            output = Path(directory) / "memories.xml"
            source.write_text(json.dumps([{"id": "m1"}]), encoding="utf-8")
            memories_to_atom.convert([str(source)], str(output))
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

    def test_convert_refuses_to_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "memories.json"
            output = Path(directory) / "memories.xml"
            source.write_text("[]", encoding="utf-8")
            output.write_bytes(b"keep this")
            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                memories_to_atom.convert([str(source)], str(output))
            self.assertEqual(output.read_bytes(), b"keep this")

    def test_cli_accepts_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / "feed.xml")
            stdin = io.StringIO(json.dumps([{"id": "m1", "content": "hello"}]))
            stdout = io.StringIO()
            with patch.object(memories_to_atom.sys, "stdin", stdin), contextlib.redirect_stdout(stdout):
                exit_code = memories_to_atom.main([output, "-"])
            self.assertEqual(exit_code, 0)
            self.assertIn("1 entry written", stdout.getvalue())
            self.assertEqual(len(ET.parse(output).getroot().findall(atom("entry"))), 1)

    def test_cli_rejects_stdin_more_than_once(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            memories_to_atom.main(["feed.xml", "-", "-"])
        self.assertIn("stdin ('-') can be used only once", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
