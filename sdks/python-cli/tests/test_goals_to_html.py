"""Tests for the goals_to_html recipe."""

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "goals_to_html.py"
spec = importlib.util.spec_from_file_location("goals_to_html", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
g2html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2html)


class TestGoalsToHTML(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample_goals = [
            {
                "id": "goal_01",
                "title": "Read 20 Books; non-fiction, fiction & science",
                "goal_type": "numeric",
                "current_value": 12,
                "target_value": 20,
                "unit": "books",
                "is_active": True,
                "is_achieved": False,
            },
            {
                "id": "goal_02",
                "title": "Run 50km",
                "goal_type": "numeric",
                "current_value": 55,
                "target_value": 50,
                "unit": "km",
                "is_active": True,
                "is_achieved": True,
            },
            {
                "id": "goal_03",
                "title": "Meditate Daily",
                "goal_type": "boolean",
                "current_value": 1,
                "target_value": 1,
                "is_active": True,
                "is_achieved": True,
            },
            {
                "id": "goal_04",
                "title": "Old Inactive Goal",
                "goal_type": "numeric",
                "current_value": 5,
                "target_value": 100,
                "is_active": False,
                "is_achieved": False,
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_text_sanitization(self):
        self.assertEqual(g2html.text("Clean Title"), "Clean Title")
        self.assertEqual(g2html.text(None), "")
        # Control characters and noncharacters dropped
        nonchars = g2html.text("Clean\x00\ufffeword\uffff")
        self.assertEqual(nonchars, "Cleanword")

    def test_calc_progress(self):
        # Normal numeric
        ratio, disp, done = g2html.calc_progress(self.sample_goals[0])
        self.assertAlmostEqual(ratio, 0.6)
        self.assertEqual(disp, "60.0%")
        self.assertFalse(done)

        # Over-achievement clamped to 1.0 for bar, ratio formatted in text
        ratio_over, disp_over, done_over = g2html.calc_progress(self.sample_goals[1])
        self.assertEqual(ratio_over, 1.0)
        self.assertEqual(disp_over, "110.0%")
        self.assertTrue(done_over)

        # Boolean completed
        ratio_b, disp_b, done_b = g2html.calc_progress(self.sample_goals[2])
        self.assertEqual(ratio_b, 1.0)
        self.assertEqual(disp_b, "100.0%")
        self.assertTrue(done_b)

        # Scale with min and max
        scale_goal = {
            "current_value": 30,
            "target_value": 50,
            "min_value": 10,
            "is_active": True,
        }
        ratio_s, disp_s, done_s = g2html.calc_progress(scale_goal)
        self.assertAlmostEqual(ratio_s, 0.5)
        self.assertEqual(disp_s, "50.0%")
        self.assertFalse(done_s)

        # Target 0 fallback
        t0_goal = {"current_value": 0, "target_value": 0, "is_active": True}
        ratio_0, disp_0, done_0 = g2html.calc_progress(t0_goal)
        self.assertEqual(ratio_0, 1.0)
        self.assertEqual(disp_0, "100.0%")
        self.assertTrue(done_0)

        # Qualitative goal completed without targets
        qual_goal = {"title": "Learn guitar", "is_achieved": True, "is_active": True}
        ratio_q, disp_q, done_q = g2html.calc_progress(qual_goal)
        self.assertEqual(ratio_q, 1.0)
        self.assertEqual(disp_q, "100.0%")
        self.assertTrue(done_q)

        # Unparseable values
        bad_goal = {"current_value": "not-a-number", "target_value": "bad", "is_active": True}
        ratio_bad, disp_bad, done_bad = g2html.calc_progress(bad_goal)
        self.assertEqual(ratio_bad, 0.0)
        self.assertEqual(disp_bad, "—")
        self.assertFalse(done_bad)

    def test_derive_status_precedence(self):
        # Inactive precedence: is_active=False takes priority even if is_achieved=True
        self.assertEqual(
            g2html.derive_status({"is_active": False, "is_achieved": True}),
            "inactive",
        )
        self.assertEqual(
            g2html.derive_status({"is_active": "0", "is_achieved": True}),
            "inactive",
        )
        # Completed
        self.assertEqual(
            g2html.derive_status({"is_active": True, "is_achieved": True}),
            "completed",
        )
        self.assertEqual(
            g2html.derive_status({"is_active": True, "is_completed": True}),
            "completed",
        )
        # Active
        self.assertEqual(
            g2html.derive_status({"is_active": True, "is_achieved": False}),
            "active",
        )

    def test_unwrap_goals(self):
        for key in ("goals", "items", "data", "results"):
            wrapped = {key: self.sample_goals}
            items = g2html.unwrap_goals(wrapped, "test")
            self.assertEqual(len(items), 4)

        # Bare list
        self.assertEqual(len(g2html.unwrap_goals(self.sample_goals, "test")), 4)

        # Single goal dict
        single = {"id": "single", "title": "Single Goal"}
        self.assertEqual(len(g2html.unwrap_goals(single, "test")), 1)

        # Non-goal dict returns empty list
        self.assertEqual(len(g2html.unwrap_goals({"error": "not found"}, "test")), 0)

        # Non-dict/list raises ValueError
        with self.assertRaises(ValueError):
            g2html.unwrap_goals("invalid string", "test")

    def test_load_and_deduplication(self):
        f1 = self.tmp / "g1.json"
        f2 = self.tmp / "g2.json"
        f1.write_text(json.dumps(self.sample_goals[:3]), encoding="utf-8")
        f2.write_text(json.dumps(self.sample_goals[1:]), encoding="utf-8")

        loaded = g2html.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 4)
        self.assertIn("goal_01", loaded)
        self.assertIn("goal_02", loaded)
        self.assertIn("goal_03", loaded)
        self.assertIn("goal_04", loaded)

    def test_load_idless_and_empty_file(self):
        idless = [{"title": "Goal Without ID"}]
        f_idless = self.tmp / "idless.json"
        f_idless.write_text(json.dumps(idless), encoding="utf-8")

        f_empty = self.tmp / "empty.json"
        f_empty.write_text("   \n\t  ", encoding="utf-8")

        loaded = g2html.load([str(f_idless), str(f_empty)])
        self.assertEqual(len(loaded), 1)
        key = list(loaded.keys())[0]
        self.assertTrue(key.startswith("auto_"))
        self.assertEqual(loaded[key]["id"], key)

    def test_html_dashboard_rendering_and_escaping(self):
        xss_goals = {
            "g_xss": {
                "id": "g_xss",
                "title": "<script>alert(1)</script>",
                "goal_type": "<b>bold</b>",
                "current_value": 5,
                "target_value": 10,
                "unit": "<img src=x onerror=alert(2)>",
                "is_active": True,
                "is_achieved": False,
            }
        }
        rendered = g2html.generate_html_dashboard(xss_goals, report_title="<Evil> & 'Dashboard'")
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<b>bold</b>", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertIn("&lt;Evil&gt; &amp; &#x27;Dashboard&#x27;", rendered)

    def test_html_dashboard_filtering_and_metrics(self):
        goals_dict = {g["id"]: g for g in self.sample_goals}
        rendered_all = g2html.generate_html_dashboard(goals_dict, status_filter="all")
        self.assertIn("Total Goals", rendered_all)
        self.assertIn("4</div>", rendered_all)  # 4 total goals

        rendered_active = g2html.generate_html_dashboard(goals_dict, status_filter="active")
        self.assertIn("Read 20 Books", rendered_active)
        self.assertNotIn("Old Inactive Goal", rendered_active)

        rendered_inactive = g2html.generate_html_dashboard(goals_dict, status_filter="inactive")
        self.assertIn("Old Inactive Goal", rendered_inactive)
        self.assertNotIn("Read 20 Books", rendered_inactive)

    def test_convert_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "dashboard.html"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        count = g2html.convert([str(src)], destination=str(dest))
        self.assertEqual(count, 4)
        self.assertTrue(dest.exists())
        orig_bytes = dest.read_bytes()

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            g2html.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        count2 = g2html.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(count2, 4)

        # No leftover temp files exist
        tmp_files = list(self.tmp.glob(".tmp_goals_html_*"))
        self.assertEqual(tmp_files, [])

        # Failing tmp write in overwrite mode cleans up temporary file and leaves destination intact
        real_open = Path.open

        def failing_tmp_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            if ".tmp_goals_html_" in self_path.name:
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk full"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_tmp_open):
            with self.assertRaises(OSError):
                g2html.convert([str(src)], destination=str(dest), overwrite=True)

        self.assertEqual(dest.read_bytes(), orig_bytes)
        self.assertEqual(list(self.tmp.glob(".tmp_goals_html_*")), [])

    def test_failed_initial_creation_cleans_up(self):
        src = self.tmp / "input_fail.json"
        dest = self.tmp / "fail.html"
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
                g2html.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_main_cli_execution_and_overwrite(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_report.html"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        # First run succeeds
        ret = g2html.main([
            str(src),
            "-o", str(dest),
            "--status", "active",
            "--title", "CLI OKRs",
        ])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        self.assertIn("CLI OKRs", dest.read_text(encoding="utf-8"))

        # Second run without --overwrite fails with SystemExit
        with self.assertRaises(SystemExit) as ctx:
            g2html.main([str(src), "-o", str(dest)])
        self.assertIn("Refusing to overwrite", str(ctx.exception))

        # Third run with --overwrite succeeds
        ret_over = g2html.main([str(src), "-o", str(dest), "--overwrite"])
        self.assertEqual(ret_over, 0)

    def test_main_broken_pipe_error(self):
        src = self.tmp / "cli_pipe.json"
        src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

        orig_fd = os.dup(sys.stdout.fileno())
        try:
            with patch("sys.stdout.buffer.write", side_effect=BrokenPipeError):
                ret = g2html.main([str(src), "-o", "-"])
                self.assertEqual(ret, 1)
        finally:
            os.dup2(orig_fd, sys.stdout.fileno())
            os.close(orig_fd)

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_goals).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = g2html.load(["-"])
            self.assertEqual(len(loaded), 4)


if __name__ == "__main__":
    unittest.main()
