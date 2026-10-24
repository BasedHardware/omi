"""Regression tests for the conversations to markdown exporter (#23485).

Pins the four failure paths reported in #23485:

* ``export_conversations(overwrite=True)`` silently discarded a conversation
  when two conversations in the same batch resolved to the same file name,
  because the batch-collision guard existed only on the ``overwrite=False``
  path.
* A non-string ``structured.category`` raised ``AttributeError`` while the
  neighbouring fields already coerced with ``str(...)``.
* A boolean speaker rendered as "Speaker False" (``isinstance(False, int)`` is
  true), and an integer speaker under ``speaker_id``, including speaker ``0``,
  was ignored.
* A multi-line transcript segment escaped its Markdown blockquote.

The exporter script is loaded dynamically, the same way the sibling example
tests load theirs, so this suite is hermetic: no network, no real API.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_markdown.py"
spec = importlib.util.spec_from_file_location("conversations_to_markdown", script_path)
c2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2m)


def conversation(conv_id: str, title: str, **overrides):
    """A minimal conversation that shares date, title and id prefix with any
    other conversation built the same way, so the base file name collides."""
    conv = {
        "id": conv_id,
        "started_at": "2026-05-04T10:00:00Z",
        "structured": {"title": title, "category": "general"},
    }
    conv.update(overrides)
    return conv


class TestOverwriteBatchCollisions(unittest.TestCase):
    """#23485 item 1: overwrite=True must not clobber a same-batch sibling."""

    def test_two_colliding_conversations_get_distinct_files_and_contents(self):
        first = conversation("12345678-1111-4abc-8def-000000000001", "Same Title")
        second = conversation("12345678-2222-4abc-8def-000000000002", "Same Title")
        first["structured"]["overview"] = "first conversation body"
        second["structured"]["overview"] = "second conversation body"

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            paths = c2m.export_conversations([first, second], out, overwrite=True)

            self.assertEqual(len(paths), 2, "both conversations must be exported")
            self.assertNotEqual(paths[0], paths[1], "colliding names must be disambiguated")
            self.assertEqual(len(set(paths)), 2)

            first_text = paths[0].read_text(encoding="utf-8")
            second_text = paths[1].read_text(encoding="utf-8")
            # Neither conversation may be lost.
            self.assertIn("first conversation body", first_text)
            self.assertIn("second conversation body", second_text)
            self.assertNotIn("second conversation body", first_text)
            self.assertNotIn("first conversation body", second_text)

    def test_overwrite_still_replaces_a_pre_existing_file(self):
        """Disambiguation applies to this batch only, so a file left by an
        earlier run is still replaced at its own name."""
        conv = conversation("12345678-3333-4abc-8def-000000000003", "Same Title")
        conv["structured"]["overview"] = "fresh body"

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            base = out / f"2026-05-04_same_title_12345678.md"
            out.mkdir(parents=True, exist_ok=True)
            base.write_text("stale body", encoding="utf-8")

            paths = c2m.export_conversations([conv], out, overwrite=True)

            self.assertEqual(paths, [base], "an earlier run's file must be replaced in place")
            self.assertIn("fresh body", base.read_text(encoding="utf-8"))
            self.assertNotIn("stale body", base.read_text(encoding="utf-8"))

    def test_non_overwrite_still_disambiguates(self):
        """The pre-existing overwrite=False behaviour must not regress."""
        first = conversation("12345678-4444-4abc-8def-000000000004", "Same Title")
        second = conversation("12345678-5555-4abc-8def-000000000005", "Same Title")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            paths = c2m.export_conversations([first, second], out, overwrite=False)
            self.assertEqual(len(set(paths)), 2)
            for path in paths:
                self.assertTrue(path.exists())


class TestNonStringCategory(unittest.TestCase):
    """#23485 item 2: a non-string category must not raise AttributeError."""

    def test_category_as_list_does_not_raise(self):
        conv = conversation("abc-1", "T", structured={"title": "T", "category": ["work", "family"]})
        text = c2m.conversation_to_markdown(conv)
        self.assertIn("category:", text)

    def test_category_as_int_does_not_raise(self):
        conv = conversation("abc-2", "T", structured={"title": "T", "category": 7})
        text = c2m.conversation_to_markdown(conv)
        self.assertIn("7", text)

    def test_category_as_dict_does_not_raise(self):
        conv = conversation("abc-3", "T", structured={"title": "T", "category": {"name": "work"}})
        text = c2m.conversation_to_markdown(conv)
        self.assertIn("category:", text)

    def test_string_category_is_slugged_as_before(self):
        conv = conversation(
            "abc-4", "T", structured={"title": "T", "category": "Team Meeting"}
        )
        text = c2m.conversation_to_markdown(conv)
        self.assertIn("team-meeting", text)


class TestSpeakerLabels(unittest.TestCase):
    """#23485 item 3: boolean, integer and named speakers all resolve."""

    def label(self, segment):
        return c2m.speaker_label(segment)

    def test_boolean_speaker_is_not_rendered_as_a_number(self):
        self.assertEqual(self.label({"speaker": False}), "Speaker")
        self.assertEqual(self.label({"speaker": True}), "Speaker")

    def test_integer_speaker_is_numbered(self):
        self.assertEqual(self.label({"speaker": 3}), "Speaker 3")

    def test_speaker_zero_is_a_real_speaker(self):
        self.assertEqual(self.label({"speaker_id": 0}), "Speaker 0")
        self.assertEqual(self.label({"speaker": 0}), "Speaker 0")

    def test_named_speaker_wins(self):
        self.assertEqual(self.label({"speaker": "Alice"}), "Alice")
        self.assertEqual(self.label({"speaker_name": "Bob"}), "Bob")

    def test_named_speaker_beats_a_bare_number(self):
        self.assertEqual(self.label({"speaker": "Alice", "speaker_id": 2}), "Alice")

    def test_empty_and_blank_names_fall_through(self):
        self.assertEqual(self.label({"speaker": "", "speaker_id": 1}), "Speaker 1")
        self.assertEqual(self.label({"speaker": "   ", "speaker_id": 1}), "Speaker 1")
        self.assertEqual(self.label({}), "Speaker")

    def test_false_speaker_falls_back_to_speaker_id(self):
        self.assertEqual(self.label({"speaker": False, "speaker_id": 4}), "Speaker 4")

    def test_rendered_transcript_uses_the_resolved_label(self):
        conv = conversation(
            "abc-5",
            "T",
            transcript_segments=[{"speaker_id": 0, "start": 0, "text": "hello"}],
        )
        text = c2m.conversation_to_markdown(conv)
        self.assertIn("Speaker 0", text)
        self.assertNotIn("Speaker False", text)


class TestMultilineTranscriptText(unittest.TestCase):
    """#23485 item 4: a multi-line segment must stay inside the blockquote."""

    def test_every_transcript_line_is_quoted(self):
        conv = conversation(
            "abc-6",
            "T",
            transcript_segments=[
                {"speaker": "Alice", "start": 0, "text": "first line\nsecond line"}
            ],
        )
        text = c2m.conversation_to_markdown(conv)
        blockquote_lines = [line for line in text.splitlines() if line.startswith(">")]
        self.assertTrue(blockquote_lines, "the transcript must be emitted as a blockquote")
        for line in text.splitlines():
            if "first line" in line or "second line" in line:
                self.assertTrue(
                    line.startswith(">"),
                    f"transcript text escaped the blockquote: {line!r}",
                )

    def test_windows_newlines_are_flattened(self):
        conv = conversation(
            "abc-7",
            "T",
            transcript_segments=[{"speaker": "A", "start": 0, "text": "one\r\ntwo\r\nthree"}],
        )
        text = c2m.conversation_to_markdown(conv)
        for fragment in ("one", "two", "three"):
            line = next(line for line in text.splitlines() if fragment in line)
            self.assertTrue(line.startswith(">"), line)

    def test_blank_line_runs_do_not_survive(self):
        conv = conversation(
            "abc-8",
            "T",
            transcript_segments=[{"speaker": "A", "start": 0, "text": "alpha\n\n\nbeta"}],
        )
        text = c2m.conversation_to_markdown(conv)
        line = next(line for line in text.splitlines() if "alpha" in line)
        self.assertIn("beta", line)
        self.assertNotIn("\n", line)


class TestSegmentsKeyFallback(unittest.TestCase):
    """#23485: an export may carry the transcript under ``segments``."""

    def test_segments_key_is_used_when_transcript_segments_is_absent(self):
        conv = conversation(
            "abc-9",
            "T",
            segments=[{"speaker": "Alice", "start": 5, "text": "from the segments key"}],
        )
        conv.pop("transcript_segments", None)
        text = c2m.conversation_to_markdown(conv)
        self.assertIn("from the segments key", text)
        self.assertIn("00:05", text)

    def test_transcript_segments_still_wins_when_both_are_present(self):
        conv = conversation(
            "abc-10",
            "T",
            transcript_segments=[{"speaker": "A", "start": 0, "text": "preferred"}],
            segments=[{"speaker": "B", "start": 0, "text": "ignored"}],
        )
        text = c2m.conversation_to_markdown(conv)
        self.assertIn("preferred", text)
        self.assertNotIn("ignored", text)


if __name__ == "__main__":
    unittest.main()