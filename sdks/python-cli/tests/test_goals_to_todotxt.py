"""Unit tests for the goals_to_todotxt recipe.

Verifies:
- Todo.txt line formatting for active and completed/inactive goals.
- Priority assignment and metric tags (cur, target, pct, unit, omi).
- Zero-width space (ZWSP) syntax collision protection for titles.
- Envelope unwrapping and missing ID synthesis.
- Timezone date adjustments.
- Atomic write, force overwrite, and symlink/traversal defenses.
- Hermetic offline execution.
"""

from __future__ import annotations

from datetime import timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_todotxt.py"
spec = importlib.util.spec_from_file_location("goals_to_todotxt", script_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load module from {script_path}")
g2todo = importlib.util.module_from_spec(spec)
sys.modules["goals_to_todotxt"] = g2todo
spec.loader.exec_module(g2todo)

ZWSP = "\u200b"
UTC = timezone.utc
JST = timezone(timedelta(hours=9))


class TestGoalsToTodoTxt(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def export(self, items: List[Dict[str, Any]], zone: timezone = UTC, **kwargs: Any) -> List[str]:
        source = self.tmp / "goals.json"
        dest = self.tmp / "todo.txt"
        if dest.exists():
            dest.unlink()
        source.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        g2todo.convert(source, dest, zone, **kwargs)
        return dest.read_text(encoding="utf-8").splitlines()

    def test_active_goal_formatting(self) -> None:
        items = [
            {
                "id": "g1",
                "title": "Daily 10k steps",
                "goal_type": "scale",
                "current_value": 8500,
                "target_value": 10000,
                "unit": "steps",
                "is_active": True,
                "created_at": "2026-09-30T10:00:00Z",
            }
        ]
        lines = self.export(items, UTC)
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            lines[0],
            "(B) 2026-09-30 Daily 10k steps +scale cur:8500 target:10000 pct:85% unit:steps omi:g1",
        )

    def test_completed_goal_formatting(self) -> None:
        items = [
            {
                "id": "g2",
                "title": "Read 20 books",
                "goal_type": "numeric",
                "current_value": 20,
                "target_value": 20,
                "unit": "books",
                "status": "completed",
                "created_at": "2026-09-01T00:00:00Z",
                "completed_at": "2026-09-28T12:00:00Z",
            }
        ]
        lines = self.export(items, UTC)
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            lines[0],
            "x 2026-09-28 2026-09-01 Read 20 books +numeric cur:20 target:20 pct:100% unit:books omi:g2",
        )

    def test_inactive_abandoned_goal_formatting(self) -> None:
        items = [
            {
                "id": "g3",
                "title": "Old abandoned project",
                "goal_type": "boolean",
                "current_value": 0,
                "target_value": 1,
                "is_active": False,
                "status": "archived",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-05T00:00:00Z",
            }
        ]
        lines = self.export(items, UTC)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("x 2026-08-05"))
        self.assertIn("Old abandoned project +boolean cur:0 target:1 pct:0% omi:g3", lines[0])

    def test_custom_priority(self) -> None:
        items = [
            {
                "id": "g_pri",
                "title": "Critical goal",
                "goal_type": "scale",
                "current_value": 5,
                "target_value": 10,
                "is_active": True,
            }
        ]
        lines = self.export(items, UTC, default_priority="A")
        self.assertTrue(lines[0].startswith("(A) "))

    def test_syntax_escaping_zwsp(self) -> None:
        items = [
            {
                "id": "esc1",
                "title": "+ImportantProject goal with @ContextTag and due:today and x priority (A)",
                "goal_type": "numeric",
                "current_value": 1,
                "target_value": 2,
            }
        ]
        lines = self.export(items, UTC)
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn(f"{ZWSP}+ImportantProject", line)
        self.assertIn(f"{ZWSP}@ContextTag", line)
        self.assertIn(f"due{ZWSP}:today", line)

    def test_envelope_unwrapping(self) -> None:
        test_payloads = [
            {"goals": [{"id": "e1", "title": "Env Goals"}]},
            {"items": [{"id": "e2", "title": "Env Items"}]},
            {"data": [{"id": "e3", "title": "Env Data"}]},
            {"results": [{"id": "e4", "title": "Env Results"}]},
        ]
        for payload in test_payloads:
            src = self.tmp / "env.json"
            dst = self.tmp / "env.txt"
            src.write_text(json.dumps(payload), encoding="utf-8")
            tot, _ = g2todo.convert(src, dst, UTC, force=True)
            self.assertEqual(tot, 1)

    def test_missing_id_synthesis(self) -> None:
        items = [{"title": "Synthetic ID goal", "current_value": 1, "target_value": 2}]
        lines = self.export(items, UTC)
        self.assertEqual(len(lines), 1)
        self.assertIn("omi:goal_", lines[0])

    def test_refuse_overwrite_without_force(self) -> None:
        src = self.tmp / "src.json"
        src.write_text(json.dumps([{"id": "1", "title": "A"}]), encoding="utf-8")
        dst = self.tmp / "existing.txt"
        dst.write_text("existing", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            g2todo.convert(src, dst, UTC, force=False)

        self.assertEqual(dst.read_text(encoding="utf-8"), "existing")

    def test_atomic_write_with_force(self) -> None:
        src = self.tmp / "src.json"
        src.write_text(json.dumps([{"id": "1", "title": "Updated"}]), encoding="utf-8")
        dst = self.tmp / "existing.txt"
        dst.write_text("existing", encoding="utf-8")

        tot, _ = g2todo.convert(src, dst, UTC, force=True)
        self.assertEqual(tot, 1)
        self.assertIn("Updated", dst.read_text(encoding="utf-8"))

    def test_symlink_rejection(self) -> None:
        src = self.tmp / "src.json"
        src.write_text(json.dumps([{"id": "1", "title": "A"}]), encoding="utf-8")
        real_dst = self.tmp / "real.txt"
        real_dst.write_text("real", encoding="utf-8")
        link_dst = self.tmp / "link.txt"
        os.symlink(real_dst, link_dst)

        with self.assertRaises(ValueError) as ctx:
            g2todo.convert(src, link_dst, UTC, force=True)
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_path_traversal_guard(self) -> None:
        src = self.tmp / "src.json"
        src.write_text(json.dumps([{"id": "1", "title": "A"}]), encoding="utf-8")
        with self.assertRaises(ValueError):
            g2todo.convert(src, "../evil.txt", UTC)

    def test_timezone_date_rollover(self) -> None:
        items = [
            {
                "id": "tz1",
                "title": "Night owl goal",
                "created_at": "2026-09-30T23:30:00Z",
            }
        ]
        # At UTC, it's 2026-09-30
        lines_utc = self.export(items, UTC)
        self.assertIn("2026-09-30", lines_utc[0])

        # At JST (+09:00), it's 2026-10-01 08:30:00
        lines_jst = self.export(items, JST)
        self.assertIn("2026-10-01", lines_jst[0])

    def test_nan_and_inf_defense(self) -> None:
        items = [
            {
                "id": "nan_inf",
                "title": "Extreme numbers",
                "current_value": float("nan"),
                "target_value": float("inf"),
            }
        ]
        lines = self.export(items, UTC)
        self.assertEqual(len(lines), 1)
        self.assertIn("cur:0 target:0 pct:0%", lines[0])

    def test_overflow_defense(self) -> None:
        large_val = "1" + "0" * 400
        items = [
            {
                "id": "overflow",
                "title": "Huge numbers",
                "current_value": large_val,
                "target_value": large_val,
            }
        ]
        lines = self.export(items, UTC)
        self.assertEqual(len(lines), 1)
        self.assertIn("cur:0 target:0 pct:0%", lines[0])

    def test_cli_stdin_to_stdout_streaming(self) -> None:
        raw_json = json.dumps([{"id": "pipe_g", "title": "Piped Goal", "current_value": 5, "target_value": 10}])
        saved_stdin = sys.stdin
        saved_stdout = sys.stdout
        saved_argv = sys.argv
        try:
            sys.stdin = io.StringIO(raw_json)
            sys.stdout = io.StringIO()
            sys.argv = ["goals_to_todotxt.py", "-", "-"]
            g2todo.main()
            output = sys.stdout.getvalue()
            self.assertIn("Piped Goal", output)
            self.assertIn("omi:pipe_g", output)
        finally:
            sys.stdin = saved_stdin
            sys.stdout = saved_stdout
            sys.argv = saved_argv

    def test_cli_file_execution(self) -> None:
        src = self.tmp / "goals.json"
        dst = self.tmp / "out_todo.txt"
        src.write_text(json.dumps([{"id": "c1", "title": "CLI Goal"}]), encoding="utf-8")

        saved_argv = sys.argv
        try:
            sys.argv = [
                "goals_to_todotxt.py",
                str(src),
                str(dst),
                "--utc-offset",
                "+02:00",
                "--priority",
                "A",
            ]
            g2todo.main()
        finally:
            sys.argv = saved_argv

        self.assertTrue(dst.exists())
        content = dst.read_text(encoding="utf-8")
        self.assertIn("(A) ", content)
        self.assertIn("CLI Goal", content)


if __name__ == "__main__":
    unittest.main()
