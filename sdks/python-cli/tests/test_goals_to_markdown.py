"""Hermetic tests for examples/goals_to_markdown.py (#19369).

Covers: ASCII progress bars, frontmatter, envelope unwrapping, directory
splitting, slugging, and path-traversal/overwrite safety.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import goals_to_markdown as m  # noqa: E402

GOAL = {
    "id": "g1",
    "title": "Drink water",
    "category": "health",
    "goal_type": "numeric",
    "current_value": 6.0,
    "target_value": 10.0,
    "unit": "glasses",
    "is_active": True,
    "created_at": "2026-10-01T00:00:00Z",
}


class TestProgressBar(unittest.TestCase):
    def test_bar_renders(self):
        self.assertEqual(m.progress_bar(0.6), "██████░░░░ 60%")

    def test_full_bar(self):
        self.assertEqual(m.progress_bar(1.0), "██████████ 100%")

    def test_qualitative_no_bar(self):
        self.assertEqual(m.progress_bar(None), "")
        self.assertIsNone(m.progress_ratio({"current_value": 1, "target_value": 0}))


class TestRendering(unittest.TestCase):
    def test_frontmatter_and_fields(self):
        md = m.goal_to_markdown(GOAL)
        self.assertIn("---", md)
        self.assertIn('goal_type: "numeric"', md)
        self.assertIn("# Drink water", md)
        self.assertIn("**Progress:** 6 / 10 glasses", md)
        self.assertIn("**Status:** active", md)
        self.assertIn("**Omi ID:** `g1`", md)

    def test_inactive_status(self):
        md = m.goal_to_markdown({**GOAL, "is_active": False})
        self.assertIn("**Status:** inactive", md)

    def test_missing_title_fallback(self):
        md = m.goal_to_markdown({"id": "g"})
        self.assertIn("# (no title)", md)

    def test_loose_types_coerced(self):
        md = m.goal_to_markdown({"id": "g", "title": {"odd": 1}, "category": 42})
        self.assertIn("# ", md)  # doesn't crash


class TestSlug(unittest.TestCase):
    def test_slug_sanitizes(self):
        self.assertEqual(m.slugify("Drink Water!!"), "drink_water")

    def test_slug_no_traversal(self):
        self.assertNotIn("/", m.slugify("../../etc"))
        self.assertNotIn("..", m.slugify("../../etc"))


class TestConvert(unittest.TestCase):
    def test_writes_notes(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text(json.dumps({"goals": [GOAL, {**GOAL, "id": "g2", "title": "Read"}]}))
            out = str(Path(td) / "notes")
            n = m.convert(str(src), out)
            self.assertEqual(n, 2)
            self.assertTrue((Path(out) / "drink_water.md").exists())
            self.assertTrue((Path(out) / "read.md").exists())

    def test_envelope_and_bare(self):
        for payload in ({"goals": [GOAL]}, {"items": [GOAL]}, {"data": [GOAL]}, [GOAL], GOAL):
            self.assertEqual(len(m.extract_goals(payload)), 1)

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text(json.dumps([GOAL]))
            with self.assertRaises(ValueError):
                m.convert(str(src), "../escape")

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text(json.dumps([GOAL]))
            out = Path(td) / "notes"
            out.mkdir()
            (out / "drink_water.md").write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert(str(src), str(out))

    def test_duplicate_slugs_deduped(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text(json.dumps({"goals": [{"id": "a", "title": "Same"}, {"id": "b", "title": "Same"}]}))
            out = str(Path(td) / "n")
            n = m.convert(str(src), out)
            self.assertEqual(n, 2)
            self.assertTrue((Path(out) / "same.md").exists())
            self.assertTrue((Path(out) / "same_2.md").exists())


if __name__ == "__main__":
    unittest.main()
