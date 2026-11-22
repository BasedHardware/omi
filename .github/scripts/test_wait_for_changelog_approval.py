#!/usr/bin/env python3
"""Behavioral tests for the bounded changelog approval wait (SCA-3432).

The hourly desktop candidate planner admin-merges its changelog-sync PR, and the
`UI author approval` ruleset check is posted asynchronously. These tests pin the
replacement contract: wait on the exact head, fail closed on timeout, rejection,
an unreadable status or a changed head, and never reach a merge or a tag from a
failed wait.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/wait-for-changelog-approval.py"
WORKFLOW = ROOT / ".github/workflows/desktop_auto_release.yml"

SPEC = importlib.util.spec_from_file_location("wait_for_changelog_approval", SCRIPT)
assert SPEC and SPEC.loader
waiter = importlib.util.module_from_spec(SPEC)
sys.modules["wait_for_changelog_approval"] = waiter
SPEC.loader.exec_module(waiter)

HEAD = "1" * 40
OTHER_HEAD = "2" * 40
BASE = "3" * 40
OTHER_BASE = "4" * 40
PR_URL = "https://github.com/BasedHardware/omi/pull/25884"
# #25884: created 2026-11-20T17:14:43Z, status success 17:31:26Z.
OBSERVED_APPROVAL_DELAY_SECONDS = 16 * 60 + 43


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def pull_request(
    *,
    state: str = "open",
    head: str = HEAD,
    base: str = "main",
    url: str = PR_URL,
    number: int = 25884,
) -> waiter.PullRequestSnapshot:
    return waiter.PullRequestSnapshot(
        number=number, url=url, state=state, head_sha=head, base_ref=base
    )


def commit_status(
    state: str,
    *,
    description: str = "",
    creator_id: int | None = waiter.GITHUB_ACTIONS_BOT_ID,
    creator_login: str | None = waiter.GITHUB_ACTIONS_BOT_LOGIN,
) -> waiter.StatusSnapshot:
    return waiter.StatusSnapshot(
        state=state,
        description=description,
        creator_id=creator_id,
        creator_login=creator_login,
        created_at="2026-11-20T17:31:26Z",
    )


class Sequence:
    """Return queued values in order, repeating the last one."""

    def __init__(self, values: list[object]) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        if not self.values:
            raise AssertionError("sequence exhausted")
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


def wait(clock: FakeClock, *, fetch_pr, fetch_status, timeout_seconds: int = 1500, **kwargs):
    return waiter.wait_for_approval(
        repository="BasedHardware/omi",
        pr_number=25884,
        expected_head_sha=HEAD,
        timeout_seconds=timeout_seconds,
        poll_seconds=15,
        fetch_pr=fetch_pr,
        fetch_status=fetch_status,
        fetch_base_sha=kwargs.pop("fetch_base_sha", lambda: BASE),
        clock=clock,
        sleep=clock.sleep,
        log=lambda _message: None,
        **kwargs,
    )


class WaitForChangelogApprovalTests(unittest.TestCase):
    def test_immediate_success_returns_without_sleeping(self) -> None:
        clock = FakeClock()
        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(),
            fetch_status=lambda: commit_status("success", description="approved"),
        )

        self.assertTrue(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_APPROVED)
        self.assertEqual(evidence["attempts"], 1)
        self.assertEqual(clock.sleeps, [])
        self.assertEqual(evidence["expected_head_sha"], HEAD)
        self.assertEqual(evidence["pull_request"]["url"], PR_URL)

    def test_approved_evidence_records_the_authoritative_base(self) -> None:
        clock = FakeClock()
        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(),
            fetch_status=lambda: commit_status("success"),
            fetch_base_sha=lambda: BASE,
        )

        self.assertTrue(evidence["approved"])
        self.assertEqual(evidence["base_ref"], "refs/heads/main")
        self.assertEqual(evidence["base_sha"], BASE)

    def test_unreadable_base_fails_closed(self) -> None:
        clock = FakeClock()

        def unreadable():
            raise waiter.TransientReadError("GitHub API request failed (exit 1): HTTP 502")

        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(),
            fetch_status=lambda: commit_status("success"),
            fetch_base_sha=unreadable,
            max_consecutive_read_errors=3,
        )

        self.assertFalse(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_UNREADABLE)
        self.assertEqual(evidence["base_sha"], "")
        self.assertIn("base ref", evidence["reason"])

    def test_delayed_success_waits_above_the_observed_delay(self) -> None:
        clock = FakeClock()

        def fetch_status():
            if clock.now < OBSERVED_APPROVAL_DELAY_SECONDS:
                return commit_status("pending", description="Checking account-scoped UI approval")
            return commit_status("success", description="UI approval satisfied")

        evidence = wait(clock, fetch_pr=lambda: pull_request(), fetch_status=fetch_status)

        self.assertTrue(evidence["approved"])
        self.assertGreaterEqual(evidence["waited_seconds"], OBSERVED_APPROVAL_DELAY_SECONDS)
        self.assertLess(evidence["waited_seconds"], 1500)
        self.assertGreater(evidence["attempts"], 1)
        self.assertEqual(evidence["status_history"][0]["state"], "pending")
        self.assertEqual(evidence["status_history"][-1]["state"], "success")

    def test_rejected_approval_fails_closed_with_pr_head_and_reason(self) -> None:
        clock = FakeClock()
        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(),
            fetch_status=lambda: commit_status("failure", description="Waiting for Nik or David approval"),
        )

        self.assertFalse(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_REJECTED)
        self.assertEqual(evidence["pull_request"]["url"], PR_URL)
        self.assertEqual(evidence["observed_head_sha"], HEAD)
        self.assertIn("failure", evidence["reason"])

    def test_timeout_fails_closed(self) -> None:
        clock = FakeClock()
        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(),
            fetch_status=lambda: commit_status("pending", description="Checking"),
            timeout_seconds=60,
        )

        self.assertFalse(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_TIMEOUT)
        self.assertGreaterEqual(evidence["waited_seconds"], 60)
        self.assertLess(evidence["waited_seconds"], 75)
        self.assertIn("did not reach success", evidence["reason"])

    def test_changed_head_fails_closed_before_any_merge(self) -> None:
        clock = FakeClock()
        heads = Sequence([pull_request(), pull_request(head=OTHER_HEAD)])
        evidence = wait(
            clock,
            fetch_pr=heads,
            fetch_status=lambda: commit_status("pending", description="Checking"),
        )

        self.assertFalse(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_HEAD_CHANGED)
        self.assertEqual(evidence["observed_head_sha"], OTHER_HEAD)
        self.assertIn(OTHER_HEAD, evidence["reason"])

    def test_unreadable_status_fails_closed_after_bounded_retries(self) -> None:
        clock = FakeClock()

        def unreadable():
            raise waiter.TransientReadError("GitHub API request failed (exit 1): HTTP 502")

        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(),
            fetch_status=unreadable,
            max_consecutive_read_errors=3,
        )

        self.assertFalse(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_UNREADABLE)
        self.assertEqual(evidence["attempts"], 3)
        self.assertIn("HTTP 502", evidence["reason"])

    def test_closed_pull_request_fails_closed(self) -> None:
        clock = FakeClock()
        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(state="closed"),
            fetch_status=lambda: commit_status("success"),
        )

        self.assertFalse(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_PR_NOT_OPEN)

    def test_changed_base_fails_closed(self) -> None:
        clock = FakeClock()
        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(base="release"),
            fetch_status=lambda: commit_status("success"),
        )

        self.assertFalse(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_BASE_CHANGED)

    def test_status_from_an_untrusted_creator_fails_closed(self) -> None:
        clock = FakeClock()
        evidence = wait(
            clock,
            fetch_pr=lambda: pull_request(),
            fetch_status=lambda: commit_status(
                "success", creator_id=1234, creator_login="not-github-actions"
            ),
        )

        self.assertFalse(evidence["approved"])
        self.assertEqual(evidence["outcome"], waiter.OUTCOME_UNTRUSTED)

    def test_main_writes_evidence_and_fails_on_rejection(self) -> None:
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "approval.json"
            output_path = Path(directory) / "github-output"
            output_path.write_text("", encoding="utf-8")
            with (
                patch.object(waiter, "_monotonic", clock),
                patch.object(waiter, "_sleep", clock.sleep),
                patch.object(waiter, "fetch_pull_request", lambda *a, **k: pull_request()),
                patch.object(
                    waiter,
                    "fetch_status",
                    lambda *a, **k: commit_status("failure", description="rejected"),
                ),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                code = waiter.main(
                    [
                        "--repository", "BasedHardware/omi",
                        "--pr-number", "25884",
                        "--expected-head-sha", HEAD,
                        "--timeout-seconds", "60",
                        "--poll-seconds", "15",
                        "--evidence", str(evidence_path),
                        "--github-output",
                    ]
                )

            self.assertEqual(code, 1)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["schema"], waiter.EVIDENCE_SCHEMA)
            self.assertFalse(evidence["approved"])
            self.assertEqual(evidence["outcome"], waiter.OUTCOME_REJECTED)
            self.assertEqual(evidence["pull_request"]["url"], PR_URL)
            self.assertEqual(evidence["observed_head_sha"], HEAD)
            self.assertTrue(evidence["reason"])
            outputs = output_path.read_text(encoding="utf-8")
            self.assertIn("approved=false", outputs)
            self.assertIn(f"head_sha={HEAD}", outputs)

    def test_main_returns_zero_only_for_an_approved_head(self) -> None:
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "approval.json"
            with (
                patch.object(waiter, "_monotonic", clock),
                patch.object(waiter, "_sleep", clock.sleep),
                patch.object(waiter, "fetch_pull_request", lambda *a, **k: pull_request()),
                patch.object(waiter, "fetch_status", lambda *a, **k: commit_status("success")),
                patch.object(waiter, "fetch_base_sha", lambda *a, **k: BASE),
            ):
                code = waiter.main(
                    [
                        "--repository", "BasedHardware/omi",
                        "--pr-number", "25884",
                        "--expected-head-sha", HEAD,
                        "--evidence", str(evidence_path),
                    ]
                )

            self.assertEqual(code, 0)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertTrue(evidence["approved"])
            self.assertEqual(evidence["base_ref"], "refs/heads/main")
            self.assertEqual(evidence["base_sha"], BASE)

    def test_invalid_expected_head_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            waiter.wait_for_approval(
                repository="BasedHardware/omi",
                pr_number=25884,
                expected_head_sha="not-a-sha",
                fetch_pr=lambda: pull_request(),
                fetch_status=lambda: commit_status("success"),
                fetch_base_sha=lambda: BASE,
            )


class WorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.job = self.workflow["jobs"]["plan-and-tag"]
        self.steps = self.job["steps"]
        self.by_name = {step.get("name"): step for step in self.steps}

    def _index(self, name: str) -> int:
        for index, step in enumerate(self.steps):
            if step.get("name") == name:
                return index
        raise AssertionError(f"workflow step not found: {name}")

    def test_wait_precedes_merge_and_publication(self) -> None:
        wait_index = self._index("Wait for UI author approval on the exact changelog head")
        merge_index = self._index("Merge the approved changelog PR at the exact head")
        publish_index = self._index("Publish immutable tag from merged release source")
        self.assertLess(wait_index, merge_index)
        self.assertLess(merge_index, publish_index)

    def test_wait_is_bounded_above_the_observed_delay(self) -> None:
        run = self.by_name["Wait for UI author approval on the exact changelog head"]["run"]
        self.assertIn("wait-for-changelog-approval.py", run)
        self.assertIn('--expected-head-sha "${{ steps.changelog.outputs.commit }}"', run)
        self.assertIn('--context "UI author approval"', run)
        self.assertIn("--timeout-seconds 1500", run)
        self.assertGreater(1500, OBSERVED_APPROVAL_DELAY_SECONDS)

    def test_wait_budget_fits_the_job_timeout_and_token_lifetime(self) -> None:
        job_timeout_seconds = self.job["timeout-minutes"] * 60
        wait_step = self.by_name["Wait for UI author approval on the exact changelog head"]
        # 25-minute wait + 10 minutes of planning/merge/tag/dispatch headroom.
        self.assertLessEqual(1500 + 600, job_timeout_seconds)
        self.assertLessEqual(wait_step["timeout-minutes"] * 60, job_timeout_seconds)
        # create-github-app-token defaults to a 60-minute token.
        self.assertLess(job_timeout_seconds, 60 * 60)

    def test_wait_step_never_merges(self) -> None:
        run = self.by_name["Wait for UI author approval on the exact changelog head"]["run"]
        self.assertNotIn("gh pr merge", run)
        self.assertNotIn("--admin", run)

    def test_wait_reads_statuses_with_a_read_only_workflow_token(self) -> None:
        self.assertEqual(self.workflow["permissions"]["statuses"], "read")
        wait_step = self.by_name["Wait for UI author approval on the exact changelog head"]
        self.assertEqual(wait_step["env"]["GH_TOKEN"], "${{ github.token }}")
        merge_step = self.by_name["Merge the approved changelog PR at the exact head"]
        self.assertEqual(merge_step["env"]["GH_TOKEN"], "${{ steps.app-token.outputs.token }}")

    def test_merge_is_conditional_on_the_same_head(self) -> None:
        step = self.by_name["Merge the approved changelog PR at the exact head"]
        run = step["run"]
        self.assertIn('--match-head-commit "$CHANGELOG_COMMIT"', run)
        self.assertIn('--json state,baseRefName,headRefOid', run)
        self.assertIn('"OPEN main $CHANGELOG_COMMIT"', run)
        self.assertIn('test "$(git rev-parse "${MERGED_MAIN_SHA}^2")" = "$CHANGELOG_COMMIT"', run)
        self.assertIn("needs_merge == 'true'", step["if"])

    def test_merge_compares_every_fresh_base_read_to_the_captured_base(self) -> None:
        step = self.by_name["Merge the approved changelog PR at the exact head"]
        run = step["run"]
        self.assertIn('BASE_SHA="${{ steps.approval.outputs.base_sha }}"', run)
        self.assertIn("git ls-remote origin refs/heads/main", run)
        self.assertIn('if [ "$CURRENT_BASE" != "$BASE_SHA" ]', run)
        self.assertIn("CHANGELOG_MERGE_BASE_MOVED", run)
        # The fresh read must sit inside the retry loop, before each attempt.
        loop = run.split("for attempt in 1 2 3; do", 1)[1].split("done", 1)[0]
        self.assertIn("git ls-remote origin refs/heads/main", loop)
        self.assertIn("gh pr merge", loop)

    def test_merge_checks_the_merge_commit_first_parent_before_tagging(self) -> None:
        step = self.by_name["Merge the approved changelog PR at the exact head"]
        run = step["run"]
        self.assertIn('MERGE_BASE_PARENT=$(git rev-parse "${MERGED_MAIN_SHA}^1")', run)
        self.assertIn('if [ "$MERGE_BASE_PARENT" != "$BASE_SHA" ]', run)
        self.assertIn("CHANGELOG_MERGE_BASE_MISMATCH", run)
        self.assertIn("action=reviewed-revert", run)
        # The first-parent check must precede the tag publication step.
        self.assertLess(
            self._index("Merge the approved changelog PR at the exact head"),
            self._index("Publish immutable tag from merged release source"),
        )

    def test_failed_wait_skips_merge_and_publication(self) -> None:
        for name in (
            "Merge the approved changelog PR at the exact head",
            "Bind immutable planner evidence to merged release source",
            "Publish immutable tag from merged release source",
            "Dispatch or reuse the exact-tag Codemagic build",
        ):
            condition = self.by_name[name].get("if", "")
            self.assertNotIn("always()", condition, name)
            self.assertNotIn("failure()", condition, name)

    def test_approval_evidence_is_retained_on_failure(self) -> None:
        step = self.by_name["Retain changelog approval wait evidence"]
        self.assertIn("always()", step["if"])
        self.assertIn("desktop-changelog-approval-wait.json", step["with"]["path"])


FAKE_GH = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$GH_CALLS"
if [ "$1" = "pr" ] && [ "$2" = "view" ]; then
  case "$*" in
    *state,baseRefName,headRefOid*) printf '%s\\n' "$PR_SNAPSHOT" ;;
    *mergeCommit*) printf '%s\\n' "$MERGE_SHA" ;;
    *--json\\ url*) printf 'https://github.com/BasedHardware/omi/pull/25891\\n' ;;
    *--json\\ state\\ *) printf 'MERGED\\n' ;;
    *) printf '\\n' ;;
  esac
  exit 0
fi
if [ "$1" = "pr" ] && [ "$2" = "merge" ]; then
  : > "$MERGE_MARKER"
  exit 0
fi
exit 0
"""

FAKE_GIT = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$GIT_CALLS"
case "$*" in
  "ls-remote origin refs/heads/main") printf '%s\\trefs/heads/main\\n' "$CURRENT_BASE" ;;
  "rev-parse ${MERGE_SHA}^1") printf '%s\\n' "$MERGE_PARENT" ;;
  "rev-parse ${MERGE_SHA}^2") printf '%s\\n' "$HEAD" ;;
  *) exit 0 ;;
esac
"""


class MergeStepBehaviorTests(unittest.TestCase):
    """Run the merge step's real shell against fake gh/git.

    The regression case is the one the review named: the PR head and base name
    are unchanged, but the branch tip moved, so the merge and tag paths must be
    skipped.
    """

    def _run(
        self,
        *,
        current_base: str,
        merge_parent: str | None = None,
        pr_snapshot: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        step = next(
            item for item in workflow["jobs"]["plan-and-tag"]["steps"]
            if item.get("name") == "Merge the approved changelog PR at the exact head"
        )
        script = (
            step["run"]
            .replace("${{ steps.changelog-pr.outputs.number }}", "25891")
            .replace("${{ steps.changelog.outputs.commit }}", HEAD)
            .replace("${{ steps.approval.outputs.base_sha }}", BASE)
        )
        merge_sha = "5" * 40
        directory = Path(tempfile.mkdtemp())
        bin_dir = directory / "bin"
        bin_dir.mkdir()
        for name, body in (("gh", FAKE_GH), ("git", FAKE_GIT)):
            path = bin_dir / name
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)
        calls = directory / "calls"
        merge_marker = directory / "merged"
        output = directory / "github-output"
        output.write_text("", encoding="utf-8")
        environment = {
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
            "GH_CALLS": str(calls),
            "GIT_CALLS": str(calls),
            "MERGE_MARKER": str(merge_marker),
            "GITHUB_OUTPUT": str(output),
            "PR_SNAPSHOT": pr_snapshot or f"OPEN main {HEAD}",
            "MERGE_SHA": merge_sha,
            "MERGE_PARENT": merge_parent or BASE,
            "CURRENT_BASE": current_base,
            "HEAD": HEAD,
            "BASE": BASE,
        }
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env=environment,
            cwd=directory,
        )
        return result, calls, merge_marker, output

    def test_moved_branch_tip_skips_merge_and_tag(self) -> None:
        result, calls, merge_marker, output = self._run(current_base=OTHER_BASE)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHANGELOG_MERGE_BASE_MOVED", result.stderr)
        self.assertFalse(merge_marker.exists(), "the merge must not run when the base moved")
        self.assertNotIn("pr merge", calls.read_text(encoding="utf-8"))
        self.assertNotIn("merged_main_sha", output.read_text(encoding="utf-8"))

    def test_changed_pr_base_name_skips_merge_and_tag(self) -> None:
        result, calls, merge_marker, output = self._run(
            current_base=BASE, pr_snapshot=f"OPEN release {HEAD}"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHANGELOG_MERGE_PRECONDITION_CHANGED", result.stderr)
        self.assertFalse(merge_marker.exists())
        self.assertNotIn("pr merge", calls.read_text(encoding="utf-8"))
        self.assertNotIn("merged_main_sha", output.read_text(encoding="utf-8"))

    def test_merge_commit_first_parent_mismatch_skips_tag(self) -> None:
        result, _, merge_marker, output = self._run(
            current_base=BASE, merge_parent=OTHER_BASE
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHANGELOG_MERGE_BASE_MISMATCH", result.stderr)
        self.assertIn("action=reviewed-revert", result.stderr)
        self.assertTrue(merge_marker.exists(), "the merge itself already happened")
        self.assertNotIn("merged_main_sha", output.read_text(encoding="utf-8"))

    def test_matching_base_and_parent_publishes_merge_evidence(self) -> None:
        result, _, merge_marker, output = self._run(current_base=BASE, merge_parent=BASE)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(merge_marker.exists())
        written = output.read_text(encoding="utf-8")
        self.assertIn(f"merged_main_sha={'5' * 40}", written)
        self.assertIn(f"base_sha={BASE}", written)


if __name__ == "__main__":
    unittest.main()
