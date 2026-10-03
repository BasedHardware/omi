import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

# Add scratch path to sys.path
sys.path.insert(0, str(Path(__file__).parent))
import conversations_to_podcast as c2p


class TestConversationsToPodcast(unittest.TestCase):

    def setUp(self):
        self.sample_convs = [
            {
                "id": "conv-001",
                "title": "Morning Sync Meeting",
                "category": "work",
                "started_at": "2026-09-27T09:00:00Z",
                "finished_at": "2026-09-27T09:30:00Z",
                "structured": {
                    "overview": "Discussed Q4 roadmap and client deliverables."
                },
                "transcript": "Speaker 1: Welcome everyone to the morning sync.",
                "audio_url": "https://cdn.example.com/audio/conv-001.mp4"
            },
            {
                "id": "conv-002",
                "title": "Coffee Chat with Alex",
                "category": "personal",
                "created_at": "2026-09-27T14:15:00Z",
                "duration_seconds": 720,
                "summary": "Catching up on weekend plans.",
                "transcript": "Speaker 2: How was your weekend?"
            }
        ]

    def test_feed_generation_valid_xml(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "conversations.json"
            input_file.write_text(json.dumps(self.sample_convs), encoding="utf-8")
            output_file = Path(tmpdir) / "feed.xml"

            ret = c2p.main([
                str(input_file),
                "-o", str(output_file),
                "--title", "Test Podcast",
                "--author", "Test Host"
            ])
            self.assertEqual(ret, 0)
            self.assertTrue(output_file.exists())

            # Parse XML
            root = ET.fromstring(output_file.read_text(encoding="utf-8"))
            self.assertEqual(root.tag, "rss")
            channel = root.find("channel")
            self.assertIsNotNone(channel)
            self.assertEqual(channel.find("title").text, "Test Podcast")

            items = channel.findall("item")
            self.assertEqual(len(items), 2)

            # Check item 1 (Morning Sync)
            item1 = next(it for it in items if "conv-001" in it.find("guid").text)
            self.assertEqual(item1.find("title").text, "Morning Sync Meeting")
            enclosure = item1.find("enclosure")
            self.assertIsNotNone(enclosure)
            self.assertEqual(enclosure.get("url"), "https://cdn.example.com/audio/conv-001.mp4")
            self.assertEqual(enclosure.get("type"), "audio/mp4")

            # Check duration (30 mins = 30:00)
            dur = item1.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
            self.assertIsNotNone(dur)
            self.assertEqual(dur.text, "30:00")

    def test_deduplication_across_files(self):
        with TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "page1.json"
            f2 = Path(tmpdir) / "page2.json"

            f1.write_text(json.dumps([self.sample_convs[0]]), encoding="utf-8")
            # f2 has both conv-001 and conv-002
            f2.write_text(json.dumps(self.sample_convs), encoding="utf-8")

            output_file = Path(tmpdir) / "feed.xml"
            ret = c2p.main([str(f1), str(f2), "-o", str(output_file)])
            self.assertEqual(ret, 0)

            root = ET.fromstring(output_file.read_text(encoding="utf-8"))
            items = root.find("channel").findall("item")
            # Should have exactly 2 unique items, not 3
            self.assertEqual(len(items), 2)

    def test_wrapped_json_format(self):
        with TemporaryDirectory() as tmpdir:
            wrapped = {"conversations": self.sample_convs}
            input_file = Path(tmpdir) / "wrapped.json"
            input_file.write_text(json.dumps(wrapped), encoding="utf-8")
            output_file = Path(tmpdir) / "feed.xml"

            ret = c2p.main([str(input_file), "-o", str(output_file)])
            self.assertEqual(ret, 0)
            root = ET.fromstring(output_file.read_text(encoding="utf-8"))
            items = root.find("channel").findall("item")
            self.assertEqual(len(items), 2)

    def test_category_filter(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "conversations.json"
            input_file.write_text(json.dumps(self.sample_convs), encoding="utf-8")
            output_file = Path(tmpdir) / "feed.xml"

            ret = c2p.main([
                str(input_file),
                "-o", str(output_file),
                "--filter-category", "work"
            ])
            self.assertEqual(ret, 0)
            root = ET.fromstring(output_file.read_text(encoding="utf-8"))
            items = root.find("channel").findall("item")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].find("title").text, "Morning Sync Meeting")

    def test_path_traversal_protection(self):
        ret = c2p.main(["dummy.json", "-o", "../evil_feed.xml"])
        self.assertEqual(ret, 2)


if __name__ == "__main__":
    unittest.main()
