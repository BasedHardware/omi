#!/usr/bin/env python3
"""Portability contract tests for the pre-push single-flight runner."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "preflight_runner.py"
REPO_ROOT = SCRIPT_DIR.parents[1]
WRAPPER_PATH = REPO_ROOT / "scripts" / "pre-push-singleflight"
SPEC = importlib.util.spec_from_file_location("preflight_runner", MODULE_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def find_hook_bash() -> str | None:
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_root = Path(git).resolve().parent.parent
            for relative_path in (Path("bin/bash.exe"), Path("usr/bin/bash.exe")):
                candidate = git_root / relative_path
                if candidate.is_file():
                    return str(candidate)
    return shutil.which("bash")


class FakeChild:
    def __init__(self, returncode: int | None = None) -> None:
        self.pid = 4321
        self.returncode = returncode
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


class OwnedSignalTests(unittest.TestCase):
    def test_skips_signals_the_host_does_not_define(self) -> None:
        windows_signal = types.SimpleNamespace(SIGINT=2, SIGTERM=15, SIGBREAK=21)

        self.assertEqual(runner.owned_signals(windows_signal), (2, 15, 21))

    def test_registers_sighup_when_the_host_defines_it(self) -> None:
        posix_signal = types.SimpleNamespace(SIGINT=2, SIGTERM=15, SIGHUP=1)

        self.assertEqual(runner.owned_signals(posix_signal), (2, 15, 1))

    def test_every_selected_signal_is_registrable_on_this_host(self) -> None:
        for signum in runner.owned_signals():
            previous = signal.getsignal(signum)
            signal.signal(signum, previous)


class SignalChildTests(unittest.TestCase):
    def test_posix_signals_the_whole_child_process_group(self) -> None:
        child = FakeChild()

        with mock.patch.object(runner, "HAS_PROCESS_GROUPS", True):
            with mock.patch.object(runner.os, "killpg", create=True) as killpg:
                runner.signal_child(child, signal.SIGINT)

        killpg.assert_called_once_with(child.pid, signal.SIGINT)
        self.assertFalse(child.terminated)

    def test_hosts_without_process_groups_terminate_the_child(self) -> None:
        child = FakeChild()

        with mock.patch.object(runner, "HAS_PROCESS_GROUPS", False):
            runner.signal_child(child, signal.SIGINT)

        self.assertTrue(child.terminated)

    def test_exited_child_is_left_alone(self) -> None:
        child = FakeChild(returncode=0)

        with mock.patch.object(runner, "HAS_PROCESS_GROUPS", False):
            runner.signal_child(child, signal.SIGINT)

        self.assertFalse(child.terminated)

    def test_dead_child_does_not_raise(self) -> None:
        child = FakeChild()

        with mock.patch.object(runner, "HAS_PROCESS_GROUPS", True):
            with mock.patch.object(runner.os, "killpg", side_effect=ProcessLookupError, create=True):
                runner.signal_child(child, signal.SIGTERM)


class ProcessExistsTests(unittest.TestCase):
    def test_windows_never_calls_os_kill(self) -> None:
        with mock.patch.object(runner, "IS_WINDOWS", True):
            with mock.patch.object(runner, "windows_process_exists", return_value=True) as probe:
                with mock.patch.object(runner.os, "kill", side_effect=AssertionError("os.kill terminates on Windows")):
                    self.assertTrue(runner.process_exists(99))

        probe.assert_called_once_with(99)

    def test_live_and_dead_pids(self) -> None:
        self.assertTrue(runner.process_exists(os.getpid()))
        self.assertFalse(runner.process_exists(0))


class WrapperContractTests(unittest.TestCase):
    def test_launches_extensionless_pre_push_through_active_bash(self) -> None:
        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")

        self.assertIn(' -- "$BASH" scripts/pre-push "$@"', wrapper)

    def test_runner_launches_bash_on_this_host(self) -> None:
        bash = find_hook_bash()
        self.assertIsNotNone(bash)

        with tempfile.TemporaryDirectory() as state_dir:
            env = {**os.environ, "OMI_PREFLIGHT_STATE_DIR": state_dir}
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--name", "bash-launch", "--", bash, "-c", "printf bash-ok"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("bash-ok", completed.stdout)


if __name__ == "__main__":
    unittest.main()
