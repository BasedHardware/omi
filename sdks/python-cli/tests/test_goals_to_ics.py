"""Unit tests for the goals_to_ics recipe.

Verifies:
- RFC 5545 text escaping and 75-octet line folding.
- Strict CRLF line terminations.
- VEVENT milestone event generation.
- VTODO actionable task generation with PERCENT-COMPLETE.
- Multi-page ID deduplication preserving latest updated_at.
- Resilient envelope unwrapping and missing ID synthesis.
- Path traversal protection and overwrite protection.
- CLI execution and stdin streaming.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

# Dynamically import goals_to_ics from examples
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_ics.py"
spec = importlib.util.spec_from_file_location("goals_to_ics", script_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load module from {script_path}")
g2i = importlib.util.module_from_spec(spec)
sys.modules["goals_to_ics"] = g2i
spec.loader.exec_module(g2i)


SAMPLE_GOALS_PAGE1 = [
    {
        "id": "goal_1",
        "title": "Read 20 books",
        "goal_type": "numeric",
        "current_value": 15.0,
        "target_value": 20.0,
        "unit": "books",
        "is_active": True,
        "target_date": "2026-12-31T23:59:59Z",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-10T12:00:00Z",
    },
    {
        "id": "goal_2",
        "title": "Run marathon",
        "goal_type": "scale",
        "current_value": 42.2,
        "target_value": 42.2,
        "unit": "km",
        "is_active": True,
        "target_date": "2026-10-15T08:00:00+02:00",
        "created_at": "2026-09-02T10:00:00Z",
        "updated_at": "2026-09-15T12:00:00Z",
    },
]

SAMPLE_GOALS_PAGE2 = [
    {
        "id": "goal_1",
        "title": "Read 20 books",
        "goal_type": "numeric",
        "current_value": 20.0,  # Now completed!
        "target_value": 20.0,
        "unit": "books",
        "is_active": True,
        "target_date": "2026-12-31T23:59:59Z",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-25T18:00:00Z",
    },
    {
        "id": "goal_3",
        "title": "Cancelled resolution",
        "goal_type": "boolean",
        "current_value": 0,
        "target_value": 1,
        "is_active": False,
        "status": "cancelled",
        "created_at": "2026-08-01T10:00:00Z",
    },
]


class TestGoalsToIcs(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rfc5545_text_escaping(self) -> None:
        self.assertEqual(
            g2i.ics_escape("Read, study; test\\one\r\ntwo\nthree"),
            "Read\\, study\\; test\\\\one\\ntwo\\nthree",
        )
        self.assertEqual(g2i.ics_escape(None), "")
        self.assertEqual(g2i.ics_escape(123), "123")

    def test_line_folding(self) -> None:
        long_line = "DESCRIPTION:" + "A" * 150
        folded = g2i.fold_line(long_line, max_octets=75)
        self.assertGreater(len(folded), 1)
        # Continuation lines must start with space
        for continuation in folded[1:]:
            self.assertTrue(continuation.startswith(" "))

    def test_vevent_mode_generation(self) -> None:
        content, count = g2i.generate_ics_content(SAMPLE_GOALS_PAGE1, mode="vevent")
        self.assertEqual(count, 2)
        self.assertTrue(content.endswith("\r\n"))
        self.assertIn("BEGIN:VCALENDAR\r\n", content)
        self.assertIn("BEGIN:VEVENT\r\n", content)
        self.assertIn("UID:omi-goal-goal_1@basedhardware.com", content)
        self.assertIn("DTSTART:20261231T235959Z", content)
        self.assertIn("STATUS:CONFIRMED", content)

        # Goal 2 is completed
        self.assertIn("UID:omi-goal-goal_2@basedhardware.com", content)
        self.assertIn("STATUS:COMPLETED", content)
        # 08:00+02:00 -> 06:00:00Z
        self.assertIn("DTSTART:20261015T060000Z", content)
        self.assertIn("✅ [Done] Run marathon", content)

    def test_vtodo_mode_generation(self) -> None:
        content, count = g2i.generate_ics_content(SAMPLE_GOALS_PAGE1, mode="vtodo")
        self.assertEqual(count, 2)
        self.assertIn("BEGIN:VTODO\r\n", content)
        self.assertIn("UID:omi-goal-goal_1@basedhardware.com", content)
        # 15 / 20 = 75%
        self.assertIn("PERCENT-COMPLETE:75", content)
        self.assertIn("STATUS:IN-PROCESS", content)
        self.assertIn("DUE:20261231T235959Z", content)

        # Goal 2: 42.2 / 42.2 = 100%
        self.assertIn("UID:omi-goal-goal_2@basedhardware.com", content)
        self.assertIn("PERCENT-COMPLETE:100", content)
        self.assertIn("STATUS:COMPLETED", content)

    def test_multi_file_deduplication(self) -> None:
        p1 = self.dir_path / "page1.json"
        p2 = self.dir_path / "page2.json"
        p1.write_text(json.dumps(SAMPLE_GOALS_PAGE1), encoding="utf-8")
        p2.write_text(json.dumps(SAMPLE_GOALS_PAGE2), encoding="utf-8")

        loaded = g2i.load_and_deduplicate([p1, p2])
        self.assertEqual(len(loaded), 3)

        by_id = {g["id"]: g for g in loaded}
        # goal_1 from page2 should overwrite page1
        self.assertEqual(by_id["goal_1"]["current_value"], 20.0)

    def test_envelope_unwrapping(self) -> None:
        test_payloads = [
            json.dumps({"goals": [{"id": "g1", "title": "Test"}]}),
            json.dumps({"items": [{"id": "g2", "title": "Test"}]}),
            json.dumps({"data": [{"id": "g3", "title": "Test"}]}),
            json.dumps({"id": "g4", "title": "Single"}),
        ]
        for p in test_payloads:
            goals = g2i.extract_goals(p, "test")
            self.assertEqual(len(goals), 1)

    def test_missing_id_synthesis(self) -> None:
        raw = json.dumps([{"title": "Goal without id"}])
        goals = g2i.extract_goals(raw, "test")
        self.assertEqual(len(goals), 1)
        self.assertTrue(goals[0]["id"].startswith("goal_"))

    def test_path_traversal_guard(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            g2i.write_ics("content", "../traversal.ics")
        self.assertIn("Path traversal sequence '..' is forbidden", str(ctx.exception))

    def test_refuse_overwrite_without_force(self) -> None:
        target = self.dir_path / "existing.ics"
        target.write_text("old content", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            g2i.write_ics("new content", target, force=False)

        self.assertEqual(target.read_text(encoding="utf-8"), "old content")

    def test_atomic_write_with_force(self) -> None:
        target = self.dir_path / "output.ics"
        target.write_text("old", encoding="utf-8")

        g2i.write_ics("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", target, force=True)
        self.assertIn("BEGIN:VCALENDAR", target.read_text(encoding="utf-8"))

    def test_cli_end_to_end_and_filter(self) -> None:
        p = self.dir_path / "input.json"
        out = self.dir_path / "output.ics"
        p.write_text(json.dumps(SAMPLE_GOALS_PAGE1), encoding="utf-8")

        saved_argv = sys.argv
        try:
            sys.argv = [
                "goals_to_ics.py",
                str(p),
                "-o",
                str(out),
                "--mode",
                "vtodo",
                "--status",
                "achieved",
            ]
            g2i.main()
        finally:
            sys.argv = saved_argv

        self.assertTrue(out.exists())
        content = out.read_text(encoding="utf-8")
        self.assertIn("BEGIN:VTODO", content)
        self.assertIn("Run marathon", content)
        self.assertNotIn("Read 20 books", content)  # 15/20 is active, filtered out

    def test_cli_stdin_streaming(self) -> None:
        raw = json.dumps([{"id": "piped", "title": "Piped Goal", "target_value": 10}])
        saved_stdin = sys.stdin
        saved_stdout = sys.stdout
        saved_argv = sys.argv
        try:
            sys.stdin = io.StringIO(raw)
            sys.stdout = io.StringIO()
            sys.argv = ["goals_to_ics.py", "-"]
            g2i.main()
            output = sys.stdout.getvalue()
            self.assertIn("BEGIN:VCALENDAR", output)
            self.assertIn("Piped Goal", output)
        finally:
            sys.stdin = saved_stdin
            sys.stdout = saved_stdout
            sys.argv = saved_argv


if __name__ == "__main__":
    unittest.main()
