"""Tests for goals to Logseq-format Markdown converter.

Pins progress computation, active/completed hashtag selection, escaping of
untrusted `[[`/`]]`/`#` in the title, block properties, and atomic-write /
overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_logseq.py"
spec = importlib.util.spec_from_file_location("goals_to_logseq", script_path)
g2l = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2l)


class TestGoalsToLogseq(unittest.TestCase):
    def setUp(self):
        self.sample_goals = [
            {
                "id": "g1",
                "title": "Read #20 [[books]]",
                "current_value": 12,
                "target_value": 20,
                "min_value": 0,
                "max_value": 20,
                "is_active": True,
            },
            {"id": "g2", "title": "Meditate", "current_value": 1, "target_value": 1, "is_active": False},
        ]

    def test_progress_pct(self):
        self.assertAlmostEqual(g2l.progress_pct(12, 20, 0, 20), 0.6)
        self.assertAlmostEqual(g2l.progress_pct(5, 0, 0, 10), 0.5)
        self.assertIsNone(g2l.progress_pct("n/a", None, None, None))

    def test_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            g2l.convert(json_file, md_file)
            content = md_file.read_text(encoding="utf-8")

            self.assertIn("type:: omi-goals", content)
            self.assertIn("count:: 2", content)
            self.assertIn("#active", content)
            self.assertIn("#completed", content)
            self.assertIn("progress:: 60%", content)
            self.assertIn("omi-id:: g1", content)
            # Untrusted title content must be escaped.
            self.assertIn("\\#20 \\[\\[books\\]\\]", content)

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps({"goals": self.sample_goals}), encoding="utf-8")

            g2l.convert(json_file, md_file)
            self.assertIn("count:: 2", md_file.read_text(encoding="utf-8"))

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(["nope"]), encoding="utf-8")

            with self.assertRaises(ValueError):
                g2l.convert(json_file, md_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")
            md_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2l.convert(json_file, md_file)


if __name__ == "__main__":
    unittest.main()
