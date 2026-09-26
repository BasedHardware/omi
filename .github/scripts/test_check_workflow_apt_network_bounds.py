#!/usr/bin/env python3
"""Self-test: the guard must fail on the shape it exists to prevent."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "check_workflow_apt_network_bounds.py"
_spec = importlib.util.spec_from_file_location("check_workflow_apt_network_bounds", _MODULE_PATH)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)

BOUNDED = "sudo apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=10 -o Acquire::https::Timeout=10"


def _workflow(directory: Path, run: str, *, timeout: bool = True) -> Path:
    step = "      - name: deps\n"
    if timeout:
        step += "        timeout-minutes: 5\n"
    step += "        run: |\n"
    for line in run.splitlines():
        step += f"          {line}\n"
    path = directory / "wf.yml"
    path.write_text(f"name: t\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n{step}")
    return path


class AptNetworkBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_bounded_call_with_step_timeout_passes(self) -> None:
        path = _workflow(self.tmp_path, f"{BOUNDED} update\n{BOUNDED} install --yes redis-server")
        self.assertEqual(guard.check_workflow(path), [])

    def test_unbounded_install_is_rejected_even_when_update_is_bounded(self) -> None:
        """The exact regression: the update line bounded, the install line forgotten."""
        path = _workflow(self.tmp_path, f"{BOUNDED} update\nsudo apt-get install -y xvfb")
        problems = guard.check_workflow(path)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("install -y xvfb", problems[0])
        self.assertIn("Acquire::Retries", problems[0])

    def test_missing_step_timeout_is_rejected(self) -> None:
        path = _workflow(self.tmp_path, f"{BOUNDED} update", timeout=False)
        problems = guard.check_workflow(path)
        self.assertTrue(any("timeout-minutes" in problem for problem in problems), problems)

    def test_every_network_subcommand_is_covered(self) -> None:
        for subcommand in ("update", "install --yes curl", "upgrade", "build-dep foo", "download bar"):
            with self.subTest(subcommand=subcommand):
                path = _workflow(self.tmp_path, f"sudo apt-get {subcommand}")
                self.assertTrue(guard.check_workflow(path), f"{subcommand!r} should require acquire bounds")

    def test_non_network_subcommands_are_left_alone(self) -> None:
        """``clean``/``autoremove`` touch no mirror; bounding them would be noise."""
        path = _workflow(self.tmp_path, "sudo apt-get clean\nsudo apt-get autoremove --yes", timeout=False)
        self.assertEqual(guard.check_workflow(path), [])

    def test_repository_workflows_are_bounded(self) -> None:
        root = Path(__file__).resolve().parents[1] / "workflows"
        problems: list[str] = []
        for path in sorted(root.glob("*.yml")):
            problems.extend(guard.check_workflow(path))
        self.assertEqual(problems, [], "\n".join(problems))


class CompositeActionBoundsTests(unittest.TestCase):
    """A bounded apt call may live in a composite action; the guard must follow it there."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def _action(self, run: str, *, name: str = "install-redis-server") -> Path:
        directory = self.tmp_path / ".github" / "actions" / name
        directory.mkdir(parents=True, exist_ok=True)
        step = "  steps:\n    - name: install\n      shell: bash\n      run: |\n"
        for line in run.splitlines():
            step += f"        {line}\n"
        path = directory / "action.yml"
        path.write_text(f"name: {name}\nruns:\n  using: composite\n{step}")
        return path

    def _caller(self, uses: str, *, timeout: bool = True, name: str = "wf.yml") -> Path:
        directory = self.tmp_path / ".github" / "workflows"
        directory.mkdir(parents=True, exist_ok=True)
        step = f"      - name: deps\n        uses: {uses}\n"
        if timeout:
            step += "        timeout-minutes: 5\n"
        path = directory / name
        path.write_text(
            f"name: t\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n{step}"
        )
        return path

    def test_the_old_checker_fails_open_on_an_action(self) -> None:
        """Why a separate entry point exists: the workflow shape does not match an action.

        `check_workflow` looks under `jobs.<id>.steps`; a composite action keeps its steps
        under `runs.steps`. Pointed at an action file it reports clean, so widening only
        the glob would have produced a guard that scanned the file and still saw nothing.
        """
        path = self._action("sudo apt-get install -y redis-server")
        self.assertEqual(guard.check_workflow(path), [])
        self.assertTrue(guard.check_action(path))

    def test_unbounded_apt_in_an_action_is_rejected(self) -> None:
        path = self._action("sudo apt-get install -y redis-server")
        problems = guard.check_action(path)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("Acquire::Retries", problems[0])

    def test_bounded_apt_in_an_action_passes_without_step_timeout(self) -> None:
        """`timeout-minutes` is not a valid key on a composite step, so it is not required.

        Demanding it here would make the guard unsatisfiable for the one shape it now has
        to cover.
        """
        path = self._action(f"{BOUNDED} update\n{BOUNDED} install --yes redis-server")
        self.assertEqual(guard.check_action(path), [])

    def test_non_composite_actions_are_left_alone(self) -> None:
        directory = self.tmp_path / ".github" / "actions" / "js-action"
        directory.mkdir(parents=True)
        path = directory / "action.yml"
        path.write_text("name: js\nruns:\n  using: node20\n  main: index.js\n")
        self.assertEqual(guard.check_action(path), [])

    def test_caller_of_an_apt_action_must_declare_a_ceiling(self) -> None:
        """The backstop moves to the call site; nothing else can carry it."""
        self._action(f"{BOUNDED} install --yes redis-server")
        caller = self._caller("./.github/actions/install-redis-server", timeout=False)
        problems = guard.check_workflow_callers(
            caller, {"./.github/actions/install-redis-server"}
        )
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("timeout-minutes", problems[0])

    def test_caller_with_a_ceiling_passes(self) -> None:
        self._action(f"{BOUNDED} install --yes redis-server")
        caller = self._caller("./.github/actions/install-redis-server", timeout=True)
        self.assertEqual(
            guard.check_workflow_callers(caller, {"./.github/actions/install-redis-server"}), []
        )

    def test_callers_of_other_actions_are_not_burdened(self) -> None:
        caller = self._caller("./.github/actions/detect-changes", timeout=False)
        self.assertEqual(
            guard.check_workflow_callers(caller, {"./.github/actions/install-redis-server"}), []
        )

    def test_main_walks_both_trees_and_catches_the_laundered_ceiling(self) -> None:
        """End to end: bounded options inside the action, no ceiling on the caller."""
        self._action(f"{BOUNDED} update\n{BOUNDED} install --yes redis-server")
        self._caller("./.github/actions/install-redis-server", timeout=False)
        self.assertEqual(guard.main(["prog", str(self.tmp_path)]), 1)

    def test_main_passes_when_both_halves_are_present(self) -> None:
        self._action(f"{BOUNDED} update\n{BOUNDED} install --yes redis-server")
        self._caller("./.github/actions/install-redis-server", timeout=True)
        self.assertEqual(guard.main(["prog", str(self.tmp_path)]), 0)

    def test_main_still_accepts_the_historical_workflows_argument(self) -> None:
        """The old call form pointed at `.github/workflows`; it must not scan nothing."""
        self._caller("./.github/actions/detect-changes", timeout=True)
        workflows = self.tmp_path / ".github" / "workflows"
        self.assertEqual(guard.main(["prog", str(workflows)]), 0)

    def test_repository_actions_are_bounded(self) -> None:
        root = Path(__file__).resolve().parents[1] / "actions"
        problems: list[str] = []
        for path in sorted(root.glob("*/action.yml")):
            problems.extend(guard.check_action(path))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_repository_tree_passes_end_to_end(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.assertEqual(guard.main(["prog", str(repo_root)]), 0)


if __name__ == "__main__":
    unittest.main()
