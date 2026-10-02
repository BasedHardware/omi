"""Tests for the goals_to_jsonl recipe."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "goals_to_jsonl.py"
spec = importlib.util.spec_from_file_location("goals_to_jsonl", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
g2jsonl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2jsonl)


class TestGoalsToJSONL(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample_goals = [
            {
                "id": "goal_01",
                "title": "Read 20 Books",
                "goal_type": "numeric",
                "current_value": 12,
                "target_value": 20,
                "unit": "books",
                "is_active": True,
                "is_achieved": False,
                "created_at": "2026-09-01T12:00:00Z",
                "updated_at": "2026-09-15T15:30:00Z",
            },
            {
                "id": "goal_02",
                "title": "Run 50km",
                "goal_type": "numeric",
                "current_value": 50,
                "target_value": 50,
                "unit": "km",
                "is_active": True,
                "is_achieved": True,
                "created_at": "2026-09-05T08:00:00Z",
            },
            {
                "id": "goal_03",
                "title": "Old Archived Milestone",
                "goal_type": "numeric",
                "current_value": 5,
                "target_value": 100,
                "unit": "points",
                "is_active": False,
                "is_achieved": False,
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_text_sanitization(self):
        self.assertEqual(g2jsonl.text("Clean Title"), "Clean Title")
        self.assertIsNone(g2jsonl.text(None))
        self.assertEqual(g2jsonl.text("Clean\x00\ufffe\uffff"), "Clean")
        self.assertEqual(g2jsonl.text({"nested": 1}), '{"nested": 1}')

    def test_iso_utc(self):
        self.assertEqual(
            g2jsonl.iso_utc("2026-10-02T12:00:00Z"),
            "2026-10-02T12:00:00Z",
        )
        self.assertEqual(
            g2jsonl.iso_utc("2026-10-02T14:00:00+02:00"),
            "2026-10-02T12:00:00Z",
        )
        self.assertIsNone(g2jsonl.iso_utc("invalid"))
        self.assertIsNone(g2jsonl.iso_utc(None))

    def test_derive_status_precedence(self):
        self.assertEqual(g2jsonl.derive_status({"is_active": False, "is_achieved": True}), "inactive")
        self.assertEqual(g2jsonl.derive_status({"is_active": "0", "is_completed": True}), "inactive")
        # Inactive precedence even if 100% progress
        self.assertEqual(
            g2jsonl.derive_status({
                "is_active": "false",
                "current_value": 100,
                "target_value": 100,
            }),
            "inactive",
        )
        # Normalized string boolean flags
        self.assertEqual(
            g2jsonl.derive_status({
                "is_active": True,
                "is_achieved": "false",
                "is_completed": "true",
            }),
            "completed",
        )
        # Boolean goal reaching 1.0 without explicit flag derives completed
        self.assertEqual(
            g2jsonl.derive_status({
                "is_active": True,
                "goal_type": "boolean",
                "current_value": 1.0,
            }),
            "completed",
        )
        self.assertEqual(g2jsonl.derive_status({"is_active": True, "is_achieved": True}), "completed")
        self.assertEqual(g2jsonl.derive_status({"is_active": True, "is_achieved": False}), "active")

    def test_parse_float_overflow(self):
        self.assertIsNone(g2jsonl.parse_float("9" * 400))
        self.assertIsNone(g2jsonl.parse_float(10**400))

    def test_calc_progress_pct(self):
        self.assertEqual(g2jsonl.calc_progress_pct({}, True), 100.0)

        # Normal numeric
        goal_num = {"current_value": 15, "target_value": 20}
        self.assertEqual(g2jsonl.calc_progress_pct(goal_num, False), 75.0)

        # Scale with min and max
        goal_scale = {"current_value": 30, "target_value": 50, "min_value": 10}
        self.assertEqual(g2jsonl.calc_progress_pct(goal_scale, False), 50.0)

        # Boolean
        goal_bool = {"goal_type": "boolean", "current_value": 1}
        self.assertEqual(g2jsonl.calc_progress_pct(goal_bool, False), 100.0)

        # Missing target / qualitative
        goal_qual = {"title": "Learn guitar"}
        self.assertIsNone(g2jsonl.calc_progress_pct(goal_qual, False))

    def test_unwrap_goals(self):
        for key in ("goals", "items", "data", "results"):
            wrapped = {key: self.sample_goals}
            items = g2jsonl.unwrap_goals(wrapped, "test")
            self.assertEqual(len(items), 3)

        # Bare list
        self.assertEqual(len(g2jsonl.unwrap_goals(self.sample_goals, "test")), 3)

        # Single goal dict
        single = {"id": "single", "title": "Single Goal"}
        self.assertEqual(len(g2jsonl.unwrap_goals(single, "test")), 1)

        # Non-goal dict returns empty list
        self.assertEqual(len(g2jsonl.unwrap_goals({"error": "not found"}, "test")), 0)

        # Non-dict/list raises ValueError
        with self.assertRaises(ValueError):
            g2jsonl.unwrap_goals("invalid string", "test")

    def test_load_and_deduplication(self):
        f1 = self.tmp / "g1.json"
        f2 = self.tmp / "g2.json"
        f1.write_text(json.dumps(self.sample_goals[:2]), encoding="utf-8")
        f2.write_text(json.dumps(self.sample_goals[1:]), encoding="utf-8")

        loaded = g2jsonl.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 3)
        self.assertIn("goal_01", loaded)
        self.assertIn("goal_02", loaded)
        self.assertIn("goal_03", loaded)

    def test_load_idless_and_empty_file(self):
        idless = [{"title": "Goal Without ID"}]
        f_idless = self.tmp / "idless.json"
        f_idless.write_text(json.dumps(idless), encoding="utf-8")

        f_empty = self.tmp / "empty.json"
        f_empty.write_text("   \n\t  ", encoding="utf-8")

        loaded = g2jsonl.load([str(f_idless), str(f_empty)])
        self.assertEqual(len(loaded), 1)
        key = list(loaded.keys())[0]
        self.assertTrue(key.startswith("gen_"))
        self.assertEqual(loaded[key]["id"], key)

        # Idempotent: second load derives identical key
        loaded2 = g2jsonl.load([str(f_idless)])
        self.assertEqual(list(loaded2.keys())[0], key)

    def test_build_jsonl_output_format_and_schema(self):
        goals_dict = {g["id"]: g for g in self.sample_goals}
        jsonl_str, count = g2jsonl.build_jsonl(goals_dict, status_filter="all")
        self.assertEqual(count, 3)

        lines = [line for line in jsonl_str.split("\n") if line.strip()]
        self.assertEqual(len(lines), 3)

        for line in lines:
            parsed = json.loads(line)
            self.assertIn("id", parsed)
            self.assertIn("title", parsed)
            self.assertIn("is_active", parsed)
            self.assertIn("is_completed", parsed)
            self.assertIn("progress_pct", parsed)

    def test_status_filtering(self):
        goals_dict = {g["id"]: g for g in self.sample_goals}

        _, count_active = g2jsonl.build_jsonl(goals_dict, status_filter="active")
        self.assertEqual(count_active, 1)

        _, count_completed = g2jsonl.build_jsonl(goals_dict, status_filter="completed")
        self.assertEqual(count_completed, 1)

        _, count_inactive = g2jsonl.build_jsonl(goals_dict, status_filter="inactive")
        self.assertEqual(count_inactive, 1)

    def test_convert_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "goals.jsonl"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        count = g2jsonl.convert([str(src)], destination=str(dest))
        self.assertEqual(count, 3)
        self.assertTrue(dest.exists())

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            g2jsonl.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        count2 = g2jsonl.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(count2, 3)

        # No leftover temp files exist
        tmp_files = list(self.tmp.glob(".tmp_goals_jsonl_*"))
        self.assertEqual(tmp_files, [])

        # Capture snapshot of destination immediately before injecting write failure
        orig_bytes = dest.read_bytes()

        # Failing tmp write in overwrite mode cleans up temporary file and leaves destination intact
        real_open = Path.open

        def failing_tmp_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            if ".tmp_goals_jsonl_" in self_path.name:
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk full"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_tmp_open):
            with self.assertRaises(OSError):
                g2jsonl.convert([str(src)], destination=str(dest), overwrite=True)

        self.assertEqual(dest.read_bytes(), orig_bytes)
        self.assertEqual(list(self.tmp.glob(".tmp_goals_jsonl_*")), [])

    def test_failed_initial_creation_cleans_up(self):
        src = self.tmp / "input_fail.json"
        dest = self.tmp / "fail.jsonl"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        real_open = Path.open

        def failing_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            mode = kwargs.get("mode", args[0] if args else "r")
            if "xb" in mode and str(self_path) == str(dest):
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk write error"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_open):
            with self.assertRaises(OSError):
                g2jsonl.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_main_cli_execution_and_overwrite(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_output.jsonl"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        # First run succeeds
        ret = g2jsonl.main([
            str(src),
            "-o", str(dest),
            "--status", "active",
        ])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())

        # Second run without --overwrite fails with SystemExit
        with self.assertRaises(SystemExit) as ctx:
            g2jsonl.main([str(src), "-o", str(dest)])
        self.assertIn("Refusing to overwrite", str(ctx.exception))

        # Third run with --overwrite succeeds
        ret_over = g2jsonl.main([str(src), "-o", str(dest), "--overwrite"])
        self.assertEqual(ret_over, 0)

    def test_main_broken_pipe_error(self):
        src = self.tmp / "cli_pipe.json"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        orig_fd = os.dup(sys.stdout.fileno())
        try:
            with patch("sys.stdout.buffer.write", side_effect=BrokenPipeError):
                ret = g2jsonl.main([str(src), "-o", "-"])
                self.assertEqual(ret, 1)
        finally:
            os.dup2(orig_fd, sys.stdout.fileno())
            os.close(orig_fd)

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_goals).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = g2jsonl.load(["-"])
            self.assertEqual(len(loaded), 3)


if __name__ == "__main__":
    unittest.main()
