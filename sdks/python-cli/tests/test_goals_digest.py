"""Tests for goal list to Markdown digest exporter."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_digest.py"
spec = importlib.util.spec_from_file_location("goals_digest", script_path)
gd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gd)


class TestGoalsDigest(unittest.TestCase):
    def test_generate_digest_and_kpis(self):
        sample_goals = [
            {
                "id": "g1",
                "title": "Run marathon",
                "goal_type": "fitness",
                "current_value": 42.2,
                "target_value": 42.2,
                "unit": "km",
                "is_active": True,
            },
            {
                "id": "g2",
                "title": "Save funds",
                "goal_type": "finance",
                "current_value": 500,
                "target_value": 1000,
                "unit": "USD",
                "is_active": True,
            },
            {
                "id": "g3",
                "title": "Old goal",
                "goal_type": "fitness",
                "current_value": 10,
                "target_value": 20,
                "unit": "workouts",
                "is_active": False,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "page1.json"
            f2 = Path(tmp_dir) / "page2.json"
            out = Path(tmp_dir) / "digest.md"

            # Duplicate g1 in f2 to verify deduplication
            f1.write_text(json.dumps([sample_goals[0], sample_goals[1]]), encoding="utf-8")
            f2.write_text(json.dumps([sample_goals[0], sample_goals[2]]), encoding="utf-8")

            gd.convert([str(f1), str(f2)], str(out))
            self.assertTrue(out.exists())

            content = out.read_text(encoding="utf-8")
            self.assertIn("# Goal Tracking Digest", content)
            self.assertIn("- **Total Goals:** 3", content)
            self.assertIn("- **Active Goals:** 2", content)
            self.assertIn("- **Completed / Inactive Goals:** 1", content)
            self.assertIn("- **Achieved (>= 100%):** 1", content)
            self.assertIn("Run marathon", content)
            self.assertIn("Save funds", content)
            self.assertIn("Old goal", content)
            self.assertIn("fitness", content)
            self.assertIn("finance", content)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "page.json"
            out = Path(tmp_dir) / "digest.md"
            f1.write_text("[]", encoding="utf-8")
            out.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                gd.convert([str(f1)], str(out))

    def test_empty_goals_handled(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "empty.json"
            out = Path(tmp_dir) / "digest.md"
            f1.write_text("[]", encoding="utf-8")

            gd.convert([str(f1)], str(out))
            content = out.read_text(encoding="utf-8")
            self.assertIn("No goals found in the export.", content)


if __name__ == "__main__":
    unittest.main()
