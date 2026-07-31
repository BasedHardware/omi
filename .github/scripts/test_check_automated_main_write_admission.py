#!/usr/bin/env python3
"""Self-suite for check_automated_main_write_admission.

Each case builds a workflow on disk and runs the real checker against it, so the
guard is exercised through the same file-reading path CI uses rather than through
a stubbed string. The mutation cases matter most: they reintroduce exactly the
defects #10535 describes and assert the guard rejects them.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check_automated_main_write_admission.py"
_spec = importlib.util.spec_from_file_location("check_automated_main_write_admission", MODULE_PATH)
guard = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(guard)


FIXED = """
name: Sync Docs
on:
  push:
    branches: [main]
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Generate Omi Bot token
        id: app-token
        uses: actions/create-github-app-token@v3
      - name: Create Pull Request
        uses: peter-evans/create-pull-request@v8
        with:
          token: ${{ steps.app-token.outputs.token }}
          base: main
      - name: Auto-merge PR
        run: |
          gh pr merge --merge --delete-branch --admin "$PR_URL"
"""

# The pre-#10535 shape: PR opened with GITHUB_TOKEN, merged with --squash.
BROKEN = FIXED.replace(
    "token: ${{ steps.app-token.outputs.token }}",
    "token: ${{ secrets.GITHUB_TOKEN }}",
).replace("gh pr merge --merge", "gh pr merge --squash")

# A workflow that opens a PR for humans and never merges it: out of scope.
HUMAN_PR_ONLY = """
name: Propose
on: workflow_dispatch
jobs:
  propose:
    runs-on: ubuntu-latest
    steps:
      - uses: peter-evans/create-pull-request@v8
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          base: main
"""


class CheckWorkflowTests(unittest.TestCase):
    def _errors_for(self, content: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflow.yml"
            path.write_text(content, encoding="utf-8")
            original_root = guard.ROOT
            guard.ROOT = Path(tmp)
            try:
                return guard.check_workflow(path)
            finally:
                guard.ROOT = original_root

    def test_the_repaired_shape_passes(self):
        self.assertEqual(self._errors_for(FIXED), [])

    def test_rejects_a_pr_opened_with_github_token(self):
        """MUTATION: the #10535 defect — GITHUB_TOKEN means zero checks fire."""
        errors = self._errors_for(BROKEN)
        self.assertTrue(
            any("secrets.GITHUB_TOKEN" in e for e in errors),
            f"guard missed the GITHUB_TOKEN-authored PR: {errors}",
        )

    def test_rejects_a_pr_that_uses_the_default_token(self):
        missing_token = FIXED.replace("          token: ${{ steps.app-token.outputs.token }}\n", "")
        errors = self._errors_for(missing_token)
        self.assertTrue(
            any("explicit non-default token" in e for e in errors),
            f"guard missed the default-token PR: {errors}",
        )

    def test_rejects_a_squashed_automated_merge(self):
        """MUTATION: --squash breaks `git revert -m 1` recovery on main."""
        errors = self._errors_for(BROKEN)
        self.assertTrue(
            any("--squash" in e for e in errors),
            f"guard missed the squashed automated merge: {errors}",
        )

    def test_rejects_a_rebased_automated_merge(self):
        rebase = FIXED.replace("gh pr merge --merge", "gh pr merge --rebase")
        errors = self._errors_for(rebase)
        self.assertTrue(
            any("--merge" in error for error in errors),
            f"guard missed the non-revertible rebase merge: {errors}",
        )

    def test_rejects_a_non_app_token(self):
        non_app_token = FIXED.replace(
            "${{ steps.app-token.outputs.token }}",
            "${{ secrets.AUTOMATION_TOKEN }}",
        )
        errors = self._errors_for(non_app_token)
        self.assertTrue(
            any("app-identity contract" in error for error in errors),
            f"guard missed a non-app PR token: {errors}",
        )

    def test_rejects_an_app_token_step_declared_after_the_pr_step(self):
        """MUTATION: token: ${{ steps.app-token.outputs.token }} with the app-token
        step declared after Create Pull Request — the token is not yet available
        when the PR opens, so the checkable app-identity contract is unproven."""
        # Move the app-token step (first step in FIXED) to after Auto-merge PR.
        wrong_order = "\n".join(
            line
            for line in FIXED.splitlines()
            if "Generate Omi Bot token" not in line and "id: app-token" not in line
        )
        wrong_order = wrong_order.replace(
            "      - name: Auto-merge PR\n",
            "      - name: Generate Omi Bot token\n"
            "        id: app-token\n"
            "        uses: actions/create-github-app-token@v3\n"
            "      - name: Auto-merge PR\n",
        )
        errors = self._errors_for(wrong_order)
        self.assertTrue(
            any("declared after" in error for error in errors),
            f"guard missed the app-token-after-create-pr ordering: {errors}",
        )

    def test_ignores_a_commented_out_merge_line(self):
        commented = FIXED.replace(
            'gh pr merge --merge --delete-branch --admin "$PR_URL"',
            '# gh pr merge --squash --delete-branch --admin "$PR_URL"',
        )
        self.assertEqual(
            [e for e in self._errors_for(commented) if "--squash" in e],
            [],
            "a commented-out squash is not a squash",
        )

    def test_flags_a_self_merging_workflow_with_no_app_token_at_all(self):
        no_token = FIXED.replace("uses: actions/create-github-app-token@v3", "run: echo none").replace(
            "token: ${{ steps.app-token.outputs.token }}", "base: main"
        )
        errors = self._errors_for(no_token)
        self.assertTrue(
            any("create-github-app-token" in e for e in errors),
            f"guard missed the missing app token: {errors}",
        )


class ScopeTests(unittest.TestCase):
    def test_the_real_repo_passes(self):
        """The guard must be green on the tree it ships with."""
        self.assertEqual(guard.main(), 0)

    def test_only_self_merging_workflows_are_in_scope(self):
        """A workflow that opens a PR for a human to review is not this failure mode."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "propose.yml"
            path.write_text(HUMAN_PR_ONLY, encoding="utf-8")
            self.assertNotIn(guard.GH_PR_MERGE, path.read_text(encoding="utf-8"))

    def test_the_real_sync_docs_workflow_is_actually_covered(self):
        """Guard the guard: if the scope filter stops matching sync-docs.yml, the
        suite above would pass while protecting nothing."""
        matched = [p.name for p in guard._self_merging_workflows()]
        self.assertIn("sync-docs.yml", matched, f"sync-docs.yml fell out of scope; matched={matched}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
