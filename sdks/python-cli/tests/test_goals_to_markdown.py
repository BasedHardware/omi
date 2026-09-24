"""Tests for goals_to_markdown recipe.

Covers:
- Progress bar calculation and rendering
- Status badge determination (active, completed, inactive)
- Note generation with valid YAML frontmatter
- Dashboard aggregation and section grouping
- Vault directory output (--output-dir)
- Active-only filtering
- Error handling on invalid JSON or missing id
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load goals_to_markdown example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_markdown.py"
spec = importlib.util.spec_from_file_location("goals_to_markdown", script_path)
g2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2m)

convert_goals_to_markdown = g2m.convert_goals_to_markdown
format_progress_bar = g2m.format_progress_bar
get_status_badge = g2m.get_status_badge
goal_to_markdown_note = g2m.goal_to_markdown_note
generate_dashboard = g2m.generate_dashboard


SAMPLE_GOALS = [
    {
        "id": "goal_1",
        "title": "Read 20 books",
        "goal_type": "learning",
        "current_value": 15,
        "target_value": 20,
        "unit": "books",
        "is_active": True,
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-20T10:00:00Z",
    },
    {
        "id": "goal_2",
        "title": "Run marathon",
        "goal_type": "fitness",
        "current_value": 42.2,
        "target_value": 42.2,
        "unit": "km",
        "is_active": True,
        "created_at": "2026-08-01T08:00:00Z",
    },
    {
        "id": "goal_3",
        "title": "Old habit",
        "goal_type": "habit",
        "current_value": 2,
        "target_value": 10,
        "is_active": False,
    },
]


class TestGoalsToMarkdown(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_format_progress_bar(self):
        self.assertIn("75.0%", format_progress_bar(15, 20))
        self.assertIn("100.0%", format_progress_bar(10, 10))
        self.assertIn("0.0%", format_progress_bar(0, 10))
        self.assertIn("0.0%", format_progress_bar(None, 10))
        self.assertIn("0.0%", format_progress_bar(5, 0))

    def test_status_badge(self):
        self.assertEqual(get_status_badge(SAMPLE_GOALS[0]), "🟢 Active")
        self.assertEqual(get_status_badge(SAMPLE_GOALS[1]), "🏁 Completed")
        self.assertEqual(get_status_badge(SAMPLE_GOALS[2]), "⚪ Inactive")

    def test_goal_to_markdown_note(self):
        note = goal_to_markdown_note(SAMPLE_GOALS[0])
        self.assertTrue(note.startswith("---\n"))
        self.assertIn('id: "goal_1"', note)
        self.assertIn('title: "Read 20 books"', note)
        self.assertIn("# Read 20 books", note)
        self.assertIn("**Progress**:", note)
        self.assertIn("15 / 20 books", note)

    def test_generate_dashboard(self):
        dashboard = generate_dashboard(SAMPLE_GOALS)
        self.assertIn("# 🎯 Goals Dashboard", dashboard)
        self.assertIn("Total: **3**", dashboard)
        self.assertIn("Active: **1**", dashboard)
        self.assertIn("Completed: **1**", dashboard)
        self.assertIn("Inactive: **1**", dashboard)
        self.assertIn("Read 20 books", dashboard)
        self.assertIn("Run marathon", dashboard)

    def test_convert_to_file(self):
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(SAMPLE_GOALS), encoding="utf-8")
        out_file = self.dir_path / "Goals.md"

        count = convert_goals_to_markdown([json_file], output_dest=out_file)
        self.assertEqual(count, 3)
        self.assertTrue(out_file.exists())
        content = out_file.read_text(encoding="utf-8")
        self.assertIn("🎯 Goals Dashboard", content)

    def test_convert_to_output_dir(self):
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(SAMPLE_GOALS), encoding="utf-8")
        out_dir = self.dir_path / "vault"

        count = convert_goals_to_markdown([json_file], output_dir=out_dir)
        self.assertEqual(count, 3)
        created_files = list(out_dir.glob("*.md"))
        self.assertEqual(len(created_files), 3)

    def test_active_only_filter(self):
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(SAMPLE_GOALS), encoding="utf-8")
        out_file = self.dir_path / "ActiveGoals.md"

        count = convert_goals_to_markdown([json_file], output_dest=out_file, active_only=True)
        self.assertEqual(count, 1)  # Only goal_1 is active (goal_2 is completed, goal_3 inactive)

    def test_missing_id_raises_value_error(self):
        invalid = [{"title": "No ID goal"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_goals_to_markdown([json_file])
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
