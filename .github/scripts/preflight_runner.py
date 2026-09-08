#!/usr/bin/env python3
"""Run a command single-flight with observable per-worktree state and logs."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TextIO

POLL_SECONDS = 0.2
STATUS_INTERVAL_SECONDS = 5.0
WINDOWS_ATOMIC_REPLACE_RETRY_SECONDS = 0.01
WINDOWS_ATOMIC_REPLACE_TIMEOUT_SECONDS = 2.0
MAX_PR_BODY_FINGERPRINT_BYTES = 1024 * 1024
FORWARDED_SIGNAL_NAMES = ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK")
FINGERPRINT_ENV_NAMES = (
    "GITHUB_HEAD_REF",
    "OMI_PR_BODY_FILE",
    "PATH",
    "PYTHON",
    "PYTHONPATH",
)
IS_WINDOWS = os.name == "nt"
HAS_PROCESS_GROUPS = os.name != "nt" and hasattr(os, "killpg")
WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WINDOWS_SYNCHRONIZE = 0x00100000
WINDOWS_WAIT_OBJECT_0 = 0x00000000
WINDOWS_WAIT_TIMEOUT = 0x00000102
WINDOWS_PROCESS_SET_QUOTA = 0x0100
WINDOWS_PROCESS_TERMINATE = 0x0001
WINDOWS_ERROR_ACCESS_DENIED = 5
WINDOWS_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
WINDOWS_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
WINDOWS_CHILD_BOOTSTRAP_FLAG = "--windows-child-bootstrap"


def wait_for_stream_writable(stream: TextIO) -> None:
    """Wait for a temporarily full inherited output pipe without changing its flags."""
    if IS_WINDOWS:
        # Windows select() accepts sockets only. A short retry is the portable
        # fallback; Windows pipes are not normally inherited in non-blocking mode.
        time.sleep(POLL_SECONDS)
        return
    try:
        select.select([], [stream.fileno()], [])
    except InterruptedError:
        return
    except (OSError, ValueError):
        # Streams without a selectable descriptor are rare here, but retrying is
        # still safer than turning successful validation into a failed push.
        time.sleep(POLL_SECONDS)


def flush_output(stream: TextIO) -> None:
    """Flush buffered output, waiting through a non-blocking pipe's EAGAIN.

    Git and IDE hosts may expose stdout as a non-blocking pipe. Large child
    output can fill it between a write and flush; the buffered bytes remain
    pending, so retry the same flush once the consumer has capacity.
    """
    while True:
        try:
            stream.flush()
            return
        except BlockingIOError:
            wait_for_stream_writable(stream)
        except InterruptedError:
            continue


class WindowsJob:
    """Own a Windows process tree and terminate it when the job closes."""

    def __init__(self) -> None:
        if not IS_WINDOWS:
            raise RuntimeError("Windows jobs are only available on Windows")

        from ctypes import wintypes

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_job = kernel32.CreateJobObjectW
        create_job.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        create_job.restype = wintypes.HANDLE
        set_information = kernel32.SetInformationJobObject
        set_information.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        set_information.restype = wintypes.BOOL
        self._open_process = kernel32.OpenProcess
        self._open_process.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self._open_process.restype = wintypes.HANDLE
        self._assign_process = kernel32.AssignProcessToJobObject
        self._assign_process.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._assign_process.restype = wintypes.BOOL
        self._terminate_job = kernel32.TerminateJobObject
        self._terminate_job.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._terminate_job.restype = wintypes.BOOL
        self._close_handle = kernel32.CloseHandle
        self._close_handle.argtypes = [wintypes.HANDLE]
        self._close_handle.restype = wintypes.BOOL

        self._handle = create_job(None, None)
        self.assigned = False
        if not self._handle:
            raise self._last_error("CreateJobObjectW failed")

        limits = ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = WINDOWS_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not set_information(
            self._handle,
            WINDOWS_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = self._last_error("SetInformationJobObject failed")
            self.close()
            raise error

    @staticmethod
    def _last_error(message: str) -> OSError:
        error_code = ctypes.get_last_error()
        return OSError(error_code, f"{message}: {ctypes.FormatError(error_code).strip()}")

    def assign(self, pid: int) -> None:
        process = self._open_process(
            WINDOWS_PROCESS_SET_QUOTA | WINDOWS_PROCESS_TERMINATE,
            False,
            pid,
        )
        if not process:
            raise self._last_error(f"OpenProcess({pid}) failed")
        try:
            if not self._assign_process(self._handle, process):
                raise self._last_error(f"AssignProcessToJobObject({pid}) failed")
        finally:
            self._close_handle(process)
        self.assigned = True

    def terminate(self, exit_code: int = 1) -> bool:
        if not self._handle or not self.assigned:
            return False
        return bool(self._terminate_job(self._handle, exit_code))

    def close(self) -> None:
        if self._handle:
            self._close_handle(self._handle)
            self._handle = None


def forwardable_signals(module: object = signal) -> tuple[int, ...]:
    """Return only the forwarding signals the current host defines."""
    return tuple(signum for name in FORWARDED_SIGNAL_NAMES if isinstance((signum := getattr(module, name, None)), int))


def child_launch_command(command: list[str]) -> list[str]:
    """Delay Windows command execution until the parent assigns its Job Object."""
    if not IS_WINDOWS:
        return command
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        WINDOWS_CHILD_BOOTSTRAP_FLAG,
        *command,
    ]


def run_windows_child_bootstrap(command: list[str]) -> int:
    """Forward stdin after the Job Object assignment barrier is released."""
    if not command:
        return 2
    return subprocess.run(command, input=sys.stdin.buffer.read()).returncode


def signal_child(
    child: subprocess.Popen[str],
    signum: int,
    *,
    windows_job: WindowsJob | None = None,
) -> None:
    """Forward to the POSIX child group or terminate the Windows process tree."""
    killpg = getattr(os, "killpg", None)
    try:
        if windows_job is not None and windows_job.terminate():
            return
        if killpg is not None:
            killpg(child.pid, signum)
        else:
            child.send_signal(signum)
    except (OSError, ValueError):
        pass


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    deadline = time.monotonic() + WINDOWS_ATOMIC_REPLACE_TIMEOUT_SECONDS
    while True:
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if not IS_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(WINDOWS_ATOMIC_REPLACE_RETRY_SECONDS)


def configure_output_streams() -> None:
    """Keep captured runner output UTF-8 and non-fatal on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        options = {"errors": "backslashreplace"}
        if IS_WINDOWS:
            options["encoding"] = "utf-8"
        reconfigure(**options)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def windows_process_status(pid: int) -> tuple[bool, int | None]:
    """Return Windows liveness and immutable process creation ticks."""
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait_for_single_object.restype = wintypes.DWORD
    get_process_times = kernel32.GetProcessTimes
    get_process_times.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    get_process_times.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = open_process(
        WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION | WINDOWS_SYNCHRONIZE,
        False,
        pid,
    )
    if not handle:
        return ctypes.get_last_error() == WINDOWS_ERROR_ACCESS_DENIED, None
    try:
        wait_result = wait_for_single_object(handle, 0)
        if wait_result == WINDOWS_WAIT_OBJECT_0:
            return False, None
        if wait_result != WINDOWS_WAIT_TIMEOUT:
            return True, None

        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not get_process_times(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return True, None
        creation_ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return True, creation_ticks
    finally:
        close_handle(handle)


def process_exists(pid: int, expected_creation_ticks: int | None = None) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        exists, creation_ticks = windows_process_status(pid)
        if expected_creation_ticks is not None:
            return exists and creation_ticks == expected_creation_ticks
        return exists
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def default_state_dir(root: Path, name: str) -> Path:
    override = os.getenv("OMI_PREFLIGHT_STATE_DIR")
    if override:
        return Path(override).resolve() / name
    git_dir = subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=root,
        text=True,
        encoding="utf-8",
    ).strip()
    return Path(git_dir) / "omi-preflight" / name


def fingerprint(root: Path, command: list[str], stdin_data: str) -> str:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    digest = hashlib.sha256()
    for value in (str(root.resolve()), head, "\0".join(command), stdin_data):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    relevant_names = set(FINGERPRINT_ENV_NAMES)
    relevant_names.update(name for name in os.environ if name.startswith("PRE_PUSH_"))
    for name in sorted(relevant_names):
        digest.update(name.encode("utf-8"))
        digest.update(b"=")
        digest.update(os.getenv(name, "").encode("utf-8"))
        digest.update(b"\0")
    body_path = os.getenv("OMI_PR_BODY_FILE", "").strip()
    if body_path:
        try:
            with Path(body_path).open("rb") as body_file:
                body = body_file.read(MAX_PR_BODY_FINGERPRINT_BYTES + 1)
            digest.update(body[:MAX_PR_BODY_FINGERPRINT_BYTES])
            if len(body) > MAX_PR_BODY_FINGERPRINT_BYTES:
                digest.update(b"<truncated-pr-body>")
        except OSError:
            digest.update(b"<unreadable-pr-body>")
        digest.update(b"\0")
    return digest.hexdigest()


def acquire(lock_dir: Path, owner: dict) -> bool:
    try:
        lock_dir.mkdir()
    except FileExistsError:
        return False
    atomic_json(lock_dir / "owner.json", owner)
    return True


def remove_stale_lock(lock_dir: Path, expected_pid: int) -> bool:
    owner = read_json(lock_dir / "owner.json")
    if int(owner.get("pid") or 0) != expected_pid:
        return False
    expected_creation_ticks = int(owner.get("process_creation_ticks") or 0) or None
    if process_exists(expected_pid, expected_creation_ticks):
        return False
    try:
        shutil.rmtree(lock_dir)
        return True
    except FileNotFoundError:
        return True


def join_existing(state_dir: Path, wanted_fingerprint: str) -> int | None:
    lock_dir = state_dir / "lock"
    owner = read_json(lock_dir / "owner.json")
    if not owner:
        try:
            lock_age = time.time() - lock_dir.stat().st_mtime
        except FileNotFoundError:
            return None
        if lock_age > 2:
            shutil.rmtree(lock_dir, ignore_errors=True)
        else:
            time.sleep(POLL_SECONDS)
        return None
    active_pid = int(owner.get("pid") or 0)
    active_creation_ticks = int(owner.get("process_creation_ticks") or 0) or None
    active_fingerprint = str(owner.get("fingerprint") or "")
    if not process_exists(active_pid, active_creation_ticks):
        if remove_stale_lock(lock_dir, active_pid):
            return None
    log_path = state_dir / "preflight.log"
    status_path = state_dir / "status.json"
    if active_fingerprint != wanted_fingerprint:
        status = read_json(status_path)
        phase = status.get("phase", "starting")
        print(
            f"FAIL: preflight PID {active_pid} is already running different input "
            f"(phase={phase}, log={log_path}). Retry after it finishes.",
            file=sys.stderr,
        )
        return 75

    print(f"Joining identical preflight PID {active_pid}; live log: {log_path}")
    next_status = 0.0
    while lock_dir.exists():
        if not process_exists(active_pid, active_creation_ticks):
            remove_stale_lock(lock_dir, active_pid)
            break
        now = time.monotonic()
        if now >= next_status:
            status = read_json(status_path)
            elapsed = max(0.0, time.time() - float(status.get("started_at_epoch") or time.time()))
            print(
                f"  active phase={status.get('phase', 'starting')} elapsed={elapsed:.1f}s",
            )
            flush_output(sys.stdout)
            next_status = now + STATUS_INTERVAL_SECONDS
        time.sleep(POLL_SECONDS)
    result = read_json(state_dir / "result.json")
    if result.get("fingerprint") != wanted_fingerprint:
        print("FAIL: joined preflight ended without a matching result; retry the push.", file=sys.stderr)
        return 1
    return int(result.get("exit_code", 1))


def run_owned(
    state_dir: Path,
    lock_dir: Path,
    wanted_fingerprint: str,
    command: list[str],
    stdin_data: str,
    root: Path,
) -> int:
    log_path = state_dir / "preflight.log"
    status_path = state_dir / "status.json"
    result_path = state_dir / "result.json"
    started = time.monotonic()
    started_wall = time.time()
    phase = "starting"
    last_phase = phase
    child: subprocess.Popen[str] | None = None
    received_signal: int | None = None
    windows_job: WindowsJob | None = None

    def write_status() -> None:
        atomic_json(
            status_path,
            {
                "pid": os.getpid(),
                "fingerprint": wanted_fingerprint,
                "phase": phase,
                "last_phase": last_phase,
                "received_signal": received_signal,
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "log": str(log_path),
                "started_at_epoch": started_wall,
            },
        )

    def forward_signal(signum: int, _frame: object) -> None:
        nonlocal received_signal
        received_signal = signum
        print(
            f"FAIL: preflight runner received signal {signal.Signals(signum).name} "
            f"during phase={phase}; forwarding it to the child.",
            file=sys.stderr,
        )
        flush_output(sys.stderr)
        write_status()
        if child is None:
            return
        if windows_job is None and child.poll() is not None:
            return
        signal_child(child, signum, windows_job=windows_job)

    previous_handlers = {signum: signal.signal(signum, forward_signal) for signum in forwardable_signals()}
    exit_code = 1
    try:
        if IS_WINDOWS:
            windows_job = WindowsJob()
        print(f"Pre-push single-flight log: {log_path}")
        log_path.write_text("", encoding="utf-8")
        os.chmod(log_path, 0o600)
        write_status()
        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
        child = subprocess.Popen(
            child_launch_command(command),
            cwd=root,
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            bufsize=1,
            start_new_session=HAS_PROCESS_GROUPS,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0),
        )
        if windows_job is not None:
            windows_job.assign(child.pid)
        if child.stdin:
            child.stdin.write(stdin_data)
            child.stdin.close()
        assert child.stdout is not None
        with log_path.open("a", encoding="utf-8") as log:
            for line in child.stdout:
                sys.stdout.write(line)
                flush_output(sys.stdout)
                log.write(line)
                log.flush()
                if line.startswith("==> "):
                    phase = line[4:].strip()
                    last_phase = phase
                    write_status()
        exit_code = child.wait()
        phase = "passed" if exit_code == 0 else "failed"
        write_status()
        if exit_code != 0:
            if exit_code < 0:
                child_failure = f"child terminated by {signal.Signals(-exit_code).name}"
            else:
                child_failure = f"child exited with status {exit_code}"
            signal_note = (
                f"; runner received {signal.Signals(received_signal).name}" if received_signal is not None else ""
            )
            print(
                f"FAIL: preflight {child_failure} during phase={last_phase}{signal_note}; inspect {log_path}",
                file=sys.stderr,
            )
            flush_output(sys.stderr)
        atomic_json(
            result_path,
            {
                "exit_code": exit_code,
                "fingerprint": wanted_fingerprint,
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "finished_at_epoch": time.time(),
                "log": str(log_path),
                "last_phase": last_phase,
                "received_signal": received_signal,
            },
        )
        return exit_code
    finally:
        if child is not None and child.poll() is None:
            signal_child(child, signal.SIGTERM, windows_job=windows_job)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if windows_job is not None:
            windows_job.terminate()
            windows_job.close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        shutil.rmtree(lock_dir, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="pre-push")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def resolve_repo_root() -> Path:
    # Git runs hooks with the working directory at the top of the invoking work
    # tree, and the pre-push dispatcher cd's to the repo root before invoking
    # this runner. Fall back to that working directory when `git rev-parse
    # --show-toplevel` cannot resolve a work tree: in a linked worktree whose
    # git context resolves to a git dir rather than a work tree, show-toplevel
    # exits 128 ("this operation must be run in a work tree") and this runner
    # would otherwise abort the gate, forcing a --no-verify push.
    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    except subprocess.CalledProcessError:
        toplevel = ""
    return Path(toplevel or Path.cwd()).resolve()


def main() -> int:
    configure_output_streams()
    if sys.argv[1:2] == [WINDOWS_CHILD_BOOTSTRAP_FLAG]:
        return run_windows_child_bootstrap(sys.argv[2:])

    args = parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("FAIL: preflight runner requires a command after --", file=sys.stderr)
        return 2
    root = resolve_repo_root()
    # Git supplies ref updates on a pipe. Manual preflight runs inherit a TTY;
    # treating that as empty input avoids waiting forever for an interactive EOF.
    stdin_data = "" if sys.stdin.isatty() else sys.stdin.read()
    wanted_fingerprint = fingerprint(root, command, stdin_data)
    state_dir = default_state_dir(root, args.name)
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_dir, 0o700)
    lock_dir = state_dir / "lock"
    owner = {
        "pid": os.getpid(),
        "fingerprint": wanted_fingerprint,
        "started_at_epoch": time.time(),
    }
    if IS_WINDOWS:
        _, process_creation_ticks = windows_process_status(os.getpid())
        if process_creation_ticks is not None:
            owner["process_creation_ticks"] = process_creation_ticks

    while not acquire(lock_dir, owner):
        joined = join_existing(state_dir, wanted_fingerprint)
        if joined is not None:
            return joined
    return run_owned(state_dir, lock_dir, wanted_fingerprint, command, stdin_data, root)


if __name__ == "__main__":
    raise SystemExit(main())
