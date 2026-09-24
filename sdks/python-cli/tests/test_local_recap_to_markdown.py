#!/usr/bin/env python3
"""Tests for local desktop daily recap to markdown converter.

Pins YAML frontmatter rendering, highlights formatting, application focus table,
activity timeline, multi-recap merging, stdin piping, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Load local_recap_to_markdown example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "local_recap_to_markdown.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "local_recap_to_markdown.py"

spec = importlib.util.spec_from_file_location("local_recap_to_markdown", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
r2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r2m)

convert_recaps_to_markdown = r2m.convert_recaps_to_markdown
format_single_recap = r2m.format_single_recap
main = r2m.main
parse_recap_data = r2m.parse_recap_data
render_frontmatter = r2m.render_frontmatter


class TestLocalRecapToMarkdown(unittest.TestCase):
    def test_parse_recap_data_dict(self):
        raw = {"date": "2026-09-24", "summary": "Great day"}
        items = parse_recap_data(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["date"], "2026-09-24")

    def test_parse_recap_data_list(self):
        raw = [{"date": "2026-09-23"}, {"date": "2026-09-24"}]
        items = parse_recap_data(raw)
        self.assertEqual(len(items), 2)

    def test_parse_recap_data_invalid(self):
        with self.assertRaises(ValueError):
            parse_recap_data("{not json")

    def test_render_frontmatter(self):
        recap = {
            "highlights": ["Finished task 1", "Shipped PR"],
            "apps": [{"name": "Chrome"}, {"name": "VS Code"}],
        }
        fm = render_frontmatter(recap, "2026-09-24")
        self.assertIn('date: "2026-09-24"', fm)
        self.assertIn("highlights_count: 2", fm)
        self.assertIn("apps_count: 2", fm)
        self.assertIn("omi/recap", fm)

    def test_format_single_recap_full(self):
        recap = {
            "date": "2026-09-24",
            "summary": "Focused heavily on open source contributions.",
            "highlights": ["Submitted Weaviate recipe", "Reviewed PR feedback"],
            "apps": [
                {"name": "Visual Studio Code", "duration_minutes": 180, "notes": "Core coding"},
                {"name": "Terminal", "duration": 45, "notes": "Testing & git"},
            ],
            "timeline": [
                {"time": "09:00", "description": "Standup and task triage"},
                {"time": "14:00", "description": "Implemented test suites"},
            ],
        }
        md = format_single_recap(recap, include_frontmatter=True)
        self.assertIn("---", md)
        self.assertIn("# Daily Recap — 2026-09-24", md)
        self.assertIn("## Overview", md)
        self.assertIn("Focused heavily on open source contributions.", md)
        self.assertIn("## Key Highlights", md)
        self.assertIn("- [x] Submitted Weaviate recipe", md)
        self.assertIn("## App Usage & Focus", md)
        self.assertIn("| **Visual Studio Code** | 180m | Core coding |", md)
        self.assertIn("## Activity Timeline", md)
        self.assertIn("* **09:00**: Standup and task triage", md)

    def test_format_single_recap_no_frontmatter(self):
        recap = {"date": "2026-09-24", "summary": "Short day"}
        md = format_single_recap(recap, include_frontmatter=False)
        self.assertNotIn("---", md)
        self.assertIn("# Daily Recap — 2026-09-24", md)

    def test_convert_recaps_to_markdown_empty(self):
        md = convert_recaps_to_markdown([])
        self.assertIn("No local activity recap data provided", md)

    def test_cli_end_to_end_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "recap.json"
            out_file = tmppath / "today.md"

            sample = {
                "date": "2026-09-24",
                "summary": "Sprint review day",
                "highlights": ["Passed all checks"],
            }
            in_file.write_text(json.dumps(sample), encoding="utf-8")

            code = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("Sprint review day", content)

    def test_cli_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "input.json"
            out_file = tmppath / "output.md"

            in_file.write_text(json.dumps({"summary": "test"}), encoding="utf-8")
            out_file.write_text("existing content", encoding="utf-8")

            code_fail = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code_fail, 1)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "existing content")

            code_ok = main([str(in_file), "-o", str(out_file), "--force"])
            self.assertEqual(code_ok, 0)
            self.assertIn("test", out_file.read_text(encoding="utf-8"))

    def test_cli_stdin_to_stdout(self):
        sample = json.dumps({"summary": "Piped recap content"})
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(sample)
            sys.stdout = io.StringIO()
            code = main(["-"])
            self.assertEqual(code, 0)
            output = sys.stdout.getvalue()
            self.assertIn("Piped recap content", output)
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
