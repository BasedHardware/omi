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


if __name__ == "__main__":
    unittest.main()
