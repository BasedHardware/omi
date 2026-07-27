#!/usr/bin/env python3
"""Tests for retiring superseded Windows release sync PRs."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "retire_superseded_windows_sync_prs",
    Path(__file__).with_name("retire_superseded_windows_sync_prs.py"),
)
sync_cleanup = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = sync_cleanup
_SPEC.loader.exec_module(sync_cleanup)


def pull_request(
    number: int,
    branch: str,
    *,
    base: str = "main",
    cross_repository: bool = False,
) -> dict[str, object]:
    return {
        "number": number,
        "headRefName": branch,
        "baseRefName": base,
        "isCrossRepository": cross_repository,
    }


class FakeRunner:
    def __init__(
        self,
        payload: object,
        *,
        list_returncode: int = 0,
        close_failures: set[int] | None = None,
    ) -> None:
        self.payload = payload
        self.list_returncode = list_returncode
        self.close_failures = close_failures or set()
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(
                args,
                self.list_returncode,
                stdout=json.dumps(self.payload),
                stderr="list failed" if self.list_returncode else "",
            )
        number = int(args[3])
        return subprocess.CompletedProcess(
            args,
            1 if number in self.close_failures else 0,
            stdout="",
            stderr="close failed" if number in self.close_failures else "",
        )

    @property
    def closed_numbers(self) -> list[int]:
        return [int(args[3]) for args in self.calls if args[:3] == ["gh", "pr", "close"]]


class RetireSupersededWindowsSyncPRsTests(unittest.TestCase):
    def test_closes_only_older_same_repository_main_sync_prs(self) -> None:
        runner = FakeRunner(
            [
                pull_request(10723, "release/windows-v1.0.26"),
                pull_request(10419, "release/windows-v1.0.3"),
                pull_request(10718, "release/windows-v1.0.25"),
                pull_request(10730, "release/windows-v1.0.27"),
                pull_request(10684, "release/windows-v1.0.22", cross_repository=True),
                pull_request(10653, "release/windows-v1.0.21", base="development"),
                pull_request(10000, "release/windows-maintenance"),
            ]
        )
        stdout = io.StringIO()

        closed = sync_cleanup.retire_superseded_prs(
            repository="BasedHardware/Omi",
            current_pr=10723,
            current_version=(1, 0, 26),
            runner=runner,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(closed, 2)
        self.assertEqual(runner.closed_numbers, [10419, 10718])
        close_calls = [args for args in runner.calls if args[:3] == ["gh", "pr", "close"]]
        self.assertTrue(all("--delete-branch" not in args for args in close_calls))
        self.assertTrue(all("#10723" in args[args.index("--comment") + 1] for args in close_calls))
        self.assertIn("Retired 2 superseded", stdout.getvalue())

    def test_skips_cleanup_unless_the_current_pr_is_confirmed(self) -> None:
        runner = FakeRunner([pull_request(10419, "release/windows-v1.0.3")])
        stderr = io.StringIO()

        closed = sync_cleanup.retire_superseded_prs(
            repository="BasedHardware/Omi",
            current_pr=10723,
            current_version=(1, 0, 26),
            runner=runner,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(closed, 0)
        self.assertEqual(runner.closed_numbers, [])
        self.assertIn("current Windows sync PR #10723 was not confirmed", stderr.getvalue())

    def test_close_failure_is_nonfatal_and_does_not_stop_cleanup(self) -> None:
        runner = FakeRunner(
            [
                pull_request(10723, "release/windows-v1.0.26"),
                pull_request(10419, "release/windows-v1.0.3"),
                pull_request(10718, "release/windows-v1.0.25"),
            ],
            close_failures={10419},
        )
        stderr = io.StringIO()

        closed = sync_cleanup.retire_superseded_prs(
            repository="BasedHardware/Omi",
            current_pr=10723,
            current_version=(1, 0, 26),
            runner=runner,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(closed, 1)
        self.assertEqual(runner.closed_numbers, [10419, 10718])
        self.assertIn("could not close superseded Windows sync PR #10419", stderr.getvalue())

    def test_list_failure_is_nonfatal(self) -> None:
        runner = FakeRunner([], list_returncode=1)
        stderr = io.StringIO()

        closed = sync_cleanup.retire_superseded_prs(
            repository="BasedHardware/Omi",
            current_pr=10723,
            current_version=(1, 0, 26),
            runner=runner,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(closed, 0)
        self.assertEqual(runner.closed_numbers, [])
        self.assertIn("could not list Windows sync PRs", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
