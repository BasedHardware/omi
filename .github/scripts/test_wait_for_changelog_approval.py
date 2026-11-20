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
            self.assertTrue(json.loads(evidence_path.read_text(encoding="utf-8"))["approved"])

    def test_invalid_expected_head_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            waiter.wait_for_approval(
                repository="BasedHardware/omi",
                pr_number=25884,
                expected_head_sha="not-a-sha",
                fetch_pr=lambda: pull_request(),
                fetch_status=lambda: commit_status("success"),
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
        self.assertIn('--json headRefOid', run)
        self.assertIn('test "$(git rev-parse "${MERGED_MAIN_SHA}^2")" = "$CHANGELOG_COMMIT"', run)
        self.assertIn("needs_merge == 'true'", step["if"])

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


if __name__ == "__main__":
    unittest.main()
