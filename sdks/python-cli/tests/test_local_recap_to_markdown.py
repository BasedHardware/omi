#!/usr/bin/env python3
"""Tests for local desktop daily recap to markdown converter.

Pins YAML frontmatter rendering, real sections/totals parsing from Omi Desktop,
tasks checkbox formatting, application focus table, focus sessions, stdin piping,
and overwrite protection.
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

convert_recap_to_markdown = r2m.convert_recap_to_markdown
extract_sections_map = r2m.extract_sections_map
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

    def test_format_desktop_real_payload_schema(self):
        """Pin the exact schema structure emitted by omi --json local recap."""
        real_desktop_payload = {
            "ok": True,
            "tool": "get_daily_recap",
            "date": "2026-09-24",
            "totals": {
                "apps": 2,
                "conversations": 1,
                "tasks": 3,
                "focus": 1,
                "memories": 1,
                "observations": 5,
                "summary": 1,
            },
            "sections": [
                {
                    "name": "summary",
                    "total": 1,
                    "items": [
                        {"content": "Productive sprint day focused on frontend and backend features."}
                    ],
                },
                {
                    "name": "apps",
                    "total": 2,
                    "items": [
                        {
                            "title": "Safari",
                            "minutes": 180.5,
                            "captures": 40,
                            "firstSeenAt": "09:00:00Z",
                            "lastSeenAt": "17:30:00Z",
                        }
                    ],
                },
                {
                    "name": "tasks",
                    "total": 3,
                    "items": [
                        {
                            "title": "Implement feature X",
                            "summary": "Detailed technical spec",
                            "completed": False,
                            "priority": "high",
                        },
                        {
                            "title": "Ship PR #18673",
                            "completed": True,
                        },
                    ],
                },
                {
                    "name": "focus",
                    "total": 1,
                    "items": [
                        {"title": "Deep Work", "status": "completed", "durationSeconds": 3600}
                    ],
                },
                {
                    "name": "conversations",
                    "total": 1,
                    "items": [
                        {"title": "Sprint Planning", "summary": "Discussed roadmap milestones", "durationSeconds": 900}
                    ],
                },
            ],
        }

        md = format_single_recap(real_desktop_payload, include_frontmatter=True)
        # Frontmatter
        self.assertIn('date: "2026-09-24"', md)
        self.assertIn("apps_count: 2", md)
        self.assertIn("tasks_count: 3", md)
        # Overview
        self.assertIn("## Overview", md)
        self.assertIn("Productive sprint day focused on frontend and backend features.", md)
        # Tasks
        self.assertIn("## Tasks & Action Items", md)
        self.assertIn("- [ ] Implement feature X `[HIGH]` — Detailed technical spec", md)
        self.assertIn("- [x] Ship PR #18673", md)
        # Apps
        self.assertIn("## App Usage & Focus", md)
        self.assertIn("| **Safari** | 180.5m | 40 | 09:00:00Z - 17:30:00Z |", md)
        # Focus
        self.assertIn("## Focus Sessions", md)
        self.assertIn("- **Deep Work** (60m) — *completed*", md)
        # Conversations
        self.assertIn("## Conversations & Discussions", md)
        self.assertIn("- **Sprint Planning** (15m): Discussed roadmap milestones", md)

    def test_format_single_recap_no_frontmatter(self):
        recap = {"date": "2026-09-24", "summary": "Short day"}
        md = format_single_recap(recap, include_frontmatter=False)
        self.assertNotIn("---", md)
        self.assertIn("# Daily Recap — 2026-09-24", md)

    def test_cli_end_to_end_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "recap.json"
            out_file = tmppath / "today.md"

            sample = {
                "date": "2026-09-24",
                "summary": "Sprint review day",
                "sections": [
                    {
                        "name": "tasks",
                        "items": [{"title": "Passed all checks", "completed": True}],
                    }
                ],
            }
            in_file.write_text(json.dumps(sample), encoding="utf-8")

            code = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("Sprint review day", content)
            self.assertIn("- [x] Passed all checks", content)

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
