"""Tests for the action_items_to_atom recipe."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_atom.py"
spec = importlib.util.spec_from_file_location("action_items_to_atom", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
ai2atom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2atom)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class TestActionItemsToAtom(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample_items = [
            {
                "id": "act_01_done",
                "description": "Submit quarterly budget report",
                "completed": True,
                "due_at": "2026-09-30T17:00:00Z",
                "created_at": "2026-09-25T09:00:00Z",
                "updated_at": "2026-09-30T16:30:00Z",
                "conversation_id": "conv_991",
            },
            {
                "id": "act_02_overdue",
                "description": "Fix memory leak in background worker",
                "completed": False,
                "due_at": "2026-10-01T10:00:00Z",
                "created_at": "2026-09-28T09:00:00Z",
                "updated_at": "2026-09-28T09:00:00Z",
            },
            {
                "id": "act_03_upcoming",
                "description": "Prepare release notes for v2.4",
                "completed": False,
                "due_at": "2026-10-05T15:00:00Z",
                "created_at": "2026-10-01T09:00:00Z",
            },
            {
                "id": "act_04_undated",
                "description": "Explore speculative prototype ideas",
                "completed": False,
                "due_at": None,
                "created_at": "2026-10-01T11:00:00Z",
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_is_completed_normalization(self):
        self.assertTrue(ai2atom.is_completed(True))
        self.assertTrue(ai2atom.is_completed(1))
        self.assertTrue(ai2atom.is_completed("done"))
        self.assertTrue(ai2atom.is_completed("COMPLETED"))
        self.assertTrue(ai2atom.is_completed("yes"))
        self.assertTrue(ai2atom.is_completed("x"))
        self.assertFalse(ai2atom.is_completed(False))
        self.assertFalse(ai2atom.is_completed(0))
        self.assertFalse(ai2atom.is_completed("open"))
        self.assertFalse(ai2atom.is_completed(None))

    def test_xml_text_sanitization(self):
        self.assertEqual(ai2atom.xml_text("Simple text"), "Simple text")
        self.assertEqual(ai2atom.xml_text(None), "")
        self.assertEqual(ai2atom.xml_text("Line\nBreak\tand   spaces"), "Line Break and spaces")
        # Control codes like \x07 (bell) and \x00 must be dropped
        sanitized = ai2atom.xml_text("Hello\x00World\x07!")
        self.assertEqual(sanitized, "HelloWorld!")

    def test_parse_time_and_rfc3339(self):
        dt = ai2atom.parse_time("2026-10-02T12:00:00Z")
        self.assertEqual(dt, datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(ai2atom.rfc3339(dt), "2026-10-02T12:00:00Z")

        dt_offset = ai2atom.parse_time("2026-10-02T14:00:00+02:00")
        self.assertEqual(dt_offset, datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(ai2atom.rfc3339(dt_offset), "2026-10-02T12:00:00Z")

        self.assertIsNone(ai2atom.parse_time("not-a-date"))
        self.assertIsNone(ai2atom.parse_time(None))

    def test_unwrap_items_envelopes(self):
        for key in ("action_items", "items", "data", "results"):
            envelope = {key: self.sample_items}
            items = ai2atom.unwrap_items(envelope, "test")
            self.assertEqual(len(items), 4)

        # Bare list
        self.assertEqual(len(ai2atom.unwrap_items(self.sample_items, "test")), 4)

        # Bare single dict
        single = {"id": "single", "description": "Single task"}
        self.assertEqual(len(ai2atom.unwrap_items(single, "test")), 1)

        # Non-item dict returns empty list
        self.assertEqual(len(ai2atom.unwrap_items({"error": "not found"}, "test")), 0)

        # Invalid non-container
        with self.assertRaises(ValueError):
            ai2atom.unwrap_items("invalid string", "test")

    def test_load_and_deduplication(self):
        f1 = self.tmp / "f1.json"
        f2 = self.tmp / "f2.json"
        f1.write_text(json.dumps(self.sample_items[:2]), encoding="utf-8")
        f2.write_text(json.dumps(self.sample_items[1:]), encoding="utf-8")

        loaded = ai2atom.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 4)
        self.assertIn("act_01_done", loaded)
        self.assertIn("act_02_overdue", loaded)

    def test_build_entries_and_status_filtering(self):
        items_dict = {it["id"]: it for it in self.sample_items}

        all_entries = ai2atom.build_entries(items_dict, status_filter="all")
        self.assertEqual(len(all_entries), 4)

        open_entries = ai2atom.build_entries(items_dict, status_filter="open")
        self.assertEqual(len(open_entries), 3)
        self.assertTrue(all(not e["completed"] for e in open_entries))
        self.assertTrue(all(e["title"].startswith("[OPEN]") for e in open_entries))

        completed_entries = ai2atom.build_entries(items_dict, status_filter="completed")
        self.assertEqual(len(completed_entries), 1)
        self.assertTrue(completed_entries[0]["completed"])
        self.assertTrue(completed_entries[0]["title"].startswith("[DONE]"))

    def test_build_feed_valid_xml(self):
        items_dict = {it["id"]: it for it in self.sample_items}
        entries = ai2atom.build_entries(items_dict, status_filter="all")
        xml_string = ai2atom.build_feed(entries, feed_title="My Test Tasks")

        # Must parse as valid XML
        root = ET.fromstring(xml_string)
        self.assertEqual(root.tag, "{http://www.w3.org/2005/Atom}feed")

        title_elem = root.find("atom:title", ATOM_NS)
        self.assertIsNotNone(title_elem)
        self.assertEqual(title_elem.text, "My Test Tasks")

        entry_elems = root.findall("atom:entry", ATOM_NS)
        self.assertEqual(len(entry_elems), 4)

        # Check first entry
        first_entry = entry_elems[0]
        self.assertIsNotNone(first_entry.find("atom:id", ATOM_NS))
        self.assertIsNotNone(first_entry.find("atom:title", ATOM_NS))
        self.assertIsNotNone(first_entry.find("atom:updated", ATOM_NS))
        self.assertIsNotNone(first_entry.find("atom:category", ATOM_NS))
        self.assertIsNotNone(first_entry.find("atom:summary", ATOM_NS))
        self.assertIsNotNone(first_entry.find("atom:content", ATOM_NS))

    def test_empty_feed(self):
        xml_string = ai2atom.build_feed([], feed_title="Empty Tasks")
        root = ET.fromstring(xml_string)
        self.assertEqual(len(root.findall("atom:entry", ATOM_NS)), 0)
        updated = root.find("atom:updated", ATOM_NS)
        self.assertEqual(updated.text, "1970-01-01T00:00:00Z")

    def test_convert_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "feed.atom"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        count = ai2atom.convert([str(src)], destination=str(dest))
        self.assertEqual(count, 4)
        self.assertTrue(dest.exists())

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            ai2atom.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        count2 = ai2atom.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(count2, 4)

    def test_failed_write_cleans_up_destination(self):
        src = self.tmp / "input_err.json"
        dest = self.tmp / "feed_err.atom"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        real_open = Path.open

        def failing_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            mode = kwargs.get("mode", args[0] if args else "r")
            if "xb" in mode and str(self_path) == str(dest):
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk full"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_open):
            with self.assertRaises(OSError):
                ai2atom.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_main_cli_execution(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_feed.atom"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        ret = ai2atom.main([str(src), "-o", str(dest), "--status", "open", "--title", "CLI Tasks"])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())

        root = ET.fromstring(dest.read_text(encoding="utf-8"))
        self.assertEqual(len(root.findall("atom:entry", ATOM_NS)), 3)

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_items).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = ai2atom.load(["-"])
            self.assertEqual(len(loaded), 4)


if __name__ == "__main__":
    unittest.main()
