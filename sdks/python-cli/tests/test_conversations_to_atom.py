import json
import os
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET

# Add examples folder to sys.path
examples_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples"))
if examples_dir not in sys.path:
    sys.path.insert(0, examples_dir)

from conversations_to_atom import (
    text,
    parse_time,
    rfc3339,
    load,
    entries,
    feed,
    convert,
    main,
)


class TestConversationsToAtom(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_text_sanitization(self):
        # Empty and None
        self.assertEqual(text(None), "")
        self.assertEqual(text(""), "")

        # Normal text and whitespace collapsing
        self.assertEqual(text("Hello   World \n"), "Hello World")

        # Surrogates and control chars
        sanitized = text("Test\x00\x08\ud800Value\udfff!")
        self.assertEqual(sanitized, "TestValue!")

        # Non-string coercion
        self.assertEqual(text(123), "123")
        self.assertEqual(text({"a": 1}), '{"a": 1}')

    def test_parse_time_and_rfc3339(self):
        t = parse_time("2026-09-14T12:00:00Z")
        self.assertIsNotNone(t)
        self.assertEqual(rfc3339(t), "2026-09-14T12:00:00Z")

        # Invalid time
        self.assertIsNone(parse_time("invalid-date"))
        self.assertIsNone(parse_time(""))
        self.assertIsNone(parse_time(None))

    def test_basic_convert(self):
        sample_data = [
            {
                "id": "conv-1",
                "started_at": "2026-09-14T10:00:00Z",
                "finished_at": "2026-09-14T10:30:00Z",
                "folder_name": "Work",
                "source": "omi-device",
                "language": "en",
                "structured": {
                    "title": "Morning Standup",
                    "category": "work",
                },
            },
            {
                "id": "conv-2",
                "started_at": "2026-09-14T14:00:00Z",
                "finished_at": "2026-09-14T14:45:00Z",
                "folder_name": "Personal",
                "structured": {
                    "title": "Afternoon Walk & Chat",
                    "category": "leisure",
                },
            },
        ]

        input_path = os.path.join(self.temp_dir.name, "conversations.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        output_path = os.path.join(self.temp_dir.name, "feed.xml")
        count = convert([input_path], output_path)
        self.assertEqual(count, 2)

        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r", encoding="utf-8") as f:
            xml_content = f.read()

        # Parse XML
        root = ET.fromstring(xml_content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        title_el = root.find("atom:title", ns)
        self.assertIsNotNone(title_el)
        self.assertEqual(title_el.text, "Omi conversations")

        entries_el = root.findall("atom:entry", ns)
        self.assertEqual(len(entries_el), 2)

        # First entry should be newest (conv-2, 14:00)
        self.assertEqual(entries_el[0].find("atom:id", ns).text, "urn:omi:conversation:conv-2")
        self.assertEqual(entries_el[0].find("atom:title", ns).text, "Afternoon Walk & Chat")
        self.assertEqual(entries_el[1].find("atom:id", ns).text, "urn:omi:conversation:conv-1")

    def test_deduplication_and_multiple_files(self):
        data_a = [
            {"id": "conv-1", "started_at": "2026-09-14T10:00:00Z", "structured": {"title": "First"}},
            {"id": "conv-2", "started_at": "2026-09-14T12:00:00Z", "structured": {"title": "Second"}},
        ]
        data_b = [
            {"id": "conv-2", "started_at": "2026-09-14T12:00:00Z", "structured": {"title": "Second Updated"}},
            {"id": "conv-3", "started_at": "2026-09-14T14:00:00Z", "structured": {"title": "Third"}},
        ]

        path_a = os.path.join(self.temp_dir.name, "a.json")
        path_b = os.path.join(self.temp_dir.name, "b.json")
        with open(path_a, "w", encoding="utf-8") as f:
            json.dump(data_a, f)
        with open(path_b, "w", encoding="utf-8") as f:
            json.dump(data_b, f)

        output_path = os.path.join(self.temp_dir.name, "dedup.xml")
        count = convert([path_a, path_b], output_path)
        self.assertEqual(count, 3)

    def test_envelope_unwrapping(self):
        envelope = {
            "conversations": [
                {"id": "conv-env", "started_at": "2026-09-14T10:00:00Z", "structured": {"title": "Env Test"}}
            ]
        }
        path = os.path.join(self.temp_dir.name, "envelope.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(envelope, f)

        output_path = os.path.join(self.temp_dir.name, "env.xml")
        count = convert([path], output_path)
        self.assertEqual(count, 1)

    def test_refuses_overwrite(self):
        input_path = os.path.join(self.temp_dir.name, "input.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump([{"id": "c1", "structured": {"title": "T"}}], f)

        output_path = os.path.join(self.temp_dir.name, "existing.xml")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("already here")

        with self.assertRaises(FileExistsError):
            convert([input_path], output_path)

    def test_invalid_input_handling(self):
        path = os.path.join(self.temp_dir.name, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"random_key": "not a list"}, f)

        output_path = os.path.join(self.temp_dir.name, "out.xml")
        with self.assertRaises(ValueError):
            convert([path], output_path)

    def test_cli_usage(self):
        # Missing args
        with self.assertRaises(SystemExit):
            main([])


if __name__ == "__main__":
    unittest.main()
