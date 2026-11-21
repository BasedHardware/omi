"""Owned-process cleanup contracts; real children are bounded and reaped here.

Injected denials exercise policy only. The real zombie probe records this host's
kernel outcome separately; neither reconstructs the historical stack incident.
"""

from __future__ import annotations

import errno
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from testing.listen_pusher_stack import cleanup
from testing.listen_pusher_stack import run as runner


def child_for(process, tmp_path):
    return runner.Child('backend', process, tmp_path / 'backend.log', tmp_path, 'python:test-child', os.getuid())


def member(process, **changes):
    values = dict(pid=process.pid, ppid=os.getpid(), pgid=process.pid, uid=os.getuid(), state='S', sid=process.pid)
    return cleanup.Member(**(values | changes))


def fake_process():
    process = Mock(pid=424242, returncode=None)
    process.poll.return_value = None
    return process


def gone(*_args):
    raise ProcessLookupError(errno.ESRCH, 'group absent')


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError('bounded child fixture did not reach requested state')


@pytest.fixture
def real_child(tmp_path):
    children = []

    def launch(source):
        script = tmp_path / f'child-{len(children)}.py'
        script.write_text(source)
        process = subprocess.Popen(
            [sys.executable, '-I', str(script)],
            cwd=tmp_path,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        children.append(process)
        return child_for(process, tmp_path)

    yield launch
    # Fixture teardown targets only exact, unreaped direct Popen children. The
    # scripts never fork and also have a finite natural lifetime.
    for process in children:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def test_real_owned_session_term_exit_and_idempotence(real_child, tmp_path):
    ready = tmp_path / 'ready'
    child = real_child(f'import pathlib, time\npathlib.Path({str(ready)!r}).touch()\ntime.sleep(15)\n')
    wait_for(ready.exists)
    assert os.getpgid(child.process.pid) == os.getsid(child.process.pid) == child.process.pid
    evidence = tmp_path / 'cleanup.jsonl'
    cleanup.stop_child(child, evidence)
    assert child.process.returncode == -signal.SIGTERM
    with pytest.raises(ProcessLookupError):
        os.killpg(child.process.pid, 0)
    cleanup.stop_child(child, evidence)
    assert events(evidence)[-1]['event'] == 'cleaned'


@pytest.fixture
def real_zombie(real_child, tmp_path):
    ready, release = tmp_path / 'ready', tmp_path / 'release'
    # Hold a finite, non-forking child live until its actual session identity is
    # captured. No SID is synthesized from Darwin's missing zombie metadata.
    child = real_child(
        'import pathlib, time\n'
        f'release = pathlib.Path({str(release)!r})\n'
        f'pathlib.Path({str(ready)!r}).touch()\n'
        'deadline = time.monotonic() + 15\n'
        'while not release.exists() and time.monotonic() < deadline:\n'
        '    time.sleep(0.01)\n'
        'assert release.exists(), "fixture release deadline"\n'
    )
    wait_for(ready.exists)
    live = cleanup.group_members(child.process.pid)
    assert len(live) == 1
    row = live[0]
    assert row.pid == row.pgid == row.sid == child.process.pid
    assert row.ppid == os.getpid() and row.uid == os.getuid()
    release.touch()

    def zombie_members():
        rows = cleanup.group_members(child.process.pid)
        return rows if any(row.state.startswith('Z') for row in rows) else None

    zombie = wait_for(zombie_members)
    assert len(zombie) == 1
    row = zombie[0]
    assert row.state.startswith('Z')
    assert row.pid == row.pgid == child.process.pid
    assert row.ppid == os.getpid() and row.uid == child.uid
    assert row.sid == live[0].sid or (row.sid is None and row.sid_errno == errno.ESRCH)
    assert child.process.returncode is None  # Still unreaped: the PID cannot be reused.
    (tmp_path / 'zombie-observation.json').write_text(
        json.dumps({'live': [vars(row) for row in live], 'zombie': [vars(row) for row in zombie]})
    )
    return child


def test_real_zombie_is_observed_then_reaped_without_signal(real_zombie, tmp_path):
    child = real_zombie
    evidence = tmp_path / 'cleanup.jsonl'
    cleanup.stop_child(child, evidence)
    rows = events(evidence)
    assert rows[0]['event'] == 'poll' and rows[0]['status'] == 0
    assert not any(row['event'] == 'census' for row in rows)
    assert not any(row['event'] == 'signal' for row in rows)
    assert child.process.returncode == 0
    assert rows[-1]['event'] == 'cleaned'


def test_real_owned_zombie_group_signal_records_kernel_outcome(real_zombie, tmp_path, record_property):
    child = real_zombie
    # Authorization comes from the fixture's verified LIVE session, exact
    # unreaped child and known non-forking script, not its unknown zombie SID.
    # This real kernel observation does not enable supervisor EPERM recovery.
    outcome = 'accepted'
    try:
        os.killpg(child.process.pid, signal.SIGKILL)
    except PermissionError as error:
        assert error.errno == errno.EPERM
        outcome = 'EPERM'
    except ProcessLookupError:
        outcome = 'ESRCH'
    record_property('owned_zombie_signal', f'{sys.platform}:{outcome}')
    (tmp_path / 'zombie-kernel-outcome.json').write_text(json.dumps({'platform': sys.platform, 'outcome': outcome}))
    child.process.wait(timeout=5)
    cleanup.stop_child(child, tmp_path / 'cleanup.jsonl')


def test_terminal_child_is_reaped_before_any_census(monkeypatch, tmp_path):
    process = fake_process()

    def poll():
        process.returncode = 0
        return 0

    process.poll.side_effect = poll
    census = Mock(side_effect=AssertionError('terminal child must not need metadata'))
    monkeypatch.setattr(cleanup.os, 'killpg', gone)
    cleanup.stop_child(child_for(process, tmp_path), tmp_path / 'cleanup.jsonl', census=census)
    census.assert_not_called()
    assert process.returncode == 0


@pytest.mark.parametrize('state', ['S', 'Z'])
def test_missing_sid_is_recorded_but_cannot_authorize_signal(monkeypatch, tmp_path, state):
    process = fake_process()
    output = f'{process.pid} {os.getpid()} {process.pid} {os.getuid()} {state} python\n'
    monkeypatch.setattr(cleanup.subprocess, 'run', Mock(return_value=SimpleNamespace(stdout=output)))
    monkeypatch.setattr(cleanup.os, 'getsid', gone)
    rows = cleanup.group_members(process.pid)
    assert len(rows) == 1 and rows[0].sid is None and rows[0].sid_errno == errno.ESRCH
    assert rows[0].state == state
    monkeypatch.setattr(cleanup, 'group_members', lambda _: rows)
    send = Mock()
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    stack = runner.Stack.__new__(runner.Stack)
    stack.state_dir = tmp_path
    child = child_for(process, tmp_path)
    stack.children = {'backend': child}
    with pytest.raises(cleanup.CleanupFailure, match='foreign or unverifiable'):
        stack.stop('backend')
    assert stack.children['backend'] is child
    send.assert_not_called()


@pytest.mark.parametrize(
    'state,error',
    [
        ('S', PermissionError(errno.EPERM, 'live lookup denied')),
        ('Z', PermissionError(errno.EPERM, 'zombie lookup denied')),
        ('S', OSError(errno.EIO, 'lookup failed')),
    ],
)
def test_sid_lookup_denials_and_other_errors_propagate(monkeypatch, state, error):
    output = f'424242 {os.getpid()} 424242 {os.getuid()} {state} python\n'
    monkeypatch.setattr(cleanup.subprocess, 'run', Mock(return_value=SimpleNamespace(stdout=output)))
    monkeypatch.setattr(cleanup.os, 'getsid', Mock(side_effect=error))
    with pytest.raises(type(error)):
        cleanup.group_members(424242)


def test_census_timeout_retains_child_and_never_signals(monkeypatch, tmp_path):
    process = fake_process()
    monkeypatch.setattr(cleanup, 'group_members', Mock(side_effect=subprocess.TimeoutExpired('ps', 5)))
    send = Mock()
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    stack = runner.Stack.__new__(runner.Stack)
    stack.state_dir = tmp_path
    child = child_for(process, tmp_path)
    stack.children = {'backend': child}
    with pytest.raises(cleanup.CleanupFailure, match='TimeoutExpired'):
        stack.stop('backend')
    assert stack.children['backend'] is child
    send.assert_not_called()


@pytest.mark.parametrize('state', ['S', 'Z'])
def test_exit_during_census_reaps_before_unknown_metadata_is_used(monkeypatch, tmp_path, state):
    process = fake_process()
    statuses = iter([None, None, 0])

    def poll():
        process.returncode = next(statuses)
        return process.returncode

    process.poll.side_effect = poll
    rows = [member(process, state=state, sid=None, sid_errno=errno.ESRCH)]
    monkeypatch.setattr(cleanup.os, 'killpg', gone)
    cleanup.stop_child(child_for(process, tmp_path), tmp_path / 'cleanup.jsonl', census=lambda _: rows)
    assert process.returncode == 0
    recorded = events(tmp_path / 'cleanup.jsonl')
    observed = next(row['members'][0] for row in recorded if row['event'] == 'census')
    assert observed['state'] == state
    assert observed['sid'] is None and observed['sid_errno'] == errno.ESRCH
    assert any(row['event'] == 'group_absent' for row in recorded)
    assert not any(row['event'] == 'signal' for row in recorded)


def test_term_timeout_then_kill_waits_and_proves_group_absence(monkeypatch, tmp_path):
    process = fake_process()
    rows = [member(process)]
    signals = []

    def wait(timeout):
        assert timeout == 5
        if not signals or signals[-1] != signal.SIGKILL:
            raise subprocess.TimeoutExpired('owned-child', timeout)
        process.returncode = -signal.SIGKILL
        rows.clear()
        return process.returncode

    def send(pgid, sig):
        assert pgid == process.pid
        if sig == 0:
            gone()
        signals.append(sig)

    process.wait.side_effect = wait
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    cleanup.stop_child(child_for(process, tmp_path), tmp_path / 'cleanup.jsonl', census=lambda _: list(rows))
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert process.wait.call_count == 2


def test_exit_between_term_timeout_and_kill_requires_reap_and_absence(monkeypatch, tmp_path):
    process = fake_process()
    calls = 0

    def census(_pgid):
        nonlocal calls
        calls += 1
        return [member(process)] if calls == 1 else []

    def poll():
        if calls > 1:
            process.returncode = 0
        return process.returncode

    process.poll.side_effect = poll
    process.wait.side_effect = [subprocess.TimeoutExpired('owned-child', 5), 0]
    signals = []

    def send(_pgid, sig):
        if sig == 0:
            gone()
        signals.append(sig)

    monkeypatch.setattr(cleanup.os, 'killpg', send)
    cleanup.stop_child(child_for(process, tmp_path), tmp_path / 'cleanup.jsonl', census=census)
    assert process.returncode == 0
    assert signals == [signal.SIGTERM]


@pytest.mark.parametrize('state', ['?Es', 'S', 'Z'])
def test_deferred_waitability_uses_kill_wait_without_signal(monkeypatch, tmp_path, state):
    process = fake_process()
    process.poll.side_effect = lambda: process.returncode
    unknown = member(process, state=state, sid=None, sid_errno=errno.ESRCH)
    census = Mock(side_effect=[[member(process)], [unknown]])

    def wait(timeout):
        assert timeout == 5 and process.returncode is None
        if process.wait.call_count == 1:
            raise subprocess.TimeoutExpired('owned-child', timeout)
        # Both polls around the KILL census still found the child non-waitable.
        assert process.poll.call_count == 5
        assert process.wait.call_count == 2
        process.returncode = -signal.SIGTERM
        return process.returncode

    def send(pgid, sig):
        assert pgid == process.pid
        if sig == 0:
            assert process.returncode == -signal.SIGTERM
            gone()
        assert sig == signal.SIGTERM and process.returncode is None

    process.wait.side_effect = wait
    send_mock = Mock(side_effect=send)
    monkeypatch.setattr(cleanup.os, 'killpg', send_mock)
    monkeypatch.setattr(cleanup, 'group_members', census)
    stack = runner.Stack.__new__(runner.Stack)
    stack.state_dir = tmp_path
    stack.children = {'backend': child_for(process, tmp_path)}
    stack.stop('backend')
    assert not stack.children
    assert process.returncode == -signal.SIGTERM
    assert process.wait.call_args_list == [call(timeout=5), call(timeout=5)]
    assert send_mock.call_args_list == [call(process.pid, signal.SIGTERM), call(process.pid, 0)]
    recorded = events(tmp_path / 'cleanup.jsonl')
    observed = [row for row in recorded if row['event'] == 'census'][-1]['members']
    assert observed == [vars(unknown)]
    assert all(row['status'] is None for row in recorded if row['event'].startswith('poll'))
    tail = recorded[next(i for i, row in enumerate(recorded) if row['event'] == 'reap_only') :]
    assert [row['event'] for row in tail] == ['reap_only', 'wait_begin', 'wait_reaped', 'group_absent', 'cleaned']
    assert tail[1]['stage'] == tail[2]['stage'] == 'wait_kill'


@pytest.mark.parametrize('outcome', ['timeout', 'live', 'unknown', 'foreign', 'descendant', 'denied'])
def test_reap_only_requires_wait_and_independent_absence(monkeypatch, tmp_path, outcome):
    process = fake_process()
    process.poll.side_effect = lambda: process.returncode
    unknown = member(process, state='?Es', sid=None, sid_errno=errno.ESRCH)
    remaining = {
        'live': [member(process)],
        'unknown': [unknown],
        'foreign': [member(process, pid=process.pid + 1, uid=os.getuid() + 1)],
        'descendant': [member(process, pid=process.pid + 1, ppid=1)],
    }.get(outcome, [])
    census = Mock(side_effect=[[member(process)], [unknown], remaining])

    def wait(timeout):
        assert timeout == 5 and process.returncode is None
        if process.wait.call_count == 1 or outcome == 'timeout':
            raise subprocess.TimeoutExpired('owned-child', timeout)
        process.returncode = -signal.SIGTERM
        return process.returncode

    def send(_pgid, sig):
        if sig == 0:
            assert process.returncode == -signal.SIGTERM
            if outcome == 'denied':
                raise PermissionError(errno.EPERM, 'absence probe denied')
        else:
            assert sig == signal.SIGTERM

    process.wait.side_effect = wait
    send_mock = Mock(side_effect=send)
    monkeypatch.setattr(cleanup.os, 'killpg', send_mock)
    monkeypatch.setattr(cleanup, 'group_members', census)
    stack = runner.Stack.__new__(runner.Stack)
    stack.state_dir = tmp_path
    child = child_for(process, tmp_path)
    stack.children = {'backend': child}
    expected = 'TimeoutExpired' if outcome == 'timeout' else 'PermissionError' if outcome == 'denied' else 'surviving'
    with pytest.raises(cleanup.CleanupFailure, match=expected):
        stack.stop('backend')
    assert stack.children['backend'] is child
    assert process.wait.call_args_list == [call(timeout=5), call(timeout=5)]
    expected_calls = [call(process.pid, signal.SIGTERM)]
    if outcome != 'timeout':
        expected_calls.append(call(process.pid, 0))
    assert send_mock.call_args_list == expected_calls
    assert process.returncode == (None if outcome == 'timeout' else -signal.SIGTERM)
    recorded = events(tmp_path / 'cleanup.jsonl')
    assert any(row['event'] == 'reap_only' for row in recorded)
    assert not any(row['event'] in {'group_absent', 'cleaned'} for row in recorded)
    assert recorded[-1]['event'] == 'failed'


@pytest.mark.parametrize('mismatch', ['pid', 'ppid', 'pgid', 'uid', 'sid_errno', 'extra_member'])
def test_reap_only_does_not_accept_other_unknown_membership(monkeypatch, tmp_path, mismatch):
    process = fake_process()
    process.wait.side_effect = subprocess.TimeoutExpired('owned-child', 5)
    changes = {
        'pid': {'pid': process.pid + 1},
        'ppid': {'ppid': os.getpid() + 1},
        'pgid': {'pgid': process.pid + 1},
        'uid': {'uid': os.getuid() + 1},
        'sid_errno': {'sid_errno': errno.EPERM},
        'extra_member': {},
    }[mismatch]
    rows = [member(process, state='?Es', sid=None, sid_errno=errno.ESRCH)]
    rows[0] = cleanup.Member(**(vars(rows[0]) | changes))
    if mismatch == 'extra_member':
        rows.append(member(process, pid=process.pid + 1, ppid=process.pid))
    census = Mock(side_effect=[[member(process)], rows])
    monkeypatch.setattr(cleanup, 'group_members', census)
    send = Mock()
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    stack = runner.Stack.__new__(runner.Stack)
    stack.state_dir = tmp_path
    child = child_for(process, tmp_path)
    stack.children = {'backend': child}
    with pytest.raises(cleanup.CleanupFailure, match='foreign or unverifiable'):
        stack.stop('backend')
    assert stack.children['backend'] is child
    send.assert_called_once_with(process.pid, signal.SIGTERM)
    process.wait.assert_called_once_with(timeout=5)
    assert not any(row['event'] == 'reap_only' for row in events(tmp_path / 'cleanup.jsonl'))


@pytest.mark.parametrize('denied_signal', [signal.SIGTERM, signal.SIGKILL])
def test_eperm_is_failure_with_handle_retained(monkeypatch, tmp_path, denied_signal):
    process = fake_process()
    process.wait.side_effect = subprocess.TimeoutExpired('owned-child', 5)
    monkeypatch.setattr(cleanup, 'group_members', lambda _: [member(process)])

    def denied(_pgid, sig):
        if sig == denied_signal:
            raise PermissionError(errno.EPERM, 'injected denial, not historical evidence')

    monkeypatch.setattr(cleanup.os, 'killpg', denied)
    stack = runner.Stack.__new__(runner.Stack)
    stack.state_dir = tmp_path
    child = child_for(process, tmp_path)
    stack.children = {'backend': child}
    with pytest.raises(cleanup.CleanupFailure, match='PermissionError'):
        stack.stop('backend')
    assert stack.children['backend'] is child
    assert events(tmp_path / 'cleanup.jsonl')[-1]['errno'] == errno.EPERM


@pytest.mark.parametrize('kind', ['denied', 'unknown', 'foreign_uid', 'foreign_session', 'foreign_parent'])
def test_unverifiable_membership_never_signals(monkeypatch, tmp_path, kind):
    process = fake_process()

    def census(_pgid):
        if kind == 'denied':
            raise PermissionError(errno.EPERM, 'census denied')
        if kind == 'unknown':
            return []
        return [
            member(
                process,
                **{
                    'foreign_uid': {'uid': os.getuid() + 1},
                    'foreign_session': {'sid': process.pid + 1},
                    'foreign_parent': {'ppid': os.getpid() + 1},
                }[kind],
            )
        ]

    send = Mock()
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    with pytest.raises(cleanup.CleanupFailure):
        cleanup.stop_child(child_for(process, tmp_path), tmp_path / 'cleanup.jsonl', census=census)
    send.assert_not_called()


def test_reaped_leader_with_descendant_is_not_cleaned_or_signaled(monkeypatch, tmp_path):
    process = fake_process()
    process.returncode = 0
    process.poll.return_value = 0
    send = Mock()
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    with pytest.raises(cleanup.CleanupFailure, match='surviving group members'):
        cleanup.stop_child(
            child_for(process, tmp_path),
            tmp_path / 'cleanup.jsonl',
            census=lambda _: [member(process, pid=process.pid + 1, ppid=1)],
        )
    send.assert_called_once_with(process.pid, 0)  # Absence probe only, never a descendant signal.


def test_membership_is_rechecked_before_kill(monkeypatch, tmp_path):
    process = fake_process()
    process.wait.side_effect = subprocess.TimeoutExpired('owned-child', 5)
    calls = 0

    def census(_pgid):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [member(process)]
        return [member(process), member(process, pid=process.pid + 1, uid=os.getuid() + 1)]

    send = Mock()
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    with pytest.raises(cleanup.CleanupFailure, match='foreign or unverifiable'):
        cleanup.stop_child(child_for(process, tmp_path), tmp_path / 'cleanup.jsonl', census=census)
    send.assert_called_once_with(process.pid, signal.SIGTERM)


def test_waited_leader_with_remaining_descendant_retains_handle(monkeypatch, tmp_path):
    process = fake_process()
    rows = [member(process)]

    def wait(timeout):
        process.returncode = 0
        rows[:] = [member(process, pid=process.pid + 1, ppid=1)]
        return 0

    process.wait.side_effect = wait
    monkeypatch.setattr(cleanup, 'group_members', lambda _: list(rows))
    send = Mock()
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    stack = runner.Stack.__new__(runner.Stack)
    stack.state_dir = tmp_path
    child = child_for(process, tmp_path)
    stack.children = {'backend': child}
    with pytest.raises(cleanup.CleanupFailure, match='surviving group members'):
        stack.stop('backend')
    assert stack.children['backend'] is child
    assert send.call_args_list == [call(process.pid, signal.SIGTERM), call(process.pid, 0)]


def test_esrch_during_term_still_requires_wait_and_group_proof(monkeypatch, tmp_path):
    process = fake_process()
    rows = [member(process)]

    def wait(timeout):
        process.returncode = 0
        rows.clear()
        return 0

    process.wait.side_effect = wait
    monkeypatch.setattr(cleanup.os, 'killpg', gone)
    cleanup.stop_child(child_for(process, tmp_path), tmp_path / 'cleanup.jsonl', census=lambda _: list(rows))
    process.wait.assert_called_once_with(timeout=5)
    assert events(tmp_path / 'cleanup.jsonl')[-1]['event'] == 'cleaned'


@pytest.mark.parametrize('probe', ['denied', 'live'])
def test_empty_census_does_not_prove_absence(monkeypatch, tmp_path, probe):
    process = fake_process()
    process.returncode = 0
    process.poll.return_value = 0
    send = Mock(side_effect=PermissionError(errno.EPERM, 'denied')) if probe == 'denied' else Mock()
    monkeypatch.setattr(cleanup.os, 'killpg', send)
    with pytest.raises(cleanup.CleanupFailure):
        cleanup.stop_child(child_for(process, tmp_path), tmp_path / 'cleanup.jsonl', census=lambda _: [])


def test_close_attempts_every_child_retains_only_failures_and_preserves_primary(monkeypatch, tmp_path):
    stack = runner.Stack.__new__(runner.Stack)
    stack.state_dir = tmp_path
    stack.children = {name: SimpleNamespace(name=name) for name in ['redis', 'backend', 'pusher']}
    attempts = []

    def stop(child, _evidence):
        attempts.append(child.name)
        if child.name == 'pusher':
            raise cleanup.CleanupFailure('pusher: denied at kill; retained pid=424242')

    monkeypatch.setattr(runner, 'stop_child', stop)
    monkeypatch.setattr(runner, 'Stack', Mock(return_value=stack))
    stack.start = Mock()
    primary = AssertionError('original scenario assertion')

    async def scenario(_stack):
        raise primary

    with pytest.raises(AssertionError) as error:
        runner._run_stack_scenario(tmp_path, finalization_mode='inline', finalizer_failures=None, scenario=scenario)
    assert error.value is primary
    assert attempts == ['pusher', 'backend', 'redis']
    assert list(stack.children) == ['pusher']
    assert 'pusher: denied at kill' in primary.__notes__[0]


def test_successful_scenario_cannot_hide_cleanup_failure(monkeypatch, tmp_path):
    stack = SimpleNamespace(start=Mock(), close=Mock(side_effect=cleanup.CleanupFailure('backend retained')))
    monkeypatch.setattr(runner, 'Stack', Mock(return_value=stack))

    async def scenario(_stack):
        return

    with pytest.raises(cleanup.CleanupFailure, match='backend retained'):
        runner._run_stack_scenario(tmp_path, finalization_mode='inline', finalizer_failures=None, scenario=scenario)
