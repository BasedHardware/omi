"""Offline contract for the listen-gauntlet emulator supervisor and readiness probe.

Two failure classes produced the same red `Listen Pusher Stack Gauntlet`:
the Firestore emulator's port can be taken between the probe that chose it and
Firebase's bind, and the emulator answers HTTP/1.1 on that port before it serves
gRPC. A gRPC client in either window reports `Trying to connect an http1.x
server (HTTP status 400)`, which the default retry wrapper stretches into a 60s
`RetryError`.

These tests pin the policy offline: transient startup failures retry with a
fresh port, a gauntlet that reached its own assertions never retries, and the
attempt cap and wall-clock budget are hard.
"""

from __future__ import annotations

import socket
import stat
import threading
import time
from pathlib import Path

import pytest

from testing.listen_pusher_stack import emulator_readiness, emulator_supervisor

_FAKE_FIREBASE = '''#!/usr/bin/env python3
"""Stand-in for `firebase emulators:exec` used by the offline supervisor tests."""
import json
import os
import pathlib
import subprocess
import sys

args = sys.argv[1:]
config_path = args[args.index('--config') + 1]
inner_command = args[-1]
port = json.loads(pathlib.Path(config_path).read_text())['emulators']['firestore']['port']

with pathlib.Path(os.environ['FAKE_ATTEMPT_COUNTER']).open('a') as handle:
    handle.write(f'{port}\\n')

mode = os.environ['FAKE_FIREBASE_MODE']
if mode == 'emulator-startup-failure':
    print('Error: Could not start Firestore Emulator, port ' + str(port) + ' is already in use', file=sys.stderr)
    sys.exit(1)

environment = dict(os.environ, FIRESTORE_EMULATOR_HOST=f'127.0.0.1:{port}')
sys.exit(subprocess.call(['bash', '-c', inner_command], env=environment))
'''

_INNER_SCRIPT = '''#!/usr/bin/env bash
case "$FAKE_FIREBASE_MODE" in
  pass) exit 0 ;;
  transient-inner)
    echo "google.api_core.exceptions.RetryError: Timeout of 60.0s exceeded, last exception: 503 failed to connect to all addresses; last error: INTERNAL: ipv4:127.0.0.1:1: Trying to connect an http1.x server (HTTP status 400)" >&2
    exit 1 ;;
  assertion-inner)
    echo "FAILED backend/tests/unit/test_stale_processing_emulator_concurrency.py::test_contention - AssertionError: expected 1 job, found 0" >&2
    exit 1 ;;
  stack-failure-inner)
    echo "testing.listen_pusher_stack.run.StackFailure: listen session never reached completed" >&2
    exit 1 ;;
  transient-then-assertion)
    echo "httpx.ReadTimeout: timed out while talking to the stack" >&2
    echo "StackFailure: durable finalizer completed without the expected binding" >&2
    exit 1 ;;
esac
exit 0
'''


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _run(tmp_path: Path, mode: str, monkeypatch: pytest.MonkeyPatch, **kwargs) -> tuple[int, list[int], Path]:
    counter = tmp_path / 'attempts.txt'
    counter.touch()
    inner = _write_executable(tmp_path / 'inner.sh', _INNER_SCRIPT)
    log_dir = tmp_path / 'logs'
    monkeypatch.setenv('FAKE_FIREBASE_MODE', mode)
    monkeypatch.setenv('FAKE_ATTEMPT_COUNTER', str(counter))
    returncode = emulator_supervisor.run_supervisor(
        inner_command=f'bash {inner}',
        repo_root=tmp_path,
        log_dir=log_dir,
        readiness_command=['true'],
        firebase_command=[str(_write_executable(tmp_path / 'firebase', _FAKE_FIREBASE))],
        **kwargs,
    )
    ports = [int(line) for line in counter.read_text().splitlines() if line.strip()]
    return returncode, ports, log_dir


def _http1_responder() -> tuple[socket.socket, int]:
    """A listener that answers the HTTP/2 preface the way plain HTTP/1.1 servers do."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', 0))
    listener.listen(8)
    port = int(listener.getsockname()[1])

    def serve() -> None:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            try:
                connection.recv(65535)
                connection.sendall(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:
                connection.close()

    threading.Thread(target=serve, daemon=True).start()
    return listener, port


def test_readiness_probe_rejects_a_port_that_only_speaks_http1(monkeypatch: pytest.MonkeyPatch) -> None:
    """An open port that answers HTTP/1.1 is not a serving Firestore emulator.

    This is the client-visible failure from the incident: the emulator answers
    plain HTTP on its gRPC port, so a gRPC client there reports
    `Trying to connect an http1.x server`.
    """
    listener, port = _http1_responder()
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', f'127.0.0.1:{port}')
    try:
        with pytest.raises(Exception) as error:
            emulator_readiness.probe_once(rpc_timeout=5.0)
        assert 'http' in str(error.value).lower()

        with pytest.raises(emulator_readiness.EmulatorNotReady):
            emulator_readiness.wait_until_serving(timeout=2.0, rpc_timeout=2.0)
    finally:
        listener.close()


def test_readiness_wait_is_bounded_and_reports_the_last_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[float] = []

    def not_ready(*, rpc_timeout: float, project: str) -> None:
        attempts.append(rpc_timeout)
        raise ConnectionRefusedError('Connection refused')

    monkeypatch.setattr(emulator_readiness, 'probe_once', not_ready)
    with pytest.raises(emulator_readiness.EmulatorNotReady) as error:
        emulator_readiness.wait_until_serving(host='127.0.0.1', port=9, timeout=0.6, rpc_timeout=1.0)

    assert len(attempts) >= 2
    assert 'did not serve Firestore gRPC within' in str(error.value)
    assert 'ConnectionRefusedError' in str(error.value)


def test_transient_emulator_startup_failure_retries_every_attempt_on_a_fresh_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    returncode, ports, log_dir = _run(tmp_path, 'emulator-startup-failure', monkeypatch)

    assert returncode != 0
    assert len(ports) == emulator_supervisor.DEFAULT_MAX_ATTEMPTS == 3
    assert len(set(ports)) == 3, 'every attempt must choose a fresh emulator port'
    assert sorted(path.name for path in log_dir.glob('emulator-attempt-*.log')) == [
        'emulator-attempt-1.log',
        'emulator-attempt-2.log',
        'emulator-attempt-3.log',
    ]


def test_transient_connection_failure_inside_the_gauntlet_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    returncode, ports, _log_dir = _run(tmp_path, 'transient-inner', monkeypatch)

    assert returncode != 0
    assert len(ports) == 3
    assert len(set(ports)) == 3


def test_readiness_failure_is_treated_as_a_startup_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    counter = tmp_path / 'attempts.txt'
    counter.touch()
    inner = _write_executable(tmp_path / 'inner.sh', '#!/usr/bin/env bash\nexit 0\n')
    monkeypatch.setenv('FAKE_ATTEMPT_COUNTER', str(counter))
    returncode = emulator_supervisor.run_supervisor(
        inner_command=f'bash {inner}',
        repo_root=tmp_path,
        log_dir=tmp_path / 'logs',
        readiness_command=['false'],
        firebase_command=[str(_write_executable(tmp_path / 'firebase', _FAKE_FIREBASE))],
    )

    assert returncode != 0
    assert len(counter.read_text().split()) == 3


@pytest.mark.parametrize('mode', ['assertion-inner', 'stack-failure-inner', 'transient-then-assertion'])
def test_gauntlet_failures_are_never_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    returncode, ports, _log_dir = _run(tmp_path, mode, monkeypatch)

    assert returncode != 0
    assert len(ports) == 1, 'a gauntlet that reached its own assertions must fail immediately'


def test_exhaustion_stops_at_the_cap_and_reports_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    returncode, ports, _log_dir = _run(tmp_path, 'emulator-startup-failure', monkeypatch)

    assert returncode != 0
    assert len(ports) == 3
    stderr = capsys.readouterr().err
    assert 'attempt cap 3 reached; not retrying' in stderr
    assert 'loopback TCP listeners at failure' in stderr
    assert 'is already in use' in stderr


def test_wall_clock_budget_stops_before_another_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([0.0, 0.0, 5000.0, 5000.0, 5000.0])

    returncode, ports, _log_dir = _run(
        tmp_path,
        'emulator-startup-failure',
        monkeypatch,
        max_total_seconds=100.0,
        monotonic=lambda: next(ticks),
    )

    assert returncode != 0
    assert len(ports) == 1, 'the wall-clock budget must prevent a retry'


def test_attempt_cap_cannot_be_raised_above_three() -> None:
    with pytest.raises(ValueError):
        emulator_supervisor.run_supervisor(inner_command='true', max_attempts=4)


def test_generated_inner_script_probes_before_it_runs_the_gauntlet(tmp_path: Path) -> None:
    script = emulator_supervisor._inner_script(
        inner_command='gauntlet --state-dir /tmp/state',
        marker=tmp_path / 'marker',
        readiness_command=['python3', '-m', 'readiness', '--timeout', '120'],
    )
    lines = script.splitlines()

    probe_index = lines.index('PYTHONPATH=backend python3 -m readiness --timeout 120')
    inner_index = lines.index('gauntlet --state-dir /tmp/state')
    assert probe_index < inner_index
    assert emulator_supervisor.MARKER_READINESS_FAILED in script
    assert emulator_supervisor.MARKER_STARTED in script
    assert emulator_supervisor.MARKER_INNER_PREFIX in script


def test_each_attempt_gets_a_fresh_scenario_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A retry must not inherit the previous attempt's half-run state.

    The inner command carries the attempt-state token, so the supervisor
    rewrites it per attempt. A retry that reused the failed attempt's
    ledger/cursor/evidence files could turn a transient startup failure into a
    false assertion failure. The path contains a space: the replacement must be
    shell-quoted, not spliced in raw.
    """
    state = tmp_path / 'state dir'
    record = tmp_path / 'args.txt'
    inner = _write_executable(
        tmp_path / 'inner.sh',
        f'#!/usr/bin/env bash\necho "$@" >> {record}\necho "httpx.ReadTimeout" >&2\nexit 1\n',
    )
    counter = tmp_path / 'attempts.txt'
    counter.touch()
    monkeypatch.setenv('FAKE_ATTEMPT_COUNTER', str(counter))
    monkeypatch.setenv('FAKE_FIREBASE_MODE', 'pass')
    returncode = emulator_supervisor.run_supervisor(
        inner_command=(f'bash {inner} --state-dir {emulator_supervisor.ATTEMPT_STATE_TOKEN}'),
        repo_root=tmp_path,
        log_dir=tmp_path / 'logs',
        readiness_command=['true'],
        firebase_command=[str(_write_executable(tmp_path / 'firebase', _FAKE_FIREBASE))],
        max_attempts=2,
        state_dir=str(state),
    )
    assert returncode != 0
    lines = record.read_text().splitlines()
    assert len(lines) == 2, lines
    assert f'--state-dir {state}/attempt-1' in lines[0]
    assert f'--state-dir {state}/attempt-2' in lines[1]
    assert emulator_supervisor.ATTEMPT_STATE_TOKEN not in '\n'.join(lines)
    assert (state / 'attempt-1').is_dir() and (state / 'attempt-2').is_dir()


def test_wall_clock_budget_kills_a_hung_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung attempt is terminated inside the budget, not just between attempts.

    Checking the budget only before each attempt lets a hung Firebase startup or
    inner command run past it until the CI job ceiling cancels the job, which
    hides the real cause.
    """
    inner = _write_executable(tmp_path / 'inner.sh', '#!/usr/bin/env bash\nsleep 120\n')
    counter = tmp_path / 'attempts.txt'
    counter.touch()
    monkeypatch.setenv('FAKE_ATTEMPT_COUNTER', str(counter))
    monkeypatch.setenv('FAKE_FIREBASE_MODE', 'pass')
    started = time.monotonic()
    returncode = emulator_supervisor.run_supervisor(
        inner_command=f'bash {inner}',
        repo_root=tmp_path,
        log_dir=tmp_path / 'logs',
        readiness_command=['true'],
        firebase_command=[str(_write_executable(tmp_path / 'firebase', _FAKE_FIREBASE))],
        max_attempts=3,
        max_total_seconds=2.0,
    )
    elapsed = time.monotonic() - started
    assert returncode != 0
    assert elapsed < 45.0, f'budget was not enforced mid-attempt: {elapsed:.1f}s'
