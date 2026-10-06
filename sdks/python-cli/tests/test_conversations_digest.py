import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta

# Add examples folder to sys.path
examples_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples"))
if examples_dir not in sys.path:
    sys.path.insert(0, examples_dir)

from conversations_digest import (
    text,
    parse_time,
    parse_offset,
    hours,
    digest,
    convert,
    main,
)


class TestConversationsDigest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+09:00"), timedelta(hours=9))
        self.assertEqual(parse_offset("-05:30"), timedelta(hours=-5, minutes=-30))
        with self.assertRaises(ValueError):
            parse_offset("invalid")
        with self.assertRaises(ValueError):
            parse_offset("+9:00")

    def test_hours_formatter(self):
        self.assertEqual(hours(3600), "1.0")
        self.assertEqual(hours(1800), "0.5")
        self.assertEqual(hours(0), "0.0")

    def test_digest_generation(self):
        convs = {
            "c1": {
                "id": "c1",
                "started_at": "2026-09-14T10:00:00Z",
                "finished_at": "2026-09-14T11:00:00Z",
                "structured": {"title": "Team Sync", "category": "Work"},
            },
            "c2": {
                "id": "c2",
                "started_at": "2026-09-14T15:00:00Z",
                "finished_at": "2026-09-14T15:30:00Z",
                "structured": {"title": "Coffee Chat", "category": "Social"},
            },
            "c3": {
                "id": "c3",
                "started_at": None,
                "structured": {"title": "Undated Meeting"},
            },
        }

        output_md = digest(convs, timedelta(0))
        self.assertIn("# Omi conversation digest", output_md)
        self.assertIn("Conversations: 2", output_md)
        self.assertIn("Recorded time: 1.5 h", output_md)
        self.assertIn("Skipped (no start time): 1", output_md)
        self.assertIn("## Per day", output_md)
        self.assertIn("| 2026-09-14 | 2 | 1.5 |", output_md)
        self.assertIn("## Per category", output_md)
        self.assertIn("| Work | 1 | 1.0 |", output_md)
        self.assertIn("| Social | 1 | 0.5 |", output_md)
        self.assertIn("## Longest conversations", output_md)
        self.assertIn("Team Sync `c1`", output_md)

    def test_convert_end_to_end(self):
        sample_data = [
            {
                "id": "c1",
                "started_at": "2026-09-14T10:00:00Z",
                "finished_at": "2026-09-14T12:00:00Z",
                "structured": {"title": "Deep Work", "category": "Focus"},
            }
        ]
        input_path = os.path.join(self.temp_dir.name, "week.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        output_path = os.path.join(self.temp_dir.name, "digest.md")
        convert([input_path], output_path, timedelta(0))

        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Deep Work `c1`", content)
        self.assertIn("2.0 h", content)

    def test_refuses_overwrite(self):
        input_path = os.path.join(self.temp_dir.name, "input.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        output_path = os.path.join(self.temp_dir.name, "existing.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("content")

        with self.assertRaises(FileExistsError):
            convert([input_path], output_path, timedelta(0))

    def test_cli_usage(self):
        with self.assertRaises(SystemExit):
            main([])


if __name__ == "__main__":
    unittest.main()
