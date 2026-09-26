"""Tests for conversations_to_digest recipe.

Covers:
- Timestamp parsing and duration formatting
- Daily activity grouping
- Category share percentages
- Ranking of longest sessions
- Deduplication across multiple pages
- Error handling on invalid records
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load conversations_to_digest example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_digest.py"
spec = importlib.util.spec_from_file_location("conversations_to_digest", script_path)
c2d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2d)

convert_paths_to_digest = c2d.convert_paths_to_digest
generate_digest = c2d.generate_digest
format_duration = c2d.format_duration


SAMPLE_CONVERSATIONS = [
    {
        "id": "conv_1",
        "started_at": "2026-09-20T09:00:00Z",
        "finished_at": "2026-09-20T10:30:00Z",  # 1h 30m
        "structured": {
            "title": "Strategy Workshop",
            "category": "work",
        },
    },
    {
        "id": "conv_2",
        "started_at": "2026-09-20T14:00:00Z",
        "finished_at": "2026-09-20T14:15:00Z",  # 15m
        "structured": {
            "title": "Quick Sync",
            "category": "work",
        },
    },
    {
        "id": "conv_3",
        "started_at": "2026-09-19T11:00:00Z",
        "finished_at": "2026-09-19T11:45:00Z",  # 45m
        "structured": {
            "title": "Spanish Lesson",
            "category": "learning",
        },
    },
]


class TestConversationsToDigest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_format_duration(self):
        self.assertEqual(format_duration(90), "1m 30s")
        self.assertEqual(format_duration(3600), "1h 00m")
        self.assertEqual(format_duration(5400), "1h 30m")

    def test_digest_sections_and_metrics(self):
        digest = generate_digest(SAMPLE_CONVERSATIONS)
        self.assertIn("# 📊 Conversation Digest", digest)
        self.assertIn("3 conversations", digest)
        self.assertIn("2026-09-20", digest)
        self.assertIn("2026-09-19", digest)

        # Category breakdown: 2 work out of 3 = 66.7%, 1 learning = 33.3%
        self.assertIn("`work`", digest)
        self.assertIn("66.7%", digest)
        self.assertIn("`learning`", digest)
        self.assertIn("33.3%", digest)

        # Longest sessions
        self.assertIn("Strategy Workshop", digest)
        self.assertIn("1h 30m", digest)

    def test_deduplication(self):
        duplicated = [SAMPLE_CONVERSATIONS[0], SAMPLE_CONVERSATIONS[0]]
        digest = generate_digest(duplicated)
        self.assertIn("1 conversations", digest)

    def test_daily_activity_real_duration(self):
        digest = generate_digest(SAMPLE_CONVERSATIONS)
        # 2026-09-20: 1h 30m (90m) + 15m = 1h 45m
        self.assertIn("| **2026-09-20** | 2 | ~1h 45m |", digest)
        # 2026-09-19: 45m = 45m 00s
        self.assertIn("| **2026-09-19** | 1 | ~45m 00s |", digest)

    def test_deduplication_returns_deduped_count(self):
        duplicated = [SAMPLE_CONVERSATIONS[0], SAMPLE_CONVERSATIONS[0]]
        json_file = self.dir_path / "dup.json"
        json_file.write_text(json.dumps(duplicated), encoding="utf-8")
        out_digest = self.dir_path / "dup.md"

        count = convert_paths_to_digest([json_file], out_digest)
        self.assertEqual(count, 1)

    def test_convert_to_file(self):
        json_file = self.dir_path / "conversations.json"
        json_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")
        out_digest = self.dir_path / "digest.md"

        count = convert_paths_to_digest([json_file], out_digest)
        self.assertEqual(count, 3)
        self.assertTrue(out_digest.exists())
        content = out_digest.read_text(encoding="utf-8")
        self.assertIn("Conversation Digest", content)

    def test_overwrite_refusal_and_force(self):
        json_file = self.dir_path / "conversations.json"
        json_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")
        out_digest = self.dir_path / "digest.md"

        # First write creates the file
        convert_paths_to_digest([json_file], out_digest)
        self.assertTrue(out_digest.exists())

        # Second write without force must raise FileExistsError
        with self.assertRaises(FileExistsError):
            convert_paths_to_digest([json_file], out_digest, force=False)

        # Overwrite with force=True must succeed
        count = convert_paths_to_digest([json_file], out_digest, force=True)
        self.assertEqual(count, 3)

    def test_wrapped_conversations_envelope(self):
        envelope = {"conversations": SAMPLE_CONVERSATIONS}
        json_file = self.dir_path / "envelope.json"
        json_file.write_text(json.dumps(envelope), encoding="utf-8")
        out_digest = self.dir_path / "env_digest.md"

        count = convert_paths_to_digest([json_file], out_digest)
        self.assertEqual(count, 3)
        self.assertTrue(out_digest.exists())

    def test_stdin_input(self):
        import io
        import sys
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(json.dumps(SAMPLE_CONVERSATIONS))
            out_digest = self.dir_path / "stdin_digest.md"
            count = convert_paths_to_digest(["-"], out_digest)
            self.assertEqual(count, 3)
            self.assertTrue(out_digest.exists())
        finally:
            sys.stdin = old_stdin

    def test_missing_id_raises_value_error(self):
        invalid = [{"title": "No ID here"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_paths_to_digest([json_file])
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
