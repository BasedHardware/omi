#!/usr/bin/env python3
"""Run a command single-flight with observable per-worktree state and logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

POLL_SECONDS = 0.2
STATUS_INTERVAL_SECONDS = 5.0

# Signals forwarded to the owned child. SIGHUP is POSIX-only and is simply absent
# on Windows, so the set is resolved against the host rather than assumed —
# referencing signal.SIGHUP unconditionally raised AttributeError before any
# pre-push check could run.
FORWARDED_SIGNAL_NAMES = ("SIGINT", "SIGTERM", "SIGHUP")


def forwardable_signals() -> tuple[int, ...]:
    """Return the forwardable signals this platform actually defines."""
    resolved = (getattr(signal, name, None) for name in FORWARDED_SIGNAL_NAMES)
    return tuple(signum for signum in resolved if signum is not None)


def signal_child(child: subprocess.Popen, signum: int) -> None:
    """Forward a signal to the child, preferring its process group where supported.

    The child is started with ``start_new_session=True``, so on POSIX it leads its
    own process group and ``os.killpg`` reaches the whole tree. Windows has no
    ``os.killpg``; fall back to signalling the process directly.
    """
    killpg = getattr(os, "killpg", None)
    try:
        if killpg is not None:
            killpg(child.pid, signum)
        else:
            child.send_signal(signum)
    except (ProcessLookupError, OSError):
        pass


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
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
    git_dir = subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=root, text=True).strip()
    return Path(git_dir) / "omi-preflight" / name


def fingerprint(root: Path, command: list[str], stdin_data: str) -> str:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    ).stdout.strip()
    digest = hashlib.sha256()
    for value in (str(root.resolve()), head, "\0".join(command), stdin_data):
        digest.update(value.encode("utf-8"))
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
    if process_exists(expected_pid):
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
    active_fingerprint = str(owner.get("fingerprint") or "")
    if not process_exists(active_pid):
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
        if not process_exists(active_pid):
            remove_stale_lock(lock_dir, active_pid)
            break
        now = time.monotonic()
        if now >= next_status:
            status = read_json(status_path)
            elapsed = max(0.0, time.time() - float(status.get("started_at_epoch") or time.time()))
            print(
                f"  active phase={status.get('phase', 'starting')} elapsed={elapsed:.1f}s",
                flush=True,
            )
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
    child: subprocess.Popen[str] | None = None

    def write_status() -> None:
        atomic_json(
            status_path,
            {
                "pid": os.getpid(),
                "fingerprint": wanted_fingerprint,
                "phase": phase,
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "log": str(log_path),
                "started_at_epoch": started_wall,
            },
        )

    def forward_signal(signum: int, _frame: object) -> None:
        if child is not None and child.poll() is None:
            signal_child(child, signum)

    previous_handlers = {signum: signal.signal(signum, forward_signal) for signum in forwardable_signals()}
    exit_code = 1
    try:
        print(f"Pre-push single-flight log: {log_path}")
        log_path.write_text("", encoding="utf-8")
        os.chmod(log_path, 0o600)
        write_status()
        child = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        if child.stdin:
            child.stdin.write(stdin_data)
            child.stdin.close()
        assert child.stdout is not None
        with log_path.open("a", encoding="utf-8") as log:
            for line in child.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write(line)
                log.flush()
                if line.startswith("==> "):
                    phase = line[4:].strip()
                    write_status()
        exit_code = child.wait()
        phase = "passed" if exit_code == 0 else "failed"
        write_status()
        atomic_json(
            result_path,
            {
                "exit_code": exit_code,
                "fingerprint": wanted_fingerprint,
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "finished_at_epoch": time.time(),
                "log": str(log_path),
            },
        )
        return exit_code
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        shutil.rmtree(lock_dir, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="pre-push")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("FAIL: preflight runner requires a command after --", file=sys.stderr)
        return 2
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    # Git supplies ref updates on a pipe. Manual preflight runs inherit a TTY;
    # treating that as empty input avoids waiting forever for an interactive EOF.
    stdin_data = "" if sys.stdin.isatty() else sys.stdin.read()
    wanted_fingerprint = fingerprint(root, command, stdin_data)
    state_dir = default_state_dir(root, args.name)
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_dir, 0o700)
    lock_dir = state_dir / "lock"
    owner = {"pid": os.getpid(), "fingerprint": wanted_fingerprint, "started_at_epoch": time.time()}

    while not acquire(lock_dir, owner):
        joined = join_existing(state_dir, wanted_fingerprint)
        if joined is not None:
            return joined
    return run_owned(state_dir, lock_dir, wanted_fingerprint, command, stdin_data, root)


if __name__ == "__main__":
    raise SystemExit(main())
