#!/usr/bin/env python3
"""Portability contract tests for the pre-push single-flight runner."""

from __future__ import annotations

import ctypes
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
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


def wait_for_windows_process_exit(pid: int, timeout_ms: int = 10_000) -> bool:
    """Wait on a process handle instead of polling wall-clock time."""
    if os.name != "nt":
        raise RuntimeError("Windows process waits are only available on Windows")

    from ctypes import wintypes

    synchronize = 0x00100000
    wait_object_0 = 0
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait_for_single_object.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = open_process(synchronize, False, pid)
    if not handle:
        return not runner.process_exists(pid)
    try:
        return wait_for_single_object(handle, timeout_ms) == wait_object_0
    finally:
        close_handle(handle)


class FakeChild:
    def __init__(self, returncode: int | None = None) -> None:
        self.pid = 4321
        self.returncode = returncode
        self.signals: list[int] = []
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def send_signal(self, signum: int) -> None:
        self.signals.append(signum)

    def terminate(self) -> None:
        self.terminated = True


class FakeWindowsJob:
    def __init__(self, terminated: bool = True) -> None:
        self.terminated = terminated
        self.calls = 0

    def terminate(self, exit_code: int = 1) -> bool:
        self.calls += 1
        return self.terminated


class ForwardableSignalTests(unittest.TestCase):
    def test_skips_signals_the_host_does_not_define(self) -> None:
        windows_signal = types.SimpleNamespace(SIGINT=2, SIGTERM=15, SIGBREAK=21)

        self.assertEqual(runner.forwardable_signals(windows_signal), (2, 15, 21))

    def test_registers_sighup_when_the_host_defines_it(self) -> None:
        posix_signal = types.SimpleNamespace(SIGINT=2, SIGTERM=15, SIGHUP=1)

        self.assertEqual(runner.forwardable_signals(posix_signal), (2, 15, 1))

    def test_every_selected_signal_is_registrable_on_this_host(self) -> None:
        for signum in runner.forwardable_signals():
            previous = signal.getsignal(signum)
            signal.signal(signum, previous)


class OutputFlushTests(unittest.TestCase):
    def test_retries_a_temporarily_full_nonblocking_pipe(self) -> None:
        stream = mock.Mock()
        stream.flush.side_effect = [
            BlockingIOError(35, "write could not complete without blocking"),
            BlockingIOError(35, "write could not complete without blocking"),
            None,
        ]

        with mock.patch.object(runner, "wait_for_stream_writable") as wait:
            runner.flush_output(stream)

        self.assertEqual(stream.flush.call_count, 3)
        self.assertEqual(wait.call_count, 2)
        wait.assert_called_with(stream)

    def test_retries_an_interrupted_flush_without_waiting_for_capacity(self) -> None:
        stream = mock.Mock()
        stream.flush.side_effect = [InterruptedError(), None]

        with mock.patch.object(runner, "wait_for_stream_writable") as wait:
            runner.flush_output(stream)

        self.assertEqual(stream.flush.call_count, 2)
        wait.assert_not_called()


class SignalChildTests(unittest.TestCase):
    def test_posix_signals_the_whole_child_process_group(self) -> None:
        child = FakeChild()

        with mock.patch.object(runner.os, "killpg", create=True) as killpg:
            runner.signal_child(child, signal.SIGINT)

        killpg.assert_called_once_with(child.pid, signal.SIGINT)
        self.assertEqual(child.signals, [])

    def test_hosts_without_process_groups_forward_to_the_child(self) -> None:
        child = FakeChild()

        with mock.patch.object(runner.os, "killpg", None, create=True):
            runner.signal_child(child, signal.SIGINT)

        self.assertEqual(child.signals, [signal.SIGINT])

    def test_windows_job_terminates_the_process_tree(self) -> None:
        child = FakeChild()
        job = FakeWindowsJob()

        runner.signal_child(child, signal.SIGINT, windows_job=job)

        self.assertEqual(job.calls, 1)
        self.assertEqual(child.signals, [])

    def test_windows_job_still_terminates_descendants_after_root_exit(self) -> None:
        child = FakeChild(returncode=0)
        job = FakeWindowsJob()

        runner.signal_child(child, signal.SIGINT, windows_job=job)

        self.assertEqual(job.calls, 1)

    def test_dead_child_does_not_raise(self) -> None:
        child = FakeChild()

        with mock.patch.object(runner.os, "killpg", side_effect=ProcessLookupError, create=True):
            runner.signal_child(child, signal.SIGTERM)

    def test_dead_child_without_process_groups_does_not_raise(self) -> None:
        child = mock.Mock(pid=4321)
        child.send_signal.side_effect = ProcessLookupError

        with mock.patch.object(runner.os, "killpg", None, create=True):
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
        child = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
            stdin=subprocess.PIPE,
        )
        try:
            self.assertTrue(runner.process_exists(child.pid))
            self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=10)
            if child.stdin is not None:
                child.stdin.close()

    @unittest.skipUnless(os.name == "nt", "native Windows process-tree contract")
    def test_windows_job_terminates_descendants(self) -> None:
        parent_code = (
            "import subprocess, sys;"
            "sys.stdin.buffer.read(1);"
            "child=subprocess.Popen("
            "[sys.executable, '-c', 'import sys; sys.stdin.buffer.read()'],"
            "stdin=subprocess.PIPE"
            ");"
            "print(child.pid, flush=True);"
            "sys.stdin.buffer.read()"
        )
        parent = subprocess.Popen(
            [sys.executable, "-c", parent_code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        job = runner.WindowsJob()
        descendant_pid = 0
        try:
            job.assign(parent.pid)
            assert parent.stdin is not None
            assert parent.stdout is not None
            parent.stdin.write("g")
            parent.stdin.flush()
            descendant_pid = int(parent.stdout.readline())
            self.assertTrue(runner.process_exists(descendant_pid))

            self.assertTrue(job.terminate())
            parent.wait(timeout=10)
            self.assertTrue(wait_for_windows_process_exit(descendant_pid))
            self.assertFalse(runner.process_exists(descendant_pid))
        finally:
            job.terminate()
            job.close()
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=10)
            if parent.stdin is not None:
                parent.stdin.close()
            if parent.stdout is not None:
                parent.stdout.close()


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

        self.assertIn("source scripts/dev-harness/_resolve_python.sh", wrapper)
        self.assertIn('PYTHON_BIN="$(dev_harness_python)"', wrapper)
        self.assertIn('PREFLIGHT_COMMAND=(scripts/pre-push "$@")', wrapper)
        self.assertIn(
            'exec "$PYTHON_BIN" .github/scripts/preflight_runner.py --name pre-push -- "${PREFLIGHT_COMMAND[@]}"',
            wrapper,
        )
        self.assertIn("source scripts/dev-harness/_resolve_python.sh", pre_push)
        self.assertIn('PYTHON_BIN="$(dev_harness_python)"', pre_push)
        self.assertIn(
            'CI_PREDICTION_SELECTION=$("$PYTHON_BIN" scripts/pre_push_ci_prediction.py',
            pre_push,
        )
        self.assertIn(
            '"$PYTHON_BIN" .github/scripts/check_failure_class_guard_ratchet.py',
            pre_push,
        )
        self.assertIn('PYRIGHT_PYTHON="$BACKEND_PYTHON" bash scripts/typecheck.sh', pre_push)
        self.assertIn("source scripts/dev-harness/_resolve_python.sh", pr_preflight)
        self.assertIn('exec "$PYTHON_BIN" .github/scripts/pr_preflight.py "$@"', pr_preflight)

    @unittest.skipUnless(os.name == "nt", "native Windows interpreter contract")
    def test_pr_preflight_uses_explicit_python_without_python3_on_path(self) -> None:
        bash = find_hook_bash()
        git = shutil.which("git")
        self.assertIsNotNone(bash)
        self.assertIsNotNone(git)

        env = os.environ.copy()
        env["PYTHON"] = Path(sys.executable).as_posix()
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
            (scripts / "dev-harness").mkdir()
            subprocess.run(
                [git, "init", "--quiet", str(root)],
                check=True,
                capture_output=True,
            )
            shutil.copy2(WRAPPER_PATH, scripts / "pre-push-singleflight")
            shutil.copy2(
                REPO_ROOT / "scripts" / "dev-harness" / "_resolve_python.sh",
                scripts / "dev-harness" / "_resolve_python.sh",
            )
            shutil.copy2(MODULE_PATH, github_scripts / "preflight_runner.py")
            proof_path = root / "wrapper-proof.txt"
            (scripts / "pre-push").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'printf "%s\\n" "$PYTHON" > "$PROOF_PATH"\n'
                'printf "wrapper-ok\\n"\n',
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PYTHON"] = Path(sys.executable).as_posix()
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
