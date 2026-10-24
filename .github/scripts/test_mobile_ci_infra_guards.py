#!/usr/bin/env python3
"""Static contract for the 2026-10-21 mobile CI infra flake guards.

Two recurring infra failures, both on mobile-app-checks.yml:

* Android NDK download corruption. Every Gradle-configuring mobile job
  auto-downloaded NDK 28.2 inside Gradle configure with no retry, and a
  truncated dl.google.com response failed the job before any app code ran
  ("Error on ZipFile unknown archive"; runs 39506049904, 39469917718,
  39626150998). The jobs must preinstall the pinned NDK through
  install_android_ndk.py, with the pin keyed once per job as NDK_VERSION
  (build.gradle resolves the same variable), equal to the ndkVersion
  fallback in app/android/app/build.gradle, and cached under one shared key
  with exactly one writer (android-emulator-checks, the only job that runs
  in every event the readers do and is not the compile-smoke wall).
* iOS Compile Check ceiling. The 40-minute timeout sat below the measured
  cold path — 39:25 of real steps plus the ~1 min post-job "Post Setup
  Flutter" cache save (run 39634604539 attempt 1) — cancelling a healthy
  job after every real step passed. 50 is the asserted budget: above that
  cold path with wedge headroom, while the CI budget check counts p50
  (19), not the ceiling.
"""

from pathlib import Path
import re
import unittest

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "mobile-app-checks.yml"
BUILD_GRADLE_PATH = REPO_ROOT / "app" / "android" / "app" / "build.gradle"

# Jobs whose Gradle configure resolves ndkVersion and therefore must
# preinstall the pinned NDK instead of relying on AGP's unretried download.
NDK_JOBS = ("android-compile-smoke", "android-unit-tests", "android-emulator-checks")
NDK_CACHE_WRITER = "android-emulator-checks"
NDK_CACHE_PATH = "/usr/local/lib/android/sdk/ndk/${{ env.NDK_VERSION }}"
NDK_CACHE_KEY = "${{ runner.os }}-android-ndk-${{ env.NDK_VERSION }}"
NDK_INSTALL_RUN = 'install_android_ndk.py --ndk-version "$NDK_VERSION"'
IOS_COLD_PATH_TIMEOUT_MINUTES = 50

BUILD_GRADLE_NDK_PIN_RE = re.compile(
    r'ndkVersion\s+System\.getenv\(\)\["NDK_VERSION"\]\s*\?:\s*"([0-9][0-9.]*)"'
)


def load_workflow() -> dict:
    doc = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) parses the bare `on:` key as boolean True.
    if isinstance(doc, dict) and "on" not in doc and True in doc:
        doc["on"] = doc.pop(True)
    return doc


def build_gradle_ndk_pin() -> str:
    match = BUILD_GRADLE_NDK_PIN_RE.search(BUILD_GRADLE_PATH.read_text(encoding="utf-8"))
    if match is None:
        raise AssertionError(
            f"{BUILD_GRADLE_PATH.relative_to(REPO_ROOT)}: ndkVersion fallback pin not found; "
            "update NDK_VERSION in mobile-app-checks.yml and this pattern together"
        )
    return match.group(1)


class MobileCIInfraGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = load_workflow()
        cls.jobs = cls.doc["jobs"]

    def test_ndk_pin_matches_build_gradle_fallback(self) -> None:
        expected = build_gradle_ndk_pin()
        for job_id in NDK_JOBS:
            with self.subTest(job=job_id):
                version = self.jobs[job_id].get("env", {}).get("NDK_VERSION")
                self.assertEqual(
                    expected,
                    version,
                    f"{job_id}: NDK_VERSION must equal app/android/app/build.gradle's "
                    "ndkVersion fallback; AGP would otherwise download a second NDK "
                    "inside Gradle configure despite the preinstall",
                )

    def test_gradle_jobs_preinstall_the_pinned_ndk(self) -> None:
        for job_id in NDK_JOBS:
            with self.subTest(job=job_id):
                steps = self.jobs[job_id]["steps"]
                cache_steps = [
                    step
                    for step in steps
                    if step.get("uses", "").split("@")[0] in ("actions/cache", "actions/cache/restore")
                    and step.get("with", {}).get("path") == NDK_CACHE_PATH
                ]
                self.assertEqual(
                    1,
                    len(cache_steps),
                    f"{job_id}: expected exactly one NDK cache step with path {NDK_CACHE_PATH}",
                )
                self.assertEqual(NDK_CACHE_KEY, cache_steps[0]["with"].get("key"), f"{job_id}: NDK cache key changed")
                install_steps = [
                    step for step in steps if NDK_INSTALL_RUN in str(step.get("run", ""))
                ]
                self.assertEqual(
                    1,
                    len(install_steps),
                    f"{job_id}: must preinstall the NDK via `python3 {NDK_INSTALL_RUN}` so a "
                    "corrupt download is purged and retried instead of failing Gradle configure",
                )

    def test_exactly_one_ndk_cache_writer_and_it_covers_every_reader_event(self) -> None:
        for job_id in NDK_JOBS:
            with self.subTest(job=job_id):
                ndk_cache_uses = [
                    step["uses"]
                    for step in self.jobs[job_id]["steps"]
                    if step.get("with", {}).get("path") == NDK_CACHE_PATH
                ]
                self.assertEqual(1, len(ndk_cache_uses), f"{job_id}: expected exactly one NDK cache step")
                expected = (
                    "actions/cache@v6" if job_id == NDK_CACHE_WRITER else "actions/cache/restore@v6"
                )
                self.assertEqual(
                    expected,
                    ndk_cache_uses[0],
                    f"{job_id}: only {NDK_CACHE_WRITER} may save the NDK cache (restore-only "
                    "elsewhere keeps post-job saves off the compile-smoke wall); a second "
                    "writer also races the shared key",
                )
        writer_condition = str(self.jobs[NDK_CACHE_WRITER].get("if", ""))
        for job_id in NDK_JOBS:
            if job_id == NDK_CACHE_WRITER:
                continue
            with self.subTest(reader=job_id):
                reader_condition = str(self.jobs[job_id].get("if", ""))
                # The reader's whole condition must appear as a disjunct of the
                # writer's, so any event or path filter that runs a reader also
                # runs the writer; otherwise a reader's first run per ref would
                # download unretried while the cache stays unseeded.
                self.assertIn(
                    reader_condition,
                    writer_condition,
                    f"{job_id}: its `if` is no longer contained in {NDK_CACHE_WRITER}'s `if`; "
                    "either widen the writer's condition or make this job a writer too",
                )

    def test_ios_compile_timeout_covers_the_measured_cold_path(self) -> None:
        timeout = self.jobs["ios-compile-check"]["timeout-minutes"]
        self.assertEqual(
            IOS_COLD_PATH_TIMEOUT_MINUTES,
            timeout,
            "iOS Compile Check's ceiling must stay above the measured cold path (39:25 real "
            "steps + ~1 min post-job cache save, run 39634604539 attempt 1) or a healthy "
            "cold job is cancelled after every real step passes; re-measure before changing",
        )


if __name__ == "__main__":
    unittest.main()
