#!/usr/bin/env python3
"""Offline fixtures for the backend unit selection plan (one plan per run)."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("plan_backend_unit_selection.sh")
SHA = "a" * 40


class PlanTests(unittest.TestCase):
    def plan(self, gh_stdout: str = "", gh_fail: bool = False, **env_overrides):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            calls = root / "calls"
            gh = root / "gh"
            gh.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$FAKE_CALLS\"\n"
                + ("exit 1\n" if gh_fail else "printf '%s\\n' \"$FAKE_STDOUT\"\n")
            )
            gh.chmod(0o755)
            output = root / "output"
            env = dict(
                os.environ,
                REPO="BasedHardware/omi",
                PR_NUMBER="123",
                GH_TOKEN="fixture-token",
                GITHUB_OUTPUT=str(output),
                FAKE_CALLS=str(calls),
                FAKE_STDOUT=gh_stdout,
                PATH=f"{root}:{os.environ['PATH']}",
            )
            for key in ("EVENT_NAME", "REF", "NIGHTLY_MAIN_SHA", "MAIN_SELECTION"):
                env.pop(key, None)
            env.update(env_overrides)
            result = subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            return values, calls.read_text().splitlines() if calls.exists() else []

    def test_nightly_runs_everything_without_api(self):
        values, calls = self.plan(EVENT_NAME="workflow_call", NIGHTLY_MAIN_SHA=SHA)
        self.assertEqual(values["mode"], "all")
        self.assertEqual(calls, [])

    def test_pull_request_selects_unless_ci_full(self):
        values, calls = self.plan(gh_stdout="bug\nsync", EVENT_NAME="pull_request")
        self.assertEqual(values["mode"], "pr")
        self.assertEqual(len(calls), 1)
        values, _ = self.plan(gh_stdout="bug\nci:full", EVENT_NAME="pull_request")
        self.assertEqual(values["mode"], "all")
        self.assertEqual(values["reason"], "ci:full label")

    def test_pull_request_label_failure_keeps_selection(self):
        values, _ = self.plan(gh_fail=True, EVENT_NAME="pull_request")
        self.assertEqual(values["mode"], "pr")

    def test_main_push_diffs_from_last_green_run_with_rotation(self):
        values, calls = self.plan(gh_stdout=f"1203 {SHA}", EVENT_NAME="push", REF="refs/heads/main")
        self.assertEqual(values["mode"], "main")
        self.assertEqual(values["main_base"], SHA)
        self.assertEqual(values["rotation"], "3/8")  # 1203 green main runs % 8
        self.assertIn("status=success", calls[0])
        self.assertIn("event=push", calls[0])

    def test_main_push_falls_back_to_all(self):
        for kwargs in (
            {"gh_fail": True},
            {"gh_stdout": ""},
            {"gh_stdout": "0 "},
            {"gh_stdout": "5 not-a-sha"},
            {"gh_stdout": f"x {SHA}"},
            {"gh_stdout": f"5 {SHA}", "MAIN_SELECTION": "off"},
            {"gh_stdout": f"5 {SHA}", "MAIN_SELECTION": "0"},
        ):
            with self.subTest(kwargs=kwargs):
                values, _ = self.plan(EVENT_NAME="push", REF="refs/heads/main", **kwargs)
                self.assertEqual(values["mode"], "all")

    def test_other_events_run_everything(self):
        for env in ({"EVENT_NAME": "workflow_dispatch"}, {"EVENT_NAME": "push", "REF": "refs/heads/feature"}):
            with self.subTest(env=env):
                values, calls = self.plan(gh_stdout=f"5 {SHA}", **env)
                self.assertEqual(values["mode"], "all")
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
