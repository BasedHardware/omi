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


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.nightly = (WORKFLOWS / "main_nightly_full.yml").read_text()
        self.calls = dict(re.findall(r"(?m)^  ([\w-]+):\n    needs: source\n    uses: \./\.github/workflows/([\w-]+\.yml)$", self.nightly))

    def test_every_path_selected_pr_workflow_is_called(self):
        expected = set()
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text()
            triggers = text.split("\njobs:\n", 1)[0]
            if re.search(r"(?m)^  pull_request:", triggers):
                expected.add(path.name)
        self.assertEqual(set(self.calls.values()), expected)

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
                    self.assertEqual(re.findall(pattern, before[name]), re.findall(pattern, after[name]), (filename, name, field))


if __name__ == "__main__":
    unittest.main()
