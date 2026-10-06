"""Tests for goals_digest recipe.

Covers: KPI calculation, status precedence over >=100% progress, qualitative goals,
markdown table sanitization, multi-file deduplication by updated_at, path traversal rejection,
atomic overwrite protection, and CLI entrypoint.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

# Load goals_digest script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_digest.py"
spec = importlib.util.spec_from_file_location("goals_digest", script_path)
digest_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest_mod)

parse_float = digest_mod.parse_float
sanitize_markdown_cell = digest_mod.sanitize_markdown_cell
validate_path_safety = digest_mod.validate_path_safety
is_qualitative_goal = digest_mod.is_qualitative_goal
calculate_progress = digest_mod.calculate_progress
determine_status = digest_mod.determine_status
render_progress_bar = digest_mod.render_progress_bar
extract_goals = digest_mod.extract_goals
load_and_deduplicate = digest_mod.load_and_deduplicate
build_digest = digest_mod.build_digest
write_digest = digest_mod.write_digest
main = digest_mod.main


class TestGoalsDigest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

        self.sample_goals = [
            {
                "id": "g_run",
                "title": "Run 100km | Marathon prep",
                "goal_type": "numeric",
                "current_value": 60.0,
                "target_value": 100.0,
                "min_value": 0.0,
                "is_active": True,
                "status": "in_progress",
                "created_at": "2026-09-01T10:00:00Z",
                "updated_at": "2026-09-10T10:00:00Z",
            },
            {
                "id": "g_pause",
                "title": "Learn Latin\nAdvanced vocabulary",
                "goal_type": "numeric",
                "current_value": 100.0,
                "target_value": 100.0,
                "is_active": False,
                "status": "paused",
                "created_at": "2026-09-01T10:00:00Z",
                "updated_at": "2026-09-05T10:00:00Z",
            },
            {
                "id": "g_qual",
                "title": "Daily mindfulness",
                "goal_type": "qualitative",
                "is_active": True,
                "status": "achieved",
                "created_at": "2026-09-01T10:00:00Z",
                "updated_at": "2026-09-15T10:00:00Z",
            },
        ]

        self.goals_file = self.dir_path / "goals.json"
        self.goals_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")
        self.out_digest = self.dir_path / "goals_digest.md"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_float_edge_cases(self):
        self.assertEqual(parse_float(42.5), 42.5)
        self.assertEqual(parse_float("100"), 100.0)
        self.assertEqual(parse_float(None, 0.0), 0.0)
        self.assertEqual(parse_float(float("nan"), 5.0), 5.0)
        self.assertEqual(parse_float(float("inf"), 5.0), 5.0)
        self.assertEqual(parse_float("1e9999", 0.0), 0.0)

    def test_sanitize_markdown_cell(self):
        raw = "Item with | pipes and \\ backslashes\nand newlines\r\ntabs\there"
        clean = sanitize_markdown_cell(raw)
        self.assertNotIn("\n", clean)
        self.assertNotIn("\r", clean)
        self.assertNotIn("\t", clean)
        self.assertIn("\\|", clean)
        self.assertIn("\\\\", clean)

    def test_determine_status_lifecycle_precedence(self):
        # Even with progress >= 100%, inactive or paused status MUST have precedence
        paused_goal = {
            "id": "p1",
            "current_value": 150.0,
            "target_value": 100.0,
            "is_active": True,
            "status": "paused",
        }
        self.assertEqual(determine_status(paused_goal), "paused")

        abandoned_goal = {
            "id": "a1",
            "current_value": 100.0,
            "target_value": 100.0,
            "is_active": False,
            "status": "abandoned",
        }
        self.assertEqual(determine_status(abandoned_goal), "abandoned")

        inactive_flag_goal = {
            "id": "i1",
            "current_value": 100.0,
            "target_value": 100.0,
            "is_active": False,
        }
        self.assertEqual(determine_status(inactive_flag_goal), "inactive")

        achieved_goal = {
            "id": "done1",
            "current_value": 100.0,
            "target_value": 100.0,
            "is_active": True,
            "status": "in_progress",
        }
        self.assertEqual(determine_status(achieved_goal), "achieved")

    def test_qualitative_goals(self):
        qual_goal = {"id": "q1", "goal_type": "qualitative", "status": "achieved"}
        self.assertTrue(is_qualitative_goal(qual_goal))
        self.assertEqual(calculate_progress(qual_goal), 100.0)
        self.assertEqual(determine_status(qual_goal), "achieved")

        qual_active = {"id": "q2", "metric": None, "status": "focused"}
        self.assertTrue(is_qualitative_goal(qual_active))
        self.assertEqual(calculate_progress(qual_active), 0.0)
        self.assertEqual(determine_status(qual_active), "active")

    def test_multi_file_deduplication(self):
        older_file = self.dir_path / "older.json"
        newer_file = self.dir_path / "newer.json"

        older_file.write_text(json.dumps([
            {"id": "g1", "title": "Old title", "current_value": 10, "updated_at": "2026-09-01T00:00:00Z"}
        ]), encoding="utf-8")

        newer_file.write_text(json.dumps([
            {"id": "g1", "title": "New title", "current_value": 50, "updated_at": "2026-09-10T00:00:00Z"},
            {"id": "g2", "title": "Unique goal", "current_value": 20, "updated_at": "2026-09-05T00:00:00Z"}
        ]), encoding="utf-8")

        deduped = load_and_deduplicate([str(older_file), str(newer_file)])
        self.assertEqual(len(deduped), 2)
        g1 = next(g for g in deduped if g["id"] == "g1")
        self.assertEqual(g1["title"], "New title")
        self.assertEqual(g1["current_value"], 50)

    def test_build_digest_content(self):
        digest = build_digest(self.sample_goals)
        self.assertIn("# Omi Goals Executive Digest", digest)
        self.assertIn("## Executive Summary", digest)
        self.assertIn("**Total Goals** | 3", digest)
        self.assertIn("## Type Breakdown", digest)
        self.assertIn("## Detailed Goals Status", digest)
        self.assertIn("Run 100km \\| Marathon prep", digest)
        self.assertIn("`g_run`", digest)

    def test_path_traversal_refusal(self):
        with self.assertRaises(ValueError):
            validate_path_safety(Path("../bad.md"))
        with self.assertRaises(ValueError):
            validate_path_safety(Path("dir/../secret.json"))

    def test_atomic_write_and_overwrite_protection(self):
        write_digest("# First version", self.out_digest)
        self.assertTrue(self.out_digest.exists())

        # Overwrite without force must raise
        with self.assertRaises(FileExistsError):
            write_digest("# Second version", self.out_digest, force=False)

        # Overwrite with force succeeds
        write_digest("# Overwritten version", self.out_digest, force=True)
        self.assertIn("Overwritten version", self.out_digest.read_text(encoding="utf-8"))

    def test_cli_execution(self):
        exit_code = main([str(self.goals_file), "-o", str(self.out_digest)])
        self.assertEqual(exit_code, 0)
        self.assertTrue(self.out_digest.is_file())
        self.assertIn("Executive Summary", self.out_digest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
