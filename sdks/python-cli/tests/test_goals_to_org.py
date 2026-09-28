"""Unit tests for goals -> Org-mode exporter.

Pins envelope unwrapping, UTF-8 BOM handling, properties drawer,
progress cookies, TODO/DONE states, status and type grouping,
filtering, syntax escaping, and single-file vs directory export modes.
"""

from __future__ import annotations

from datetime import timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_org.py"
spec = importlib.util.spec_from_file_location("goals_to_org", script_path)
g2org = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2org)

UTC = timezone.utc


class TestGoalsToOrg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_extract_goals_envelopes(self):
        sample = {"id": "g1", "title": "Read 12 books", "goal_type": "numeric", "target_value": 12}

        # Bare list
        self.assertEqual(len(g2org.extract_goals([sample])), 1)

        # Envelopes
        self.assertEqual(len(g2org.extract_goals({"goals": [sample]})), 1)
        self.assertEqual(len(g2org.extract_goals({"items": [sample]})), 1)
        self.assertEqual(len(g2org.extract_goals({"data": [sample]})), 1)

        # Single dict
        self.assertEqual(len(g2org.extract_goals(sample)), 1)

        # Empty envelopes (Must return 0 without creating phantom records)
        self.assertEqual(len(g2org.extract_goals({"goals": []})), 0)
        self.assertEqual(len(g2org.extract_goals({"items": []})), 0)
        self.assertEqual(len(g2org.extract_goals({"data": []})), 0)
        self.assertEqual(len(g2org.extract_goals({})), 0)
        self.assertEqual(len(g2org.extract_goals([])), 0)

    def test_utf8_bom_handling(self):
        sample = [{"id": "g1", "title": "BOM Test Goal", "target_value": 5, "current_value": 2}]
        bom_payload = "\ufeff" + json.dumps(sample)
        source = self.tmp / "bom.json"
        source.write_bytes(bom_payload.encode("utf-8"))

        dest = self.tmp / "bom.org"
        count = g2org.convert(source, dest, UTC)
        self.assertEqual(count, 1)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("BOM Test Goal", content)
        self.assertIn(":OMI_ID: g1", content)

    def test_properties_drawer_and_metadata(self):
        sample = [{
            "id": "goal-uuid-1234",
            "title": "Drink 2L Water Daily",
            "goal_type": "numeric",
            "current_value": 1.5,
            "target_value": 2.0,
            "min_value": 0.0,
            "max_value": 3.0,
            "unit": "liters",
            "is_active": True,
            "created_at": "2026-09-28T07:00:00Z",
            "updated_at": "2026-09-28T11:00:00Z",
            "description": "Track daily water consumption with Omi.",
        }]
        source = self.tmp / "meta.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "meta.org"
        g2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* 🎯 Active Goals :active:", content)
        self.assertIn("** TODO Drink 2L Water Daily [75%] [1.5/2] :numeric:", content)
        self.assertIn(":PROPERTIES:", content)
        self.assertIn(":OMI_ID: goal-uuid-1234", content)
        self.assertIn(":GOAL_TYPE: numeric", content)
        self.assertIn(":CURRENT_VALUE: 1.5", content)
        self.assertIn(":TARGET_VALUE: 2", content)
        self.assertIn(":MIN_VALUE: 0", content)
        self.assertIn(":MAX_VALUE: 3", content)
        self.assertIn(":UNIT: liters", content)
        self.assertIn(":IS_ACTIVE: true", content)
        self.assertIn(":DATE: [2026-09-28 Mon 07:00]", content)
        self.assertIn(":CREATED: [2026-09-28 Mon 07:00]", content)
        self.assertIn(":UPDATED: [2026-09-28 Mon 11:00]", content)
        self.assertIn(":END:", content)
        self.assertIn("Track daily water consumption with Omi.", content)

    def test_todo_done_and_progress_cookies(self):
        sample = [
            {"id": "g1", "title": "Completed Marathon", "target_value": 42.2, "current_value": 42.2, "unit": "km", "is_active": True},
            {"id": "g2", "title": "Ongoing Sprint", "target_value": 10, "current_value": 4, "unit": "tasks", "is_active": True},
            {"id": "g3", "title": "Archived Habit", "target_value": 10, "current_value": 2, "is_active": False},
        ]
        source = self.tmp / "prog.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "prog.org"
        g2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        # Achieved goal is DONE
        self.assertIn("DONE Completed Marathon [100%] [42.2/42.2]", content)
        # Incomplete goal state
        self.assertIn("TODO Ongoing Sprint [40%] [4/10]", content)
        # Inactive goal is DONE
        self.assertIn("DONE Archived Habit [20%] [2/10]", content)

    def test_syntax_escaping_zwsp(self):
        sample = [
            {"id": "g1", "title": "[#A] Top Priority Metric", "target_value": 10, "current_value": 5},
            {"id": "g2", "title": "Quarter review on [2026-09-28 Mon]", "target_value": 10, "current_value": 5},
            {"id": "g3", "title": "Metric ending with tag :health:", "target_value": 10, "current_value": 5},
        ]
        source = self.tmp / "esc.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "esc.org"
        g2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        # Ensure ZWSP injected before [#A]
        self.assertIn("\u200b[#A]", content)
        # Ensure ZWSP injected into timestamp
        self.assertIn("[\u200b2026-09-28", content)
        # Ensure ZWSP injected after trailing tag
        self.assertIn(":health:\u200b", content)

    def test_group_by_status(self):
        sample = [
            {"id": "g1", "title": "Active Goal", "target_value": 10, "current_value": 2, "is_active": True},
            {"id": "g2", "title": "Completed Goal", "target_value": 10, "current_value": 10, "is_active": True},
        ]
        source = self.tmp / "status.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "status.org"
        g2org.convert(source, dest, UTC, group_by="status")

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* 🎯 Active Goals :active:", content)
        self.assertIn("** TODO Active Goal", content)
        self.assertIn("* ✅ Completed & Archived Goals :completed:", content)
        self.assertIn("** DONE Completed Goal", content)

    def test_group_by_type(self):
        sample = [
            {"id": "g1", "title": "Read Chapters", "goal_type": "numeric", "target_value": 10, "current_value": 5},
            {"id": "g2", "title": "Energy Level", "goal_type": "scale", "target_value": 10, "current_value": 8},
            {"id": "g3", "title": "Meditated", "goal_type": "boolean", "target_value": 1, "current_value": 1},
        ]
        source = self.tmp / "type.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "type.org"
        g2org.convert(source, dest, UTC, group_by="type")

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* 📊 Numeric Goals :numeric:", content)
        self.assertIn("* ⚖️ Scale Goals :scale:", content)
        self.assertIn("* ☑️ Boolean Goals :boolean:", content)

    def test_group_by_none(self):
        sample = [
            {"id": "g1", "title": "Flat Goal 1", "target_value": 5, "current_value": 1},
            {"id": "g2", "title": "Flat Goal 2", "target_value": 5, "current_value": 5},
        ]
        source = self.tmp / "flat.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "flat.org"
        g2org.convert(source, dest, UTC, group_by="none")

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* TODO Flat Goal 1", content)
        self.assertIn("* DONE Flat Goal 2", content)
        self.assertNotIn("** TODO Flat Goal 1", content)

    def test_filter_type_and_active_only(self):
        sample = [
            {"id": "g1", "title": "Active Numeric", "goal_type": "numeric", "target_value": 10, "current_value": 3, "is_active": True},
            {"id": "g2", "title": "Inactive Numeric", "goal_type": "numeric", "target_value": 10, "current_value": 3, "is_active": False},
            {"id": "g3", "title": "Active Scale", "goal_type": "scale", "target_value": 10, "current_value": 3, "is_active": True},
        ]
        source = self.tmp / "filter.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        # Active only
        dest_act = self.tmp / "act.org"
        g2org.convert(source, dest_act, UTC, active_only=True)
        content_act = dest_act.read_text(encoding="utf-8")
        self.assertIn("Active Numeric", content_act)
        self.assertIn("Active Scale", content_act)
        self.assertNotIn("Inactive Numeric", content_act)

        # Type filter
        dest_type = self.tmp / "type.org"
        g2org.convert(source, dest_type, UTC, goal_type_filter="scale")
        content_type = dest_type.read_text(encoding="utf-8")
        self.assertIn("Active Scale", content_type)
        self.assertNotIn("Active Numeric", content_type)

    def test_directory_export_mode(self):
        sample = [
            {"id": "g1", "title": "Active Step", "target_value": 10, "current_value": 2, "is_active": True},
            {"id": "g2", "title": "Done Step", "target_value": 10, "current_value": 10, "is_active": True},
        ]
        source = self.tmp / "dir.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        out_dir = self.tmp / "goals_dir"
        count = g2org.convert(source, self.tmp / "dummy.org", UTC, output_dir=out_dir, group_by="status")
        self.assertEqual(count, 2)

        files = list(out_dir.glob("*.org"))
        filenames = [f.name for f in files]
        self.assertIn("active_goals.org", filenames)
        self.assertIn("completed_goals.org", filenames)

    def test_overwrite_protection(self):
        sample = [{"id": "g1", "title": "Goal item"}]
        source = self.tmp / "ow.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "existing.org"
        dest.write_text("Existing data", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            g2org.convert(source, dest, UTC, overwrite=False)

        g2org.convert(source, dest, UTC, overwrite=True)
        self.assertIn("Goal item", dest.read_text(encoding="utf-8"))

    def test_stdin_input_support(self):
        sample = [{"id": "g1", "title": "Stdin Goal", "target_value": 5, "current_value": 2}]
        payload_str = json.dumps(sample)
        dest = self.tmp / "stdin.org"

        with patch("sys.stdin", io.StringIO(payload_str)):
            count = g2org.convert("-", dest, UTC)
            self.assertEqual(count, 1)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("Stdin Goal", content)


if __name__ == "__main__":
    unittest.main()
