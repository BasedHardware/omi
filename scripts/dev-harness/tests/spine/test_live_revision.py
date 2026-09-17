"""V1 builder-review acceptance: startup is not an RPC deadline; attach is live."""
import json
from types import SimpleNamespace

from .pending import pending
from .test_live_session import rig  # shared hermetic subprocess fixture
from dev_harness import live_session as live


@pending("V1")
def test_slow_machine_read_is_allowed_within_requested_deadline(rig):
    original = rig.factory
    timeouts = []
    def factory(spec):
        child = original(spec)
        receive = child.receive
        def bounded(timeout_s):
            timeouts.append(timeout_s)
            # Deterministically model a still-running build/operation, without sleep.
            assert timeout_s > 1, 'broker imposed a short hidden deadline'
            return receive(timeout_s)
        child.receive = bounded
        return child
    rig.factory = factory
    engine = rig.engine()
    assert engine.start()['outcome'] == 'ok'
    assert timeouts[0] > 412, 'cold start must allow the measured iOS build'
    timeouts.clear()
    assert engine.request('reload', generation=1, timeout_s=30)['outcome'] == 'ok'
    assert timeouts and all(1 < value <= 30 for value in timeouts)


@pending("V1")
def test_verify_contacts_broker_then_refuses_missing_journey_adapter(rig, monkeypatch):
    from dev_harness import mobile_verify
    engine = rig.engine()
    engine.start()
    calls = []
    def dispatch(root, session_id, operation, params=None):
        calls.append((session_id, operation))
        assert operation == 'status'
        return engine.request('status', generation=1)
    monkeypatch.setattr(live, 'dispatch', dispatch)
    assert mobile_verify.main(['fast', '--session', 'oms-fixture', '--all']) == 2
    assert calls == [('oms-fixture', 'status')]


@pending("V1")
def test_teardown_signals_owned_live_processes_and_confirms_death(tmp_path):
    from dataclasses import asdict
    import os
    import signal
    import subprocess
    import sys
    from dev_harness import mobile_session as ms
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    env = {'OMI_LOCAL_STATE_ROOT': str(tmp_path / 'state')}
    lease = ms.acquire(root, env, name='termination', listeners=lambda p: ())
    child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
                             stdin=subprocess.PIPE, start_new_session=True)
    try:
        record = live.BrokerIdentity(lease['owner']['host'], lease['owner']['user'], 'test-boot',
            child.pid, 'test-start', 'test-marker', 1, str(root), lease['session_id'])
        directory = ms.session_dir(root, lease['session_id'], env)
        # One process can represent both identities here; never signal twice.
        (directory / 'live.json').write_text(json.dumps({'broker': asdict(record), 'child': asdict(record)}))
        observed, signaled = [], []
        def probe(identity):
            observed.append(identity)
            return record if child.poll() is None else None
        def terminate(pid):
            assert pid == child.pid
            signaled.append(pid)
            os.killpg(pid, signal.SIGTERM)
            child.wait(timeout=5)
        live.teardown(root, lease['session_id'], env, probe=probe, terminate=terminate)
        assert child.poll() is not None
        assert signaled == [child.pid]
        assert len(observed) >= 2, 'teardown must confirm death after signaling'
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)
        child.stdin.close()


@pending("V1")
def test_missing_or_wrong_seed_identity_never_claims_ready(rig):
    (rig.directory / 'seed.json').write_text(json.dumps({'uid': 'other-user', 'fixture_version': 'v1'}))
    engine = rig.engine()
    try:
        assert engine.start()['outcome'] == 'blocked'
    except live.LiveError as error:
        assert error.code == 'unsafe-config'
