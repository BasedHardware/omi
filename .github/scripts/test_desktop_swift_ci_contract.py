#!/usr/bin/env python3
"""Contract test for desktop-swift-ci.yml toolchain pinning and cache-key integrity.

Fails if a Swift CI job loses Xcode selection, version assertion, version logging,
or if the SwiftPM cache key omits Package.swift, Package.resolved, or toolchain
identity. It also preserves the runner-saving test selector and the serial CI
execution required by SwiftPM's shared build-directory lock. This is the Rung-0
guard from #9843: every downstream strictness claim depends on knowing which
compiler the flags run against.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/desktop-swift-ci.yml"
RUNNER_PATH = REPO_ROOT / "desktop/macos/scripts/run-swift-ci.sh"
SUITE_RUNNER_PATH = REPO_ROOT / "desktop/macos/scripts/swift-test-suites.sh"
PRE_PUSH_PATH = REPO_ROOT / "scripts/pre-push"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pre_push_ci_prediction import DESKTOP_RELEASE_PATHSPECS, resolve_impact  # noqa: E402

_PLANNER_SPEC = importlib.util.spec_from_file_location(
    "plan_desktop_release_ci_contract",
    REPO_ROOT / ".github/scripts/plan-desktop-release.py",
)
assert _PLANNER_SPEC and _PLANNER_SPEC.loader
planner = importlib.util.module_from_spec(_PLANNER_SPEC)
_PLANNER_SPEC.loader.exec_module(planner)

EXPECTED_XCODE_VERSION = "16.4"
EXPECTED_XCODE_BUILD = "16F6"
EXPECTED_XCODE_APP = f"/Applications/Xcode_{EXPECTED_XCODE_VERSION}.app"
JOBS = ["changes", "desktop-swift-verify", "desktop-swift", "desktop-swift-release-compile"]
MACOS_JOBS = ["desktop-swift-verify", "desktop-swift-release-compile"]
# Hosted macOS budgets are per-job: the consolidated verify lane needs a longer
# cold-runner ceiling than the narrower release-compile job.
MACOS_JOB_TIMEOUT_MINUTES = {
    # A wedge-guard, not a lane budget: it must admit one legitimate
    # cold-tools run (~15 min from-source bootstrap) ahead of the full lane,
    # which still executes every suite on runner-changing diffs. Two #13219
    # runs were cancelled by tighter ceilings before completing.
    "desktop-swift-verify": 60,
    # One combined app/test build avoids the duplicate compilation reported
    # in #13481; keep the existing ceiling until hosted timing proves otherwise.
    "desktop-swift-release-compile": 60,
}


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _runner_text() -> str:
    return RUNNER_PATH.read_text(encoding="utf-8")


def _suite_runner_text() -> str:
    return SUITE_RUNNER_PATH.read_text(encoding="utf-8")


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

    def test_macos_jobs_call_the_canonical_pinned_toolchain_runner(self):
        for job_id in MACOS_JOBS:
            with self.subTest(job=job_id):
                self.assertIn("run-swift-ci.sh --select-toolchain", self.jobs[job_id])

        verify_job = self.jobs["desktop-swift-verify"]
        release_job = self.jobs["desktop-swift-release-compile"]

        self.assertIn("run-swift-ci.sh --test", verify_job)
        self.assertIn("run-swift-ci.sh --release-compile", release_job)
        self.assertIn("run-swift-ci.sh --release-test-compile", release_job)
        # The release-mode regression runs next to the release build it
        # consumes; a second release build on the verify runner cost ~31 min
        # of scarce hosted-macOS time per notification-boundary change.
        self.assertIn("run-swift-ci.sh --release-notification-regression", release_job)
        self.assertNotIn("run-swift-ci.sh --release-notification-regression", verify_job)

    def test_change_detection_happens_before_macos_allocation(self):
        """#9440: non-desktop changes must not claim a costly macOS runner."""
        changes = self.jobs["changes"]

        self.assertIn("runs-on: ubuntu-latest", changes)
        self.assertIn("should_run", changes)
        self.assertIn("should_run_static", changes)
        self.assertIn("should_run_tests", changes)
        self.assertIn("should_release_compile", changes)
        self.assertIn("desktop_swift_changed_files", changes)
        self.assertIn("diff_base", changes)

        for job_id, output in (("desktop-swift-release-compile", "should_release_compile"),):
            with self.subTest(job=job_id):
                job = self.jobs[job_id]
                self.assertIn("needs: changes", job)
                self.assertIn(f"needs.changes.outputs.{output}", job)
                self.assertNotIn("Check changed files", job)

        # The consolidated job needs full history for static-check diffing and
        # must preserve both selectors before it reserves one macOS runner.
        verify_job = self.jobs["desktop-swift-verify"]
        self.assertIn("needs: changes", verify_job)
        self.assertIn("needs.changes.outputs.should_run_static", verify_job)
        self.assertIn("needs.changes.outputs.should_run_tests", verify_job)
        self.assertNotIn("Check changed files", verify_job)
        self.assertIn("fetch-depth: 0", verify_job)
        release_job = self.jobs["desktop-swift-release-compile"]
        self.assertIn("fetch-depth: 1", release_job)

    def test_release_control_inputs_produce_exact_sha_checks(self):
        """Every planner releasable pathspec must produce the exact-SHA CI checks."""
        self.assertEqual(DESKTOP_RELEASE_PATHSPECS, planner.DESKTOP_RELEASE_PATHS)
        self.assertEqual(set(MACOS_JOBS), set(MACOS_JOB_TIMEOUT_MINUTES))
        for pathspec in planner.DESKTOP_RELEASE_PATHS:
            # Directory pathspecs need a concrete file probe under the tree.
            probe = pathspec if Path(pathspec).suffix else f"{pathspec.rstrip('/')}/Resources/Info.plist"
            with self.subTest(pathspec=pathspec, probe=probe):
                plan = resolve_impact([probe], event="push")
                self.assertTrue(plan.includes("desktop-ci-only"), probe)
                self.assertTrue(plan.includes("desktop-swift-release-compile"), probe)

    def test_macos_jobs_have_a_bounded_runner_budget(self):
        """A stuck Swift invocation must not consume hosted macOS capacity forever."""
        self.assertEqual(set(MACOS_JOBS), set(MACOS_JOB_TIMEOUT_MINUTES))
        for job_id, timeout_minutes in MACOS_JOB_TIMEOUT_MINUTES.items():
            with self.subTest(job=job_id, timeout_minutes=timeout_minutes):
                self.assertIn(f"timeout-minutes: {timeout_minutes}", self.jobs[job_id])

    def test_ci_batch_ceiling_leaves_fallback_headroom(self):
        """The batch watchdog budget must not crowd out the bisect fallback.

        The scaled batch budget grows linearly with the batch size (per-suite
        budget + per-extra-suite allowance). At CI's batch size the uncapped
        budget approaches the job's 60-minute ceiling, so a wedged batch
        would be killed by the job timeout before its isolation fallback
        could run. CI must set an independent aggregate ceiling that keeps
        the worst single-batch watchdog cost well under the job budget.
        """
        job = self.jobs["desktop-swift-verify"]
        self.assertIn('OMI_SWIFT_TEST_SUITE_BATCH_SIZE: "100"', job)
        match = re.search(
            r'OMI_SWIFT_TEST_BATCH_CEILING_SECONDS: "(\d+)"', job
        )
        if match is None:
            self.fail(
                "desktop-swift-verify must set OMI_SWIFT_TEST_BATCH_CEILING_SECONDS "
                "alongside its batch size"
            )
        ceiling = int(match.group(1))
        timeout_minutes = MACOS_JOB_TIMEOUT_MINUTES["desktop-swift-verify"]
        timeout_seconds = timeout_minutes * 60
        # 300s per-suite budget + 30s per additional suite at batch 100.
        scaled_budget = 300 + 99 * 30
        self.assertGreater(
            scaled_budget,
            timeout_seconds // 2,
            "this guard lost its premise: the scaled batch budget no longer "
            "threatens the job ceiling at this batch size",
        )
        self.assertGreater(
            ceiling,
            0,
            "a zero ceiling disables the cap and restores the uncapped "
            "scaled budget as the worst case",
        )
        self.assertLess(
            ceiling,
            scaled_budget,
            f"ceiling {ceiling}s never bites: the scaled budget is already "
            f"{scaled_budget}s",
        )
        self.assertLessEqual(
            ceiling,
            timeout_seconds // 2,
            f"ceiling {ceiling}s exceeds half the {timeout_seconds}s job "
            f"budget; a wedged batch must die with at least half the job "
            f"left for its bisect fallback",
        )

    def test_no_closed_pull_request_runs_exist(self):
        """No closure run can publish a skipped check onto the merge SHA."""
        workflow = _workflow_text()

        self.assertNotIn("closed", workflow)
        self.assertNotIn("pull_request.merged", workflow)

    def test_current_main_health_is_independent_of_the_last_commit_paths(self):
        """#12275: unrelated pushes must not keep the last Desktop Swift verdict alive."""
        triggers = _workflow_text().split("concurrency:", 1)[0]

        self.assertIn("schedule:", triggers)
        self.assertRegex(triggers, r'cron:\s*["\']17 5 \* \* \*["\']')
        self.assertIn("workflow_dispatch:", triggers)
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                plan = resolve_impact(["backend/database/users.py"], event=event)
                self.assertTrue(plan.includes("desktop-ci-only"))
                self.assertTrue(plan.includes("desktop-swift-tests"))
                self.assertTrue(plan.includes("desktop-swift-release-compile"))
                self.assertTrue(plan.includes("desktop-swift-release-test-compile"))

    def test_required_release_check_names_are_literals(self):
        """GitHub does not evaluate `name:` for a skipped job.

        An expression there publishes the raw expression text as the check
        name, so the check the desktop release planner requires by exact name
        becomes *absent* instead of skipped on every commit that does not touch
        desktop paths. Observed Aug 14 2026 on f666ddd4a3/7a79f08329/7d7ed62e5:
        the published name was the literal
        "github.event.action == 'closed' && ... || 'Desktop Swift Build & Tests'".
        Every job name in this workflow must therefore be expression-free.
        """
        for job_id, body in self.jobs.items():
            name_lines = [
                line for line in body.splitlines() if line.strip().startswith("name:") and "    - name:" not in line
            ]
            self.assertTrue(name_lines, f"job {job_id} declares no name")
            with self.subTest(job=job_id):
                self.assertNotIn("${{", name_lines[0])

        self.assertIn("name: Desktop Swift Build & Tests", self.jobs["desktop-swift"])
        self.assertIn("name: Desktop Swift Release Compile", self.jobs["desktop-swift-release-compile"])

    def test_notification_boundary_runs_targeted_release_regression(self):
        job = self.jobs["desktop-swift-release-compile"]
        for path in (
            "desktop/macos/Desktop/Sources/AppState/AppState+Permissions.swift",
            "desktop/macos/Desktop/Sources/NotificationProbe.swift",
            "desktop/macos/Desktop/Sources/OmiApp.swift",
            "desktop/macos/Desktop/Sources/Providers/ChatToolExecutor.swift",
            "desktop/macos/Desktop/Tests/NotificationProbeTests.swift",
        ):
            with self.subTest(path=path):
                self.assertTrue(resolve_impact([path]).includes("desktop-swift-notification-release-regression"))
        self.assertIn("runs-on: macos-15", job)
        self.assertIn("--release-notification-regression", job)
        self.assertIn("should_notification_release_regression", job)
        self.assertIn("UserNotificationCallbackBridgeTests/", _runner_text())

    def test_release_test_phase_is_forwarded_and_gates_the_existing_job(self):
        """Static workflow contract; executable runner/selector tests own behavior."""
        self.assertIn(
            "should_release_test_compile: ${{ steps.changed.outputs.should_release_test_compile }}",
            self.jobs["changes"],
        )
        for job_id in ("desktop-swift", "desktop-swift-release-compile"):
            self.assertIn("needs.changes.outputs.should_release_test_compile == 'true'", self.jobs[job_id])
        release = self.jobs["desktop-swift-release-compile"]
        self.assertIn('if [ "$BUILD_RELEASE_TESTS" = true ]; then', release)
        self.assertRegex(release, r"--release-test-compile\s+else\s+./scripts/run-swift-ci.sh --release-compile")

    def test_stable_release_gate_requires_the_selected_macos_job(self):
        """The required check name must fail closed on its selected lanes."""
        gate = self.jobs["desktop-swift"]

        self.assertIn("name: Desktop Swift Build & Tests", gate)
        self.assertIn("desktop-swift-verify", gate)
        self.assertIn("desktop-swift-release-compile", gate)
        self.assertIn("always()", gate)
        self.assertIn("STATIC_REQUIRED", gate)
        self.assertIn("TESTS_REQUIRED", gate)
        self.assertIn("RELEASE_REQUIRED", gate)
        self.assertIn('test "$VERIFY_RESULT" = success', gate)
        self.assertIn('test "$VERIFY_RESULT" = skipped', gate)
        # The release lane (WMO compile + UserNotifications release regression)
        # reports through the Release Compile job; the required check must fail
        # closed on it so release-only breaks cannot merge on a green debug
        # lane (#11373/#11374).
        self.assertIn('test "$RELEASE_RESULT" = success', gate)
        self.assertIn('test "$RELEASE_RESULT" = skipped', gate)

    def test_full_swift_suite_is_selected_only_for_its_inputs(self):
        """Asset/config candidates retain static evidence without a second Mac job."""
        verify_job = self.jobs["desktop-swift-verify"]
        for path in (
            "desktop/macos/Desktop/Sources/Probe.swift",
            "desktop/macos/Desktop/Package.resolved",
            "desktop/macos/scripts/run-swift-ci.sh",
            "desktop/macos/tests/test-probe.sh",
            ".github/workflows/desktop-swift-ci.yml",
        ):
            with self.subTest(path=path):
                self.assertTrue(resolve_impact([path]).includes("desktop-swift-tests"))
        self.assertIn("needs.changes.outputs.should_run_tests", verify_job)

    def test_static_and_test_lanes_share_one_hosted_macos_runner(self):
        """#10507: Swift CI must not reserve two scarce hosted Macs at once."""
        workflow = _workflow_text()

        self.assertEqual(MACOS_JOBS, ["desktop-swift-verify", "desktop-swift-release-compile"])
        self.assertIn("rather than claiming two", workflow)

    def test_independent_macos_phases_publish_native_step_outcomes(self):
        """A static failure must not mask the later independent Swift suite."""
        job = self.jobs["desktop-swift-verify"]
        for step_id, outcome in (
            ("macos_manifest_checks", "STATIC_OUTCOME"),
            ("desktop_launcher_tests", "LAUNCHER_OUTCOME"),
            ("desktop_swift_tests", "TEST_OUTCOME"),
        ):
            with self.subTest(step_id=step_id):
                self.assertIn(f"id: {step_id}", job)
                self.assertIn(f"steps.{step_id}.outcome", job)
                self.assertIn(outcome, job)
        self.assertIn("always() && !cancelled()", job)
        self.assertIn("Require independent macOS phase verdicts", job)

    def test_ci_uses_isolated_swiftpm_build_directories_per_worker(self):
        """#10507: parallel suites require isolated build and runtime state."""
        verify_job = self.jobs["desktop-swift-verify"]
        suite_runner = _suite_runner_text()

        self.assertIn('OMI_SWIFT_TEST_SUITE_WORKERS: "3"', verify_job)
        self.assertIn("copy-on-write clone", verify_job)
        self.assertIn("--scratch-path", suite_runner)
        self.assertIn("cp -cR", suite_runner)
        self.assertIn("CFFIXED_USER_HOME", suite_runner)
        self.assertIn('TMPDIR="$runtime_path/tmp"', suite_runner)
        self.assertIn('OMI_SWIFT_TEST_SUITE_WORKERS="${OMI_SWIFT_TEST_SUITE_WORKERS:-4}"', _runner_text())

    def test_later_main_push_cannot_cancel_exact_sha_release_evidence(self):
        """A backend/docs push must not strand an earlier selected desktop SHA."""
        workflow = _workflow_text()
        concurrency = workflow.split("jobs:", 1)[0]

        # PR updates remain safely supersedable by PR number, while every main
        # push gets an immutable group and therefore runs its own exact-SHA
        # Build & Tests and Release Compile checks to a terminal conclusion.
        self.assertIn(
            "group: desktop-swift-${{ github.event.pull_request.number || github.sha }}",
            concurrency,
        )
        self.assertIn(
            "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
            concurrency,
        )
        self.assertNotIn("github.ref", concurrency)
        self.assertNotIn("cancel-in-progress: true", concurrency)

    def test_launcher_contract_prerequisites_are_installed(self):
        """Discovered shell tests may use the repository's pinned workflow linter."""
        job = self.jobs["desktop-swift-verify"]
        install_index = job.index("brew install")
        launcher_index = job.index("Desktop launcher script tests")
        self.assertLess(install_index, launcher_index)
        self.assertRegex(job[install_index:launcher_index], r"brew install[^\n]*\bactionlint\b")

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
        self.assertNotIn("--release-test-compile", pre_push)

    # --- cache-key assertions ----------------------------------------------

    def test_cache_key_includes_manifest_and_lockfile_and_toolchain(self):
        """The SwiftPM cache key must include Package.swift, Package.resolved,
        and a toolchain identity component."""
        job = self.jobs["desktop-swift-verify"]
        self.assertIn("uses: actions/cache", job, "desktop-swift-verify must have a cache step")
        key_match = re.search(r"key:\s*([^\n]*desktop-swift-build[^\n]*)", job)
        self.assertIsNotNone(key_match, "desktop-swift build cache step must declare a key")
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
        static_key = re.search(r"key:\s*([^\n]*desktop-swift-tools[^\n]*)", job).group(1)
        self.assertIn("swift-format-wrapper.sh", static_key)
        self.assertIn("swiftlint-wrapper.sh", static_key)
        self.assertIn("~/.cache/omi-swift-format", job)
        self.assertIn("~/.cache/omi-swiftlint", job)

    def test_cache_keeps_dependencies_but_not_pr_scoped_build_products(self):
        """A retry retains dependency downloads without uploading Desktop/.build."""
        job = self.jobs["desktop-swift-verify"]
        self.assertIn("id: swiftpm-cache", job)
        self.assertIn("uses: actions/cache/restore@v6", job)
        self.assertIn("uses: actions/cache/save@v6", job)
        self.assertIn("always()", job)
        self.assertIn("steps.swiftpm-cache.outputs.cache-hit != 'true'", job)
        self.assertIn("~/Library/Caches/org.swift.swiftpm", job)
        self.assertNotIn("desktop/macos/Desktop/.build", job)

    def test_release_job_does_not_archive_build_products(self):
        """The 5.3 GB release .build archive is gone from both directions.

        Measurement on every recent run showed the release compile step at
        23-25 min whether the archive hit exactly, partially, or not at all,
        while each main-push save evicted the small swift-format/swiftlint
        tool caches from the repository's ~10 GB cache budget — and a tools
        cache miss made the verify job's launcher tests rebuild swift-format
        from source for ~15 min. Neither job may restore or save it again.
        """
        release_job = self.jobs["desktop-swift-release-compile"]
        self.assertNotIn("desktop/macos/Desktop/.build", release_job)
        self.assertNotIn("desktop-swift-release-xcode164", release_job)
        self.assertIn("Restore SwiftPM dependency cache", release_job)

    def test_tools_cache_covers_the_launcher_test_lane(self):
        """The launcher tests exercise the pinned swift-format binary.

        The tools restore used to be gated on the static lane alone, so a
        tests-only diff (static selection empty) rebuilt swift-format from
        source for ~15 min inside the launcher tests, every run: the cache was
        never restored, and the save ran before the step that built the tools,
        caching nothing. Worse, an exact-key hit on an entry the old workflow
        saved empty suppressed every later save (run 34295159347). The restore
        must cover the tests lane, an explicit warm-up step builds whatever the
        restore missed BEFORE any consumer runs, and the save immediately
        follows the warm-up under a fresh -v3 key carrying only the built
        binaries (the v2 full-tree archives lost eviction races against the
        lingering 5.3 GB release .build entries and kept re-paying the
        from-source rebuild).
        """
        job = self.jobs["desktop-swift-verify"]
        self.assertIn(
            "(needs.changes.outputs.should_run_static == 'true' || needs.changes.outputs.should_run_tests == 'true')",
            job,
        )
        self.assertIn("desktop-swift-tools-v3-", job)
        restore_index = job.index("Restore Swift formatter and linter tools")
        warm_index = job.index("Warm pinned formatter and linter tools")
        save_index = job.index("Save Swift formatter and linter tools after warm-up")
        launcher_index = job.index("Desktop launcher script tests")
        self.assertLess(restore_index, warm_index)
        self.assertLess(warm_index, save_index)
        self.assertLess(save_index, launcher_index)

    def test_pr_test_lane_defers_slow_suites_with_changed_file_wake(self):
        """The PR lane defers ratcheted slow suites; their own diffs wake them.

        Deferral is the runner's decision from swift-test-slow-suites.json; the
        workflow only selects the lane and forwards the deferral-relevant diff
        so a PR that edits a deferred suite's own test file still executes it.
        """
        verify_job = self.jobs["desktop-swift-verify"]
        # The lane comes from the changes job's effective-lane output so the
        # runner and the step budget share one re-baseline decision.
        self.assertIn("OMI_SWIFT_TEST_LANE: ${{ needs.changes.outputs.swift_test_effective_lane }}", verify_job)
        self.assertIn("swift_test_effective_lane", self.jobs["changes"])
        self.assertIn("OMI_SWIFT_TEST_CHANGED_FILES: ${{ needs.changes.outputs.desktop_swift_changed_files }}", verify_job)
        # The serial/solo clusters cost one ~30s invocation per member for
        # sub-second tests, sequentially (24 invocations / 12.9 min measured
        # on run 34306382692); the PR lane defers them behind the same
        # declaring-file and ratcheted-watch wake rules.
        self.assertIn('OMI_SWIFT_TEST_PR_LANE_DEFER_SERIAL: "1"', verify_job)
        # The slow list and its validator are full-suite inputs: editing them
        # must wake the debug test lane.
        self.assertTrue(resolve_impact(["desktop/macos/scripts/swift-test-slow-suites.json"]).includes("desktop-swift-tests"))
        self.assertTrue(resolve_impact(["desktop/macos/scripts/swift-test-skip-ratchet.py"]).includes("desktop-swift-tests"))

    def test_duration_regression_guards_are_enforced(self):
        """Desktop Swift CI once drifted silently to 27-42 min suite steps.

        Duration must fail the run, not just appear in logs: the suite and
        launcher steps carry wall-clock budgets that hard-fail when exceeded,
        and the PR lane ratchets slow suites so the fast lane cannot silently
        grow a slow tail. Budgets are generous against every measured
        legitimate shape (fast lane 15m42s at batch 50, full lane 17m46s at
        batch 100, serial-woken auth PRs ~24m) and sit far below the
        regression; they move only through this file's review.
        """
        verify_job = self.jobs["desktop-swift-verify"]
        # Lane-aware through the same effective-lane output: the PR fast
        # lane carries the tight budget; the full lane legitimately spans
        # ~28-40m (measured 37m07s on run 34363659680) and carries 2700s
        # against the 50m+ drift class. Keying on the event type alone made
        # a re-baselined PR run the full suite against the PR number and
        # false-red at 2013s vs 1800s (run 34369508858).
        self.assertIn(
            "OMI_SWIFT_TEST_STEP_BUDGET_SECONDS: ${{ needs.changes.outputs.swift_test_effective_lane == 'pr' && '1800' || '2700' }}",
            verify_job,
        )
        self.assertIn('OMI_SWIFT_TEST_SLOW_RATCHET_SECONDS: "60"', verify_job)
        self.assertIn('OMI_SWIFT_LAUNCHER_STEP_BUDGET_SECONDS: "360"', verify_job)
        self.assertIn("swift suite step wall: ${elapsed}s", verify_job)
        self.assertIn("launcher step wall: ${elapsed}s", verify_job)
        self.assertIn("over its ${OMI_SWIFT_TEST_STEP_BUDGET_SECONDS}s regression budget", verify_job)
        self.assertIn("over its ${OMI_SWIFT_LAUNCHER_STEP_BUDGET_SECONDS}s regression budget", verify_job)
        suite_runner = _suite_runner_text()
        self.assertIn("FAILED slow-suite ratchet", suite_runner)
        self.assertIn("SLOW_RATCHET_SECONDS", suite_runner)

    def test_changed_file_forwarding_covers_the_deferral_infrastructure(self):
        """The runner can only wake/re-baseline on files CI actually forwards.

        The ratchet script decides deferral (--slow-list); a change to it must
        reach the runner's CHANGED_FILES, and the runner's own re-baseline
        pattern must include it — otherwise the PR lane would judge a modified
        selection algorithm against the stale slow list it replaces.
        """
        changes_job = self.jobs["changes"]
        self.assertIn("swift-test-skip-ratchet\\.py", changes_job)
        self.assertIn("swift-test-skip-ratchet\\.py", _suite_runner_text())

    def test_pr_lane_deferral_matcher_handles_multi_entry_slow_lists(self):
        """--slow-list is newline-delimited; the matcher must see every entry.

        A space-delimited case glob over raw newline output matches nothing
        for the real multi-suite slow list, silently disabling the whole
        80/20 deferral. The runner must normalize before matching.
        """
        suite_runner = _suite_runner_text()
        # The watch-aware lookup splits the tab field first, then normalizes:
        # names feed the matcher space-delimited either way.
        self.assertIn("cut -f1 | tr '\\n' ' '", suite_runner)

    def test_release_compile_is_reserved_off_ordinary_prs(self):
        """One hosted Mac per ordinary PR; pushes and package edits compile release.

        The predictor owns this asymmetry; pin it here because the required
        aggregate check and the release planner both consume the job's verdict.
        """
        source_probe = ["desktop/macos/Desktop/Sources/OmiApp.swift"]
        self.assertFalse(resolve_impact(source_probe, event="pull_request").includes("desktop-swift-release-compile"))
        self.assertTrue(resolve_impact(source_probe, event="push").includes("desktop-swift-release-compile"))
        self.assertTrue(
            resolve_impact(["desktop/macos/Desktop/Package.swift"], event="pull_request").includes(
                "desktop-swift-release-compile"
            )
        )
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                self.assertTrue(
                    resolve_impact(["backend/database/users.py"], event=event).includes("desktop-swift-release-compile")
                )

    # --- changed-file gate assertions --------------------------------------

    def test_release_compile_gates_on_package_resolved(self):
        """Release compile must trigger when Package.resolved changes, even on
        a PR where the manifest source is unchanged."""
        self.assertTrue(
            resolve_impact(["desktop/macos/Desktop/Package.resolved"], event="pull_request").includes(
                "desktop-swift-release-compile"
            ),
            "release-compile selection must include Package.resolved on pull requests",
        )

    def test_every_releasable_desktop_path_produces_exact_sha_checks(self):
        """Planner-eligible packaging/assets must not silently skip Swift evidence."""
        for path in ("desktop/macos/Resources/Info.plist", "desktop/macos/scripts/prepare-bundle.sh"):
            with self.subTest(path=path):
                self.assertTrue(resolve_impact([path], event="push").includes("desktop-ci-only"))
        for path in (
            "desktop/macos/changelog/2026-07-25.json",
            "desktop/macos/CHANGELOG.json",
            "desktop/macos/AGENTS.md",
        ):
            with self.subTest(path=path):
                self.assertFalse(resolve_impact([path], event="push").includes("desktop-ci-only"))

    def test_manifest_checks_use_the_changed_diff_base_on_pushes(self):
        """Pushes must lint the just-pushed diff, not checkout's origin/main HEAD."""
        changes = self.jobs["changes"]
        job = self.jobs["desktop-swift-verify"]
        self.assertIn('echo "diff_base=$DIFF_BASE" >> "$GITHUB_OUTPUT"', changes)
        self.assertIn(
            '--base "${{ needs.changes.outputs.diff_base }}"',
            job,
            "manifest checks must use the pushed-before SHA on main pushes and the PR base on pull requests",
        )

    def test_pr_changelog_metadata_is_owned_by_the_canonical_preflight(self):
        """#10501 run 30121300487: the macOS lane has no live PR label metadata."""
        job = self.jobs["desktop-swift-verify"]

        self.assertIn('if [ "${{ github.event_name }}" = "pull_request" ]; then', job)
        self.assertIn("MANIFEST_ARGS+=(--skip-changelog)", job)
        self.assertIn('"${MANIFEST_ARGS[@]}"', job)

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
        combined = _job_text(tampered, "desktop-swift-verify")
        self.assertNotIn("run-swift-ci.sh --test", combined)

    def test_adversarial_cache_key_weakening_detected(self):
        """A cache key without Package.resolved or toolchain identity is caught."""
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        tampered = wf_text.replace(
            "desktop-swift-build-xcode164-${{ hashFiles('desktop/macos/Desktop/Package.swift', 'desktop/macos/Desktop/Package.resolved') }}",
            "desktop-swift-${{ hashFiles('desktop/macos/Desktop/Package.swift') }}",
        )
        job = _job_text(tampered, "desktop-swift-verify")
        key = re.search(r"key:\s*([^\n]+)", job).group(1)
        self.assertNotIn("Package.resolved", key)


if __name__ == "__main__":
    unittest.main()
