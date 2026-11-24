"""Bounded retry supervisor for ``firebase emulators:exec`` in the listen gauntlet.

Why this exists
---------------
Firebase needs a concrete loopback port for the Firestore emulator, and it can
only bind that port after the probe socket which chose it has been closed.
Between the close and Firebase's bind, anything else on the host can take the
port. A Firestore gRPC client that lands on an HTTP/1.1 responder fails with
``Trying to connect an http1.x server (HTTP status 400)``, which the client's
default retry wrapper stretches into a 60-second
``google.api_core.exceptions.RetryError``; a port that is bound but not yet
serving produces ``httpx.ReadTimeout`` against the stack. Both were reported as
the same transient gauntlet failure.

What it guarantees
------------------
* Every attempt chooses a **fresh** port and prints it.
* Before the gauntlet's inner command runs, the emulator must answer a real
  Firestore RPC (``emulator_readiness``), not merely accept a TCP connection.
* Only emulator/connection/protocol startup failures are retried. A non-zero
  exit that carries an assertion, ``StackFailure``, or pytest failure is final
  and is never retried - a real regression must stay red.
* Attempts stop at the cap (3) and at the wall-clock budget. Both are hard.
* Each attempt runs with its own ``<state-dir>/attempt-<n>`` scenario state.
  ``run.sh`` embeds ``ATTEMPT_STATE_TOKEN`` instead of the caller's path, so a
  state root containing a space is still rewritten (the inner command is one
  shell string, where that path is already escaped).

The retry contract is the per-attempt marker file written by the generated
inner script:
``readiness_failed`` (emulator never served), ``started`` (the session died
while the gauntlet was running), ``inner:<code>`` (the gauntlet's own exit).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
GAUNTLET_PYTHON = REPO_ROOT / 'backend' / '.venv' / 'bin' / 'python'
DEFAULT_PROJECT = 'demo-omi-listen-stack'
DEFAULT_MAX_ATTEMPTS = 3
MAX_ATTEMPTS_CEILING = 3
# The CI job that runs this gauntlet has timeout-minutes: 25 (1500s) for
# checkout, dependency sync and the run itself. 900s of retry budget leaves
# 10 minutes of headroom for the parts this process does not time, so a slow
# attempt fails cleanly here instead of being cancelled by the job ceiling.
DEFAULT_MAX_TOTAL_SECONDS = 900.0
MAX_TOTAL_SECONDS_CEILING = 1800.0
DEFAULT_READINESS_TIMEOUT_SECONDS = 120.0
FIREBASE_COMMAND = ('npx', '--no-install', 'firebase')
# `run.sh` embeds this token where the caller's state root belongs; each
# attempt substitutes its own `<state>/attempt-<n>` so a retry can never inherit
# a half-run ledger, cursor or evidence set.
ATTEMPT_STATE_TOKEN = '@ATTEMPT_STATE_DIR@'

MARKER_READINESS_FAILED = 'readiness_failed'
MARKER_STARTED = 'started'
MARKER_INNER_PREFIX = 'inner:'
READINESS_EXIT_CODE = 75

_LOG_SCAN_LINES = 400
_REPORT_TAIL_LINES = 60
_REPORT_PORT_LINES = 30


class Outcome(str, Enum):
    SUCCESS = 'success'
    TRANSIENT = 'transient'
    REAL = 'real'


# A retry may only cover emulator/connection/protocol startup failures. These
# are the signatures a stolen or not-yet-serving emulator port produces.
TRANSIENT_SIGNATURES = (
    'Trying to connect an http1.x server',
    'failed to connect to all addresses',
    'Failed parsing HTTP/2',
    'google.api_core.exceptions.RetryError',
    'google.api_core.exceptions.ServiceUnavailable',
    'google.api_core.exceptions.DeadlineExceeded',
    'google.api_core.exceptions.TooManyRequests',
    'httpcore.ReadTimeout',
    'httpcore.ConnectError',
    'httpcore.RemoteProtocolError',
    'httpx.ReadTimeout',
    'httpx.ConnectError',
    'httpx.RemoteProtocolError',
    'ConnectionRefusedError',
    'ConnectionResetError',
    'is already in use',
    'Could not start Firestore Emulator',
)

# Any of these means the gauntlet reached its own assertions. Real failures win
# over a transient signature in the same output, so a stack-contract failure is
# never laundered into a pass by an earlier connection error.
REAL_SIGNATURES = (
    'StackFailure',
    'AssertionError',
    'short test summary info',
    'FAILED backend/',
    'ERROR backend/',
)


@dataclass
class Attempt:
    index: int
    port: int
    returncode: int
    marker: str
    outcome: Outcome
    reason: str
    log_path: Path
    tail: list[str] = field(default_factory=list)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', 0))
        return int(probe.getsockname()[1])


def classify_attempt(*, returncode: int, marker: str, output: str) -> tuple[Outcome, str]:
    """Decide whether one attempt may be retried.

    The marker is authoritative; free-text signatures are only consulted for a
    gauntlet that started and exited non-zero, to separate "the emulator went
    away underneath us" from "a scenario failed".
    """
    if marker == MARKER_READINESS_FAILED:
        return Outcome.TRANSIENT, 'emulator never served Firestore gRPC'
    if marker == MARKER_STARTED:
        # No exit status was recorded: the emulator session ended (or killed the
        # inner command) before the gauntlet could finish. That is a session
        # failure, not an assertion result.
        return Outcome.TRANSIENT, 'emulator session ended mid-run'
    if marker.startswith(MARKER_INNER_PREFIX):
        recorded = marker[len(MARKER_INNER_PREFIX) :].strip()
        if not recorded.isdigit():
            return Outcome.REAL, f'unreadable inner exit marker {marker!r}'
        code = int(recorded)
        if code == 0:
            if returncode == 0:
                return Outcome.SUCCESS, 'gauntlet passed'
            # The gauntlet passed but the emulator session did not, which is not
            # a startup failure we can safely re-run. Fail closed.
            return Outcome.REAL, f'inner command passed but firebase exited {returncode}'
        if _has_real_signature(output):
            return Outcome.REAL, f'gauntlet failed with its own assertions (exit {code})'
        if _has_transient_signature(output):
            return Outcome.TRANSIENT, f'gauntlet hit a transient transport failure (exit {code})'
        return Outcome.REAL, f'gauntlet exited {code} without a recognised transient signature'
    # No marker at all: Firebase never ran the inner command (emulator failed to
    # start, or the port was already taken).
    if returncode != 0:
        return Outcome.TRANSIENT, 'emulator failed before the gauntlet started'
    return Outcome.REAL, 'firebase exited 0 without ever running the gauntlet'


def _has_real_signature(output: str) -> bool:
    return any(signature in output for signature in REAL_SIGNATURES)


def _has_transient_signature(output: str) -> bool:
    return any(signature in output for signature in TRANSIENT_SIGNATURES)


def _inner_script(*, inner_command: str, marker: Path, readiness_command: Sequence[str]) -> str:
    probe = ' '.join(shlex.quote(part) for part in readiness_command)
    quoted_marker = shlex.quote(str(marker))
    return '\n'.join(
        (
            '#!/usr/bin/env bash',
            '# Generated per attempt by emulator_supervisor.py; the marker file is',
            '# the retry contract described in that module.',
            f'PYTHONPATH=backend {probe}',
            'if [ "$?" -ne 0 ]; then',
            f"  printf 'readiness_failed\\n' > {quoted_marker}",
            f'  exit {READINESS_EXIT_CODE}',
            'fi',
            f"printf 'started\\n' > {quoted_marker}",
            inner_command,
            'status=$?',
            f"printf 'inner:%s\\n' \"$status\" > {quoted_marker}",
            'exit "$status"',
            '',
        )
    )


def _quote(value: str) -> str:
    return shlex.quote(value)


def _read_marker(marker: Path) -> str:
    try:
        return marker.read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def _terminate(process: subprocess.Popen) -> None:
    """Stop an attempt, preferring its whole process group.

    The attempt runs Firebase in its own session, so the emulator JVM and the
    inner gauntlet are in the same group. A plain ``process.kill()`` would leave
    the JVM behind and keep the log pipe open.
    """
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except OSError:
        return
    time.sleep(5.0)
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except OSError:
        pass


def _run_attempt(
    *,
    index: int,
    inner_command: str,
    repo_root: Path,
    project: str,
    log_dir: Path,
    readiness_command: Sequence[str],
    firebase_command: Sequence[str],
    state_dir: str = '',
    budget_seconds: float | None = None,
) -> Attempt:
    port = _free_port()
    print(f'[emulator] attempt {index}: Firestore on 127.0.0.1:{port}', flush=True)
    work_dir = Path(tempfile.mkdtemp(prefix=f'omi-listen-pusher-emulator-{index}-'))
    marker = work_dir / 'attempt-marker'
    log_path = log_dir / f'emulator-attempt-{index}.log'
    # A retry must not inherit the previous attempt's scenario state: a half-run
    # leaves ledgers, cursors and evidence files that make the next attempt
    # non-deterministic and can turn a transient startup failure into a false
    # assertion failure.
    if state_dir:
        attempt_state = Path(state_dir) / f'attempt-{index}'
        attempt_state.mkdir(parents=True, exist_ok=True)
        # The token, not the caller's path, is what run.sh embeds: the inner
        # command is a shell string, so a path with a space is already escaped
        # there and a literal substitution would silently miss it. The
        # replacement is shell-quoted for the same reason.
        inner_command = inner_command.replace(ATTEMPT_STATE_TOKEN, shlex.quote(str(attempt_state)))
    # Printed so the shell-routing contract (which state dir each phase gets) is
    # observable after the generated script is removed.
    print(f'[emulator] attempt {index} inner: {inner_command}', flush=True)
    try:
        config = work_dir / 'firebase.json'
        config.write_text(
            json.dumps({'emulators': {'firestore': {'host': '127.0.0.1', 'port': port}}}),
            encoding='utf-8',
        )
        script = work_dir / 'inner.sh'
        script.write_text(
            _inner_script(inner_command=inner_command, marker=marker, readiness_command=readiness_command),
            encoding='utf-8',
        )
        command = [
            *firebase_command,
            'emulators:exec',
            '--only',
            'firestore',
            '--project',
            project,
            '--config',
            str(config),
            f'bash {_quote(str(script))}',
        ]
        tail: deque[str] = deque(maxlen=_LOG_SCAN_LINES)
        budget_hit = threading.Event()
        with log_path.open('w', encoding='utf-8') as log_file:
            process = subprocess.Popen(
                command,
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            timer: threading.Timer | None = None
            if budget_seconds is not None:

                def _on_timeout() -> None:
                    budget_hit.set()
                    _terminate(process)

                timer = threading.Timer(max(0.0, budget_seconds), _on_timeout)
                timer.daemon = True
                timer.start()
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    log_file.write(line)
                    log_file.flush()
                    tail.append(line.rstrip('\n'))
                    sys.stdout.write(line)
                    sys.stdout.flush()
                returncode = process.wait()
            finally:
                if timer is not None:
                    timer.cancel()
        if budget_hit.is_set():
            return Attempt(
                index=index,
                port=port,
                returncode=returncode,
                marker=_read_marker(marker),
                outcome=Outcome.TRANSIENT,
                reason='wall-clock budget exhausted mid-attempt',
                log_path=log_path,
                tail=list(tail)[-_REPORT_TAIL_LINES:],
            )
        marker_value = _read_marker(marker)
        outcome, reason = classify_attempt(returncode=returncode, marker=marker_value, output='\n'.join(tail))
        return Attempt(
            index=index,
            port=port,
            returncode=returncode,
            marker=marker_value,
            outcome=outcome,
            reason=reason,
            log_path=log_path,
            tail=list(tail)[-_REPORT_TAIL_LINES:],
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _listening_ports() -> str:
    for command in (('lsof', '-nP', '-iTCP', '-sTCP:LISTEN'), ('ss', '-ltn')):
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        lines = completed.stdout.splitlines()
        if completed.returncode != 0 or not lines:
            continue
        shown = lines[:_REPORT_PORT_LINES]
        if len(lines) > len(shown):
            shown.append(f'... {len(lines) - len(shown)} more listener line(s)')
        return '\n'.join(shown)
    return 'unavailable (neither lsof nor ss produced a listener list)'


def _report_failure(attempts: Sequence[Attempt]) -> None:
    print('[emulator] no attempt completed the gauntlet.', file=sys.stderr, flush=True)
    for attempt in attempts:
        print(
            f'[emulator]   attempt {attempt.index}: port {attempt.port} '
            f'outcome={attempt.outcome.value} firebase_exit={attempt.returncode} '
            f'marker={attempt.marker!r} reason={attempt.reason} log={attempt.log_path}',
            file=sys.stderr,
            flush=True,
        )
    print('[emulator] loopback TCP listeners at failure:', file=sys.stderr, flush=True)
    print(_listening_ports(), file=sys.stderr, flush=True)
    if attempts:
        last = attempts[-1]
        print(
            f'[emulator] last {len(last.tail)} line(s) of {last.log_path}:',
            file=sys.stderr,
            flush=True,
        )
        print('\n'.join(last.tail) or '<empty>', file=sys.stderr, flush=True)


def run_supervisor(
    *,
    inner_command: str,
    repo_root: Path = REPO_ROOT,
    project: str = DEFAULT_PROJECT,
    log_dir: Path | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_total_seconds: float = DEFAULT_MAX_TOTAL_SECONDS,
    readiness_timeout: float = DEFAULT_READINESS_TIMEOUT_SECONDS,
    readiness_command: Sequence[str] | None = None,
    firebase_command: Sequence[str] = FIREBASE_COMMAND,
    state_dir: str = '',
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    if not 1 <= max_attempts <= MAX_ATTEMPTS_CEILING:
        raise ValueError(f'max_attempts must be between 1 and {MAX_ATTEMPTS_CEILING}')
    if ATTEMPT_STATE_TOKEN in inner_command and not state_dir:
        raise ValueError('inner command references the attempt state token but no state_dir was given')
    if log_dir is None:
        log_dir = Path(tempfile.mkdtemp(prefix='omi-listen-pusher-emulator-logs-'))
    log_dir.mkdir(parents=True, exist_ok=True)
    if readiness_command is None:
        readiness_command = [
            str(GAUNTLET_PYTHON),
            '-m',
            'testing.listen_pusher_stack.emulator_readiness',
            '--timeout',
            f'{readiness_timeout:.0f}',
        ]
    started = monotonic()
    attempts: list[Attempt] = []
    for index in range(1, max_attempts + 1):
        elapsed = monotonic() - started
        if elapsed >= max_total_seconds:
            print(
                f'[emulator] wall-clock budget {max_total_seconds:.0f}s exhausted after '
                f'{len(attempts)} attempt(s); not starting attempt {index}',
                file=sys.stderr,
                flush=True,
            )
            break
        attempt = _run_attempt(
            index=index,
            inner_command=inner_command,
            repo_root=repo_root,
            project=project,
            log_dir=log_dir,
            readiness_command=readiness_command,
            firebase_command=firebase_command,
            state_dir=state_dir,
            budget_seconds=max(0.0, max_total_seconds - elapsed),
        )
        attempts.append(attempt)
        if attempt.outcome is Outcome.SUCCESS:
            print(f'[emulator] attempt {index} passed on 127.0.0.1:{attempt.port}', flush=True)
            return 0
        print(
            f'[emulator] attempt {index}: {attempt.outcome.value} - {attempt.reason} ' f'(port {attempt.port})',
            file=sys.stderr,
            flush=True,
        )
        if attempt.outcome is Outcome.REAL:
            _report_failure(attempts)
            return attempt.returncode or 1
        if index == max_attempts:
            print(
                f'[emulator] attempt cap {max_attempts} reached; not retrying',
                file=sys.stderr,
                flush=True,
            )
    _report_failure(attempts)
    if not attempts:
        return 1
    return attempts[-1].returncode or 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inner', required=True, help='shell command run inside the emulator session')
    parser.add_argument('--project', default=DEFAULT_PROJECT)
    parser.add_argument('--log-dir', type=Path, default=None)
    parser.add_argument('--max-attempts', type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument('--max-total-seconds', type=float, default=DEFAULT_MAX_TOTAL_SECONDS)
    parser.add_argument('--readiness-timeout', type=float, default=DEFAULT_READINESS_TIMEOUT_SECONDS)
    parser.add_argument(
        '--state-dir',
        default='',
        help=(
            'scenario state root passed to the inner command; each attempt gets '
            '<root>/attempt-<n> so a retry never inherits a half-run state'
        ),
    )
    args = parser.parse_args(argv)
    if not 1 <= args.max_attempts <= MAX_ATTEMPTS_CEILING:
        parser.error(f'--max-attempts must be between 1 and {MAX_ATTEMPTS_CEILING}')
    if not 60 <= args.max_total_seconds <= MAX_TOTAL_SECONDS_CEILING:
        parser.error(f'--max-total-seconds must be between 60 and {MAX_TOTAL_SECONDS_CEILING:.0f}')
    if not 5 <= args.readiness_timeout <= 600:
        parser.error('--readiness-timeout must be between 5 and 600 seconds')
    return run_supervisor(
        inner_command=args.inner,
        project=args.project,
        log_dir=args.log_dir,
        max_attempts=args.max_attempts,
        state_dir=args.state_dir,
        max_total_seconds=args.max_total_seconds,
        readiness_timeout=args.readiness_timeout,
    )


if __name__ == '__main__':
    raise SystemExit(main())
