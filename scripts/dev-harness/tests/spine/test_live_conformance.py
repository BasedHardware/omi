"""T7 adversarial acceptance: fake-backed does not mean fabricated ownership/evidence."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from .pending import pending
from .test_live_session import rig
from dev_harness import live_session as live, session_evidence as se


def test_start_cannot_attribute_a_build_to_source_observed_only_after_launch(rig):
    factory = rig.factory

    def changed(spec):
        child = factory(spec)
        rig.stamp = replace(rig.stamp, inputs_sha256='e' * 64)
        return child

    rig.factory = changed
    engine = rig.engine()
    reply = engine.start()
    assert reply['outcome'] == 'blocked'
    assert reply['evidence']['live']['loaded_source'] is None
    engine.close()


def test_close_reaps_child_even_when_no_app_start_event_arrived(rig):
    class Dead:
        closed = False

        def send(self, line):
            pass

        def receive(self, timeout_s):
            return None

        def close(self):
            self.closed = True

    child = Dead()
    rig.factory = lambda spec: child
    engine = rig.engine()
    try:
        assert engine.start()['outcome'] == 'blocked'
    except live.LiveError as error:
        assert error.code == 'daemon-exited'
    engine.close()
    assert child.closed


def test_factory_failure_does_not_leave_a_live_worktree_claim(rig):
    factory = rig.factory

    def fail(spec):
        raise OSError('synthetic spawn failure')

    rig.factory = fail
    first = rig.engine()
    with pytest.raises(OSError):
        first.start()
    rig.factory = factory
    second = rig.engine()
    assert second.start()['outcome'] == 'ok'
    second.close()


@pytest.mark.parametrize('operation,params', [('status', {}), ('logs', {}), ('controls', {'method': 'state'})])
def test_new_lease_generation_cannot_adopt_old_child_even_with_new_request_generation(rig, operation, params):
    engine = rig.engine()
    engine.start()
    rig.lease['generation'] += 1
    with pytest.raises(live.LiveError) as error:
        engine.request(operation, generation=2, params=params)
    assert error.value.code == 'stale-session'
    engine.close()


def test_source_change_during_post_reload_readiness_does_not_advance_loaded_identity(rig):
    factory = rig.factory
    armed = False

    def create(spec):
        child = factory(spec)
        send = child.send

        def changed(line):
            if armed and 'ext.omi.controls.state' in line:
                rig.stamp = replace(rig.stamp, inputs_sha256='f' * 64)
            send(line)

        child.send = changed
        return child

    rig.factory = create
    engine = rig.engine()
    before = engine.start()['evidence']['live']
    armed = True
    reply = engine.request('reload', generation=1)
    assert reply['outcome'] == 'blocked'
    assert reply['evidence']['live']['loaded_source'] == before['loaded_source']
    assert reply['evidence']['live']['loaded_sequence'] == before['loaded_sequence']
    engine.close()


def test_operation_elapsed_time_measures_work_not_receipt_serialization(rig, monkeypatch):
    now = [0.0]
    factory = rig.factory

    def create(spec):
        child = factory(spec)
        send = child.send

        def delayed(line):
            if json.loads(line)[0]['method'] == 'app.restart':
                now[0] += 2.5
            send(line)

        child.send = delayed
        return child

    monkeypatch.setattr(
        se,
        'utc_now',
        lambda: (datetime(2026, 9, 17, tzinfo=timezone.utc) + timedelta(seconds=now[0]))
        .isoformat()
        .replace('+00:00', 'Z'),
    )
    engine = live.LiveSession(
        rig.directory.parent,
        rig.directory,
        load_lease=lambda: rig.lease,
        source=lambda: rig.stamp,
        factory=create,
        screenshot=rig.screenshot,
        monotonic=lambda: now[0],
    )
    engine.start()
    receipt = engine.request('reload', generation=1)['evidence']['live']
    assert receipt['elapsed_ms'] == 2500
    assert receipt['started_at'] < receipt['finished_at']
    engine.close()


def test_vm_auth_urls_are_sanitized_by_shape_not_one_fixture_secret(rig):
    factory = rig.factory
    secret = 'UNRELATED-secret-42='
    armed = False

    def create(spec):
        child = factory(spec)
        receive = child.receive

        def read(timeout_s):
            nonlocal armed
            if armed:
                armed = False
                return json.dumps(
                    [
                        {
                            'event': 'app.log',
                            'params': {
                                'appId': 'app-fixture',
                                'log': 'VM service ws://127.0.0.1:43123/' + secret + '/ws',
                                'error': False,
                            },
                        }
                    ]
                )
            return receive(timeout_s)

        child.receive = read
        return child

    rig.factory = create
    engine = rig.engine()
    engine.start()
    armed = True
    engine.request('reload', generation=1)
    reply = engine.request('logs', generation=1)
    assert secret not in json.dumps(reply)
    for path in rig.directory.glob('operations/*/evidence.json'):
        assert secret not in path.read_text()
    engine.close()


def test_progress_events_cannot_reset_the_absolute_rpc_deadline(rig):
    now, reads, armed = [0.0], [], [False]
    factory = rig.factory

    def create(spec):
        child = factory(spec)
        receive = child.receive

        def read(timeout_s):
            if armed[0]:
                reads.append(timeout_s)
                assert len(reads) <= 5, 'progress events kept a timed-out operation alive'
                now[0] += 0.05
                return json.dumps([{'event': 'app.log', 'params': {'log': 'compile progress'}}])
            return receive(timeout_s)

        child.receive = read
        return child

    engine = live.LiveSession(
        rig.directory.parent,
        rig.directory,
        load_lease=lambda: rig.lease,
        source=lambda: rig.stamp,
        factory=create,
        screenshot=rig.screenshot,
        monotonic=lambda: now[0],
    )
    before = engine.start()['evidence']['live']['loaded_source']
    armed[0] = True
    reply = engine.request('reload', generation=1, timeout_s=0.2)
    armed[0] = False
    assert reply['outcome'] == 'blocked' and reply['error_code'] == 'deadline'
    assert reply['evidence']['live']['loaded_source'] == before
    assert reads and reads[-1] < reads[0] <= 0.2
    engine.close()


def test_read_control_cannot_steal_an_inflight_restart_response(rig):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    factory = rig.factory
    armed, entered, resume = threading.Event(), threading.Event(), threading.Event()
    main_thread = threading.current_thread()

    def create(spec):
        child = factory(spec)
        receive = child.receive

        def read(timeout_s):
            if armed.is_set() and threading.current_thread() is not main_thread:
                armed.clear()
                entered.set()
                assert resume.wait(5), 'test synchronization deadline'
            return receive(timeout_s)

        child.receive = read
        return child

    rig.factory = create
    engine = rig.engine()
    engine.start()
    armed.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        reloading = pool.submit(engine.request, 'reload', generation=1, timeout_s=0.3)
        try:
            assert entered.wait(5)
            # Cached status is always available. VM reads may return busy, or
            # succeed via real response demultiplexing; they must not consume another RPC.
            assert engine.request('status', generation=1)['result']['state'] == 'busy'
            try:
                assert (
                    engine.request('controls', generation=1, params={'method': 'state'}, timeout_s=0.3)['outcome']
                    == 'ok'
                )
            except live.LiveError as error:
                assert error.code == 'busy'
        finally:
            resume.set()
        assert reloading.result(timeout=5)['outcome'] == 'ok'
    engine.close()
