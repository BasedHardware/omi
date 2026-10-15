#!/usr/bin/env python3
"""Supervise one owned process tree for a test launcher.

The supervisor is a direct child of the launcher. It starts the command in a
new session and records the leader pid, process-group id, start identity, and
an unguessable token. The token is one argv element of the leader and the
exact environment field OWNED_PROCESS_TOKEN, which children inherit.

A process is signalled only when that proof is rechecked immediately
beforehand: the environment field is exactly OWNED_PROCESS_TOKEN=<token>, or
the recorded leader pid still has that start identity and the token as its own
argv element. A token buried inside a longer argument is not proof. Process
group membership is not proof. It is only a reason to refuse success when a
member remains that cannot be proven, so an env-cleared child is not reported
as cleaned up and is not signalled.

`stop --receipt` uses the same proof. A malformed token or schema fails
closed. A live pid whose start identity does not match is not signalled.

This does not cover SIGKILL of the supervisor itself, a grandchild that both
leaves the process group and clears OWNED_PROCESS_TOKEN, or a host crash.
macOS has no parent-death signal. The supervisor polls its parent pid and, on
Linux, also requests PR_SET_PDEATHSIG.
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
_PS_CAP_SECONDS = 2.0

_STOP = {"requested": False, "signal": signal.SIGTERM}
_DEADLINE = {"at": None}


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


def _ps_timeout() -> float | None:
    if _DEADLINE["at"] is None:
        return _PS_CAP_SECONDS
    remaining = _DEADLINE["at"] - time.monotonic()
    if remaining <= 0:
        return None
    return min(_PS_CAP_SECONDS, remaining)


def _ps(args: list[str], *, missing_ok: bool) -> bytes | None:
    """Run ps. None means the table could not be read; b'' means no rows."""
    timeout = _ps_timeout()
    if timeout is None:
        return None
    try:
        return subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    except subprocess.CalledProcessError:
        return b"" if missing_ok else None
    except OSError:
        return None


def _linux_stat(pid: int) -> list[str] | None:
    try:
        data = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    marker = data.rfind(")")
    if marker < 0:
        return None
    return data[marker + 2 :].split()


def _pid_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 1:
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
    out = _ps(["ps", "-p", str(pid), "-o", "lstart="], missing_ok=True)
    if not out:
        return None
    start = " ".join(out.decode("utf-8", "replace").split())
    return start or None


def _valid_token(token: object) -> bool:
    return isinstance(token, str) and len(token) == 32 and all(char in "0123456789abcdef" for char in token)


def receipt_signal_error(receipt: object) -> str | None:
    """Fail closed before any signal. A short or non-hex token is forged."""
    if not isinstance(receipt, dict):
        return "receipt must be an object"
    if receipt.get("schema_version") != SCHEMA_VERSION:
        return "unsupported receipt schema"
    if not _valid_token(receipt.get("token")):
        return "token must be 32 lowercase hex characters"
    return None


def _exact_env_field(token: str) -> bytes:
    return f"{TOKEN_ENV}={token}".encode()


def _blob_has_exact_env(blob: bytes, token: str) -> bool:
    """True when the token is its own environment field.

    ps records end in a newline, and the token is often the last field. A
    newline or NUL is a field boundary, same as a space. A longer value that
    merely contains the token is not a match.
    """
    field = _exact_env_field(token)
    normalized = blob.replace(b"\0", b" ").replace(b"\r", b" ").replace(b"\n", b" ")
    padded = b" " + normalized + b" "
    return b" " + field + b" " in padded


def _linux_exact_env(pid: int, token: str) -> bool:
    try:
        blob = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return False
    return _exact_env_field(token) in blob.split(b"\0")


def _command_line(pid: int) -> str | None:
    """None when ps cannot be read. Empty when the pid is gone."""
    if sys.platform == "linux":
        try:
            blob = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return ""
        return blob.replace(b"\0", b" ").decode("utf-8", "replace").strip()
    out = _ps(["ps", "-p", str(pid), "-ww", "-o", "command="], missing_ok=True)
    if out is None:
        return None
    return out.decode("utf-8", "replace").strip()


def _has_exact_word(text: str, word: str) -> bool:
    if not word:
        return False
    return f" {word} " in f" {text} "


def _argv_has_exact_token(pid: int, token: str) -> bool:
    command = _command_line(pid)
    if not command:
        return False
    return _has_exact_word(command, token)


def _record_is_comm_only(blob: bytes) -> bool:
    """macOS ps sometimes prints only `(name)` and omits the environment.

    That record is not evidence the token is absent.
    """
    stripped = blob.strip()
    return (
        bool(stripped)
        and b"=" not in stripped
        and len(stripped) < 64
        and stripped.startswith(b"(")
        and stripped.endswith(b")")
    )


def _exact_env(pid: int, token: str) -> bool:
    if sys.platform == "linux":
        return _linux_exact_env(pid, token)
    args = ["ps", "-p", str(pid), "-ww", "-E", "-o", "command="]
    out = _ps(args, missing_ok=True)
    if out is None:
        return False
    if _record_is_comm_only(out):
        again = _ps(args, missing_ok=True)
        if again is None:
            return False
        out = again
    if not out or _record_is_comm_only(out):
        return False
    return _blob_has_exact_env(out, token)


def _pids_with_exact_env(token: str) -> set[int] | None:
    if sys.platform == "linux":
        found: set[int] = set()
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return None
        for entry in entries:
            if entry.name.isdigit() and _linux_exact_env(int(entry.name), token):
                found.add(int(entry.name))
        return found
    out = _ps(["ps", "-axww", "-E", "-o", "pid=", "-o", "command="], missing_ok=False)
    if out is None:
        return None
    found = set()
    for line in out.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, sep, rest = stripped.partition(b" ")
        if sep and pid_text.isdigit() and _blob_has_exact_env(rest, token):
            found.add(int(pid_text))
    return found


def _proven_leader(receipt: dict) -> int | None:
    pid = receipt.get("leader_pid")
    start = receipt.get("leader_start")
    token = receipt.get("token")
    if not isinstance(pid, int) or pid <= 1 or not isinstance(start, str) or not start or not _valid_token(token):
        return None
    if process_start(pid) != start:
        return None
    if _exact_env(pid, token) or _argv_has_exact_token(pid, token):
        return pid
    return None


def _snapshot() -> list[tuple[int, int, int]] | None:
    """(pid, ppid, pgid). None means the table could not be read."""
    rows: list[tuple[int, int, int]] = []
    if sys.platform == "linux":
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return None
        for entry in entries:
            if not entry.name.isdigit():
                continue
            fields = _linux_stat(int(entry.name))
            if not fields or len(fields) < 3:
                continue
            rows.append((int(entry.name), int(fields[1]), int(fields[2])))
        return rows
    out = _ps(["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "pgid="], missing_ok=False)
    if out is None:
        return None
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return rows


def supervisor_matches(receipt: dict, receipt_path: Path) -> bool:
    pid = receipt.get("supervisor_pid")
    start = receipt.get("supervisor_start")
    if not isinstance(pid, int) or pid <= 1 or pid == os.getpid() or not isinstance(start, str) or not start:
        return False
    if process_start(pid) != start:
        return False
    command = _command_line(pid)
    if command is None:
        return False
    return _has_exact_word(command, str(receipt_path))


def owned_pids(receipt: dict) -> set[int] | None:
    """Pids safe to consider. None means ownership could not be read."""
    if receipt_signal_error(receipt):
        return set()
    token = receipt["token"]
    found = _pids_with_exact_env(token)
    if found is None:
        return None
    leader = _proven_leader(receipt)
    if leader is not None:
        found.add(leader)
    found.discard(os.getpid())
    found.discard(1)
    supervisor_pid = receipt.get("supervisor_pid")
    if isinstance(supervisor_pid, int):
        found.discard(supervisor_pid)
    return {pid for pid in found if pid > 1}


def _pid_owned_now(pid: int, receipt: dict) -> bool:
    """Recheck proof immediately before a signal. Never trust an earlier set."""
    if pid <= 1 or pid == os.getpid() or receipt_signal_error(receipt):
        return False
    supervisor_pid = receipt.get("supervisor_pid")
    if isinstance(supervisor_pid, int) and pid == supervisor_pid:
        return False
    token = receipt["token"]
    if _exact_env(pid, token):
        return True
    return _proven_leader(receipt) == pid


def _unproven_group_members(receipt: dict) -> set[int] | None:
    """Live same-group pids we must not signal and must not call cleaned up.

    The recorded leader is excluded: a stale leader is a refusal, not a child.
    None means the process table could not be read.
    """
    pgid = receipt.get("leader_pgid")
    if not isinstance(pgid, int) or pgid <= 1:
        return set()
    rows = _snapshot()
    if rows is None:
        return None
    token = receipt["token"]
    leader_pid = receipt.get("leader_pid")
    leftover: set[int] = set()
    for pid, _ppid, row_pgid in rows:
        if row_pgid != pgid or pid <= 1 or pid == os.getpid():
            continue
        if isinstance(leader_pid, int) and pid == leader_pid:
            continue
        if not _pid_alive(pid):
            continue
        if _exact_env(pid, token) or _proven_leader(receipt) == pid:
            continue
        leftover.add(pid)
    return leftover


def _signal_pids(pids: set[int], sig: int, receipt: dict) -> None:
    for pid in sorted(pids):
        if not _pid_owned_now(pid, receipt):
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
    if not isinstance(payload, dict):
        raise SystemExit(f"owned-process: receipt is not an object: {path}")
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


def _alive_owned(pids: set[int], receipt: dict) -> set[int]:
    return {pid for pid in pids if _pid_owned_now(pid, receipt) and _pid_alive(pid)}


def _force_reserve(shutdown_deadline: float) -> float:
    """Seconds kept inside the caller's deadline for SIGKILL and a proof check.

    The TERM wait must stop before this reserve, or a ps lookup at kill time
    sees no time left and cannot authorize the signal.
    """
    if shutdown_deadline <= 0.2:
        return shutdown_deadline / 2
    return min(1.0, shutdown_deadline / 2)


def reap(receipt: dict, first_signal: int, shutdown_deadline: float) -> bool:
    """Signal proven processes, then fail if an unproven group member remains."""
    if receipt_signal_error(receipt):
        return False
    deadline_at = time.monotonic() + shutdown_deadline
    term_end = deadline_at - _force_reserve(shutdown_deadline)
    _DEADLINE["at"] = deadline_at
    try:
        targets = owned_pids(receipt)
        if targets is None:
            return False
        _signal_pids(targets, first_signal, receipt)
        while time.monotonic() < term_end:
            targets = _alive_owned(targets, receipt)
            if not targets:
                break
            time.sleep(0.05)
        else:
            _signal_pids(targets, signal.SIGKILL, receipt)
            while time.monotonic() < deadline_at and any(_pid_alive(pid) for pid in targets):
                time.sleep(0.05)
            if any(_pid_alive(pid) for pid in targets):
                return False
        confirmed = owned_pids(receipt)
        if confirmed is None:
            return False
        if confirmed:
            _signal_pids(confirmed, signal.SIGKILL, receipt)
            if _alive_owned(confirmed, receipt):
                return False
        leftover = _unproven_group_members(receipt)
        return leftover is not None and not leftover
    finally:
        _DEADLINE["at"] = None


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
    if original_ppid <= 1:
        # The launcher exited before this process sampled it. Do not start work.
        payload = {
            "schema_version": SCHEMA_VERSION,
            "label": args.label,
            "token": token,
            "state": "stopped",
            "outcome": "parent_died",
            "cleared": True,
            "supervisor_pid": os.getpid(),
            "supervisor_start": process_start(os.getpid()),
            "leader_pid": None,
            "leader_pgid": None,
            "leader_start": None,
            "command": command,
            "limits": _limits(args.shutdown_deadline, args.run_deadline),
        }
        _write_receipt(args.receipt, payload)
        return EXIT_PARENT_DIED
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
        payload["cleared"] = False
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
        payload["cleared"] = True
        _write_receipt(receipt_path, payload)
        return EXIT_STARTUP

    payload["leader_pid"] = leader.pid
    payload["leader_pgid"] = os.getpgid(leader.pid)
    payload["leader_start"] = process_start(leader.pid)
    payload["state"] = "running"
    _write_receipt(receipt_path, payload)
    if os.getppid() != original_ppid:
        cleared = reap(payload, signal.SIGTERM, args.shutdown_deadline)
        payload["state"] = "stopped"
        payload["outcome"] = "parent_died"
        payload["cleared"] = cleared
        payload["exit_code"] = EXIT_PARENT_DIED if cleared else 1
        _write_receipt(receipt_path, payload)
        return EXIT_PARENT_DIED if cleared else 1

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
    payload["outcome"] = outcome if cleared or outcome != "exited" else "exited_children_unproven"
    payload["exit_code"] = code
    payload["cleared"] = cleared
    _write_receipt(receipt_path, payload)
    return code


def _stop_supervisor(receipt: dict, receipt_path: Path, deadline: float) -> None:
    if not supervisor_matches(receipt, receipt_path):
        return
    try:
        os.kill(int(receipt["supervisor_pid"]), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, TypeError, ValueError):
        return
    end = time.monotonic() + deadline
    while time.monotonic() < end and supervisor_matches(receipt, receipt_path):
        time.sleep(0.05)
    if supervisor_matches(receipt, receipt_path):
        try:
            os.kill(int(receipt["supervisor_pid"]), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, TypeError, ValueError):
            pass


def stop(args: argparse.Namespace) -> int:
    path = args.receipt
    if not path.is_file():
        print(f"owned-process: receipt not found: {path}", file=sys.stderr)
        return 2
    try:
        receipt = _load_receipt(path)
    except (OSError, json.JSONDecodeError, SystemExit, UnicodeError, RecursionError):
        print("owned-process: receipt is not usable", file=sys.stderr)
        return 2
    error = receipt_signal_error(receipt)
    if error:
        print(f"owned-process: {error}", file=sys.stderr)
        return 2
    deadline = args.shutdown_deadline
    if deadline is None:
        recorded = receipt.get("limits", {}).get("shutdown_deadline_seconds", 10) if isinstance(receipt.get("limits"), dict) else 10
        try:
            deadline = float(recorded)
        except (TypeError, ValueError):
            deadline = 10
    if deadline <= 0:
        print("owned-process: deadlines must be positive", file=sys.stderr)
        return 2
    leader_pid = receipt.get("leader_pid")
    mismatched = (
        isinstance(leader_pid, int)
        and leader_pid > 1
        and _pid_alive(leader_pid)
        and _proven_leader(receipt) != leader_pid
    )
    cleared = reap(receipt, signal.SIGTERM, deadline)
    _stop_supervisor(receipt, path, deadline)
    if mismatched and not (owned_pids(receipt) or set()):
        return EXIT_REFUSED
    if not cleared:
        receipt["state"] = "stopped"
        receipt["outcome"] = "stop_incomplete"
        receipt["cleared"] = False
        _write_receipt(path, receipt)
        return 1
    if receipt.get("state") != "stopped":
        receipt["state"] = "stopped"
        receipt["outcome"] = receipt.get("outcome") or "stopped"
        receipt["cleared"] = True
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
