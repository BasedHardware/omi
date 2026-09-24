"""Tests for Omi conversations to WebVTT subtitle export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_vtt.py"
spec = importlib.util.spec_from_file_location("conversations_to_vtt", script_path)
c2v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2v)


class TestConversationsToVtt(unittest.TestCase):
    def test_format_vtt_timestamp(self):
        self.assertEqual(c2v.format_vtt_timestamp(0.0), "00:00:00.000")
        self.assertEqual(c2v.format_vtt_timestamp(65.5), "00:01:05.500")
        self.assertEqual(c2v.format_vtt_timestamp(3661.125), "01:01:01.125")

    def test_parse_seconds(self):
        self.assertEqual(c2v.parse_seconds(10), 10.0)
        self.assertEqual(c2v.parse_seconds("01:30"), 90.0)
        self.assertEqual(c2v.parse_seconds("01:00:10"), 3610.0)
        self.assertEqual(c2v.parse_seconds(None, 5.0), 5.0)

    def test_extract_conversations(self):
        raw_list = '[{"id": "conv-1", "title": "Meeting 1"}]'
        raw_wrapped = '{"conversations": [{"id": "conv-2", "title": "Meeting 2"}]}'

        res1 = c2v.extract_conversations(raw_list)
        res2 = c2v.extract_conversations(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "conv-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "conv-2")

    def test_render_vtt_segments_and_speakers(self):
        conv = {
            "id": "c-999",
            "structured": {"title": "Architecture Review"},
            "transcript_segments": [
                {
                    "text": "Let's review the API contracts.",
                    "speaker": "Alice",
                    "start": 1.5,
                    "end": 4.0,
                },
                {
                    "text": "Sounds good, looking at them now.",
                    "speaker": "Bob",
                    "start": 4.5,
                    "end": 7.0,
                },
            ],
        }
        vtt = c2v.render_vtt(conv)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:01.500 --> 00:00:04.000", vtt)
        self.assertIn("<v Alice>Let's review the API contracts.</v>", vtt)
        self.assertIn("00:00:04.500 --> 00:00:07.000", vtt)
        self.assertIn("<v Bob>Sounds good, looking at them now.</v>", vtt)

    def test_convert_conversations_to_vtt_output_dir(self):
        conv1 = {"id": "c-1", "transcript": "Hello world"}
        conv2 = {"id": "c-2", "transcript": "Second meeting"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "data.json"
            out_dir = tmp / "subtitles"

            f.write_text(json.dumps([conv1, conv2]), encoding="utf-8")
            count = c2v.convert_conversations_to_vtt([f], output_dir=out_dir)

            self.assertEqual(count, 2)
            self.assertTrue((out_dir / "c-1.vtt").exists())
            self.assertTrue((out_dir / "c-2.vtt").exists())

            content = (out_dir / "c-1.vtt").read_text(encoding="utf-8")
            self.assertIn("WEBVTT", content)
            self.assertIn("Hello world", content)


if __name__ == "__main__":
    unittest.main()
