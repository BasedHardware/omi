#!/usr/bin/env python3
"""Unit tests for check_runner_cost_policy.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_runner_cost_policy import validate


def write_workflow(root: Path, name: str, runs_on: str) -> None:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / name).write_text(
        f"name: fixture\njobs:\n  test:\n    runs-on: {runs_on}\n    steps: []\n",
        encoding="utf-8",
    )


class RunnerCostPolicyTests(unittest.TestCase):
    def test_accepts_standard_public_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_workflow(root, "standard.yml", "ubuntu-latest")
            self.assertEqual(validate(root), [])

    def test_rejects_paid_runner_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_workflow(root, "paid.yml", "ubuntu-latest-m")
            self.assertEqual(
                validate(root),
                [
                    ".github/workflows/paid.yml:4: paid runner label 'ubuntu-latest-m' "
                    "is forbidden; public-repository jobs must use a standard runner"
                ],
            )

    def test_checks_yaml_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_workflow(root, "paid.yaml", "ubuntu-latest-m")
            self.assertEqual(len(validate(root)), 1)


if __name__ == "__main__":
    unittest.main()
