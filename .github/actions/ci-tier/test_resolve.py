#!/usr/bin/env python3
"""Exercise the live tier lookup and its fail-closed behavior."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("resolve.sh")
MOBILE_WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/mobile-app-checks.yml"


def workflow_script(step_name: str) -> str:
    lines = MOBILE_WORKFLOW.read_text().splitlines()
    start = lines.index(f"      - name: {step_name}")
    body_start = lines.index("        run: |", start) + 1
    body = []
    for line in lines[body_start:]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:] if line else "")
    return "\n".join(body)


class CITierTests(unittest.TestCase):
    def resolve(self, event: str, head: str, labels: str = "", fail: bool = False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            calls = root / "calls"
            gh = root / "gh"
            gh.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$FAKE_CALLS\"\n"
                + ("exit 1\n" if fail else "printf '%s\\n' \"$FAKE_LABELS\"\n")
            )
            gh.chmod(0o755)
            output = root / "output"
            env = dict(
                os.environ,
                EVENT_NAME=event,
                REPO="BasedHardware/omi",
                HEAD_REPO=head,
                PR_NUMBER="123",
                GH_TOKEN="fixture-token",
                GITHUB_OUTPUT=str(output),
                FAKE_CALLS=str(calls),
                FAKE_LABELS=labels,
                PATH=f"{root}:{os.environ['PATH']}",
            )
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

    def test_mobile_aggregate_requires_selected_dart_on_forks(self):
        script = workflow_script("Aggregate conditional mobile checks")
        with tempfile.TemporaryDirectory() as temp:
            env = dict(
                os.environ,
                CHANGES_RESULT="success",
                FULL_CI="false",
                HAS_GENERATED="false",
                HAS_DART="false",
                DART_EXPECTED="false",
                HAS_JOURNEYS="false",
                HAS_ANDROID="false",
                HAS_IOS="false",
                GENERATED_FILES_RESULT="skipped",
                ANALYZE_AND_TEST_RESULT="skipped",
                DART_TIMEZONE_RESULT="skipped",
                JOURNEYS_RESULT="skipped",
                ANDROID_COMPILE_RESULT="skipped",
                ANDROID_UNIT_RESULT="skipped",
                ANDROID_EMULATOR_RESULT="skipped",
                EMULATOR_EXPECTED="false",
                IOS_COMPILE_RESULT="skipped",
                GITHUB_STEP_SUMMARY=str(Path(temp) / "summary"),
            )
            result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no mobile heavy checks selected", result.stdout)
            env["HAS_DART"] = "true"
            for full_ci in ("false", "true"):
                env["FULL_CI"] = full_ci
                for conclusion in ("skipped", "failure", "cancelled", ""):
                    with self.subTest(full_ci=full_ci, conclusion=conclusion):
                        env["ANALYZE_AND_TEST_RESULT"] = conclusion
                        result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
                        self.assertEqual(result.returncode, 1)
                        self.assertIn("Required Dart Analyze & Tests did not pass", result.stderr)
                env["ANALYZE_AND_TEST_RESULT"] = "success"
                result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                if full_ci == "false":
                    self.assertIn("Dart Analyze & Tests passed", result.stdout)
                    self.assertNotIn("no mobile heavy checks selected", result.stdout)
                    self.assertIn("Dart Analyze & Tests passed", Path(env["GITHUB_STEP_SUMMARY"]).read_text())
            # A cheap-tier fork can still defer expensive jobs after Dart passes.
            env.update(FULL_CI="false", HAS_IOS="true")
            result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("::notice title=Heavy CI deferred::", result.stdout)
            self.assertIn("a maintainer adds label ci:full, then Re-run all jobs", result.stdout)
            self.assertIn("Heavy CI deferred:", Path(env["GITHUB_STEP_SUMMARY"]).read_text())
            # Nightly Dart is required even when the latest commit is unrelated.
            env.update(FULL_CI="true", HAS_IOS="false", HAS_DART="false", DART_EXPECTED="true", ANALYZE_AND_TEST_RESULT="skipped")
            result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Required Dart Analyze & Tests did not pass: skipped", result.stderr)

    def run_issue_bot(self, result: str, expected: str, title: str):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            calls = root / "calls"
            issues = root / "issues.json"
            issues.write_text(json.dumps([{"number": 42, "title": title, "state": "open"}]))
            gh = root / "gh"
            gh.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "with open(os.environ['FAKE_CALLS'], 'a') as output:\n"
                "    output.write(json.dumps(args) + '\\n')\n"
                "path = Path(os.environ['FAKE_ISSUES'])\n"
                "issues = json.loads(path.read_text())\n"
                "if args[0] == 'api':\n"
                "    assert '--paginate' in args and '--slurp' in args\n"
                "    print(json.dumps([[i for i in issues if i['state'] == 'open']]))\n"
                "elif args[:2] == ['issue', 'close']:\n"
                "    for issue in issues:\n"
                "        if str(issue['number']) == args[2]: issue['state'] = 'closed'\n"
                "    path.write_text(json.dumps(issues))\n"
                "else:\n"
                "    raise SystemExit('unexpected gh call: ' + repr(args))\n"
            )
            gh.chmod(0o755)
            env = dict(
                os.environ,
                PATH=f"{root}:{os.environ['PATH']}",
                FAKE_CALLS=str(calls),
                FAKE_ISSUES=str(issues),
                GH_TOKEN="fixture-token",
                REPO="fixture/repo",
                RUN_URL="https://example.invalid/run",
                EVENT="push",
                DART=result,
                DART_EXPECTED=expected,
                JOURNEYS="skipped",
                ANDROID_COMPILE="skipped",
                ANDROID_JVM="skipped",
                ANDROID_EMULATOR="skipped",
                TIMEZONES="skipped",
                JOURNEYS_EXPECTED="false",
                ANDROID_EXPECTED="false",
                TIMEZONES_EXPECTED="false",
            )
            command = subprocess.run(
                ["bash", "-c", workflow_script("Reconcile one issue per mobile suite")],
                env=env, text=True, capture_output=True,
            )
            self.assertEqual(command.returncode, 0, command.stderr)
            recorded_calls = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            return json.loads(issues.read_text()), recorded_calls

    def test_issue_bot_closes_matching_title_on_success(self):
        issues, calls = self.run_issue_bot("success", "true", "CI post-merge failure: Dart Analyze & Tests")
        self.assertEqual(issues[0]["state"], "closed")
        self.assertEqual(calls[-1][:3], ["issue", "close", "42"])

    def test_issue_bot_preserves_issue_on_unselected_skipped_push(self):
        issues, calls = self.run_issue_bot("skipped", "false", "CI post-merge failure: Dart Analyze & Tests")
        self.assertEqual(issues[0]["state"], "open")
        self.assertEqual(calls, [])

    def test_issue_bot_preserves_nonmatching_title(self):
        issues, calls = self.run_issue_bot("success", "true", "CI post-merge failure: Dart Analyze & Tests extra")
        self.assertEqual(issues[0]["state"], "open")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "api")


if __name__ == "__main__":
    unittest.main()
