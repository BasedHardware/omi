#!/usr/bin/env python3
"""Self-test: the guard must fail on the shape it exists to prevent."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "check_workflow_checkout_stall_bounds.py"
_spec = importlib.util.spec_from_file_location("check_workflow_checkout_stall_bounds", _MODULE_PATH)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)

BOUND_ENV = 'env:\n  GIT_HTTP_LOW_SPEED_LIMIT: "1000"\n  GIT_HTTP_LOW_SPEED_TIME: "60"\n'


class CheckoutStallBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / ".github" / "workflows").mkdir(parents=True)

    def _workflow(self, uses: str, *, env: str = "", job_env: str = "", name: str = "wf.yml") -> Path:
        path = self.root / ".github" / "workflows" / name
        path.write_text(
            f"name: t\non: push\n{env}jobs:\n  j:\n    runs-on: ubuntu-latest\n{job_env}"
            f"    steps:\n      - uses: {uses}\n"
        )
        return path

    def _action(self, uses: str, *, name: str = "deploy") -> None:
        directory = self.root / ".github" / "actions" / name
        directory.mkdir(parents=True)
        (directory / "action.yml").write_text(
            f"name: {name}\nruns:\n  using: composite\n  steps:\n    - uses: {uses}\n"
        )

    def test_checkout_with_workflow_env_passes(self) -> None:
        self.assertEqual(guard.check_workflow(self._workflow("actions/checkout@v7", env=BOUND_ENV)), [])

    def test_checkout_without_env_is_rejected(self) -> None:
        """The exact regression: checkout with no stall bound hangs until the TCP reset."""
        problems = guard.check_workflow(self._workflow("actions/checkout@v7"))
        self.assertEqual(len(problems), 2, problems)

    def test_only_one_variable_is_rejected(self) -> None:
        """git needs both: LIMIT alone never trips, TIME alone has no threshold."""
        env = 'env:\n  GIT_HTTP_LOW_SPEED_LIMIT: "1000"\n'
        problems = guard.check_workflow(self._workflow("actions/checkout@v7", env=env))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("GIT_HTTP_LOW_SPEED_TIME", problems[0])

    def test_job_level_env_does_not_count(self) -> None:
        """Workflow level is the contract, so a new job cannot silently miss it."""
        job_env = '    env:\n      GIT_HTTP_LOW_SPEED_LIMIT: "1000"\n      GIT_HTTP_LOW_SPEED_TIME: "60"\n'
        self.assertTrue(guard.check_workflow(self._workflow("actions/checkout@v7", job_env=job_env)))

    def test_zero_or_empty_values_are_rejected(self) -> None:
        env = 'env:\n  GIT_HTTP_LOW_SPEED_LIMIT: "0"\n  GIT_HTTP_LOW_SPEED_TIME: ""\n'
        self.assertEqual(len(guard.check_workflow(self._workflow("actions/checkout@v7", env=env))), 2)

    def test_workflow_without_checkout_is_left_alone(self) -> None:
        self.assertEqual(guard.check_workflow(self._workflow("actions/setup-python@v6")), [])

    def test_caller_of_a_checkout_action_must_be_bounded(self) -> None:
        """A checkout moved into a composite action inherits the caller's env."""
        self._action("actions/checkout@v7")
        refs = guard.checkout_action_refs(self.root)
        self.assertEqual(refs, {"./.github/actions/deploy"})
        self.assertTrue(guard.check_workflow(self._workflow("./.github/actions/deploy"), refs))
        self.assertEqual(guard.check_workflow(self._workflow("./.github/actions/deploy", env=BOUND_ENV), refs), [])

    def test_staged_copy_of_a_checkout_action_counts(self) -> None:
        """Deploy workflows call the action from a staged tree under another prefix."""
        self._action("actions/checkout@v7", name="firestore-readiness")
        refs = guard.checkout_action_refs(self.root)
        staged = "./.github/firestore-workflow/.github/actions/firestore-readiness"
        self.assertTrue(guard.check_workflow(self._workflow(staged), refs))
        self.assertEqual(guard.check_workflow(self._workflow(staged, env=BOUND_ENV), refs), [])
        # A different action that merely shares a name prefix is not a match.
        self.assertEqual(guard.check_workflow(self._workflow("./.github/actions/firestore-readiness-lite"), refs), [])

    def test_main_fails_on_unbounded_tree_and_passes_bounded_one(self) -> None:
        self._workflow("actions/checkout@v7", name="a.yml")
        self.assertEqual(guard.main(["prog", str(self.root)]), 1)
        self._workflow("actions/checkout@v7", env=BOUND_ENV, name="a.yml")
        self.assertEqual(guard.main(["prog", str(self.root)]), 0)

    def test_repository_tree_is_bounded(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.assertEqual(guard.main(["prog", str(repo_root)]), 0)


if __name__ == "__main__":
    unittest.main()
