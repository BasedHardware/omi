"""Skeleton entrypoints must fail closed without changing ordinary commands."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev_harness import live_session, mobile_session, mobile_verify


def test_live_cli_routes_all_operations_to_owner(monkeypatch, capsys):
    # This is a wiring test, not a pinned requirement to remain unimplemented.
    def unavailable(*args, **kwargs):
        raise live_session.LiveNotImplemented('V1 not implemented')
    monkeypatch.setattr(live_session, 'dispatch', unavailable)
    for operation in live_session.OPERATIONS:
        assert mobile_session.main(['live', operation, 'oms-fixture', '--json']) == 2
    assert 'not implemented' in capsys.readouterr().err


def test_fast_session_routes_to_live_without_invoking_cold(monkeypatch):
    calls = []
    def attach(root, args):
        calls.append(args.session)
        return 2
    def cold(*args):
        raise AssertionError('cold fallback forbidden')
    monkeypatch.setattr(live_session, 'verify_live', attach)
    monkeypatch.setattr(mobile_verify, 'cmd_fast', cold)
    assert mobile_verify.main(['fast', '--session', 'oms-fixture', '--all']) == 2
    assert calls == ['oms-fixture']


def test_fake_flutter_process_uses_real_array_framing(tmp_path):
    import json
    from spine.test_live_session import Child
    child = Child('reject', tmp_path / 'wire.jsonl', 'owned-app', 'owned-device')
    try:
        events = [json.loads(child.receive(5))[0] for _ in range(4)]
        assert [event['event'] for event in events] == ['daemon.connected', 'app.start', 'app.debugPort', 'app.started']
        assert events[0]['params']['pid'] == child.process.pid
        assert events[1]['params']['directory'] == str(Path.cwd())
        assert events[1]['params']['deviceId'] == 'owned-device'
        child.send(json.dumps([{'id': 42, 'method': 'app.restart', 'params': {'appId': 'owned-app', 'fullRestart': False}}]) + '\n')
        replies = [json.loads(child.receive(5))[0] for _ in range(3)]
        assert replies[-1] == {'id': 42, 'result': {'code': 1, 'message': 'Reload rejected: class changed'}}
        assert replies[1]['id'] != 42
    finally:
        child.close()


def test_module_cli_refusal_is_exit_two_without_traceback(tmp_path):
    import os
    import subprocess
    root = Path(__file__).resolve().parents[3]
    env = {**os.environ, 'PYTHONPATH': str(root / 'scripts/dev-harness'),
           'OMI_LOCAL_STATE_ROOT': str(tmp_path / 'state')}
    result = subprocess.run([sys.executable, '-m', 'dev_harness.mobile_session',
                             'live', 'start', 'oms-never-acquired', '--json'],
                            cwd=root, env=env, text=True, capture_output=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert 'Traceback' not in result.stderr
    assert result.stderr.startswith('error: ')
