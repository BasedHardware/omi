import json
import tempfile
import unittest
from datetime import timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_markdown import (
    export_markdown,
    format_goal_line,
    generate_markdown,
    merge_goals,
)


class TestGoalsToMarkdown(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_format_goal_line(self):
        active_goal = {
            "id": "g1",
            "title": "Meditate daily",
            "is_active": True,
            "goal_type": "scale",
            "current_value": 7,
            "target_value": 10,
            "unit": "days",
        }
        line = format_goal_line(active_goal)
        self.assertTrue(line.startswith("- [ ] **Meditate daily**"))
        self.assertIn("progress: 7/10 days (70%)", line)
        self.assertIn("#scale", line)

        done_goal = {
            "id": "g2",
            "title": "Complete course",
            "is_active": False,
            "goal_type": "boolean",
        }
        done_line = format_goal_line(done_goal)
        self.assertTrue(done_line.startswith("- [x] **Complete course**"))
        self.assertIn("#boolean", done_line)

    def test_generate_markdown_structure(self):
        goals = [
            {"id": "g1", "title": "Run marathon", "is_active": True, "goal_type": "numeric", "current_value": 20, "target_value": 42, "unit": "km"},
            {"id": "g2", "title": "Write book", "is_active": False, "goal_type": "qualitative"}
        ]
        md = generate_markdown(goals, timezone.utc)
        self.assertIn("---", md)
        self.assertIn("active_goals: 1", md)
        self.assertIn("completed_goals: 1", md)
        self.assertIn("## Active Goals", md)
        self.assertIn("Run marathon", md)
        self.assertIn("## Completed / Inactive Goals", md)
        self.assertIn("Write book", md)

    def test_export_markdown_exclusive_creation(self):
        goals = [{"id": "g1", "title": "Save money", "is_active": True}]
        in_file = self.dir_path / "goals.json"
        in_file.write_text(json.dumps(goals), encoding="utf-8")
        out_file = self.dir_path / "vault_goals.md"

        export_markdown([str(in_file)], out_file, timezone.utc)
        self.assertTrue(out_file.exists())
        self.assertIn("Save money", out_file.read_text(encoding="utf-8"))

        # Refuse overwrite
        with self.assertRaises(FileExistsError):
            export_markdown([str(in_file)], out_file, timezone.utc)


if __name__ == "__main__":
    unittest.main()
