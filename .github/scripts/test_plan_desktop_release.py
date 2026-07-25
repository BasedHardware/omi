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
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("plan-desktop-release.py")
PUBLISH_SCRIPT = Path(__file__).with_name("publish-desktop-candidate-tag.py")
WORKFLOW = Path(__file__).parents[1] / "workflows" / "desktop_auto_release.yml"
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("plan_desktop_release", SCRIPT)
assert SPEC and SPEC.loader
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)
PUBLISH_SPEC = importlib.util.spec_from_file_location("publish_desktop_candidate_tag", PUBLISH_SCRIPT)
assert PUBLISH_SPEC and PUBLISH_SPEC.loader
publisher = importlib.util.module_from_spec(PUBLISH_SPEC)
PUBLISH_SPEC.loader.exec_module(publisher)

REPOSITORY = "BasedHardware/omi"
SOURCE_SHA = "a" * 40
LATER_NON_DESKTOP_SHA = "b" * 40
LATEST_TAG = "v0.0.1+1-macos"
RELEASABLE_PATH = "desktop/macos/Desktop/Sources/AppDelegate.swift"
PR_NUMBER = 10603
APPROVED_RELEASE_SOURCE_SHA = "79c29fa76e577379812d43b1cfaadc9602cc020a"
DETACHED_CHANGELOG_SHA = "1c58581a124164e94cda66722c5ca4e1a3e409ca"
MERGED_MAIN_SHA = "f48b2ddfbadcac3774366a1884461ef337607da2"
CHANGED_MAIN_SHA = "9" * 40
RELEASE_TAG = "v0.12.124+12124-macos"


class PublicationFixture:
    def __init__(
        self,
        *,
        main_observations: list[str] | None = None,
        pr_state: str = "MERGED",
        merge_sha: str | None = MERGED_MAIN_SHA,
        remote_tag_exists: bool = False,
    ) -> None:
        self.main_observations = iter(main_observations or [MERGED_MAIN_SHA, MERGED_MAIN_SHA])
        self.pr_state = pr_state
        self.merge_sha = merge_sha
        self.remote_tag_exists = remote_tag_exists
        self.calls: list[tuple[list[str], bool]] = []

    def __call__(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, check))
        stdout = ""
        returncode = 0
        if args[:3] == ["gh", "pr", "view"]:
            merge_commit = {"oid": self.merge_sha} if self.merge_sha else None
            stdout = json.dumps({"state": self.pr_state, "mergeCommit": merge_commit})
        elif args == ["git", "rev-parse", "origin/main"]:
            stdout = next(self.main_observations)
        elif args[:2] == ["git", "merge-base"]:
            stdout = APPROVED_RELEASE_SOURCE_SHA
        elif args[:4] == ["git", "ls-remote", "--exit-code", "--tags"]:
            returncode = 0 if self.remote_tag_exists else 2
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    @property
    def commands(self) -> list[list[str]]:
        return [args for args, _check in self.calls]


def ready_gate(_repository: str, _sha: str) -> object:
    return SimpleNamespace(state="ready", reason=None)


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
            ".github/scripts/plan-desktop-release.py",
            ".github/workflows/desktop_auto_release.yml",
            ".github/workflows/desktop-swift-ci.yml",
        ]

        with patch.object(planner, "git", return_value="codemagic.yaml\ndesktop/macos/AGENTS.md") as git:
            changes = planner.releasable_desktop_changes_since(LATEST_TAG)

        git.assert_called_once_with(expected_args)
        self.assertEqual(changes, ["codemagic.yaml"])

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
            patch.object(planner, "required_source_checks_gate", return_value=waiting),
            patch.object(planner.time, "monotonic", side_effect=(100, 100, 121)),
            patch.object(planner.time, "sleep") as sleep,
        ):
            gate = planner.wait_for_required_source_checks(REPOSITORY, SOURCE_SHA, wait_seconds=20, poll_seconds=10)

        self.assertEqual(gate.state, "blocked")
        self.assertIn("timed out after 20s", gate.reason or "")
        sleep.assert_called_once_with(10)

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

    def test_workflow_has_no_input_manual_trigger_and_uses_merged_main_publisher(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        # workflow_dispatch stays bare (no manual inputs). Continuous deployment:
        # auto-release fires on macOS-affecting merges to main (push); the schedule
        # remains a backstop. No `inputs:` may appear in the trigger block.
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertNotIn("inputs:", workflow.split("\njobs:", 1)[0])
        self.assertIn("  push:\n    branches: [main]", workflow)
        self.assertIn("- cron: '*/15 * * * *'", workflow)
        self.assertNotIn("break_glass", workflow)
        self.assertIn("source_sha: ${{ steps.plan.outputs.source_sha }}", workflow)
        self.assertIn("ref: ${{ steps.recheck.outputs.source_sha }}", workflow)
        self.assertEqual(workflow.count("--source-check-wait-seconds 720"), 2)
        self.assertEqual(workflow.count("--source-check-poll-seconds 30"), 2)
        self.assertIn("id: changelog-pr", workflow)
        self.assertIn("python3 .github/scripts/publish-desktop-candidate-tag.py", workflow)
        self.assertIn('--pr-number "${{ steps.changelog-pr.outputs.pr_number }}"', workflow)
        self.assertIn('--approved-source-sha "${{ steps.recheck.outputs.source_sha }}"', workflow)
        self.assertNotIn('git tag "$RELEASE_TAG"', workflow)
        self.assertNotIn('git push origin "$RELEASE_TAG"', workflow)

    def test_candidate_creation_has_no_selfhosted_pre_tag_gate(self) -> None:
        # Continuous deployment: candidate creation (tag-release) must depend only
        # on the hosted planner gate, NOT on a self-hosted pre-candidate readiness
        # job. A self-hosted gate before immutable tag creation was a single point
        # of failure (a down runner blocked ALL releases) and contradicted "create
        # on every change, then qualify". Heavy validation belongs to
        # desktop_qualify_beta.yml, which runs AFTER the candidate exists.
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("pre-tag-readiness:", workflow)
        self.assertNotIn("desktop-pre-tag-readiness-evidence", workflow)
        self.assertNotIn("verify-pre-tag-readiness.py", workflow)
        tag_release = workflow.split("\n  tag-release:\n", 1)[1].split("\n  ", 1)[0]
        self.assertIn("needs: [plan-release]", tag_release)

    def test_push_paths_cover_releasable_desktop_paths(self) -> None:
        # Continuous deployment: every releasable desktop input the planner
        # recognizes must also be in the workflow's push filter, or a merge
        # touching only that input would be releasable yet never get the immediate
        # push trigger (only the schedule backstop would catch it). A directory
        # entry maps to '<dir>/**'.
        #
        # Parse the push filter without PyYAML: this check runs in the `local` and
        # `ci` lanes across environments that do not all ship PyYAML.
        branches, push_paths = _parse_push_filter(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(branches, ["main"])
        for path in planner.DESKTOP_RELEASE_PATHS:
            expected = f"{path}/**" if (ROOT / path).is_dir() else path
            self.assertIn(
                expected,
                push_paths,
                f"releasable desktop path {path!r} (expected push filter {expected!r}) "
                "is missing from desktop_auto_release.yml push.paths",
            )


class CandidateTagPublicationTests(unittest.TestCase):
    def test_candidate_tag_targets_the_exact_merged_main_commit(self) -> None:
        fixture = PublicationFixture()

        target = publisher.publish_candidate_tag(
            repository=REPOSITORY,
            pr_number=PR_NUMBER,
            release_tag=RELEASE_TAG,
            approved_source_sha=APPROVED_RELEASE_SOURCE_SHA,
            runner=fixture,
            source_gate=ready_gate,
            newest_source=lambda _ref: APPROVED_RELEASE_SOURCE_SHA,
        )

        self.assertEqual(target, MERGED_MAIN_SHA)
        self.assertIn(["git", "tag", RELEASE_TAG, MERGED_MAIN_SHA], fixture.commands)
        self.assertIn(
            ["git", "push", "origin", f"refs/tags/{RELEASE_TAG}:refs/tags/{RELEASE_TAG}"],
            fixture.commands,
        )
        self.assertEqual(
            fixture.commands.count(
                [
                    "git",
                    "fetch",
                    "--force",
                    "origin",
                    "refs/heads/main:refs/remotes/origin/main",
                ]
            ),
            2,
        )

    def test_old_detached_tag_then_merge_order_is_rejected(self) -> None:
        fixture = PublicationFixture(main_observations=[DETACHED_CHANGELOG_SHA])

        with self.assertRaisesRegex(
            publisher.CandidatePublicationError,
            "origin/main changed after the changelog merge",
        ):
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                pr_number=PR_NUMBER,
                release_tag=RELEASE_TAG,
                approved_source_sha=APPROVED_RELEASE_SOURCE_SHA,
                runner=fixture,
                source_gate=ready_gate,
                newest_source=lambda _ref: APPROVED_RELEASE_SOURCE_SHA,
            )

        self.assertFalse(any(command[:2] == ["git", "tag"] for command in fixture.commands))
        self.assertFalse(any(command[:2] == ["git", "push"] for command in fixture.commands))

    def test_main_change_during_final_recheck_fails_closed(self) -> None:
        fixture = PublicationFixture(main_observations=[MERGED_MAIN_SHA, CHANGED_MAIN_SHA])

        with self.assertRaisesRegex(publisher.CandidatePublicationError, "origin/main changed before tag push"):
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                pr_number=PR_NUMBER,
                release_tag=RELEASE_TAG,
                approved_source_sha=APPROVED_RELEASE_SOURCE_SHA,
                runner=fixture,
                source_gate=ready_gate,
                newest_source=lambda _ref: APPROVED_RELEASE_SOURCE_SHA,
            )

        self.assertFalse(any(command[:2] == ["git", "tag"] for command in fixture.commands))
        self.assertFalse(any(command[:2] == ["git", "push"] for command in fixture.commands))

    def test_changed_releasable_source_fails_before_publication(self) -> None:
        fixture = PublicationFixture()

        with self.assertRaisesRegex(
            publisher.CandidatePublicationError,
            "newest releasable desktop source",
        ):
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                pr_number=PR_NUMBER,
                release_tag=RELEASE_TAG,
                approved_source_sha=APPROVED_RELEASE_SOURCE_SHA,
                runner=fixture,
                source_gate=ready_gate,
                newest_source=lambda _ref: CHANGED_MAIN_SHA,
            )

        self.assertFalse(any(command[:2] == ["git", "tag"] for command in fixture.commands))

    def test_open_changelog_pr_cannot_publish_a_tag(self) -> None:
        fixture = PublicationFixture(pr_state="OPEN", merge_sha=None)

        with self.assertRaisesRegex(publisher.CandidatePublicationError, "still open"):
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                pr_number=PR_NUMBER,
                release_tag=RELEASE_TAG,
                approved_source_sha=APPROVED_RELEASE_SOURCE_SHA,
                runner=fixture,
                source_gate=ready_gate,
                newest_source=lambda _ref: APPROVED_RELEASE_SOURCE_SHA,
            )

        self.assertFalse(any(command[:2] == ["git", "tag"] for command in fixture.commands))

    def test_existing_immutable_tag_is_never_reused(self) -> None:
        fixture = PublicationFixture(remote_tag_exists=True)

        with self.assertRaisesRegex(publisher.CandidatePublicationError, "already exists; refusing reuse"):
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                pr_number=PR_NUMBER,
                release_tag=RELEASE_TAG,
                approved_source_sha=APPROVED_RELEASE_SOURCE_SHA,
                runner=fixture,
                source_gate=ready_gate,
                newest_source=lambda _ref: APPROVED_RELEASE_SOURCE_SHA,
            )

        self.assertFalse(any(command[:2] == ["git", "tag"] for command in fixture.commands))
        self.assertFalse(any(command[:2] == ["git", "push"] for command in fixture.commands))


if __name__ == "__main__":
    unittest.main()
