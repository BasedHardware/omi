"""Tests for exclusive-creation safety in the conversations Markdown export (#21168).

Pins that ``overwrite=False`` never truncates a file that appears between the
existence check and the write, and that normal, duplicate and overwrite=True
paths keep their previous behaviour.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

script_path = (
    Path(__file__).resolve().parent.parent / "examples" / "conversations_to_markdown.py"
)
spec = importlib.util.spec_from_file_location("conversations_to_markdown", script_path)
c2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2m)


def _conv(idx: int = 1, title: str = "Race", day: int = 1) -> dict:
    return {
        "id": f"id{idx}",
        "started_at": f"2026-01-0{day}T00:00:00Z",
        "structured": {"title": title},
        "transcript_segments": [],
    }


class TestConcurrentClobber(unittest.TestCase):
    def test_existing_file_is_never_truncated(self):
        """A file created between the check and the write must survive."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            target = out / "2026-01-01_race_id1.md"
            target.write_text("PRECIOUS USER NOTE\n", encoding="utf-8")

            # Model the race deterministically: the existence check reports the
            # path as free while it is in fact already taken.
            real_exists = Path.exists
            Path.exists = lambda self: False
            try:
                paths = c2m.export_conversations([_conv()], out, overwrite=False)
            finally:
                Path.exists = real_exists

            self.assertEqual(target.read_text(encoding="utf-8"), "PRECIOUS USER NOTE\n")
            self.assertEqual(len(paths), 1)
            self.assertNotEqual(paths[0].resolve(), target.resolve())

    def test_distinct_conversations_get_distinct_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = c2m.export_conversations(
                [_conv(1, "A", 2), _conv(2, "B", 3)], Path(tmp), overwrite=False
            )
            self.assertEqual(len(set(p.name for p in paths)), 2)
            self.assertTrue(all(p.exists() for p in paths))

    def test_duplicate_names_in_one_batch_disambiguate(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = c2m.export_conversations(
                [_conv(1, "Same", 2), _conv(1, "Same", 2)], Path(tmp), overwrite=False
            )
            self.assertEqual(len(paths), 2)
            self.assertEqual(len(set(p.name for p in paths)), 2)

    def test_overwrite_true_still_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            target = out / "2026-01-02_t_id1.md"
            target.write_text("OLD", encoding="utf-8")
            paths = c2m.export_conversations([_conv(1, "T", 2)], out, overwrite=True)
            self.assertEqual(paths[0].resolve(), target.resolve())
            self.assertNotEqual(target.read_text(encoding="utf-8"), "OLD")

    def test_many_identical_conversations_terminate(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = c2m.export_conversations(
                [_conv(1, "X", 2)] * 5, Path(tmp), overwrite=False
            )
            self.assertEqual(len(paths), 5)
            self.assertEqual(len(set(p.name for p in paths)), 5)


if __name__ == "__main__":
    unittest.main()
