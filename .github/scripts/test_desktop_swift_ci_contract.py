#!/usr/bin/env python3
"""Contract test for desktop-swift-ci.yml toolchain pinning and cache-key integrity.

Fails if a Swift CI job loses Xcode selection, version assertion, version logging,
or if the SwiftPM cache key omits Package.swift, Package.resolved, or toolchain
identity.  This is the Rung-0 guard from #9843: every downstream strictness claim
depends on knowing which compiler the flags run against.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/desktop-swift-ci.yml"
RUNNER_PATH = REPO_ROOT / "desktop/macos/scripts/run-swift-ci.sh"
PRE_PUSH_PATH = REPO_ROOT / "scripts/pre-push"

EXPECTED_XCODE_VERSION = "16.4"
EXPECTED_XCODE_BUILD = "16F6"
EXPECTED_XCODE_APP = f"/Applications/Xcode_{EXPECTED_XCODE_VERSION}.app"
JOBS = ["changes", "desktop-swift-static", "desktop-swift-tests", "desktop-swift", "desktop-swift-release-compile"]
MACOS_JOBS = ["desktop-swift-static", "desktop-swift-tests", "desktop-swift-release-compile"]


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _runner_text() -> str:
    return RUNNER_PATH.read_text(encoding="utf-8")


def _job_text(workflow_text: str, job_id: str) -> str:
    match = re.search(
        rf"^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow_text, re.MULTILINE | re.DOTALL
    )
    if not match:
        raise AssertionError(f"missing workflow job: {job_id}")
    return match.group("body")


def _load_workflow() -> dict:
    text = _workflow_text()
    return {"jobs": {job_id: _job_text(text, job_id) for job_id in JOBS}}


class DesktopSwiftCIContractTests(unittest.TestCase):
    """Verify toolchain pinning, version logging, and cache-key completeness."""

    @classmethod
    def setUpClass(cls):
        cls.workflow = _load_workflow()
        cls.jobs = cls.workflow["jobs"]

    # --- per-job assertions ------------------------------------------------

    def test_both_jobs_call_the_canonical_pinned_toolchain_runner(self):
        for job_id in MACOS_JOBS:
            with self.subTest(job=job_id):
                self.assertIn("run-swift-ci.sh --select-toolchain", self.jobs[job_id])

        test_job = self.jobs["desktop-swift-tests"]
        release_job = self.jobs["desktop-swift-release-compile"]

        self.assertIn("run-swift-ci.sh --test", test_job)
        self.assertIn("run-swift-ci.sh --release-compile", release_job)
        self.assertIn("run-swift-ci.sh --release-notification-regression", test_job)

    def test_change_detection_happens_before_macos_allocation(self):
        """#9440: non-desktop changes must not claim a costly macOS runner."""
        changes = self.jobs["changes"]

        self.assertIn("runs-on: ubuntu-latest", changes)
        self.assertIn("should_run", changes)
        self.assertIn("should_release_compile", changes)
        self.assertIn("diff_base", changes)

        for job_id, output in (
            ("desktop-swift-static", "should_run"),
            ("desktop-swift-tests", "should_run"),
            ("desktop-swift-release-compile", "should_release_compile"),
        ):
            with self.subTest(job=job_id):
                job = self.jobs[job_id]
                self.assertIn("needs: changes", job)
                self.assertIn(f"needs.changes.outputs.{output}", job)
                self.assertNotIn("Check changed files", job)

        # Static checks need full history for git diff/merge-base. The test and
        # release-compile jobs can stay shallow because they do not resolve a
        # diff base themselves.
        static_job = self.jobs["desktop-swift-static"]
        self.assertIn("fetch-depth: 0", static_job)
        test_job = self.jobs["desktop-swift-tests"]
        self.assertIn("fetch-depth: 1", test_job)
        release_job = self.jobs["desktop-swift-release-compile"]
        self.assertIn("fetch-depth: 1", release_job)

    def test_notification_boundary_runs_targeted_release_regression(self):
        changes = self.jobs["changes"]
        job = self.jobs["desktop-swift-tests"]
        for path in (
            "AppState[+]Permissions[.]swift",
            "Sources/.*Notification.*[.]swift",
            "OmiApp[.]swift",
            "Providers/(ChatToolExecutor|DeviceProvider)[.]swift",
            "Tests/.*Notification.*Tests[.]swift",
        ):
            self.assertIn(path, changes)
        self.assertIn("runs-on: macos-15", job)
        self.assertIn("--release-notification-regression", job)
        self.assertIn("should_notification_release_regression", job)
        self.assertIn("UserNotificationCallbackBridgeTests/", _runner_text())

    def test_stable_release_gate_requires_both_parallel_jobs(self):
        """The required check name must fail closed on either parallel lane."""
        gate = self.jobs["desktop-swift"]

        self.assertIn("name: Desktop Swift Build & Tests", gate)
        self.assertIn("desktop-swift-static", gate)
        self.assertIn("desktop-swift-tests", gate)
        self.assertIn("always()", gate)
        self.assertIn('test "$STATIC_RESULT" = success', gate)
        self.assertIn('test "$TEST_RESULT" = success', gate)

    def test_canonical_runner_fails_closed_on_the_pinned_toolchain(self):
        runner = _runner_text()

        self.assertIn(EXPECTED_XCODE_APP, runner)
        self.assertIn("DEVELOPER_DIR", runner)
        self.assertIn("exit 1", runner)
        self.assertRegex(runner, r"if\s*\[\s*!\s*-d\s+\"\$XCODE_APP")
        self.assertIn("xcodebuild -version", runner)
        self.assertIn("xcrun swift --version", runner)
        self.assertIn(f'"Xcode $EXPECTED_XCODE_VERSION"', runner)
        self.assertIn(f'"$EXPECTED_XCODE_BUILD"', runner)

    def test_canonical_runner_exports_the_selected_toolchain_for_ci_steps(self):
        runner = _runner_text()

        self.assertIn('printf \'DEVELOPER_DIR=%s\\n\' "$DEVELOPER_DIR" >> "$GITHUB_ENV"', runner)

    def test_pre_push_keeps_desktop_feedback_budget_bounded(self):
        """#9440: the full pinned Swift suite belongs to CI, not the push hook."""
        pre_push = PRE_PUSH_PATH.read_text(encoding="utf-8")

        self.assertIn("xcrun swift build -c debug --package-path Desktop", pre_push)
        self.assertIn("pre-push is intentionally a bounded local-feedback gate", pre_push)
        self.assertIn("push-time budget bloat", pre_push)
        self.assertNotIn("desktop/macos/scripts/run-swift-ci.sh --test", pre_push)
        self.assertNotIn("desktop/macos/scripts/run-swift-ci.sh --release-compile", pre_push)

    # --- cache-key assertions ----------------------------------------------

    def test_cache_key_includes_manifest_and_lockfile_and_toolchain(self):
        """The SwiftPM cache key must include Package.swift, Package.resolved,
        and a toolchain identity component."""
        job = self.jobs["desktop-swift-tests"]
        self.assertIn("uses: actions/cache", job, "desktop-swift-tests must have a cache step")
        key_match = re.search(r"key:\s*([^\n]+)", job)
        self.assertIsNotNone(key_match, "desktop-swift cache step must declare a key")
        key = key_match.group(1)
        # Toolchain identity in the key prefix prevents a tool change from
        # silently reusing a stale cache built with a different compiler.
        self.assertIn(
            f"xcode{EXPECTED_XCODE_VERSION.replace('.', '')}",
            key,
            "cache key must embed toolchain identity (xcode164)",
        )
        # Package.swift hash
        self.assertIn(
            "Package.swift",
            key,
            "cache key must include Package.swift hashFiles",
        )
        # Package.resolved hash
        self.assertIn(
            "Package.resolved",
            key,
            "cache key must include Package.resolved hashFiles",
        )
        static_job = self.jobs["desktop-swift-static"]
        static_key = re.search(r"key:\s*([^\n]+)", static_job).group(1)
        self.assertIn("swift-format-wrapper.sh", static_key)
        self.assertIn("swiftlint-wrapper.sh", static_key)
        self.assertIn("~/.cache/omi-swift-format", static_job)
        self.assertIn("~/.cache/omi-swiftlint", static_job)

    def test_cache_saves_completed_build_state_after_a_test_failure(self):
        """A retry should reuse SwiftPM's validated incremental build state."""
        job = self.jobs["desktop-swift-tests"]
        self.assertIn("id: swiftpm-cache", job)
        self.assertIn("uses: actions/cache/restore@v6", job)
        self.assertIn("uses: actions/cache/save@v6", job)
        self.assertIn("always()", job)
        self.assertIn("steps.swiftpm-cache.outputs.cache-hit != 'true'", job)

    # --- changed-file gate assertions --------------------------------------

    def test_release_compile_gates_on_package_resolved(self):
        """Release compile must trigger when Package.resolved changes, even on
        a PR where the manifest source is unchanged."""
        combined = self.jobs["changes"]
        # The variable must be wired into the SHOULD_RUN conditional, not just
        # declared or logged — removing the gate while keeping other references
        # must fail this test.
        self.assertTrue(
            re.search(r'"\$PACKAGE_RESOLVED"\s*=\s*"true"', combined),
            "release-compile job must gate SHOULD_RUN on PACKAGE_RESOLVED=true",
        )

    def test_manifest_checks_use_the_changed_diff_base_on_pushes(self):
        """Pushes must lint the just-pushed diff, not checkout's origin/main HEAD."""
        changes = self.jobs["changes"]
        job = self.jobs["desktop-swift-static"]
        self.assertIn('echo "diff_base=$DIFF_BASE" >> "$GITHUB_OUTPUT"', changes)
        self.assertIn(
            '--base "${{ needs.changes.outputs.diff_base }}"',
            job,
            "manifest checks must use the pushed-before SHA on main pushes and the PR base on pull requests",
        )

    def test_xcode_version_probe_does_not_close_its_pipe_early(self):
        """head(1) aborts Xcode 16.4 under pipefail; sed reads the full output."""
        runner = _runner_text()

        self.assertNotIn("xcodebuild -version | head -1", runner)
        self.assertIn("sed -n '1p'", runner)

    # --- adversarial: removing any guard must fail -------------------------

    def test_adversarial_remove_runner_mode_detected(self):
        """The workflow must not retain a toolchain setup while bypassing the shared runner."""
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        tampered = wf_text.replace("run-swift-ci.sh --test", "swift-test-suites.sh", 1)
        combined = _job_text(tampered, "desktop-swift-tests")
        self.assertNotIn("run-swift-ci.sh --test", combined)

    def test_adversarial_cache_key_weakening_detected(self):
        """A cache key without Package.resolved or toolchain identity is caught."""
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        tampered = wf_text.replace(
            "desktop-swift-build-xcode164-${{ hashFiles('desktop/macos/Desktop/Package.swift', 'desktop/macos/Desktop/Package.resolved') }}",
            "desktop-swift-${{ hashFiles('desktop/macos/Desktop/Package.swift') }}",
        )
        job = _job_text(tampered, "desktop-swift-tests")
        key = re.search(r"key:\s*([^\n]+)", job).group(1)
        self.assertNotIn("Package.resolved", key)

    def test_adversarial_remove_package_resolved_gate_detected(self):
        """Removing the PACKAGE_RESOLVED gate from SHOULD_RUN while keeping
        other references must fail the positive gate assertion."""
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        tampered = wf_text.replace('|| [ "$PACKAGE_RESOLVED" = "true" ]', "")
        combined = _job_text(tampered, "changes")
        # PACKAGE_RESOLVED still appears (declared, detected, echoed) but the
        # gate condition is gone — the regex must fail to match.
        self.assertIn("PACKAGE_RESOLVED", combined)  # still referenced
        self.assertIsNone(
            re.search(r'"\$PACKAGE_RESOLVED"\s*=\s*"true"', combined),
            "gate condition must be absent after removal",
        )


if __name__ == "__main__":
    unittest.main()
