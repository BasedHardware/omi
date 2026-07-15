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

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/desktop-swift-ci.yml"

EXPECTED_XCODE_VERSION = "16.4"
EXPECTED_XCODE_BUILD = "16F6"
EXPECTED_XCODE_APP = f"/Applications/Xcode_{EXPECTED_XCODE_VERSION}.app"
JOBS = ["desktop-swift", "desktop-swift-release-compile"]


def _load_workflow() -> dict:
    with open(WORKFLOW_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _steps(job_def: dict) -> list[dict]:
    return job_def.get("steps", [])


def _run_texts(job_def: dict) -> list[str]:
    """Return the concatenated ``run`` body of every step that has one."""
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
        cache_step = None
        for step in _steps(job):
            if step.get("uses", "").startswith("actions/cache"):
                cache_step = step
                break
        self.assertIsNotNone(cache_step, "desktop-swift must have a cache step")
        key = cache_step["with"]["key"]
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

    # --- changed-file gate assertions --------------------------------------

    def test_release_compile_gates_on_package_resolved(self):
        """Release compile must trigger when Package.resolved changes, even on
        a PR where the manifest source is unchanged."""
        job = self.jobs["desktop-swift-release-compile"]
        combined = "\n".join(_run_texts(job))
        self.assertIn(
            "PACKAGE_RESOLVED",
            combined,
            "release-compile job must check for Package.resolved changes",
        )

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
        tampered_wf = yaml.safe_load(tampered)
        combined = "\n".join(_run_texts(tampered_wf["jobs"]["desktop-swift"]))
        self.assertNotIn("DEVELOPER_DIR", combined)

    def test_adversarial_cache_key_weakening_detected(self):
        """A cache key without Package.resolved or toolchain identity is caught."""
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        tampered = wf_text.replace(
            "desktop-swift-xcode164-${{ hashFiles('desktop/macos/Desktop/Package.swift', 'desktop/macos/Desktop/Package.resolved') }}",
            "desktop-swift-${{ hashFiles('desktop/macos/Desktop/Package.swift') }}",
        )
        tampered_wf = yaml.safe_load(tampered)
        job = tampered_wf["jobs"]["desktop-swift"]
        cache_step = next(
            s for s in _steps(job) if s.get("uses", "").startswith("actions/cache")
        )
        key = cache_step["with"]["key"]
        self.assertNotIn("Package.resolved", key)


if __name__ == "__main__":
    unittest.main()
