"""Round-3 admission, durable gap fencing and serving-latency regressions."""

from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.cloud import firestore

from config import episode_log as config
from database import episode_log as store, episodes
from routers import episodes as api
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.episodes.log import capture, reads, reconcile, retention, worker
from utils.episodes.log.fold import Fold
from utils.episodes.log.policy import home_policy_write
from utils.executors import MonitoredThreadPoolExecutor, submit_with_context
from utils.other import endpoints

pytestmark = pytest.mark.usefixtures('isolated_episode_capture')


NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
UID = 'round3-synthetic'


@pytest.fixture
def client(monkeypatch):
    for key in ('EPISODES_ENABLED', 'EPISODES_LOG_ENABLED', 'EPISODES_HOME_ROWS_ENABLED'):
        monkeypatch.setenv(key, 'on')
    monkeypatch.setenv('EPISODES_PERCENT', '100')
    monkeypatch.setenv('EPISODES_LOG_READ_PERCENT', '100')
    return StrictFirestore()


def owner(client):
    path = ('users', UID, 'episode_log_state', 'owner')
    client.rows[path] = dict(cursor=0, next_seq=0, home_version=1, home_rows_ready=True, backfill_complete=True)
    return path


def test_neighboring_fixed_candidate_keeps_members_in_home(client, monkeypatch):
    from tests.unit.episode_log_support.oracle import Oracle
    from utils.episodes import home_read
    from utils.episodes.log.codec import loads
    from utils.encryption import decrypt

    with Oracle(UID) as oracle:
        client = oracle.store
        fixed = dict(
            id='fixed',
            status='closed',
            close_reason='user',
            state_version=1,
            started_at=NOW,
            last_activity_at=NOW + timedelta(minutes=10),
            closed_at=NOW + timedelta(minutes=10),
            recorded_end=NOW + timedelta(minutes=10),
            conversation_ids=['existing'],
            member_activity={'existing': NOW + timedelta(minutes=10)},
            sources=['omi'],
        )
        client.rows[('users', UID, 'episodes', 'fixed')] = fixed
        oracle.attach('late', NOW + timedelta(minutes=20), NOW + timedelta(minutes=21))
        members = {
            'existing': dict(
                status='completed',
                started_at=NOW,
                discarded=False,
                structured={'title': 'Existing member', 'emoji': '🗒️'},
            )
        }
        monkeypatch.setattr(home_read, 'read_members', lambda *a, **kw: members)
        monkeypatch.setattr(worker, 'wake', lambda *a: None)
        at = store.state(UID, firestore_client=client)['drain_at']
        assert worker.drain(UID, firestore_client=client, now=at) == 'drained'
        view = client.rows[('users', UID, 'episode_views', 'fixed')]
        assert view['conversation_ids'] == ['existing']
        assert view['member_activity'] == fixed['member_activity']
        home = loads(decrypt(view['home_payload'], UID))
        assert home['members'][0]['id'] == 'existing'
        assert home['members'][0]['title'] == 'Existing member'


@pytest.mark.parametrize('failure', ['capture', 'overflow', 'policy_entry', 'policy_refresh'])
def test_dropped_work_home_100_uses_legacy_until_full_repair(client, monkeypatch, failure):
    owner(client)
    assert reads.ready(UID, firestore_client=client)
    if failure == 'capture':
        monkeypatch.setattr(store, 'append', Mock(side_effect=RuntimeError('outage')))
        intent = capture.DeferredCapture(client, UID)
        intent.stage([{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}])
        intent.flush()
    elif failure == 'overflow':
        monkeypatch.setattr(capture, 'submit', Mock(side_effect=RuntimeError('queue full')))
        capture.dispatch(lambda: None, uid=UID, client=client)
    else:
        responses = [RuntimeError('entry')] if failure == 'policy_entry' else [None, RuntimeError('refresh')]
        monkeypatch.setattr(store, 'policy_barrier', Mock(side_effect=responses))
        writer = Mock(return_value='committed')

        @home_policy_write(firestore_client=lambda: client)
        def edit(uid, conversation_id):
            return writer()

        assert edit(UID, 'c') == 'committed'
        writer.assert_called_once()
    dirty = store.state(UID, firestore_client=client)
    assert dirty['capture_dirty'] and not reads.ready(UID, firestore_client=client)
    # Exercise the actual Home route: at 100%, readiness decides the namespace.
    monkeypatch.setattr(api, '_admitted', lambda *a: True)
    real_ready = reads.ready
    monkeypatch.setattr(reads, 'ready', lambda uid: real_ready(uid, firestore_client=client))
    legacy = Mock(return_value=([], None))
    log = Mock(return_value=([], [], None))
    monkeypatch.setattr(api.home_read, 'list_episode_window', legacy)
    monkeypatch.setattr(api.home_read, 'project_episodes', lambda *a: [])
    monkeypatch.setattr(reads, 'list_window', log)
    monkeypatch.setattr(worker, 'sample_read', lambda *a: None)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[endpoints.get_current_user_uid] = lambda: UID
    http = TestClient(app)
    params = {'from': NOW.isoformat(), 'to': NOW.isoformat()}
    response = http.get('/v1/episodes', params=params)
    assert response.status_code == 200 and legacy.called and not log.called
    # Ordinary publication must not clear the gap, even at a caught-up cursor.
    claim = store.claim(UID, firestore_client=client, now=dirty['drain_at'])
    store.publish(UID, claim, 0, {}, {}, {}, firestore_client=client, now=dirty['drain_at'])
    assert store.state(UID, firestore_client=client)['capture_dirty']
    # Full reconciliation only; emulator tests exercise its real collection reads.
    monkeypatch.setattr(reconcile, 'snapshot', lambda *a: (Fold(UID), (), ()))
    monkeypatch.setattr(worker, 'wake', lambda *a: None)
    at = store.state(UID, firestore_client=client)['drain_at'] + timedelta(minutes=26)
    assert worker.drain(UID, firestore_client=client, now=at) == 'drained'
    assert not store.state(UID, firestore_client=client).get('capture_dirty')
    legacy.reset_mock()
    response = http.get('/v1/episodes', params=params)
    assert response.status_code == 200 and log.called and not legacy.called


def test_new_gap_fences_already_claimed_full_repair(client):
    owner(client)
    store.invalidate(UID, firestore_client=client, now=NOW)
    claim = store.claim(UID, firestore_client=client, now=NOW)
    store.invalidate(UID, firestore_client=client, now=NOW)
    with pytest.raises(store.LostLease):
        store.publish(UID, claim, 0, {}, {}, {}, repaired=True, firestore_client=client, now=NOW)
    assert store.state(UID, firestore_client=client)['capture_dirty']


@pytest.mark.parametrize('kind', ['capture', 'policy_refresh'])
def test_serving_returns_while_background_io_is_blocked(client, monkeypatch, kind):
    owner(client)
    entered, release = Event(), Event()
    pool = MonitoredThreadPoolExecutor(name='episode-latency-proof', max_workers=1, max_queue_size=1)
    monkeypatch.setattr(capture, 'submit', lambda fn: submit_with_context(pool, fn))

    def blocked(*args, **kwargs):
        if kind == 'capture' or not kwargs.get('entering'):
            entered.set()
            assert release.wait(5), 'test failed to release background worker'

    monkeypatch.setattr(store, 'append', blocked)
    monkeypatch.setattr(store, 'policy_barrier', blocked)
    try:
        if kind == 'capture':
            ref = store.root(client, UID).collection('conversations').document('c')

            @firestore.transactional
            def edit(transaction):
                intent = store.prepare(transaction, client, UID)
                transaction.set(ref, {'committed': True})
                intent.stage([{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}])
                return 'committed'

            assert edit(client.transaction()) == 'committed'
        else:

            @home_policy_write(firestore_client=lambda: client)
            def edit(uid, conversation_id):
                return 'committed'

            assert edit(UID, 'c') == 'committed'
        assert entered.wait(2) and not release.is_set()
    finally:
        release.set()
        pool.shutdown(wait=True)


def test_capture_default_off_and_inactive_ttl_refuses_all_fact_writers(client, monkeypatch):
    monkeypatch.delenv('EPISODES_LOG_ENABLED')
    assert not config.enabled(UID)
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'true')
    monkeypatch.setattr(retention, 'active', lambda client: False)
    calls = [
        lambda: store.append(UID, 'k', [], firestore_client=client),
        lambda: store.policy_barrier(UID, 'c', 't', entering=True, firestore_client=client),
        lambda: store.finish_backfill(UID, firestore_client=client),
        lambda: store.recover_policy_barriers(UID, firestore_client=client),
    ]
    for call in calls:
        with pytest.raises(RuntimeError, match='ttl_not_active'):
            call()
    assert not client.rows


def test_drain_rechecks_kill_before_publish(client, monkeypatch):
    store.append(UID, 'k', [], firestore_client=client, now=NOW)
    monkeypatch.setattr(store, 'fact_page', lambda *a, **kw: [])
    monkeypatch.setattr(store, 'read_batch', lambda *a, **kw: ([], 1))
    admitted = iter([True, False])
    monkeypatch.setattr(config, 'enabled', lambda uid: next(admitted))
    publish = Mock()
    monkeypatch.setattr(store, 'publish', publish)
    assert worker.drain(UID, firestore_client=client, now=NOW + timedelta(minutes=3)) == 'disabled'
    publish.assert_not_called()
    assert store.state(UID, firestore_client=client).get('cursor', 0) == 0


REAL_ACTIVE = retention.active
REAL_GUARD = retention.guard


def test_ttl_check_is_cached_and_unknown_fails_closed(monkeypatch):
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(retention, 'active', REAL_ACTIVE)
    monkeypatch.setattr(retention, '_cache', {})
    clock = [0]
    monkeypatch.setattr(retention.time, 'monotonic', lambda: clock[0])
    lookup = Mock(side_effect=[True, False, RuntimeError('admin unavailable')])
    monkeypatch.setattr(retention, 'ttl_active', lookup)
    client = SimpleNamespace(project='demo', _database='(default)')
    assert retention.active(client) and retention.active(client)
    assert lookup.call_count == 1
    clock[0] = 61
    assert not retention.active(client)
    clock[0] = 122
    assert not retention.active(client)


def test_periodic_guard_logs_and_measures_facts_without_ttl(monkeypatch, caplog):
    from utils.episodes.log.metrics import FACTS_WITHOUT_TTL

    monkeypatch.setattr(retention, '_guard_until', {})
    monkeypatch.setattr(retention, 'guard', REAL_GUARD)
    monkeypatch.setattr(retention, 'active', lambda client: False)
    client = Mock(project='demo', _database='(default)')
    client.collection_group.return_value.select.return_value.limit.return_value.stream.return_value = iter([{}])
    retention.guard(client)
    assert FACTS_WITHOUT_TTL._value.get() == 1
    assert 'facts_without_active_ttl' in caplog.text
    retention.guard(client)
    client.collection_group.assert_called_once_with('episode_facts')


@pytest.mark.parametrize('active', [False, True])
def test_flag_on_precondition_checks_customer_data_ttl_before_flag_write(monkeypatch, active):
    from scripts import omi_flags as cli

    flag_client = Mock()
    monkeypatch.setattr(cli, '_client', lambda args: flag_client)
    monkeypatch.setattr(cli.store, 'read_all', lambda client: ({}, {}))
    write = Mock()
    monkeypatch.setattr(cli, '_write', write)
    lookup = Mock(return_value=active)
    monkeypatch.setattr(retention, 'ttl_active', lookup)
    args = ['set', 'EPISODES_LOG_ENABLED', '--active', '--rollout', '100', '--yes', '--reason', 'synthetic']
    assert cli.main(args) == 2  # No customer data project: no write or admin call.
    lookup.assert_not_called()
    assert cli.main(args + ['--episode-data-project', 'demo-data']) == (0 if active else 2)
    lookup.assert_called_once_with('demo-data', '(default)')
    assert write.call_count == int(active)


def test_real_bounded_executor_overflow_marks_owner_dirty_without_waiting(client, monkeypatch):
    owner(client)
    entered, release = Event(), Event()
    pool = MonitoredThreadPoolExecutor(name='episode-overflow-proof', max_workers=1, max_queue_size=0)
    monkeypatch.setattr(capture, 'submit', lambda fn: submit_with_context(pool, fn))

    def blocked():
        entered.set()
        assert release.wait(5)

    try:
        capture.dispatch(blocked, uid=UID, client=client)
        assert entered.wait(2)
        work = Mock()
        capture.dispatch(work, uid=UID, client=client)
        work.assert_not_called()
        assert store.state(UID, firestore_client=client)['capture_dirty']
        assert reads.ready(UID, firestore_client=client) is None
    finally:
        release.set()
        pool.shutdown(wait=True)


def test_failed_policy_entry_cannot_be_repaired_before_original_writer_finishes(client, monkeypatch):
    owner(client)
    barrier = store.policy_barrier

    def fail_entry(*args, **kwargs):
        if kwargs['entering']:
            raise RuntimeError('entry append failed')
        return barrier(*args, **kwargs)

    monkeypatch.setattr(store, 'policy_barrier', fail_entry)

    @home_policy_write(firestore_client=lambda: client)
    def edit(uid, conversation_id):
        row = store.state(uid, firestore_client=client)
        assert row['capture_dirty'] and row['policy_barriers']
        claimed = store.claim(uid, firestore_client=client, now=row['drain_at'])
        with pytest.raises(store.LostLease, match='reconcile_changed'):
            store.publish(uid, claimed, 0, {}, {}, {}, repaired=True, firestore_client=client, now=row['drain_at'])
        return 'committed'

    assert edit(UID, 'c') == 'committed'
    row = store.state(UID, firestore_client=client)
    assert row['capture_dirty'] and not row['policy_barriers']
    assert reads.ready(UID, firestore_client=client) is None
