"""Fail closed when PR workflows drift outside the unfiltered nightly graph."""

from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"


def jobs(text):
    body = text.split("\njobs:\n", 1)[1]
    chunks = re.split(r"(?m)^  ([\w-]+):\n", body)
    return dict(zip(chunks[1::2], chunks[2::2]))


# Deliberate, reviewed budget changes to nightly-reusable jobs. The default
# contract is that a PR never changes a reusable job's runner or timeout, so
# the nightly graph's cost stays what CI budgets. Record the new value here
# with the PR that changed it; the assertion below then pins the exact value,
# so any later drift still fails until this dict is edited in review.
# P65: PR-triggered schema provisioning is an external writer, not an offline
# test suite. Calling it from the nightly graph would cross the no-writes
# boundary. Its behavioral tests still run via backend-unit-tests.yml.
PR_SCHEMA_WRITERS = {"gcp_firestore_indexes.yml"}

INTENTIONAL_BUDGET_CHANGES = {
    # iOS Compile Check: the 40-min ceiling sat below the measured cold path
    # (39:25 real steps + ~1 min post-job Post Setup Flutter cache save, run
    # 39634604539 attempt 1), cancelling a healthy cold job after every real
    # step passed. 50 restores wedge headroom; budget_p50 stays 19.
    ("mobile-app-checks.yml", "ios-compile-check", "timeout-minutes"): "50",
    # Backend unit shard: the 15-min job ceiling includes runner setup, but
    # the 720s step regression budget excludes it, leaving 180s for setup.
    # Setup measured 73-92s typical, 227s worst (run 39741901310 attempt 2:
    # checkout 72s, apt-get 155s), so 227s + 720s crossed the ceiling and the
    # shard was cancelled mid-run while still inside its step budget — four
    # such 917-920s walls in the week to 2026-10-22 (39741901310,
    # 39739120103, 39676205452, 39668020536). 20m held until the apt
    # cold-cache step needed recycling room. Run 40009383869 still exhausted
    # the Azure mirror slices; the step now uses official Ubuntu archives,
    # slices downloads only within 300s, and caps the whole install at 7m.
    # 25m holds 720s tests + 72s checkout + 90s toolchain + 420s apt, leaving
    # 198s for cache save and post-actions (test_nightly_main_native_audio.py).
    # The test regression gate and warm-path walls stay unchanged, so
    # budget_p50 stays 8.
    ("backend-unit-tests.yml", "backend-unit-shard", "timeout-minutes"): "25",
}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.nightly = (WORKFLOWS / "main_nightly_full.yml").read_text()
        self.calls = dict(re.findall(r"(?m)^  ([\w-]+):\n    needs: source\n    uses: \./\.github/workflows/([\w-]+\.yml)$", self.nightly))

    def test_every_path_selected_pr_workflow_is_called(self):
        expected = set()
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text()
            triggers = text.split("\njobs:\n", 1)[0]
            if re.search(r"(?m)^  pull_request:", triggers) and path.name not in PR_SCHEMA_WRITERS:
                expected.add(path.name)
        self.assertEqual(set(self.calls.values()), expected)

    def test_pr_schema_writers_stay_outside_the_offline_nightly_graph(self):
        self.assertTrue(PR_SCHEMA_WRITERS.isdisjoint(self.calls.values()))
        for filename in PR_SCHEMA_WRITERS:
            text = (WORKFLOWS / filename).read_text()
            self.assertIn('firestore-schema-', text)
            self.assertIn('id-token:', text)
            self.assertIn('--provision-missing', text)

    def test_nightly_does_not_implement_tests_or_inherit_secrets(self):
        self.assertIn("cron: '7 3 * * *'", self.nightly)
        self.assertIn("  workflow_dispatch:", self.nightly)
        self.assertIn("  cancel-in-progress: true", self.nightly)
        self.assertNotIn("secrets:", self.nightly)
        self.assertNotIn("secrets.", self.nightly)
        self.assertIn("          ref: main", self.nightly)
        self.assertEqual(self.nightly.count("nightly_main_sha: ${{ needs.source.outputs.main_sha }}"), len(self.calls))
        self.assertEqual(set(jobs(self.nightly)) - set(self.calls), {"source", "report"})

    def test_checkouts_are_pinned_and_external_writer_jobs_are_disabled(self):
        for filename in self.calls.values():
            text = (WORKFLOWS / filename).read_text()
            with self.subTest(workflow=filename):
                self.assertIn("  workflow_call:", text)
                self.assertEqual(len(re.findall(r"uses: actions/checkout@", text)),
                                 text.count("ref: ${{ inputs.nightly_main_sha || github.sha }}"))
                # Scripts that read GITHUB_SHA see the workflow-file commit, not the checkout.
                if "preflight_public_build_config.py" in text:
                    self.assertIn('--ref "${{ inputs.nightly_main_sha || github.sha }}"', text)
                for name, body in jobs(text).items():
                    if "issues: write" in body or "id-token: write" in body:
                        self.assertRegex(body, r"if: .*inputs\.nightly_main_sha == ''", name)

    def test_reusable_jobs_keep_their_existing_runner_and_timeout(self):
        # Compare with this tree's integration base, never a newer main fetched
        # after a nightly pinned its source (that would create a false red).
        base = subprocess.run(["git", "merge-base", "origin/main", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
        for filename in self.calls.values():
            baseline = subprocess.run(["git", "show", f"{base}:.github/workflows/{filename}"],
                                      cwd=ROOT, capture_output=True, text=True, check=True).stdout
            before, after = jobs(baseline), jobs((WORKFLOWS / filename).read_text())
            self.assertEqual(set(before), set(after), filename)
            for name in before:
                for field in ("runs-on", "timeout-minutes"):
                    pattern = rf"(?m)^    {field}:.*$"
                    after_values = re.findall(pattern, after[name])
                    pinned = INTENTIONAL_BUDGET_CHANGES.get((filename, name, field))
                    if pinned is not None:
                        self.assertEqual([f"    {field}: {pinned}"], after_values, (filename, name, field))
                        continue
                    self.assertEqual(re.findall(pattern, before[name]), after_values, (filename, name, field))


if __name__ == "__main__":
    unittest.main()
