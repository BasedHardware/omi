#!/usr/bin/env python3
"""Supervise one owned process tree for a test launcher.

The supervisor is a direct child of the launcher. It starts the command in a
new session and records the leader pid, process-group id, start identity, and
an unguessable token placed in the leader argv and in OWNED_PROCESS_TOKEN.
Children inherit that environment.

On success, failure, SIGINT, SIGTERM, SIGHUP, an optional run deadline, or
death of the launcher, the supervisor signals only processes that still match
that identity: the token, or membership in the leader's process group while
the leader's start identity still matches. A shutdown deadline bounds the
SIGTERM wait; leftovers are then SIGKILL'd. `stop --receipt` uses the same
check and will not signal a pid whose start identity or token does not match.

This does not cover SIGKILL of the supervisor itself, a grandchild that both
leaves the process group and clears OWNED_PROCESS_TOKEN, or a host crash.
macOS has no parent-death signal. The supervisor polls its parent pid and, on
Linux, also requests PR_SET_PDEATHSIG. A reused pid is not signalled when the
recorded start identity or token does not match; a check-then-signal race
remains and is narrowed by that pair of checks.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time


SCHEMA_VERSION = 1
TOKEN_ENV = "OWNED_PROCESS_TOKEN"
EXIT_TIMEOUT = 124
EXIT_STARTUP = 125
EXIT_PARENT_DIED = 129
EXIT_REFUSED = 2

_STOP = {"requested": False, "signal": signal.SIGTERM}


def _install_handlers() -> None:
    def handle(signum, _frame):
        _STOP["requested"] = True
        _STOP["signal"] = signum

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, handle)


def _arm_parent_death_signal() -> None:
    """Ask Linux to deliver SIGTERM if the launcher dies, including during wait."""
    if sys.platform != "linux":
        return
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
    except OSError:
        return
    # PR_SET_PDEATHSIG = 1. Failure leaves the ppid poll as the only signal.
    if libc.prctl(1, signal.SIGTERM) != 0:
        return


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _linux_stat(pid: int) -> list[str] | None:
    try:
        data = _read_text(Path(f"/proc/{pid}/stat"))
    except OSError:
        return None
    marker = data.rfind(")")
    if marker < 0:
        return None
    return data[marker + 2 :].split()


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_start(pid: int) -> str | None:
    """Stable start identity. Equality is the check; resolution is one second on macOS."""
    if sys.platform == "linux":
        fields = _linux_stat(pid)
        if not fields or len(fields) < 20:
            return None
        return "ticks:" + fields[19]
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "lstart="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    start = " ".join(out.split())
    return start or None


def _command_line(pid: int) -> str:
    if sys.platform == "linux":
        try:
            blob = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return ""
        return blob.replace(b"\0", b" ").decode("utf-8", "replace")
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-ww", "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return ""
    return out.strip()


def _process_has_token(pid: int, token: str) -> bool:
    if token.encode() in _process_blob(pid):
        return True
    return False


def _process_blob(pid: int) -> bytes:
    if sys.platform == "linux":
        chunks = []
        for name in ("cmdline", "environ"):
            try:
                chunks.append(Path(f"/proc/{pid}/{name}").read_bytes())
            except OSError:
                continue
        return b"\0".join(chunks)
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-ww", "-E", "-o", "command="],
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return b""
    return out


def _snapshot() -> list[tuple[int, int, int]]:
    """Return (pid, ppid, pgid) for current processes. No environments."""
    rows: list[tuple[int, int, int]] = []
    if sys.platform == "linux":
        proc = Path("/proc")
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            fields = _linux_stat(int(entry.name))
            if not fields or len(fields) < 3:
                continue
            ppid, pgrp = int(fields[1]), int(fields[2])
            rows.append((int(entry.name), ppid, pgrp))
        return rows
    try:
        out = subprocess.check_output(
            ["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "pgid="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return rows
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return rows


def leader_matches(receipt: dict) -> bool:
    pid = receipt.get("leader_pid")
    start = receipt.get("leader_start")
    token = receipt.get("token")
    if not isinstance(pid, int) or pid <= 1 or not isinstance(start, str) or not isinstance(token, str):
        return False
    if process_start(pid) != start:
        return False
    return _process_has_token(pid, token)


def _pgid(pid: int, rows: list[tuple[int, int, int]] | None = None) -> int | None:
    table = rows if rows is not None else _snapshot()
    for row_pid, _ppid, row_pgid in table:
        if row_pid == pid:
            return row_pgid
    return None


def supervisor_matches(receipt: dict, receipt_path: Path) -> bool:
    pid = receipt.get("supervisor_pid")
    start = receipt.get("supervisor_start")
    if not isinstance(pid, int) or pid <= 1 or not isinstance(start, str):
        return False
    if pid == os.getpid() or process_start(pid) != start:
        return False
    return str(receipt_path) in _command_line(pid)


def owned_pids(receipt: dict) -> set[int]:
    """Pids safe to signal. Never includes this process, the supervisor, or pid 1."""
    token = receipt.get("token")
    if not isinstance(token, str) or not token:
        return set()
    rows = _snapshot()
    matched = leader_matches(receipt)
    leader_pid = receipt.get("leader_pid")
    leader_pgid = receipt.get("leader_pgid")
    by_pid = {pid: (ppid, pgid) for pid, ppid, pgid in rows}
    selected: set[int] = set()
    if matched and isinstance(leader_pgid, int):
        selected.update(pid for pid, (_ppid, pgid) in by_pid.items() if pgid == leader_pgid)
        changed = True
        while changed:
            changed = False
            for pid, (ppid, _pgid) in by_pid.items():
                if pid not in selected and ppid in selected:
                    selected.add(pid)
                    changed = True
    token_hits = _pids_with_token(token)
    if matched:
        confirmed = set(token_hits)
        confirmed.update(
            pid
            for pid in selected
            if pid in token_hits or by_pid.get(pid, (None, None))[1] == leader_pgid
        )
    else:
        # The leader pid may have been reused. Do not signal it without a token.
        confirmed = set(token_hits)
        if isinstance(leader_pid, int) and leader_pid not in token_hits:
            confirmed.discard(leader_pid)
    confirmed.discard(os.getpid())
    confirmed.discard(1)
    supervisor_pid = receipt.get("supervisor_pid")
    if isinstance(supervisor_pid, int):
        confirmed.discard(supervisor_pid)
    return {pid for pid in confirmed if pid > 1}


def _pids_with_token(token: str) -> set[int]:
    found: set[int] = set()
    encoded = token.encode()
    if sys.platform == "linux":
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if encoded in _process_blob(pid):
                found.add(pid)
        return found
    try:
        out = subprocess.check_output(
            ["ps", "-axww", "-E", "-o", "pid=", "-o", "command="],
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return found
    for line in out.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, sep, rest = stripped.partition(b" ")
        if sep and pid_text.isdigit() and encoded in rest:
            found.add(int(pid_text))
    return found


def _signal_pids(pids: set[int], sig: int) -> None:
    for pid in sorted(pids):
        if pid <= 1 or pid == os.getpid():
            continue
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            continue


def _write_receipt(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, blob.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _load_receipt(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(f"owned-process: unsupported receipt schema in {path}")
    return payload


def _limits(shutdown: float, run_deadline: float | None) -> dict:
    return {
        "shutdown_deadline_seconds": shutdown,
        "run_deadline_seconds": run_deadline,
        "parent_death": "ppid poll; PR_SET_PDEATHSIG on Linux when the libc call succeeds",
        "not_covered": [
            "SIGKILL of the supervisor",
            "a grandchild that leaves the process group and clears OWNED_PROCESS_TOKEN",
            "host crash",
        ],
    }


def _still_owned(pid: int, receipt: dict) -> bool:
    token = receipt.get("token")
    if not isinstance(token, str) or pid <= 1 or pid == os.getpid():
        return False
    if _process_has_token(pid, token):
        return True
    leader_pgid = receipt.get("leader_pgid")
    return leader_matches(receipt) and isinstance(leader_pgid, int) and _pgid(pid) == leader_pgid


def _alive_owned(pids: set[int], receipt: dict) -> set[int]:
    alive: set[int] = set()
    for pid in pids:
        if pid <= 1 or pid == os.getpid():
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            alive.add(pid)
            continue
        if _still_owned(pid, receipt):
            alive.add(pid)
    return alive


def reap(receipt: dict, first_signal: int, shutdown_deadline: float) -> bool:
    """Signal the owned set, then SIGKILL anything still matching after the deadline."""
    targets = owned_pids(receipt)
    _signal_pids(targets, first_signal)
    end = time.monotonic() + shutdown_deadline
    next_scan = time.monotonic() + 0.2
    while time.monotonic() < end:
        if time.monotonic() >= next_scan:
            targets = owned_pids(receipt)
            next_scan = time.monotonic() + 0.2
        else:
            targets = _alive_owned(targets, receipt)
        if not targets:
            return True
        time.sleep(0.05)
    targets = owned_pids(receipt)
    _signal_pids(targets, signal.SIGKILL)
    kill_end = time.monotonic() + min(2.0, shutdown_deadline)
    while time.monotonic() < kill_end:
        targets = _alive_owned(targets, receipt)
        if not targets:
            return True
        time.sleep(0.05)
    return not _alive_owned(owned_pids(receipt), receipt)


def _leader_argv(token: str, command: list[str]) -> list[str]:
    code = (
        "import os, subprocess, sys\n"
        "token = sys.argv[1]\n"
        "cmd = sys.argv[2:]\n"
        f"os.environ[{TOKEN_ENV!r}] = token\n"
        "try:\n"
        "    proc = subprocess.Popen(cmd)\n"
        "except OSError:\n"
        "    raise SystemExit(125)\n"
        "raise SystemExit(proc.wait())\n"
    )
    return [sys.executable, "-c", code, token, *command]


def _exit_from_wait(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 1


def supervise(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        print("owned-process: supervise requires a command", file=sys.stderr)
        return 2
    if args.shutdown_deadline <= 0 or (args.run_deadline is not None and args.run_deadline <= 0):
        print("owned-process: deadlines must be positive", file=sys.stderr)
        return 2
    if args.parent_poll <= 0:
        print("owned-process: parent poll must be positive", file=sys.stderr)
        return 2

    _install_handlers()
    _arm_parent_death_signal()
    token = secrets.token_hex(16)
    original_ppid = os.getppid()
    supervisor_pid = os.getpid()
    supervisor_start = process_start(supervisor_pid)
    receipt_path = args.receipt
    payload: dict = {
        "schema_version": SCHEMA_VERSION,
        "label": args.label,
        "token": token,
        "state": "starting",
        "supervisor_pid": supervisor_pid,
        "supervisor_start": supervisor_start,
        "leader_pid": None,
        "leader_pgid": None,
        "leader_start": None,
        "command": command,
        "limits": _limits(args.shutdown_deadline, args.run_deadline),
    }
    _write_receipt(receipt_path, payload)
    if os.getppid() != original_ppid:
        payload["state"] = "stopped"
        payload["outcome"] = "parent_died"
        _write_receipt(receipt_path, payload)
        return EXIT_PARENT_DIED

    try:
        leader = subprocess.Popen(
            _leader_argv(token, command),
            start_new_session=True,
            cwd=str(args.cwd) if args.cwd else None,
        )
    except OSError as exc:
        payload["state"] = "stopped"
        payload["outcome"] = "startup_failed"
        payload["detail"] = str(exc)
        _write_receipt(receipt_path, payload)
        return EXIT_STARTUP

    payload["leader_pid"] = leader.pid
    payload["leader_pgid"] = os.getpgid(leader.pid)
    payload["leader_start"] = process_start(leader.pid)
    payload["state"] = "running"
    _write_receipt(receipt_path, payload)

    started = time.monotonic()
    run_deadline = args.run_deadline
    outcome = "exited"
    wait_status = 0
    while True:
        if _STOP["requested"]:
            outcome = "signal"
            break
        if os.getppid() != original_ppid:
            outcome = "parent_died"
            break
        if run_deadline is not None and time.monotonic() - started >= run_deadline:
            outcome = "timeout"
            break
        pid, raw = os.waitpid(leader.pid, os.WNOHANG)
        if pid == leader.pid:
            wait_status = raw
            outcome = "exited"
            break
        time.sleep(min(args.parent_poll, 0.05 if run_deadline else args.parent_poll))

    if outcome == "signal":
        first = int(_STOP["signal"])
    elif outcome == "timeout":
        first = signal.SIGTERM
    elif outcome == "parent_died":
        first = signal.SIGTERM
    else:
        first = signal.SIGTERM
    cleared = reap(payload, first, args.shutdown_deadline)
    if outcome == "exited":
        code = _exit_from_wait(wait_status)
    elif outcome == "timeout":
        code = EXIT_TIMEOUT
    elif outcome == "parent_died":
        code = EXIT_PARENT_DIED
    else:
        code = 128 + int(_STOP["signal"])
    if not cleared:
        code = 1 if code == 0 else code
    payload["state"] = "stopped"
    payload["outcome"] = outcome
    payload["exit_code"] = code
    payload["cleared"] = cleared
    _write_receipt(receipt_path, payload)
    return code


def stop(args: argparse.Namespace) -> int:
    path = args.receipt
    if not path.is_file():
        print(f"owned-process: receipt not found: {path}", file=sys.stderr)
        return 2
    receipt = _load_receipt(path)
    deadline = args.shutdown_deadline
    if deadline is None:
        recorded = receipt.get("limits", {}).get("shutdown_deadline_seconds", 10)
        deadline = float(recorded)
    if deadline <= 0:
        print("owned-process: deadlines must be positive", file=sys.stderr)
        return 2
    leader_pid = receipt.get("leader_pid")
    # A live pid whose start identity cannot be read is still not this receipt.
    # ps can fail under load; that must not become a successful stop.
    mismatched = (
        isinstance(leader_pid, int)
        and leader_pid > 1
        and _pid_alive(leader_pid)
        and not leader_matches(receipt)
    )
    cleared = reap(receipt, signal.SIGTERM, deadline)
    if supervisor_matches(receipt, path):
        try:
            os.kill(int(receipt["supervisor_pid"]), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, TypeError, ValueError):
            pass
        end = time.monotonic() + deadline
        while time.monotonic() < end and supervisor_matches(receipt, path):
            time.sleep(0.05)
        if supervisor_matches(receipt, path):
            try:
                os.kill(int(receipt["supervisor_pid"]), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, TypeError, ValueError):
                pass
    if not cleared:
        receipt["state"] = "stopped"
        receipt["outcome"] = "stop_incomplete"
        _write_receipt(path, receipt)
        return 1
    if mismatched and not owned_pids(receipt):
        return EXIT_REFUSED
    if receipt.get("state") != "stopped":
        receipt["state"] = "stopped"
        receipt["outcome"] = receipt.get("outcome") or "stopped"
        _write_receipt(path, receipt)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command_name", required=True)
    supervise_parser = sub.add_parser("supervise", help="run a command and reap its owned tree")
    supervise_parser.add_argument("--receipt", required=True, type=Path)
    supervise_parser.add_argument("--label", required=True)
    supervise_parser.add_argument("--shutdown-deadline", type=float, default=10)
    supervise_parser.add_argument("--run-deadline", type=float, default=None)
    supervise_parser.add_argument("--parent-poll", type=float, default=0.2)
    supervise_parser.add_argument("--cwd", type=Path, default=None)
    supervise_parser.add_argument("command", nargs=argparse.REMAINDER)
    supervise_parser.set_defaults(func=supervise)
    stop_parser = sub.add_parser("stop", help="reap the tree recorded in a receipt")
    stop_parser.add_argument("--receipt", required=True, type=Path)
    stop_parser.add_argument("--shutdown-deadline", type=float, default=None)
    stop_parser.set_defaults(func=stop)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
