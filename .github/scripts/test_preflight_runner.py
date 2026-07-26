#!/usr/bin/env python3
"""Portability contract tests for the pre-push single-flight runner."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "preflight_runner.py"
PR_PREFLIGHT_MODULE_PATH = SCRIPT_DIR / "pr_preflight.py"
REPO_ROOT = SCRIPT_DIR.parents[1]
WRAPPER_PATH = REPO_ROOT / "scripts" / "pre-push-singleflight"
PRE_PUSH_PATH = REPO_ROOT / "scripts" / "pre-push"
PR_PREFLIGHT_PATH = REPO_ROOT / "scripts" / "pr-preflight"
SPEC = importlib.util.spec_from_file_location("preflight_runner", MODULE_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
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


def windows_path_without_python(bash: str, git: str) -> str:
    return os.pathsep.join(
        [
            str(Path(git).parent),
            str(Path(bash).parent),
            str(Path(os.environ["SystemRoot"]) / "System32"),
        ]
    )


class FakeChild:
    def __init__(self, returncode: int | None = None) -> None:
        self.pid = 4321
        self.returncode = returncode
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


class FakeWindowsJob:
    def __init__(self, terminated: bool = True) -> None:
        self.terminated = terminated
        self.calls = 0

    def terminate(self, exit_code: int = 1) -> bool:
        self.calls += 1
        return self.terminated


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

        with (
            mock.patch.object(runner, "HAS_PROCESS_GROUPS", True),
            mock.patch.object(runner.os, "killpg", create=True) as killpg,
        ):
            runner.signal_child(child, signal.SIGINT)

        killpg.assert_called_once_with(child.pid, signal.SIGINT)
        self.assertFalse(child.terminated)

    def test_hosts_without_process_groups_terminate_the_child(self) -> None:
        child = FakeChild()

        with mock.patch.object(runner, "HAS_PROCESS_GROUPS", False):
            runner.signal_child(child, signal.SIGINT)

        self.assertTrue(child.terminated)

    def test_windows_job_terminates_the_process_tree(self) -> None:
        child = FakeChild()
        job = FakeWindowsJob()

        with mock.patch.object(runner, "HAS_PROCESS_GROUPS", False):
            runner.signal_child(child, signal.SIGINT, job)

        self.assertEqual(job.calls, 1)
        self.assertFalse(child.terminated)

    def test_windows_job_still_terminates_descendants_after_root_exit(self) -> None:
        child = FakeChild(returncode=0)
        job = FakeWindowsJob()

        runner.signal_child(child, signal.SIGINT, job)

        self.assertEqual(job.calls, 1)

    def test_exited_child_is_left_alone(self) -> None:
        child = FakeChild(returncode=0)

        with mock.patch.object(runner, "HAS_PROCESS_GROUPS", False):
            runner.signal_child(child, signal.SIGINT)

        self.assertFalse(child.terminated)

    def test_dead_child_does_not_raise(self) -> None:
        child = FakeChild()

        with (
            mock.patch.object(runner, "HAS_PROCESS_GROUPS", True),
            mock.patch.object(runner.os, "killpg", side_effect=ProcessLookupError, create=True),
        ):
            runner.signal_child(child, signal.SIGTERM)


class ProcessExistsTests(unittest.TestCase):
    def test_windows_never_calls_os_kill(self) -> None:
        with (
            mock.patch.object(runner, "IS_WINDOWS", True),
            mock.patch.object(runner, "windows_process_status", return_value=(True, 123)) as probe,
            mock.patch.object(
                runner.os,
                "kill",
                side_effect=AssertionError("os.kill is destructive on Windows"),
            ),
        ):
            self.assertTrue(runner.process_exists(99))

        probe.assert_called_once_with(99)

    def test_windows_pid_reuse_does_not_match_the_lock_owner(self) -> None:
        with (
            mock.patch.object(runner, "IS_WINDOWS", True),
            mock.patch.object(runner, "windows_process_status", return_value=(True, 456)),
        ):
            self.assertFalse(runner.process_exists(99, expected_creation_ticks=123))
            self.assertTrue(runner.process_exists(99, expected_creation_ticks=456))

    def test_windows_unknown_creation_time_does_not_match_the_lock_owner(self) -> None:
        with (
            mock.patch.object(runner, "IS_WINDOWS", True),
            mock.patch.object(runner, "windows_process_status", return_value=(True, None)),
        ):
            self.assertFalse(runner.process_exists(99, expected_creation_ticks=123))

    def test_live_and_dead_pids(self) -> None:
        self.assertTrue(runner.process_exists(os.getpid()))
        self.assertFalse(runner.process_exists(0))

    @unittest.skipUnless(os.name == "nt", "native Windows liveness contract")
    def test_windows_liveness_probe_does_not_terminate_the_target(self) -> None:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(runner.process_exists(child.pid))
            self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=10)

    @unittest.skipUnless(os.name == "nt", "native Windows process-tree contract")
    def test_windows_job_terminates_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            go_path = root / "go"
            child_pid_path = root / "child.pid"
            parent_code = (
                "import pathlib, subprocess, sys, time;"
                f"go=pathlib.Path({str(go_path)!r});"
                f"child_pid=pathlib.Path({str(child_pid_path)!r});"
                "\nwhile not go.exists(): time.sleep(0.02)"
                "\nchild=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])"
                "\nchild_pid.write_text(str(child.pid), encoding='utf-8')"
                "\ntime.sleep(30)"
            )
            parent = subprocess.Popen([sys.executable, "-c", parent_code])
            job = runner.WindowsJob()
            descendant_pid = 0
            try:
                job.assign(parent.pid)
                go_path.touch()
                deadline = time.monotonic() + 5
                while not child_pid_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(child_pid_path.exists(), "descendant did not start")
                descendant_pid = int(child_pid_path.read_text(encoding="utf-8"))
                self.assertTrue(runner.process_exists(descendant_pid))

                self.assertTrue(job.terminate())
                parent.wait(timeout=10)
                deadline = time.monotonic() + 5
                while runner.process_exists(descendant_pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(runner.process_exists(descendant_pid))
            finally:
                job.terminate()
                job.close()
                if parent.poll() is None:
                    parent.terminate()
                    parent.wait(timeout=10)


class LaunchContractTests(unittest.TestCase):
    def test_windows_launch_uses_a_job_assignment_barrier(self) -> None:
        command = ["bash", "scripts/pre-push"]

        with mock.patch.object(runner, "IS_WINDOWS", True):
            launch_command = runner.child_launch_command(command)

        self.assertEqual(launch_command[0], sys.executable)
        self.assertEqual(launch_command[2], runner.WINDOWS_CHILD_BOOTSTRAP_FLAG)
        self.assertEqual(launch_command[3:], command)

    def test_wrapper_and_backend_python_paths_are_explicit(self) -> None:
        """Static tripwire for the interpreter boundaries exercised below."""
        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
        pre_push = PRE_PUSH_PATH.read_text(encoding="utf-8")
        pr_preflight = PR_PREFLIGHT_PATH.read_text(encoding="utf-8")

        self.assertIn(' -- "$BASH_EXECUTABLE" scripts/pre-push "$@"', wrapper)
        self.assertIn("export PYTHONUTF8=1", wrapper)
        self.assertIn('export OMI_BASH_EXECUTABLE="$BASH_EXECUTABLE"', wrapper)
        self.assertIn('export OMI_PYTHON_EXECUTABLE="$PREFLIGHT_PYTHON"', wrapper)
        self.assertIn('PYTHON_EXECUTABLE="${OMI_PYTHON_EXECUTABLE:-}"', pre_push)
        self.assertIn(
            'CI_PREDICTION_SELECTION=$("$PYTHON_EXECUTABLE" scripts/pre_push_ci_prediction.py',
            pre_push,
        )
        self.assertIn('"$PWD/backend/.venv/Scripts/python.exe"', pre_push)
        self.assertIn('PYRIGHT_PYTHON="$BACKEND_PYTHON" bash scripts/typecheck.sh', pre_push)
        self.assertIn(
            'exec "$PYTHON_EXECUTABLE" .github/scripts/pr_preflight.py "$@"',
            pr_preflight,
        )

    @unittest.skipUnless(os.name == "nt", "native Windows interpreter contract")
    def test_pr_preflight_uses_explicit_python_without_python3_on_path(self) -> None:
        bash = find_hook_bash()
        git = shutil.which("git")
        self.assertIsNotNone(bash)
        self.assertIsNotNone(git)

        env = os.environ.copy()
        env["OMI_PYTHON_EXECUTABLE"] = Path(sys.executable).as_posix()
        env["PATH"] = windows_path_without_python(bash, git)
        python3_probe = subprocess.run(
            [bash, "-c", "command -v python3"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertNotEqual(python3_probe.returncode, 0, python3_probe.stdout)

        completed = subprocess.run(
            [bash, str(PR_PREFLIGHT_PATH), "--help"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage:", completed.stdout)

    @unittest.skipUnless(os.name == "nt", "native Windows wrapper contract")
    def test_wrapper_launches_pre_push_without_python3_on_path(self) -> None:
        bash = find_hook_bash()
        git = shutil.which("git")
        self.assertIsNotNone(bash)
        self.assertIsNotNone(git)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            scripts = root / "scripts"
            github_scripts = root / ".github" / "scripts"
            scripts.mkdir(parents=True)
            github_scripts.mkdir(parents=True)
            subprocess.run(
                [git, "init", "--quiet", str(root)],
                check=True,
                capture_output=True,
            )
            shutil.copy2(WRAPPER_PATH, scripts / "pre-push-singleflight")
            shutil.copy2(MODULE_PATH, github_scripts / "preflight_runner.py")
            proof_path = root / "wrapper-proof.txt"
            (scripts / "pre-push").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'printf "%s\\n" "$OMI_PYTHON_EXECUTABLE" > "$PROOF_PATH"\n'
                'printf "wrapper-ok\\n"\n',
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["BACKEND_PYTHON"] = Path(sys.executable).as_posix()
            env["OMI_PREFLIGHT_STATE_DIR"] = (root / "state").as_posix()
            env["PATH"] = windows_path_without_python(bash, git)
            env["PROOF_PATH"] = proof_path.as_posix()
            python3_probe = subprocess.run(
                [bash, "-c", "command -v python3"],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertNotEqual(python3_probe.returncode, 0, python3_probe.stdout)
            completed = subprocess.run(
                [bash, str(scripts / "pre-push-singleflight"), "fork"],
                cwd=root,
                env=env,
                input="",
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("wrapper-ok", completed.stdout)
            self.assertEqual(
                proof_path.read_text(encoding="utf-8").strip(),
                Path(sys.executable).as_posix(),
            )

    def test_runner_launches_bash_on_this_host(self) -> None:
        bash = find_hook_bash()
        self.assertIsNotNone(bash)

        with tempfile.TemporaryDirectory() as state_dir:
            env = {**os.environ, "OMI_PREFLIGHT_STATE_DIR": state_dir}
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--name",
                    "bash-launch",
                    "--",
                    bash,
                    "-c",
                    "printf bash-ok",
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("bash-ok", completed.stdout)

    def test_invalid_utf8_child_output_is_escaped_without_aborting(self) -> None:
        with tempfile.TemporaryDirectory() as state_dir:
            env = {**os.environ, "OMI_PREFLIGHT_STATE_DIR": state_dir}
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--name",
                    "invalid-utf8",
                    "--",
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.buffer.write(b'bad:\\xa1\\n'); sys.stdout.buffer.flush()",
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn(r"bad:\xa1", completed.stdout)

    @unittest.skipUnless(os.name == "nt", "native Windows Git encoding contract")
    def test_runner_handles_utf8_git_worktree_path_without_utf8_mode(self) -> None:
        git = shutil.which("git")
        self.assertIsNotNone(git)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo-\u96ea"
            root.mkdir()
            subprocess.run(
                [git, "init", "--quiet"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            env = os.environ.copy()
            env["PYTHONUTF8"] = "0"
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--name",
                    "unicode-path",
                    "--",
                    sys.executable,
                    "-c",
                    "print('unicode-path-ok')",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("unicode-path-ok", completed.stdout)

    @unittest.skipUnless(os.name == "nt", "native Windows Git encoding contract")
    def test_pr_preflight_handles_utf8_git_worktree_path_without_utf8_mode(self) -> None:
        git = shutil.which("git")
        self.assertIsNotNone(git)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo-\u96ea"
            root.mkdir()
            subprocess.run(
                [git, "init", "--quiet"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    git,
                    "-c",
                    "user.name=Omi portability test",
                    "-c",
                    "user.email=portability@example.invalid",
                    "commit",
                    "--allow-empty",
                    "--quiet",
                    "-m",
                    "initial",
                ],
                cwd=root,
                check=True,
                capture_output=True,
            )
            env = os.environ.copy()
            env["PYTHONUTF8"] = "0"
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PR_PREFLIGHT_MODULE_PATH),
                    "--base",
                    "HEAD",
                    "--head",
                    "HEAD",
                    "--list",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("PR preflight:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
