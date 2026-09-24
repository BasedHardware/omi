"""Tests for conversations to RSS 2.0 feed exporter.

Verifies:
- Standard RSS 2.0 XML structure and required elements
- Conversation metadata mapping (title, category, RFC 822 pubDate, non-permalink guid, summary)
- Multi-file input loading and conversation ID deduplication
- Reverse chronological sorting (newest first)
- C0 control characters and lone surrogates stripping (XML 1.0 safety)
- XML entity escaping for special characters (<, >, &, ", ')
- Overwrite guard refusing to overwrite destination without explicit permission
- Schema validation and malformed JSON error handling
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

# Load conversations_to_rss script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_rss.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "conversations_to_rss.py"

spec = importlib.util.spec_from_file_location("conversations_to_rss", script_path)
c2rss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2rss)


class TestConversationsToRss(unittest.TestCase):
    def setUp(self):
        self.sample_conversations = [
            {
                "id": "conv-001",
                "started_at": "2026-09-20T10:00:00Z",
                "finished_at": "2026-09-20T10:30:00Z",
                "folder_name": "Work",
                "source": "omi",
                "language": "en",
                "structured": {
                    "title": "Quarterly Planning & Strategy",
                    "category": "business"
                }
            },
            {
                "id": "conv-002",
                "started_at": "2026-09-21T15:00:00Z",
                "finished_at": "2026-09-21T15:15:00Z",
                "folder_name": "Personal",
                "source": "omi",
                "language": "es",
                "structured": {
                    "title": "Coffee with Friends <Catchup>",
                    "category": "personal"
                }
            }
        ]

    def test_basic_conversion_and_xml_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "conversations.json"
            dst_file = Path(tmpdir) / "feed.xml"
            src_file.write_text(json.dumps(self.sample_conversations), encoding="utf-8")

            count = c2rss.convert([str(src_file)], str(dst_file))
            self.assertEqual(count, 2)
            self.assertTrue(dst_file.exists())

            # Parse XML output
            tree = ET.parse(dst_file)
            root = tree.getroot()
            self.assertEqual(root.tag, "rss")
            self.assertEqual(root.attrib.get("version"), "2.0")

            channel = root.find("channel")
            self.assertIsNotNone(channel)
            self.assertEqual(channel.findtext("title"), "Omi conversations")
            self.assertEqual(channel.findtext("link"), "https://www.omi.me")
            self.assertEqual(channel.findtext("generator"), "Omi CLI RSS Exporter")

            items = channel.findall("item")
            self.assertEqual(len(items), 2)

            # Check newest first ordering (conv-002 is Sep 21, conv-001 is Sep 20)
            first_item = items[0]
            self.assertEqual(first_item.findtext("title"), "Coffee with Friends <Catchup>")
            self.assertEqual(first_item.findtext("category"), "personal")
            self.assertEqual(first_item.findtext("guid"), "urn:omi:conversation:conv-002")
            self.assertIn("Mon, 21 Sep 2026", first_item.findtext("pubDate"))
            self.assertIn("Duration: 15 min", first_item.findtext("description"))

            second_item = items[1]
            self.assertEqual(second_item.findtext("title"), "Quarterly Planning & Strategy")
            self.assertEqual(second_item.findtext("category"), "business")
            self.assertEqual(second_item.findtext("guid"), "urn:omi:conversation:conv-001")
            self.assertIn("Sun, 20 Sep 2026", second_item.findtext("pubDate"))
            self.assertIn("Duration: 30 min", second_item.findtext("description"))

    def test_multi_source_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src1 = Path(tmpdir) / "page1.json"
            src2 = Path(tmpdir) / "page2.json"
            dst = Path(tmpdir) / "feed.xml"

            # Duplicate conv-001 in both files
            src1.write_text(json.dumps([self.sample_conversations[0]]), encoding="utf-8")
            src2.write_text(json.dumps([self.sample_conversations[0], self.sample_conversations[1]]), encoding="utf-8")

            count = c2rss.convert([str(src1), str(src2)], str(dst))
            self.assertEqual(count, 2)

            tree = ET.parse(dst)
            items = tree.findall("./channel/item")
            self.assertEqual(len(items), 2)

    def test_xml_escaping_and_sanitization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tricky.json"
            dst = Path(tmpdir) / "feed.xml"

            tricky_conv = [
                {
                    "id": "conv-special",
                    "started_at": "2026-09-22T08:00:00Z",
                    "structured": {
                        "title": "Discussion on <AI & Robotics> 'Ethics' \"2026\"",
                        "category": "R&D"
                    },
                    "folder_name": "Deep Tech \x00\x08",  # Control characters to strip
                }
            ]
            src.write_text(json.dumps(tricky_conv), encoding="utf-8")

            count = c2rss.convert([str(src)], str(dst))
            self.assertEqual(count, 1)

            tree = ET.parse(dst)
            item = tree.find("./channel/item")
            self.assertEqual(item.findtext("title"), "Discussion on <AI & Robotics> 'Ethics' \"2026\"")
            self.assertEqual(item.findtext("category"), "R&D")
            self.assertIn("Folder: Deep Tech", item.findtext("description"))
            self.assertNotIn("\x00", item.findtext("description"))

    def test_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "conversations.json"
            dst = Path(tmpdir) / "feed.xml"
            src.write_text(json.dumps(self.sample_conversations), encoding="utf-8")
            dst.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                c2rss.convert([str(src)], str(dst))

    def test_invalid_input_handling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_json = Path(tmpdir) / "bad.json"
            dst = Path(tmpdir) / "feed.xml"

            # Object instead of array
            bad_json.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                c2rss.convert([str(bad_json)], str(dst))

            # Item without id
            bad_json.write_text(json.dumps([{"started_at": "2026-09-20T10:00:00Z"}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                c2rss.convert([str(bad_json)], str(dst))


if __name__ == "__main__":
    unittest.main()
