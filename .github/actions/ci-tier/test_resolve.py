#!/usr/bin/env python3
"""Exercise the live tier lookup and its fail-closed behavior."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("resolve.sh")
MOBILE_WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/mobile-app-checks.yml"


class CITierTests(unittest.TestCase):
    def resolve(self, event: str, head: str, labels: str = "", fail: bool = False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            calls = root / "calls"
            gh = root / "gh"
            gh.write_text("#!/bin/sh\n"
                          "printf '%s\\n' \"$*\" >> \"$FAKE_CALLS\"\n"
                          + ("exit 1\n" if fail else "printf '%s\\n' \"$FAKE_LABELS\"\n"))
            gh.chmod(0o755)
            output = root / "output"
            env = dict(os.environ, EVENT_NAME=event, REPO="BasedHardware/omi",
                       HEAD_REPO=head, PR_NUMBER="123", GH_TOKEN="fixture-token",
                       GITHUB_OUTPUT=str(output), FAKE_CALLS=str(calls),
                       FAKE_LABELS=labels, PATH=f"{root}:{os.environ['PATH']}")
            result = subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True)
            return result, output.read_text(), calls.read_text().splitlines() if calls.exists() else []

    def test_internal_and_non_pr_are_full_without_api(self):
        for event, head in (("pull_request", "BasedHardware/omi"), ("push", "other/fork")):
            result, output, calls = self.resolve(event, head)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(output, "full_ci=true\n")
            self.assertEqual(calls, [])

    def test_fork_uses_one_current_label_read(self):
        result, output, calls = self.resolve("pull_request", "other/fork", "other\nci:full")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(output, "full_ci=true\n")
        self.assertEqual(len(calls), 1)
        self.assertIn("repos/BasedHardware/omi/issues/123/labels", calls[0])

    def test_fork_without_label_or_failed_lookup_stays_cheap(self):
        for fail in (False, True):
            result, output, calls = self.resolve("pull_request", "other/fork", "other", fail)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(output, "full_ci=false\n")
            self.assertEqual(len(calls), 1)
            if fail:
                self.assertIn("could not be read", result.stderr)

    def test_mobile_aggregate_defers_only_affected_forks(self):
        lines = MOBILE_WORKFLOW.read_text().splitlines()
        start = lines.index("      - name: Aggregate conditional mobile checks")
        body_start = lines.index("        run: |", start) + 1
        body = []
        for line in lines[body_start:]:
            if line and not line.startswith("          "):
                break
            body.append(line[10:] if line else "")
        script = "\n".join(body)
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, CHANGES_RESULT="success", FULL_CI="false",
                       HAS_GENERATED="false", HAS_DART="false", HAS_JOURNEYS="false",
                       HAS_ANDROID="false", HAS_IOS="false", GITHUB_STEP_SUMMARY=str(Path(temp) / "summary"))
            result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no mobile heavy checks selected", result.stdout)
            env["HAS_DART"] = "true"
            result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("a maintainer adds label ci:full, then Re-run all jobs", result.stderr)


if __name__ == "__main__":
    unittest.main()
