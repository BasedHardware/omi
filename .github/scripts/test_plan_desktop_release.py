#!/usr/bin/env python3
"""Regression tests for the automatic desktop candidate gate."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("plan-desktop-release.py")
WORKFLOW = Path(__file__).parents[1] / "workflows" / "desktop_auto_release.yml"
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("plan_desktop_release", SCRIPT)
assert SPEC and SPEC.loader
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)

REPOSITORY = "BasedHardware/omi"
SOURCE_SHA = "a" * 40
LATER_NON_DESKTOP_SHA = "b" * 40
LATEST_TAG = "v0.0.1+1-macos"
RELEASABLE_PATH = "desktop/macos/Desktop/Sources/AppDelegate.swift"
QUALIFICATION_LIFECYCLE_PATH = "scripts/dev-harness/dev_harness/qualification.py"
UNRELATED_DEV_HARNESS_PATH = "scripts/dev-harness/dev_harness/config.py"


def _parse_push_filter(workflow_text: str) -> tuple[list[str], set[str]]:
    """Extract `on.push.branches` and `on.push.paths` from the release workflow.

    A deliberately small parser for the workflow's fixed shape (a `push:` block
    with an inline `branches: [main]` and a `paths:` list of single-quoted
    strings), so the check needs no PyYAML in any lane. Raises if the expected
    structure is missing rather than silently returning empty results.
    """
    lines = workflow_text.splitlines()
    branches: list[str] = []
    paths: set[str] = set()
    in_push = False
    in_paths = False
    for raw in lines:
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip(" "))
        if indent <= 2 and stripped.endswith(":") and stripped != "push:":
            # Left the push block on any sibling/parent key (e.g. schedule:).
            if in_push and indent <= 2:
                in_push = False
            in_paths = False
        if stripped == "push:":
            in_push = True
            continue
        if not in_push:
            continue
        if stripped.startswith("branches:"):
            inside = stripped.split("branches:", 1)[1].strip().strip("[]")
            branches = [b.strip().strip("'\"") for b in inside.split(",") if b.strip()]
            in_paths = False
        elif stripped == "paths:":
            in_paths = True
        elif in_paths and stripped.startswith("- "):
            paths.add(stripped[2:].strip().strip("'\""))
        elif in_paths and not stripped.startswith("- ") and stripped:
            in_paths = False
    if not branches or not paths:
        raise AssertionError("Could not parse push.branches/push.paths from desktop_auto_release.yml")
    return branches, paths


class DesktopCandidateSourceCheckTests(unittest.TestCase):
    def test_github_check_status_reads_all_exact_sha_runs_and_chooses_the_newest_match(self) -> None:
        response = [
            {
                "check_runs": [
                    {
                        "id": 101,
                        "name": "Release Eligibility",
                        "status": "completed",
                        "conclusion": "failure",
                        "started_at": "2026-07-25T21:00:00Z",
                        "completed_at": "2026-07-25T21:02:00Z",
                    },
                    {
                        "id": 102,
                        "name": "Unrelated check",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-07-25T21:03:00Z",
                        "completed_at": "2026-07-25T21:04:00Z",
                    },
                ]
            },
            {
                "check_runs": [
                    {
                        "id": 103,
                        "name": "Release Eligibility",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-07-25T21:28:00Z",
                        "completed_at": "2026-07-25T21:28:16Z",
                    }
                ]
            },
        ]
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(response), stderr="")

        with patch.object(planner.subprocess, "run", return_value=completed) as run:
            status, conclusion, error = planner.github_check_status(REPOSITORY, SOURCE_SHA, "Release Eligibility")

        self.assertEqual((status, conclusion, error), ("completed", "success", None))
        run.assert_called_once_with(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{REPOSITORY}/commits/{SOURCE_SHA}/check-runs?filter=all&per_page=100",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_github_check_status_uses_numeric_id_to_break_timestamp_ties(self) -> None:
        response = [
            {
                "check_runs": [
                    {
                        "id": 99_999_999_999,
                        "name": "Release Eligibility",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-07-25T21:28:00Z",
                        "completed_at": "2026-07-25T21:28:16Z",
                    },
                    {
                        "id": 100_000_000_000,
                        "name": "Release Eligibility",
                        "status": "completed",
                        "conclusion": "failure",
                        "started_at": "2026-07-25T21:28:00Z",
                        "completed_at": "2026-07-25T21:28:16Z",
                    },
                ]
            }
        ]
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(response), stderr="")

        with patch.object(planner.subprocess, "run", return_value=completed):
            status, conclusion, error = planner.github_check_status(REPOSITORY, SOURCE_SHA, "Release Eligibility")

        self.assertEqual((status, conclusion, error), ("completed", "failure", None))

    def test_codemagic_config_is_a_releasable_desktop_input(self) -> None:
        expected_args = [
            "diff",
            "--name-only",
            "--diff-filter=ACDMR",
            f"{LATEST_TAG}..HEAD",
            "--",
            "desktop/macos",
            "codemagic.yaml",
            QUALIFICATION_LIFECYCLE_PATH,
            ".github/scripts/plan-desktop-release.py",
            ".github/scripts/desktop-release-source-identity.py",
            ".github/scripts/publish-desktop-candidate-tag.py",
            ".github/scripts/verify-pre-tag-readiness.py",
            ".github/workflows/desktop_auto_release.yml",
            ".github/workflows/desktop_qualify_beta.yml",
            ".github/workflows/desktop-swift-ci.yml",
        ]

        with patch.object(planner, "git", return_value="codemagic.yaml\ndesktop/macos/AGENTS.md") as git:
            changes = planner.releasable_desktop_changes_since(LATEST_TAG)

        git.assert_called_once_with(expected_args)
        self.assertEqual(changes, ["codemagic.yaml"])

    def test_qualification_lifecycle_change_after_latest_tag_creates_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "git", return_value=QUALIFICATION_LIFECYCLE_PATH) as git,
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(planner, "wait_for_required_source_checks", return_value=planner.SourceCheckGate("ready")) as wait,
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        git.assert_called_once_with(
            [
                "diff",
                "--name-only",
                "--diff-filter=ACDMR",
                f"{LATEST_TAG}..HEAD",
                "--",
                *planner.DESKTOP_RELEASE_PATHS,
            ]
        )
        wait.assert_called_once_with(
            REPOSITORY,
            SOURCE_SHA,
            wait_seconds=planner.SOURCE_CHECK_WAIT_SECONDS,
            poll_seconds=planner.SOURCE_CHECK_POLL_SECONDS,
        )
        self.assertIn(f"source_sha={SOURCE_SHA}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_unrelated_dev_harness_change_after_latest_tag_does_not_create_candidate(self) -> None:
        git_calls: list[list[str]] = []

        def scoped_git(args: list[str], *, check: bool = True) -> str:
            git_calls.append(args)
            if args[0] == "diff":
                # Model Git's pathspec filtering: config.py changed, but it is
                # absent from the planner's release scope and therefore cannot
                # appear in the diff result.
                return UNRELATED_DEV_HARNESS_PATH if UNRELATED_DEV_HARNESS_PATH in args else ""
            self.fail(f"unexpected git invocation: {args}")

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "git", side_effect=scoped_git),
                patch.object(planner, "wait_for_required_source_checks") as wait,
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertEqual(
            git_calls,
            [
                [
                    "diff",
                    "--name-only",
                    "--diff-filter=ACDMR",
                    f"{LATEST_TAG}..HEAD",
                    "--",
                    *planner.DESKTOP_RELEASE_PATHS,
                ]
            ],
        )
        wait.assert_not_called()
        self.assertIn("source_sha=", outputs)
        self.assertIn("should_release=false", outputs)
        self.assertIn("No releasable desktop app changes", outputs)

    def test_exact_source_sha_success_for_every_required_check_passes_the_gate(self) -> None:
        checked: list[tuple[str, str]] = []

        def successful_check(_repository: str, sha: str, check_name: str):
            checked.append((sha, check_name))
            return "completed", "success", None

        with patch.object(planner, "github_check_status", side_effect=successful_check):
            gate = planner.required_source_checks_gate(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "ready")

        self.assertEqual(
            checked,
            [(SOURCE_SHA, check_name) for check_name in planner.REQUIRED_SOURCE_CHECK_NAMES],
        )

    def test_missing_or_nonterminal_exact_source_checks_wait_for_re_evaluation(self) -> None:
        for blocked_name in (
            "Release Eligibility",
            "Desktop Swift Build & Tests",
            "Desktop Swift Release Compile",
        ):
            for blocked_status, blocked_conclusion, expected in (
                (None, None, "missing"),
                ("in_progress", None, "in_progress"),
            ):
                with self.subTest(check=blocked_name, conclusion=blocked_conclusion):

                    def check_status(_repository: str, _sha: str, check_name: str):
                        if check_name == blocked_name:
                            return blocked_status, blocked_conclusion, None
                        return "completed", "success", None

                    with patch.object(planner, "github_check_status", side_effect=check_status):
                        gate = planner.required_source_checks_gate(REPOSITORY, SOURCE_SHA)
                    self.assertEqual(gate.state, "waiting")
                    self.assertIn(blocked_name, gate.reason or "")
                    self.assertIn(expected, gate.reason or "")

    def test_failed_exact_source_check_blocks_the_gate(self) -> None:
        for blocked_conclusion in ("skipped", "failure", "cancelled"):
            with self.subTest(conclusion=blocked_conclusion):

                def check_status(_repository: str, _sha: str, check_name: str):
                    if check_name == "Desktop Swift Build & Tests":
                        return "completed", blocked_conclusion, None
                    return "completed", "success", None

                with patch.object(planner, "github_check_status", side_effect=check_status):
                    gate = planner.required_source_checks_gate(REPOSITORY, SOURCE_SHA)
                self.assertEqual(gate.state, "blocked")
                self.assertIn("Desktop Swift Build & Tests", gate.reason or "")
                self.assertIn(blocked_conclusion, gate.reason or "")

    def test_transient_check_state_is_bounded_then_times_out_as_blocked(self) -> None:
        waiting = planner.SourceCheckGate("waiting", "required check is missing for exact source SHA")
        with (
            patch.object(planner, "required_source_checks_gate", return_value=waiting) as gate,
            patch.object(planner.time, "monotonic", side_effect=(100, 100, 121)),
            patch.object(planner.time, "sleep") as sleep,
        ):
            result = planner.wait_for_required_source_checks(REPOSITORY, SOURCE_SHA, wait_seconds=20, poll_seconds=10)

        self.assertEqual(result.state, "blocked")
        self.assertIn("timed out after 20s", result.reason or "")
        sleep.assert_called_once_with(10)
        # Initial probe + post-sleep probe + final re-check before timeout.
        self.assertEqual(gate.call_count, 3)

    def test_timeout_final_recheck_admits_late_exact_sha_success(self) -> None:
        waiting = planner.SourceCheckGate("waiting", "required check is missing for exact source SHA")
        ready = planner.SourceCheckGate("ready")
        with (
            patch.object(
                planner,
                "required_source_checks_gate",
                side_effect=(waiting, waiting, ready),
            ),
            patch.object(planner.time, "monotonic", side_effect=(100, 100, 121)),
            patch.object(planner.time, "sleep"),
        ):
            gate = planner.wait_for_required_source_checks(REPOSITORY, SOURCE_SHA, wait_seconds=20, poll_seconds=10)

        self.assertEqual(gate.state, "ready")

    def test_ci_gate_timeout_env_overrides_default_wait_budget(self) -> None:
        with patch.dict(os.environ, {planner.CI_GATE_TIMEOUT_ENV: "4500"}, clear=False):
            self.assertEqual(planner.default_source_check_wait_seconds(), 4500)
        with patch.dict(os.environ, {planner.CI_GATE_TIMEOUT_ENV: ""}, clear=False):
            self.assertEqual(planner.default_source_check_wait_seconds(), planner.SOURCE_CHECK_WAIT_SECONDS)

    def test_extended_wait_admits_observed_late_exact_sha_success(self) -> None:
        # Run 30179919353 timed out at the former 12-minute boundary, then its
        # final exact-SHA aggregate completed successfully 5m40s later. Model
        # that state transition through the production polling seam: a failed
        # check would still return "blocked" immediately (covered above).
        observed_success_after_seconds = 12 * 60 + 5 * 60 + 40
        elapsed_seconds = 0

        def monotonic() -> int:
            return elapsed_seconds

        def sleep(seconds: int) -> None:
            nonlocal elapsed_seconds
            elapsed_seconds += seconds

        def source_checks(_repository: str, _sha: str) -> planner.SourceCheckGate:
            if elapsed_seconds >= observed_success_after_seconds:
                return planner.SourceCheckGate("ready")
            return planner.SourceCheckGate("waiting", "Desktop Swift Build & Tests is in_progress")

        with (
            patch.object(planner, "required_source_checks_gate", side_effect=source_checks),
            patch.object(planner.time, "monotonic", side_effect=monotonic),
            patch.object(planner.time, "sleep", side_effect=sleep) as poll,
        ):
            gate = planner.wait_for_required_source_checks(
                REPOSITORY,
                SOURCE_SHA,
                wait_seconds=planner.SOURCE_CHECK_WAIT_SECONDS,
                poll_seconds=planner.SOURCE_CHECK_POLL_SECONDS,
            )

        self.assertEqual(gate.state, "ready")
        self.assertGreater(elapsed_seconds, observed_success_after_seconds)
        self.assertLess(elapsed_seconds, planner.SOURCE_CHECK_WAIT_SECONDS)
        self.assertEqual(poll.call_args_list[-1].args, (planner.SOURCE_CHECK_POLL_SECONDS,))

    def test_existing_exact_source_tag_preserves_active_or_published_candidate(self) -> None:
        for lifecycle in ("active", "published"):
            with self.subTest(lifecycle=lifecycle):
                with (
                    patch.object(planner, "candidate_tags_for_source", return_value=[LATEST_TAG]),
                    patch.object(
                        planner,
                        "normal_candidate_lifecycle",
                        return_value=(lifecycle, f"normal candidate is {lifecycle}"),
                    ),
                ):
                    reason = planner.existing_source_candidate_reason(REPOSITORY, SOURCE_SHA)

                self.assertIn(LATEST_TAG, reason or "")
                self.assertIn("already owns exact source SHA", reason or "")
                self.assertIn(lifecycle, reason or "")

    def test_backend_or_docs_commit_after_desktop_commit_keeps_exact_releasable_source(self) -> None:
        checked_shas: list[str] = []

        def fake_git(args: list[str], *, check: bool = True) -> str:
            if args == ["rev-parse", "HEAD"]:
                return LATER_NON_DESKTOP_SHA
            if args == ["log", "--first-parent", "-1", "--format=%H", "HEAD", "--", RELEASABLE_PATH]:
                return SOURCE_SHA
            self.fail(f"unexpected git invocation: {args}")

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "git", side_effect=fake_git),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "wait_for_required_source_checks",
                    side_effect=lambda _, sha, **__: checked_shas.append(sha) or planner.SourceCheckGate("ready"),
                ),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertEqual(checked_shas, [SOURCE_SHA])
        self.assertIn(f"source_sha={SOURCE_SHA}", outputs)
        self.assertNotIn(f"source_sha={LATER_NON_DESKTOP_SHA}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_duplicate_planner_invocation_does_not_create_another_tag_for_the_same_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(
                    planner,
                    "candidate_tags_for_source",
                    return_value=[LATEST_TAG],
                ),
                patch.object(planner, "normal_candidate_lifecycle", return_value=("active", "candidate is active")),
                patch.object(planner, "wait_for_required_source_checks") as wait,
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        wait.assert_not_called()
        self.assertIn("should_release=false", outputs)
        self.assertIn("Desktop candidate already exists", outputs)
        self.assertIn(LATEST_TAG, outputs)

    def test_read_only_status_watcher_reports_only_lifecycle_transitions(self) -> None:
        observations = [
            ("waiting", "", "no immutable candidate tag exists"),
            ("waiting", "", "no immutable candidate tag exists"),
            ("active", LATEST_TAG, "Release OMI Desktop (Swift) is in_progress"),
        ]
        output = io.StringIO()
        with (
            patch.object(planner, "source_candidate_status", side_effect=observations),
            patch.object(planner.time, "sleep") as sleep,
            redirect_stdout(output),
        ):
            self.assertEqual(
                planner.watch_source_candidate(REPOSITORY, SOURCE_SHA, max_polls=3, poll_seconds=30),
                0,
            )

        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("lifecycle=waiting", lines[0])
        self.assertIn("lifecycle=active", lines[1])
        self.assertIn(LATEST_TAG, lines[1])
        self.assertEqual(sleep.call_args_list, [((30,), {}), ((30,), {})])

    def test_workflow_has_no_input_manual_trigger_and_tags_only_the_merged_main_source(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        # Candidate publication is the hourly schedule plus bare manual
        # dispatch. Per-merge push tagging stays retired so merges no longer
        # mint a new macOS version tag per CI run, and workflow_dispatch stays
        # bare (no manual inputs) — the schedule/dispatch split is expressed as
        # the planner's --min-tag-interval-seconds argument instead.
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertNotIn("inputs:", workflow.split("\njobs:", 1)[0])
        trigger = workflow.split("\njobs:", 1)[0]
        self.assertNotIn("\n  push:", trigger)
        self.assertNotIn("break_glass", workflow)
        self.assertIn("source_sha: ${{ steps.plan.outputs.source_sha }}", workflow)
        self.assertIn("ref: ${{ steps.recheck.outputs.source_sha }}", workflow)
        self.assertEqual(planner.SOURCE_CHECK_WAIT_SECONDS, 60 * 60)
        self.assertGreaterEqual(planner.SOURCE_CHECK_WAIT_SECONDS, 45 * 60)
        self.assertEqual(workflow.count('--source-check-wait-seconds "${CI_GATE_TIMEOUT_SECONDS}"'), 3)
        self.assertEqual(workflow.count("--source-check-poll-seconds 30"), 3)
        self.assertIn("CI_GATE_TIMEOUT_SECONDS:", workflow)
        self.assertIn("vars.DESKTOP_CI_GATE_TIMEOUT_SECONDS || '3600'", workflow)
        self.assertIn("timeout-minutes: 75", workflow)
        self.assertIn("Surface planner non-release decision", workflow)
        self.assertIn("::error::Desktop release planner blocked:", workflow)
        self.assertIn("::warning::Desktop release planner skipped tagging:", workflow)
        self.assertIn('if: steps.plan.outputs.should_release != \'true\'', workflow)
        self.assertLess(
            workflow.index("Create and regular-merge PR to sync changelog back to main"),
            workflow.index("Publish immutable tag from exact live main source"),
        )
        self.assertIn("Replan release source after changelog sync", workflow)
        self.assertIn("git checkout --detach origin/main", workflow)
        self.assertIn('SHOULD_RELEASE="${{ steps.replan.outputs.should_release }}"', workflow)
        self.assertIn('PLANNED_SOURCE_SHA="${{ steps.final-plan.outputs.source_sha }}"', workflow)
        self.assertIn("if: steps.final-plan.outputs.should_release == 'true'", workflow)
        self.assertIn('git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main', workflow)
        self.assertEqual(workflow.count('CANDIDATE_SHA="$MAIN_SHA"'), 2)
        self.assertIn('BRANCH="changelog/v${VERSION}-${PLANNED_SOURCE_SHA:0:12}"', workflow)
        self.assertIn('CHANGELOG_PARENT_SHA="$(git rev-parse "${CHANGELOG_COMMIT}^1")"', workflow)
        self.assertEqual(workflow.count('--release-tag "$RELEASE_TAG"'), 3)
        self.assertIn('--changelog-parent-sha "$CHANGELOG_PARENT_SHA"', workflow)
        self.assertIn('python3 .github/scripts/publish-desktop-candidate-tag.py', workflow)
        self.assertIn('test "$(git rev-parse "$RELEASE_TAG^{commit}")" = "$CANDIDATE_SHA"', workflow)

    def test_tag_release_runs_readiness_verification_and_publish_in_one_m1_transaction(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("pre-tag-readiness:\n", workflow)
        self.assertNotIn("needs: pre-tag-readiness", workflow)
        tag_release = workflow.split("\n  tag-release:\n", 1)[1]
        self.assertIn("runs-on: [self-hosted, macos, omi-desktop-qualification, omi-qual-m1-studio]", tag_release)
        self.assertIn("group: desktop-auto-release-tag-main", tag_release)
        self.assertIn("cancel-in-progress: false", tag_release)
        self.assertIn("desktop/macos/scripts/pre-tag-readiness.sh", tag_release)
        self.assertIn(".github/scripts/verify-pre-tag-readiness.py verify", tag_release)
        self.assertIn(".github/scripts/publish-desktop-candidate-tag.py", tag_release)
        self.assertLess(tag_release.index("Bind immutable planner evidence to fresh main"), tag_release.index("pre-tag-readiness.sh"))
        self.assertLess(tag_release.index("pre-tag-readiness.sh"), tag_release.index("verify-pre-tag-readiness.py verify"))
        self.assertLess(tag_release.index("verify-pre-tag-readiness.py verify"), tag_release.index("publish-desktop-candidate-tag.py"))
        self.assertIn("if: always()", tag_release)
        self.assertIn("desktop-pre-tag-readiness", tag_release)

    def test_auto_release_is_an_hourly_train_plus_manual_dispatch(self) -> None:
        # Candidate tags fire from the hourly schedule (throttled by the
        # planner's --min-tag-interval-seconds so at most one candidate ships
        # per hour) and from deliberate workflow_dispatch (immediate — the
        # emergency lane #11374 relied on). Per-merge push tagging stays gone.
        workflow = WORKFLOW.read_text(encoding="utf-8")
        trigger = workflow.split("\njobs:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertIn("schedule:", trigger)
        self.assertIn('cron: "7 * * * *"', trigger)
        self.assertNotIn("\n  push:", trigger)
        with self.assertRaises(AssertionError):
            _parse_push_filter(workflow)
        self.assertIn(
            "--min-tag-interval-seconds \"${{ github.event_name == 'schedule' && '3300' || '0' }}\"",
            workflow,
        )

    def test_hourly_train_defers_while_the_latest_candidate_is_young(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "candidate_publication_age_seconds", return_value=120),
                patch.object(planner, "releasable_desktop_changes_since") as changes,
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), "--repository", REPOSITORY, "--min-tag-interval-seconds", "3300"],
                ),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        changes.assert_not_called()
        self.assertIn("should_release=false", outputs)
        self.assertIn("Hourly release train", outputs)

    def test_train_throttle_reads_release_publication_time_not_commit_time(self) -> None:
        # Candidate tags are lightweight: a tag pushed minutes ago onto an old
        # commit has an old `git log --format=%ct` answer, which would defeat
        # the throttle. The clock is the release's createdAt, and the commit
        # time must never be consulted.
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            release_json = json.dumps(
                {
                    "tagName": LATEST_TAG,
                    "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            )
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=release_json, stderr="")
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner.subprocess, "run", return_value=completed),
                patch.object(planner, "tag_age_seconds") as commit_age,
                patch.object(planner, "releasable_desktop_changes_since") as changes,
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), "--repository", REPOSITORY, "--min-tag-interval-seconds", "3300"],
                ),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        commit_age.assert_not_called()
        changes.assert_not_called()
        self.assertIn("should_release=false", outputs)
        self.assertIn("Hourly release train", outputs)

    def test_train_throttle_stands_aside_when_the_candidate_has_no_release(self) -> None:
        # No release for the latest tag = build in flight (the one-active-release
        # fence owns it) or a failed build the train should replace.
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "candidate_publication_age_seconds", return_value=None),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[]),
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), "--repository", REPOSITORY, "--min-tag-interval-seconds", "3300"],
                ),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertNotIn("Hourly release train", outputs)
        self.assertIn("No releasable desktop app changes", outputs)

    def test_manual_dispatch_ignores_the_train_interval(self) -> None:
        # --min-tag-interval-seconds defaults to 0: a fresh candidate never
        # defers a deliberate dispatch.
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "candidate_publication_age_seconds", return_value=1) as age,
                patch.object(planner, "releasable_desktop_changes_since", return_value=[]),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        age.assert_not_called()
        self.assertNotIn("Hourly release train", outputs)

    def test_blocked_newest_sha_falls_back_to_the_newest_green_releasable_sha(self) -> None:
        fallback_sha = "b" * 40
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=["desktop/macos/a.swift"]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "wait_for_required_source_checks",
                    return_value=planner.SourceCheckGate("blocked", "required check failed"),
                ),
                patch.object(planner, "releasable_desktop_shas_since", return_value=[SOURCE_SHA, fallback_sha]),
                patch.object(
                    planner,
                    "required_source_checks_gate",
                    return_value=planner.SourceCheckGate("ready"),
                ),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn(f"source_sha={fallback_sha}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_blocked_newest_sha_without_a_green_fallback_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=["desktop/macos/a.swift"]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "wait_for_required_source_checks",
                    return_value=planner.SourceCheckGate("blocked", "required check failed"),
                ),
                patch.object(planner, "releasable_desktop_shas_since", return_value=[SOURCE_SHA]),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn("should_release=false", outputs)
        self.assertIn("source gate blocked", outputs)


if __name__ == "__main__":
    unittest.main()
