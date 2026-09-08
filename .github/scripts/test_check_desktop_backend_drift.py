#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_desktop_backend_drift.py")
SPEC = importlib.util.spec_from_file_location("check_desktop_backend_drift", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ServingShaTests(unittest.TestCase):
    def test_accepts_only_40_lowercase_hex(self) -> None:
        sha = "a" * 40
        self.assertEqual(MODULE.serving_sha({"backend_release_sha": sha}), sha)
        self.assertIsNone(MODULE.serving_sha({"backend_release_sha": "ABC" + "a" * 37}))
        self.assertIsNone(MODULE.serving_sha({"backend_release_sha": "deadbeef"}))
        self.assertIsNone(MODULE.serving_sha({}))
        self.assertIsNone(MODULE.serving_sha({"backend_release_sha": None}))

    def test_unknown_sha_table_omits_deployed_at(self) -> None:
        row = MODULE.ServiceDrift("api-backend", "unknown", None, None, (), True)
        table = MODULE.render_table((row,))
        self.assertIn("`unknown`", table)
        self.assertNotIn("Deployed at", table)

    def test_self_test_mode_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-test"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("self-test OK", result.stdout)

    def test_self_test_mode_ignores_hook_git_dir(self) -> None:
        env = os.environ.copy()
        env["GIT_DIR"] = "/nonexistent/hook.git"
        env["GIT_WORK_TREE"] = "/nonexistent/worktree"
        env["GIT_INDEX_FILE"] = "/nonexistent/index"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-test"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("self-test OK", result.stdout)

    def test_writes_summary_and_exits_zero_without_strict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            summary = Path(raw) / "summary.md"
            desktop = Path(raw) / "desktop.json"
            api = Path(raw) / "api.json"
            desktop.write_text("{}", encoding="utf-8")
            api.write_text(json.dumps({"backend_release_sha": None}), encoding="utf-8")
            code = MODULE.report(
                desktop_health=MODULE._load_json(desktop),
                api_health=MODULE._load_json(api),
                repo=Path(__file__).resolve().parents[2],
                base="HEAD",
                summary_file=summary,
                strict=False,
            )
            self.assertEqual(code, 0)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("Backend drift at promotion", text)
            self.assertIn("`unknown`", text)


if __name__ == "__main__":
    unittest.main()
