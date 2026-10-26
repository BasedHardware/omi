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

    def test_is_completed_normalization(self):
        """Validates completion status normalization for loose typing."""
        # Native booleans
        self.assertTrue(c2m.is_completed(True))
        self.assertFalse(c2m.is_completed(False))

        # Numbers
        self.assertTrue(c2m.is_completed(1))
        self.assertTrue(c2m.is_completed(-1))
        self.assertFalse(c2m.is_completed(0))

        # Truthy loose strings
        for word in ("true", "TRUE", "yes", "YES", "1", "done", "DONE", "completed"):
            self.assertTrue(c2m.is_completed(word), f"Expected {word} to be truthy")

        # Falsy strings and arbitrary non-completion values
        for word in ("false", "FALSE", "no", "NO", "0", "", "   ", "pending", "in-progress", None, [], {}):
            self.assertFalse(c2m.is_completed(word), f"Expected {word} to be falsy")

    def test_action_items_completion_rendering(self):
        """Action items with string falsy values must not be rendered as completed checkboxes."""
        conv = {
            "id": "conv-test-items",
            "started_at": "2026-09-20T10:00:00Z",
            "structured": {
                "title": "Action Items Review",
                "action_items": [
                    {"description": "Open string false", "completed": "false"},
                    {"description": "Open string no", "completed": "no"},
                    {"description": "Open string zero", "completed": "0"},
                    {"description": "Open boolean false", "completed": False},
                    {"description": "Done string true", "completed": "true"},
                    {"description": "Done string yes", "completed": "yes"},
                    {"description": "Done string one", "completed": "1"},
                    {"description": "Done boolean true", "completed": True},
                    {"description": "", "completed": False},
                    "Bare string open task",
                ],
            },
        }
        md = c2m.conversation_to_markdown(conv)

        self.assertIn("- [ ] Open string false", md)
        self.assertIn("- [ ] Open string no", md)
        self.assertIn("- [ ] Open string zero", md)
        self.assertIn("- [ ] Open boolean false", md)
        self.assertIn("- [x] Done string true", md)
        self.assertIn("- [x] Done string yes", md)
        self.assertIn("- [x] Done string one", md)
        self.assertIn("- [x] Done boolean true", md)
        self.assertIn("- [ ] Untitled action item", md)
        self.assertIn("- [ ] Bare string open task", md)

    def test_extract_conversations_unwrapping(self):
        """Verify bare arrays, wrapped dictionaries, and empty wrappers unwrap properly."""
        conv1 = {"id": "c1", "structured": {"title": "Conv 1"}}
        conv2 = {"id": "c2", "structured": {"title": "Conv 2"}}

        # Bare array
        self.assertEqual(c2m.extract_conversations([conv1, conv2]), [conv1, conv2])
        self.assertEqual(c2m.extract_conversations([]), [])

        # Wrapped dictionary envelopes
        self.assertEqual(c2m.extract_conversations({"conversations": [conv1, conv2]}), [conv1, conv2])
        self.assertEqual(c2m.extract_conversations({"items": [conv1]}), [conv1])
        self.assertEqual(c2m.extract_conversations({"data": [conv2]}), [conv2])

        # Empty wrapped dictionary envelopes
        self.assertEqual(c2m.extract_conversations({"conversations": []}), [])
        self.assertEqual(c2m.extract_conversations({"items": []}), [])
        self.assertEqual(c2m.extract_conversations({"data": []}), [])

        # Single conversation dictionary
        self.assertEqual(c2m.extract_conversations(conv1), [conv1])

    def test_extract_conversations_invalid_payload_guard(self):
        """Invalid dict payloads (error responses, unrelated dicts, empty dicts) return empty list."""
        self.assertEqual(c2m.extract_conversations({}), [])
        self.assertEqual(c2m.extract_conversations({"detail": "Not authenticated"}), [])
        self.assertEqual(c2m.extract_conversations({"status": "error", "message": "unauthorized"}), [])
        self.assertEqual(c2m.extract_conversations({"error": {"code": 404}}), [])

        # Single conversation with various valid fields unwraps properly
        self.assertEqual(c2m.extract_conversations({"id": "c1"}), [{"id": "c1"}])
        self.assertEqual(c2m.extract_conversations({"transcript_segments": []}), [{"transcript_segments": []}])
        self.assertEqual(
            c2m.extract_conversations({"structured": {"title": "Test"}}), [{"structured": {"title": "Test"}}]
        )
        self.assertEqual(
            c2m.extract_conversations({"started_at": "2026-09-28T00:00:00Z"}), [{"started_at": "2026-09-28T00:00:00Z"}]
        )
        self.assertEqual(
            c2m.extract_conversations({"created_at": "2026-09-28T00:00:00Z"}), [{"created_at": "2026-09-28T00:00:00Z"}]
        )

    def test_empty_conversations_export_produces_no_files(self):
        """Exporting an empty list must create 0 files and leave the directory clean."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "empty_out"
            exported = c2m.export_conversations([], output_dir=out_dir)

            self.assertEqual(len(exported), 0)
            self.assertEqual(list(out_dir.glob("*.md")), [])

    def test_strip_surrogates_keeps_valid_text(self):
        """Only unpaired surrogates are dropped; all other text is preserved."""
        self.assertEqual(c2m.strip_surrogates("plain"), "plain")
        self.assertEqual(c2m.strip_surrogates("中文 ok"), "中文 ok")
        self.assertEqual(c2m.strip_surrogates("emoji \U0001f600 ok"), "emoji \U0001f600 ok")
        self.assertEqual(c2m.strip_surrogates("a\ud800b"), "ab")
        self.assertEqual(c2m.strip_surrogates("\udfff"), "")

    def test_rendered_note_is_always_utf8_encodable(self):
        """Regression: the rendered note must always be writable as UTF-8.

        json.loads accepts an escaped lone surrogate (e.g. "\\ud800") from a
        malformed export. It reached the rendered note verbatim, so
        `filepath.write_text(..., encoding="utf-8")` raised UnicodeEncodeError and
        the whole conversation was lost. Every field that can carry free text is
        exercised here.
        """
        conv = {
            "id": "conv_\udfff",
            "started_at": "2026-09-17T12:00:00Z",
            "structured": {
                "title": "bad \ud800 title",
                "overview": "sum\udfffmary",
                # read from structured.action_items, not a top-level key
                "action_items": [{"description": "do \ud800 it", "completed": False}],
            },
            "transcript_segments": [{"text": "x\ud800y", "speaker": "SPEAKER_00"}],
        }
        md = c2m.conversation_to_markdown(conv)
        # Must not raise: this is the exact call that failed before the fix.
        md.encode("utf-8")

    def test_frontmatter_has_no_surrogate_escapes(self):
        """Escaped surrogates are forbidden YAML code points and break note metadata.

        json.dumps would render a lone surrogate as the \\uD800 escape, which is
        valid JSON but not valid YAML, so Obsidian/Notion fail to parse the
        frontmatter. The scalars must be sanitized before escaping.
        """
        conv = {
            "id": "conv_\ud800",
            "started_at": "2026-09-17T12:00:00Z\ud800",
            "structured": {"title": "bad \ud800 title", "category": "work\udfff"},
            "source": "omi\udfff",
        }
        md = c2m.conversation_to_markdown(conv)
        frontmatter = md.split("---")[1]
        self.assertNotIn("\\ud800", frontmatter.lower())
        self.assertNotIn("\\udfff", frontmatter.lower())
        self.assertIn('title: "bad  title"', frontmatter)
        self.assertIn('date: "2026-09-17T12:00:00Z"', frontmatter)
        self.assertIn('source: "omi"', frontmatter)

    def test_lone_surrogate_in_transcript_does_not_abort_export(self):
        """The conversation still exports, minus only the unencodable code point."""
        conv = {
            "id": "12345678-3333-4333-8333-333333333333",
            "started_at": "2026-09-17T12:00:00Z",
            "structured": {"title": "Sync", "overview": "ok"},
            "transcript_segments": [
                {"text": "hello \ud800 world", "speaker": "SPEAKER_00", "start": 1.0},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            exported = c2m.export_conversations([conv], output_dir=out_dir)

            self.assertEqual(len(exported), 1)
            text = exported[0].read_text(encoding="utf-8")
            self.assertIn("hello  world", text)

    def test_same_batch_collision_disambiguation_when_overwrite_true(self):
        conv1 = {
            "id": "12345678-1111-4111-8111-111111111111",
            "started_at": "2026-09-17T12:00:00Z",
            "structured": {"title": "Team Standup", "overview": "first sync"},
        }
        conv2 = {
            "id": "12345678-2222-4222-8222-222222222222",
            "started_at": "2026-09-17T12:00:00Z",
            "structured": {"title": "Team Standup", "overview": "second sync"},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            exported = c2m.export_conversations([conv1, conv2], output_dir=out_dir, overwrite=True)
            self.assertEqual(len(exported), 2)
            self.assertNotEqual(exported[0], exported[1])
            self.assertTrue(exported[0].exists())
            self.assertTrue(exported[1].exists())
            self.assertIn("first sync", exported[0].read_text(encoding="utf-8"))
            self.assertIn("second sync", exported[1].read_text(encoding="utf-8"))

    def test_category_none_and_boolean_speaker_fallback(self):
        conv = {
            "id": "conv-fallback-test",
            "started_at": "2026-09-17T12:00:00Z",
            "structured": {"title": "Test", "category": None},
            "transcript_segments": [
                {"text": "Hello world", "speaker": False, "speaker_id": 0, "start": 0.0},
            ],
        }
        md = c2m.conversation_to_markdown(conv)
        self.assertIn("Speaker 0", md)
        self.assertNotIn("Speaker False", md)

    def test_multiline_transcript_text_flattening(self):
        conv = {
            "id": "conv-multiline-test",
            "started_at": "2026-09-17T12:00:00Z",
            "structured": {"title": "Multiline Test"},
            "transcript_segments": [
                {"text": "line one\nline two\nline three", "speaker": "Alice", "start": 1.5},
            ],
        }
        md = c2m.conversation_to_markdown(conv)
        self.assertIn("> **[00:01] Alice:** line one line two line three", md)

    def test_same_batch_collision_replaces_stale_collided_file_when_overwrite_true(self):
        """When overwrite=True, a second item disambiguating to _2.md cleanly overwrites a stale _2.md from a prior run."""
        conv1 = {
            "id": "12345678-1111-4111-8111-111111111111",
            "started_at": "2026-09-17T12:00:00Z",
            "structured": {"title": "Team Standup", "overview": "batch2 first"},
        }
        conv2 = {
            "id": "12345678-2222-4222-8222-222222222222",
            "started_at": "2026-09-17T12:00:00Z",
            "structured": {"title": "Team Standup", "overview": "batch2 second"},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            # Pre-create a stale _2.md file from a prior run
            stale_second_file = out_dir / "2026-09-17_team_standup_12345678_2.md"
            stale_second_file.write_text("stale content from prior run", encoding="utf-8")

            exported = c2m.export_conversations([conv1, conv2], output_dir=out_dir, overwrite=True)
            self.assertEqual(len(exported), 2)
            self.assertEqual(exported[1], stale_second_file)
            second_content = exported[1].read_text(encoding="utf-8")
            self.assertIn("batch2 second", second_content)
            self.assertNotIn("stale content from prior run", second_content)


if __name__ == "__main__":
    unittest.main()
