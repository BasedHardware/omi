#!/usr/bin/env python3
"""Contract test for desktop-swift-ci.yml toolchain pinning and cache-key integrity.

Fails if either CI job loses Xcode selection, version assertion, version logging,
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

EXPECTED_XCODE_VERSION = "16.4"
EXPECTED_XCODE_BUILD = "16F6"
EXPECTED_XCODE_APP = f"/Applications/Xcode_{EXPECTED_XCODE_VERSION}.app"
JOBS = ["desktop-swift", "desktop-swift-release-compile"]


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


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


def _steps(job_def: dict) -> list[dict]:
    if isinstance(job_def, str):
        return []
    return job_def.get("steps", [])


def _run_texts(job_def: dict) -> list[str]:
    """Return the concatenated ``run`` body of every step that has one."""
    if isinstance(job_def, str):
        return [job_def]
    texts: list[str] = []
    for step in _steps(job_def):
        run = step.get("run")
        if run:
            texts.append(run if isinstance(run, str) else "\n".join(run))
    return texts


class DesktopSwiftCIContractTests(unittest.TestCase):
    """Verify toolchain pinning, version logging, and cache-key completeness."""

    @classmethod
    def setUpClass(cls):
        cls.workflow = _load_workflow()
        cls.jobs = cls.workflow["jobs"]

    # --- per-job assertions ------------------------------------------------

    def test_both_jobs_select_pinned_xcode(self):
        for job_id in JOBS:
            with self.subTest(job=job_id):
                job = self.jobs[job_id]
                combined = "\n".join(_run_texts(job))
                self.assertIn(
                    EXPECTED_XCODE_APP,
                    combined,
                    f"{job_id}: must reference the pinned Xcode app path",
                )
                self.assertIn(
                    "DEVELOPER_DIR",
                    combined,
                    f"{job_id}: must set DEVELOPER_DIR to the pinned Xcode",
                )

    def test_both_jobs_fail_closed_on_missing_xcode(self):
        for job_id in JOBS:
            with self.subTest(job=job_id):
                job = self.jobs[job_id]
                combined = "\n".join(_run_texts(job))
                self.assertIn(
                    "exit 1",
                    combined,
                    f"{job_id}: must exit non-zero when pinned Xcode is absent",
                )
                # The fail-closed check must test for the directory's existence.
                dir_check = re.search(r"if\s*\[\s*!\s*-d\s+\"\$?XCODE_APP", combined)
                self.assertIsNotNone(
                    dir_check,
                    f"{job_id}: must test for the Xcode directory existence",
                )

    def test_both_jobs_print_toolchain_versions(self):
        for job_id in JOBS:
            with self.subTest(job=job_id):
                job = self.jobs[job_id]
                combined = "\n".join(_run_texts(job))
                self.assertIn(
                    "xcodebuild -version",
                    combined,
                    f"{job_id}: must print xcodebuild -version before Swift actions",
                )
                self.assertIn(
                    "xcrun swift --version",
                    combined,
                    f"{job_id}: must print xcrun swift --version before Swift actions",
                )

    def test_both_jobs_assert_expected_version_and_build(self):
        for job_id in JOBS:
            with self.subTest(job=job_id):
                job = self.jobs[job_id]
                combined = "\n".join(_run_texts(job))
                self.assertIn(
                    f'"Xcode {EXPECTED_XCODE_VERSION}"',
                    combined,
                    f"{job_id}: must assert the expected Xcode version string",
                )
                self.assertIn(
                    f'"{EXPECTED_XCODE_BUILD}"',
                    combined,
                    f"{job_id}: must assert the expected Xcode build number",
                )

    def test_both_jobs_use_same_toolchain(self):
        """Both debug and release paths must select the same pinned Xcode."""
        for job_id in JOBS:
            with self.subTest(job=job_id):
                job = self.jobs[job_id]
                combined = "\n".join(_run_texts(job))
                self.assertIn(
                    EXPECTED_XCODE_APP,
                    combined,
                    f"{job_id}: must use the same toolchain as the other job",
                )

    # --- cache-key assertions ----------------------------------------------

    def test_cache_key_includes_manifest_and_lockfile_and_toolchain(self):
        """The SwiftPM cache key must include Package.swift, Package.resolved,
        and a toolchain identity component."""
        job = self.jobs["desktop-swift"]
        self.assertIn("uses: actions/cache", job, "desktop-swift must have a cache step")
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
        self.assertIn(
            "swift-format-wrapper.sh",
            key,
            "cache key must invalidate when the pinned formatter provenance changes",
        )
        self.assertIn(
            "swiftlint-wrapper.sh",
            key,
            "cache key must invalidate when the pinned linter provenance changes",
        )
        self.assertIn("~/.cache/omi-swift-format", job)
        self.assertIn("~/.cache/omi-swiftlint", job)

    def test_cache_saves_completed_build_state_after_a_test_failure(self):
        """A retry should reuse SwiftPM's validated incremental build state."""
        job = self.jobs["desktop-swift"]
        self.assertIn("id: swiftpm-cache", job)
        self.assertIn("uses: actions/cache/restore@v4", job)
        self.assertIn("uses: actions/cache/save@v4", job)
        self.assertIn("always()", job)
        self.assertIn("steps.swiftpm-cache.outputs.cache-hit != 'true'", job)

    # --- changed-file gate assertions --------------------------------------

    def test_release_compile_gates_on_package_resolved(self):
        """Release compile must trigger when Package.resolved changes, even on
        a PR where the manifest source is unchanged."""
        job = self.jobs["desktop-swift-release-compile"]
        combined = "\n".join(_run_texts(job))
        # The variable must be wired into the SHOULD_RUN conditional, not just
        # declared or logged — removing the gate while keeping other references
        # must fail this test.
        self.assertTrue(
            re.search(r'"\$PACKAGE_RESOLVED"\s*=\s*"true"', combined),
            "release-compile job must gate SHOULD_RUN on PACKAGE_RESOLVED=true",
        )

    def test_manifest_checks_use_the_changed_diff_base_on_pushes(self):
        """Pushes must lint the just-pushed diff, not checkout's origin/main HEAD."""
        job = self.jobs["desktop-swift"]
        self.assertIn('echo "diff_base=$DIFF_BASE" >> "$GITHUB_OUTPUT"', job)
        self.assertIn(
            '--base "${{ steps.changed.outputs.diff_base }}"',
            job,
            "manifest checks must use HEAD~1 on main pushes and the PR base on pull requests",
        )

    def test_xcode_version_probe_does_not_close_its_pipe_early(self):
        """head(1) aborts Xcode 16.4 under pipefail; sed reads the full output."""
        for job_id in JOBS:
            with self.subTest(job=job_id):
                combined = "\n".join(_run_texts(self.jobs[job_id]))
                self.assertNotIn("xcodebuild -version | head -1", combined)
                self.assertIn("xcodebuild -version | sed -n '1p'", combined)

    # --- adversarial: removing any guard must fail -------------------------

    def test_adversarial_remove_xcode_step_detected(self):
        """A workflow without the Xcode selection must fail the above checks."""
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        # Remove the Xcode selection step entirely from the first job.
        tampered = re.sub(
            r"      - name: Select and assert pinned Xcode 16\.4\n"
            r"        if:.*\n"
            r"        run: \|.*?(?=\n      - name: )",
            "",
            wf_text,
            count=1,
            flags=re.DOTALL,
        )
        combined = _job_text(tampered, "desktop-swift")
        self.assertNotIn("DEVELOPER_DIR", combined)

    def test_adversarial_cache_key_weakening_detected(self):
        """A cache key without Package.resolved or toolchain identity is caught."""
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        tampered = wf_text.replace(
            "desktop-swift-xcode164-${{ hashFiles('desktop/macos/Desktop/Package.swift', 'desktop/macos/Desktop/Package.resolved', 'desktop/macos/scripts/swift-format-wrapper.sh', 'desktop/macos/scripts/swiftlint-wrapper.sh') }}",
            "desktop-swift-${{ hashFiles('desktop/macos/Desktop/Package.swift') }}",
        )
        job = _job_text(tampered, "desktop-swift")
        key = re.search(r"key:\s*([^\n]+)", job).group(1)
        self.assertNotIn("Package.resolved", key)

    def test_adversarial_remove_package_resolved_gate_detected(self):
        """Removing the PACKAGE_RESOLVED gate from SHOULD_RUN while keeping
        other references must fail the positive gate assertion."""
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        tampered = wf_text.replace('|| [ "$PACKAGE_RESOLVED" = "true" ]', "")
        combined = _job_text(tampered, "desktop-swift-release-compile")
        # PACKAGE_RESOLVED still appears (declared, detected, echoed) but the
        # gate condition is gone — the regex must fail to match.
        self.assertIn("PACKAGE_RESOLVED", combined)  # still referenced
        self.assertIsNone(
            re.search(r'"\$PACKAGE_RESOLVED"\s*=\s*"true"', combined),
            "gate condition must be absent after removal",
        )


if __name__ == "__main__":
    unittest.main()
