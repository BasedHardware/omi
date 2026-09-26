"""Tests for Omi conversations to SubRip (.srt) subtitle export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_srt.py"
spec = importlib.util.spec_from_file_location("conversations_to_srt", script_path)
c2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2s)


class TestConversationsToSrt(unittest.TestCase):
    def test_format_srt_timestamp(self):
        self.assertEqual(c2s.format_srt_timestamp(0.0), "00:00:00,000")
        self.assertEqual(c2s.format_srt_timestamp(75.25), "00:01:15,250")
        self.assertEqual(c2s.format_srt_timestamp(3600.0), "01:00:00,000")

    def test_parse_seconds(self):
        self.assertEqual(c2s.parse_seconds(12.5), 12.5)
        self.assertEqual(c2s.parse_seconds("00:02:10"), 130.0)
        self.assertEqual(c2s.parse_seconds("invalid", 1.0), 1.0)

    def test_extract_conversations(self):
        raw_list = '[{"id": "conv-1", "title": "Pod 1"}]'
        raw_wrapped = '{"conversations": [{"id": "conv-2", "title": "Pod 2"}]}'

        res1 = c2s.extract_conversations(raw_list)
        res2 = c2s.extract_conversations(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "conv-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "conv-2")

    def test_render_srt_cues_and_speakers(self):
        conv = {
            "id": "c-123",
            "transcript_segments": [
                {
                    "text": "Starting the podcast now.",
                    "speaker": "Host",
                    "start": 0.0,
                    "end": 3.0,
                },
                {
                    "text": "Happy to be here!",
                    "speaker": "Guest",
                    "start": 3.5,
                    "end": 5.5,
                },
            ],
        }
        srt = c2s.render_srt(conv)
        self.assertIn("1\n00:00:00,000 --> 00:00:03,000\n[Host] Starting the podcast now.", srt)
        self.assertIn("2\n00:00:03,500 --> 00:00:05,500\n[Guest] Happy to be here!", srt)

    def test_convert_conversations_to_srt_output_dir(self):
        conv1 = {"id": "c-1", "transcript": "Transcript 1"}
        conv2 = {"id": "c-2", "transcript": "Transcript 2"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "data.json"
            out_dir = tmp / "srt_out"

            f.write_text(json.dumps([conv1, conv2]), encoding="utf-8")
            count = c2s.convert_conversations_to_srt([f], output_dir=out_dir)

            self.assertEqual(count, 2)
            self.assertTrue((out_dir / "c-1.srt").exists())
            self.assertTrue((out_dir / "c-2.srt").exists())

            content = (out_dir / "c-1.srt").read_text(encoding="utf-8")
            self.assertIn("Transcript 1", content)


if __name__ == "__main__":
    unittest.main()
