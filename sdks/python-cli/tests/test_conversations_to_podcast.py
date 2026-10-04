from __future__ import annotations

import importlib.util
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

# Load conversations_to_podcast example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_podcast.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "conversations_to_podcast.py"

spec = importlib.util.spec_from_file_location("conversations_to_podcast", script_path)
c2p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2p)


class TestConversationsToPodcast(unittest.TestCase):

    def setUp(self):
        self.sample_convs = [
            {
                "id": "conv-001",
                "started_at": "2026-09-27T09:00:00Z",
                "finished_at": "2026-09-27T09:30:00Z",
                "structured": {
                    "title": "Morning Sync Meeting",
                    "category": "work",
                    "overview": "Discussed Q4 roadmap and client deliverables."
                },
                "transcript_segments": [
                    {"speaker": "Speaker 1", "text": "Welcome everyone to the morning sync."}
                ],
                "audio_url": "https://cdn.example.com/audio/conv-001.mp4"
            },
            {
                "id": "conv-002",
                "created_at": "2026-09-27T14:15:00Z",
                "duration_seconds": 720,
                "structured": {
                    "title": "Coffee Chat with Alex",
                    "category": "personal",
                    "overview": "Catching up on weekend plans."
                },
                "transcript_segments": [
                    {"speaker": "Alex", "text": "How was your weekend?"},
                    {"speaker": "Me", "text": "Pretty good, got a lot done!"}
                ]
                # Notice: no audio_url here!
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
                "--author", "Test Host",
                "--email", "host@example.com"
            ])
            self.assertEqual(ret, 0)
            self.assertTrue(output_file.exists())

            # Parse XML
            root = ET.fromstring(output_file.read_text(encoding="utf-8"))
            self.assertEqual(root.tag, "rss")
            channel = root.find("channel")
            self.assertIsNotNone(channel)
            self.assertEqual(channel.find("title").text, "Test Podcast")

            # Check owner email
            owner = channel.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}owner")
            self.assertIsNotNone(owner)
            self.assertEqual(owner.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}email").text, "host@example.com")

            items = channel.findall("item")
            self.assertEqual(len(items), 2)

            # Check item 1 (Morning Sync with real audio_url)
            item1 = next(it for it in items if "conv-001" in it.find("guid").text)
            self.assertEqual(item1.find("title").text, "Morning Sync Meeting")
            enclosure1 = item1.find("enclosure")
            self.assertIsNotNone(enclosure1)
            self.assertEqual(enclosure1.get("url"), "https://cdn.example.com/audio/conv-001.mp4")
            self.assertEqual(enclosure1.get("type"), "audio/mp4")

            # Check duration (30 mins = 30:00)
            dur = item1.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
            self.assertIsNotNone(dur)
            self.assertEqual(dur.text, "30:00")

            # Check item 2 (Coffee Chat with NO audio_url: must NOT emit fabricated enclosure)
            item2 = next(it for it in items if "conv-002" in it.find("guid").text)
            self.assertEqual(item2.find("title").text, "Coffee Chat with Alex")
            enclosure2 = item2.find("enclosure")
            self.assertIsNone(enclosure2)  # Clean RSS: omit enclosure if no audio URL

            # Check transcript joined from segments
            desc2 = item2.find("description").text
            self.assertIn("Alex", desc2)
            self.assertIn("Pretty good", desc2)

    def test_audio_base_url_generates_enclosure(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "conversations.json"
            input_file.write_text(json.dumps([self.sample_convs[1]]), encoding="utf-8")
            output_file = Path(tmpdir) / "feed.xml"

            ret = c2p.main([
                str(input_file),
                "-o", str(output_file),
                "--audio-base-url", "https://storage.googleapis.com/omi-recordings/"
            ])
            self.assertEqual(ret, 0)
            root = ET.fromstring(output_file.read_text(encoding="utf-8"))
            item = root.find("channel").find("item")
            enclosure = item.find("enclosure")
            self.assertIsNotNone(enclosure)
            self.assertEqual(enclosure.get("url"), "https://storage.googleapis.com/omi-recordings/conv-002.mp4")

    def test_deduplication_across_files(self):
        with TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "page1.json"
            f2 = Path(tmpdir) / "page2.json"

            f1.write_text(json.dumps([self.sample_convs[0]]), encoding="utf-8")
            f2.write_text(json.dumps(self.sample_convs), encoding="utf-8")

            output_file = Path(tmpdir) / "feed.xml"
            ret = c2p.main([str(f1), str(f2), "-o", str(output_file)])
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
