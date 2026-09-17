"""Tests for conversation to markdown exporter (#14277).

Ensures collisions between identical date/title/short_id pairs and existing disk files
are disambiguated cleanly without data loss.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

# Load conversations_to_markdown example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_markdown.py"
spec = importlib.util.spec_from_file_location("conversations_to_markdown", script_path)
c2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2m)


class TestConversationsToMarkdown(unittest.TestCase):
    def test_distinct_conversations_with_same_id_prefix_do_not_overwrite(self):
        conv1 = {
            "id": "12345678-1111-4111-8111-111111111111",
            "started_at": "2026-09-17T10:00:00Z",
            "structured": {"title": "Meeting", "overview": "First meeting content"},
        }
        conv2 = {
            "id": "12345678-2222-4222-8222-222222222222",
            "started_at": "2026-09-17T11:00:00Z",
            "structured": {"title": "Meeting", "overview": "Second meeting content"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            exported = c2m.export_conversations([conv1, conv2], output_dir=out_dir)

            self.assertEqual(len(exported), 2)
            file1 = out_dir / "2026-09-17_meeting_12345678.md"
            file2 = out_dir / "2026-09-17_meeting_12345678_2.md"

            self.assertTrue(file1.exists(), f"Expected {file1} to exist")
            self.assertTrue(file2.exists(), f"Expected {file2} to exist")

            content1 = file1.read_text(encoding="utf-8")
            content2 = file2.read_text(encoding="utf-8")

            self.assertIn("First meeting content", content1)
            self.assertIn("Second meeting content", content2)
            self.assertIn("12345678-1111-4111-8111-111111111111", content1)
            self.assertIn("12345678-2222-4222-8222-222222222222", content2)

    def test_existing_disk_file_is_not_overwritten_by_default(self):
        conv = {
            "id": "12345678-3333-4333-8333-333333333333",
            "started_at": "2026-09-17T10:00:00Z",
            "structured": {"title": "Meeting", "overview": "New incoming note"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            existing_file = out_dir / "2026-09-17_meeting_12345678.md"
            existing_file.write_text("Pre-existing vault note that must be preserved", encoding="utf-8")

            exported = c2m.export_conversations([conv], output_dir=out_dir, overwrite=False)

            self.assertEqual(len(exported), 1)
            disambiguated_file = out_dir / "2026-09-17_meeting_12345678_2.md"

            self.assertTrue(disambiguated_file.exists())
            self.assertEqual(
                existing_file.read_text(encoding="utf-8"),
                "Pre-existing vault note that must be preserved",
            )
            self.assertIn("New incoming note", disambiguated_file.read_text(encoding="utf-8"))

    def test_overwrite_flag_allows_replacing_existing_file(self):
        conv = {
            "id": "12345678-4444-4444-8444-444444444444",
            "started_at": "2026-09-17T10:00:00Z",
            "structured": {"title": "Meeting", "overview": "Updated replacement note"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            target_file = out_dir / "2026-09-17_meeting_12345678.md"
            target_file.write_text("Old obsolete note", encoding="utf-8")

            exported = c2m.export_conversations([conv], output_dir=out_dir, overwrite=True)

            self.assertEqual(len(exported), 1)
            self.assertEqual(exported[0], target_file)
            self.assertIn("Updated replacement note", target_file.read_text(encoding="utf-8"))

    def test_slugify_and_undated_fallback(self):
        conv = {
            "id": "abc-123",
            "structured": {"title": "Hello / World! @ 2026"},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            exported = c2m.export_conversations([conv], output_dir=out_dir)

            self.assertEqual(len(exported), 1)
            expected_file = out_dir / "undated_hello_world_2026_abc-123.md"
            self.assertTrue(expected_file.exists())


if __name__ == "__main__":
    unittest.main()
