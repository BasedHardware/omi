"""Durable UID ownership and bounded recovery for backfill Cloud Tasks."""

import copy
import threading
import time
from unittest.mock import MagicMock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
import fakeredis
from google.cloud import firestore

from database import sync_jobs
from database import sync_backfill_sequencer as registry
from database.sync_jobs import is_sync_job_stale
from utils.sync import uid_sequencer
from utils.sync import backfill_cutover
from utils import cloud_tasks
from scripts import repair_sync_backfill_owners as repair_script


class _Snapshot:
    def __init__(self, path, data):
        self.id = path[-1]
        self.exists = data is not None
        self._data = copy.deepcopy(data)

    def to_dict(self):
        return copy.deepcopy(self._data)


class _Ref:
    def __init__(self, client, path):
        self.client = client
        self.path = path
        self.id = path[-1]

    def get(self, transaction=None):
        if transaction is not None:
            assert not transaction.wrote, "read after transaction write"
        return _Snapshot(self.path, self.client.docs.get(self.path))

    def collection(self, name):
        return _Collection(self.client, self.path + (name,))

    def update(self, data):
        self.client.write(self.path, data, merge=True)


class _Query:
    def __init__(self, client, path, field=None, maximum=None, order=None, limit=None, equals=None):
        self.client, self.path = client, path
        self.field, self.maximum, self.order, self.maximum_results, self.equals = field, maximum, order, limit, equals

    def where(self, field=None, op=None, maximum=None, *, filter=None):
        if filter is not None:
            field, op, maximum = filter.field_path, filter.op_string, filter.value
        if op == '==':
            return _Query(
                self.client, self.path, self.field, self.maximum, self.order, self.maximum_results, (field, maximum)
            )
        assert op == '<='
        return _Query(self.client, self.path, field, maximum, self.order, self.maximum_results, self.equals)

    def order_by(self, field, direction='ASCENDING'):
        return _Query(
            self.client, self.path, self.field, self.maximum, (field, direction), self.maximum_results, self.equals
        )

    def limit(self, count):
        return _Query(self.client, self.path, self.field, self.maximum, self.order, count, self.equals)

    def select(self, fields):
        return self

    def start_after(self, snapshot):
        self.cursor_id = snapshot.id
        return self

    def stream(self, transaction=None):
        if transaction is not None:
            assert not transaction.wrote, "query after transaction write"
        rows = [(path, value) for path, value in self.client.docs.items() if path[:-1] == self.path]
        if self.field:
            rows = [(path, value) for path, value in rows if self.field in value and value[self.field] <= self.maximum]
        if self.equals:
            rows = [(path, value) for path, value in rows if value.get(self.equals[0]) == self.equals[1]]
        order = self.order[0] if self.order else self.field
        rows.sort(
            key=lambda row: (row[1].get(order), row[0]) if order else row[0],
            reverse=bool(self.order and self.order[1] == 'DESCENDING'),
        )
        if getattr(self, 'cursor_id', None):
            rows = [(path, value) for path, value in rows if path[-1] > self.cursor_id]
        if self.maximum_results is not None:
            rows = rows[: self.maximum_results]
        return [_Snapshot(path, value) for path, value in rows]


class _Collection(_Query):
    def document(self, name):
        return _Ref(self.client, self.path + (name,))


class _Transaction:
    def __init__(self, client):
        self.client = client
        self.wrote = False

    def set(self, ref, data, merge=False):
        self.wrote = True
        self.client.write(ref.path, data, merge=merge)

    def update(self, ref, data):
        self.wrote = True
        self.client.write(ref.path, data, merge=True)

    def delete(self, ref):
        self.wrote = True
        self.client.docs.pop(ref.path, None)


class _Firestore:
    def __init__(self):
        self.docs = {}
        self.lock = threading.RLock()

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self, **kwargs):
        return _Transaction(self)

    def write(self, path, data, *, merge):
        value = copy.deepcopy(self.docs.get(path, {})) if merge else {}
        for key, field_value in data.items():
            if field_value is firestore.DELETE_FIELD:
                value.pop(key, None)
            else:
                value[key] = copy.deepcopy(field_value)
        self.docs[path] = value


@pytest.fixture
def db(monkeypatch):
    client = _Firestore()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'off')
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'test-secret')
    monkeypatch.delenv('SYNC_BACKFILL_ORDER', raising=False)
    monkeypatch.delenv('SYNC_BACKFILL_ORDER_PERCENT', raising=False)
    monkeypatch.delenv('SYNC_BACKFILL_ORDER_UID_ALLOWLIST', raising=False)
    monkeypatch.setattr(backfill_cutover, 'r', fakeredis.FakeRedis())

    def transactional(fn):
        def run(transaction):
            with client.lock:
                return fn(transaction)

        return run

    monkeypatch.setattr(registry.firestore, 'transactional', transactional)
    monkeypatch.setattr(registry, 'get_firestore_client', lambda: client)
    return client


def test_nonprod_delivery_guard_is_pure_before_any_redis_read(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(
        uid_sequencer, 'get_sync_ledger_fence_mode', MagicMock(side_effect=AssertionError('Redis read'))
    )
    assert uid_sequencer.production_fence_mode() is None
    assert uid_sequencer.foreign_delivery({'lane': 'backfill', 'job_id': 'legacy'})
    assert uid_sequencer.foreign_delivery({'lane': 'fresh', 'sequencer_epoch': 3})
    assert not uid_sequencer.foreign_delivery({'lane': 'fresh'})
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert not uid_sequencer.foreign_delivery({'lane': 'backfill', 'sequencer_epoch': 3})


def test_dev_cannot_read_or_claim_production_registry(db, monkeypatch):
    _register('shared-user', 'prod-job', 0, db=db)
    before = copy.deepcopy(db.docs)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert not registry.enabled()
    assert not uid_sequencer.kick('shared-user')
    assert uid_sequencer.sweep() == {'disabled': 1}
    for operation in (
        lambda: registry.get_owner('shared-user', firestore_client=db),
        lambda: registry.has_pending('shared-user', firestore_client=db),
        lambda: registry.repair_owner('shared-user', firestore_client=db),
        lambda: registry.claim_next('shared-user', firestore_client=db),
        lambda: registry.begin_job('shared-user', 'prod-job', 1, firestore_client=db),
        lambda: registry.finish_job('shared-user', 'prod-job', 1, 'failed', firestore_client=db),
    ):
        with pytest.raises(RuntimeError, match='production-only'):
            operation()
    assert db.docs == before


def test_dev_cutover_keys_cannot_stall_prod_and_missing_mode_is_inert(db, monkeypatch):
    backfill_cutover.note_direct_admission('shared-user', 'prod-direct')
    assert backfill_cutover.quiet_remaining('shared-user')[0] > 0
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert backfill_cutover.quiet_remaining('shared-user') == (0, '')
    backfill_cutover.note_direct_admission('shared-user', 'dev-direct')
    assert backfill_cutover.quiet_remaining('shared-user')[1] == 'dev-direct'
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert backfill_cutover.quiet_remaining('shared-user')[1] == 'prod-direct'
    assert backfill_cutover.quiet_remaining('another-user') == (0, '')


NOW = datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc)


def _register(uid, job_id, seconds, *, db, now=NOW):
    return registry.register_job(
        uid, job_id, {'uid': uid, 'job_id': job_id}, now.timestamp() + seconds, firestore_client=db, now=now
    )


def test_waiting_jobs_run_oldest_first_and_terminal_failure_releases(db):
    _register('a', 'new', 300, db=db)
    assert registry.is_registered('a', 'new', firestore_client=db)
    _register('a', 'old', 100, db=db)
    _register('a', 'middle', 200, db=db)
    assert registry.has_pending('a', firestore_client=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first['job_id'] == 'old'
    assert registry.claim_next('a', firestore_client=db, now=NOW) is None
    assert registry.begin_job('a', 'old', first['epoch'], firestore_client=db, now=NOW)
    assert registry.finish_job('a', 'old', first['epoch'], 'failed', firestore_client=db, now=NOW)
    assert not registry.finish_job('a', 'old', first['epoch'], 'failed', firestore_client=db, now=NOW)
    second = registry.claim_next('a', firestore_client=db, now=NOW)
    assert second['job_id'] == 'middle'
    assert registry.is_registered('a', 'middle', firestore_client=db)


@pytest.mark.parametrize('sequencer', ['on', 'off'])
def test_newest_selection_and_expected_head_fence(db, monkeypatch, sequencer):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', sequencer)
    for job_id, stamp in [('old', 100), ('newest', 300), ('middle', 200)]:
        _register('a', job_id, stamp, db=db)
    assert registry.pending_head('a')['job_id'] == 'newest'
    assert registry.claim_next('a', expected_job_id='old', now=NOW) is None
    selected = []
    for _ in range(3):
        claim = registry.claim_next('a', now=NOW)
        selected.append(claim['job_id'])
        assert registry.finish_job('a', claim['job_id'], claim['epoch'], 'completed', now=NOW)
    assert selected == ['newest', 'middle', 'old']


def test_explicit_oldest_produces_identical_claim_and_persisted_state(db, monkeypatch):
    monkeypatch.delenv('SYNC_BACKFILL_ORDER', raising=False)
    _register('a', 'new', 300, db=db)
    _register('a', 'old', 100, db=db)
    before = copy.deepcopy(db.docs)
    default_claim = registry.claim_next('a', now=NOW)
    default_state = copy.deepcopy(db.docs)
    db.docs = before
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'oldest')
    assert registry.claim_next('a', now=NOW) == default_claim
    assert db.docs == default_state


def test_claim_sees_earlier_capture_admitted_before_transaction(db, monkeypatch):
    _register('a', 'newer', 300, db=db)
    original_transactional = registry.firestore.transactional

    def insert_before_claim(fn):
        wrapped = original_transactional(fn)

        def run(transaction):
            db.write(
                (registry.PENDING_COLLECTION, 'older'),
                {
                    'job_id': 'older',
                    'uid': 'a',
                    'payload': {'uid': 'a', 'job_id': 'older'},
                    'sort_at': NOW + timedelta(seconds=100),
                    'accepted_at': NOW,
                },
                merge=False,
            )
            return wrapped(transaction)

        return run

    monkeypatch.setattr(registry.firestore, 'transactional', insert_before_claim)
    assert registry.claim_next('a', firestore_client=db, now=NOW)['job_id'] == 'older'


def test_contention_only_one_active_and_other_uid_can_dispatch(db):
    for index in range(30):
        _register('heavy', f'h{index}', index, db=db)
    _register('light', 'l0', 0, db=db)
    with ThreadPoolExecutor(max_workers=12) as pool:
        claims = list(pool.map(lambda _: registry.claim_next('heavy', firestore_client=db, now=NOW), range(12)))
    assert len([claim for claim in claims if claim]) == 1
    assert (
        len(
            [
                path
                for path, value in db.docs.items()
                if path[0] == registry.PENDING_COLLECTION and value['uid'] == 'heavy'
            ]
        )
        == 29
    )
    assert registry.claim_next('light', firestore_client=db, now=NOW)['job_id'] == 'l0'


@pytest.mark.parametrize('order', ['oldest', 'newest'])
def test_preparation_is_read_only_ordered_and_cannot_bypass_execution_head(db, monkeypatch, order):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', order)
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY', '4')
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'on')
    for index in range(10):
        _register('a', f'job-{index}', index, db=db)
    claim = registry.claim_next('a', now=NOW)
    assert registry.preparation_candidates('a', claim['job_id'], claim['epoch']) == []
    assert registry.begin_job('a', claim['job_id'], claim['epoch'], now=NOW)
    before = copy.deepcopy(db.docs)
    candidates = registry.preparation_candidates('a', claim['job_id'], claim['epoch'])
    expected = ['job-1', 'job-2', 'job-3'] if order == 'oldest' else ['job-8', 'job-7', 'job-6']
    assert [job['job_id'] for job in candidates] == expected
    assert db.docs == before
    # Even a fully warmed future job cannot begin, finish, or steal the head.
    assert not registry.begin_job('a', candidates[0]['job_id'], claim['epoch'], now=NOW)
    assert not registry.finish_job('a', candidates[0]['job_id'], claim['epoch'], 'completed', now=NOW)
    assert registry.claim_next('a', now=NOW) is None
    assert registry.finish_job('a', claim['job_id'], claim['epoch'], 'completed', now=NOW)
    assert registry.claim_next('a', now=NOW)['job_id'] == expected[0]


def test_preparation_stale_epoch_and_small_backlog_are_inert(db, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY', '4')
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'on')
    for index in range(10):
        _register('a', f'job-{index}', index, db=db)
    claim = registry.claim_next('a', now=NOW)
    assert registry.begin_job('a', claim['job_id'], claim['epoch'], now=NOW)
    replacement = registry.redrive_job('a', claim['job_id'], claim['epoch'], now=NOW + timedelta(hours=1))
    assert registry.begin_job('a', replacement['job_id'], replacement['epoch'], now=NOW + timedelta(hours=1))
    assert registry.preparation_candidates('a', claim['job_id'], claim['epoch']) == []
    assert len(registry.preparation_candidates('a', replacement['job_id'], replacement['epoch'])) == 3
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'off')
    assert registry.preparation_candidates('a', replacement['job_id'], replacement['epoch']) == []
    # Restoring serial preparation does not release/fence a running job.
    assert registry.renew_job('a', replacement['job_id'], replacement['epoch'], now=NOW + timedelta(hours=1))
    assert registry.claim_next('a', now=NOW) is None
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'on')
    _register('b', 'b-head', 0, db=db)
    _register('b', 'b-next', 1, db=db)
    other = registry.claim_next('b', now=NOW)
    assert registry.begin_job('b', other['job_id'], other['epoch'], now=NOW)
    assert registry.preparation_candidates('b', other['job_id'], other['epoch']) == []


def test_expired_lease_redrive_is_fenced_and_duplicate_delivery_is_inert(db):
    _register('a', 'job', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    assert registry.renew_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=4))
    assert (
        registry.redrive_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=31)) is None
    )
    second = registry.redrive_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=35))
    assert second['epoch'] == first['epoch'] + 1
    assert not registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=35))
    assert not registry.finish_job(
        'a', 'job', first['epoch'], 'failed', firestore_client=db, now=NOW + timedelta(minutes=35)
    )
    assert registry.begin_job('a', 'job', second['epoch'], firestore_client=db, now=NOW + timedelta(minutes=35))


def test_sweeper_replaces_lost_dispatch_then_releases_terminal_job(db, monkeypatch):
    _register('a', 'lost', 0, db=db)
    _register('a', 'next', 1, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'queued'})
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    expired = NOW + timedelta(minutes=6)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'lease_expired'
    assert dispatched[0]['job_id'] == 'lost'
    assert dispatched[0]['epoch'] == first['epoch']
    assert dispatched[0]['dispatch_attempt'] == 1
    assert registry.finish_job('a', 'lost', dispatched[0]['epoch'], 'failed', firestore_client=db, now=expired)
    assert uid_sequencer.kick('a')
    assert dispatched[-1]['job_id'] == 'next'


@pytest.mark.parametrize('flag', ['on', 'off'])
@pytest.mark.parametrize('delivery', ['original', 'replacement'])
def test_delivery_after_running_lease_survives_repeated_dispatch_redrives(db, monkeypatch, flag, delivery):
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', flag)
    monkeypatch.setenv('SYNC_BACKFILL_ROUTING_ENABLED', 'false')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://sync.example.com/v2/sync-jobs/run')
    monkeypatch.setattr(registry, '_now', lambda: NOW)
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'queued'})
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))
    tasks = {}

    def enqueue(_queue, _url, task_id, payload, **_kwargs):
        # Model named-task dedup, including names retained after task deletion.
        tasks.setdefault(task_id, copy.deepcopy(payload))

    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    payload = {key: None for key in cloud_tasks.SYNC_JOB_TASK_PAYLOAD_KEYS}
    payload.update(uid='a', job_id='delayed', lane='backfill')
    registry.register_job('a', 'delayed', payload, NOW.timestamp(), now=NOW)
    _register('a', 'next', 1, db=db)
    first = registry.claim_next('a', now=NOW)
    uid_sequencer._dispatch(first)
    original_name = f"delayed-s{first['epoch']}"
    # No delivery for two hours. Each sweep previously invalidated every task
    # already in the queue, even well before the 30-minute running lease.
    for minute in range(6, 121, 6):
        current = NOW + timedelta(minutes=minute)
        assert uid_sequencer.reconcile_uid('a', registry.get_owner('a'), now=current) == 'lease_expired'
        assert registry.get_owner('a')['active_epoch'] == first['epoch']
        assert registry.claim_next('a', now=current) is None
    assert len(tasks) == 21
    replacement_name = f"{original_name}-d20"
    assert tasks[replacement_name] == tasks[original_name]
    # Retrying an uncertain acknowledgement is idempotent for that attempt.
    owner = registry.get_owner('a')
    uid_sequencer._dispatch({**first, 'dispatch_attempt': owner['dispatch_attempt']})
    assert len(tasks) == 21
    delivered = tasks[original_name if delivery == 'original' else replacement_name]
    current = NOW + timedelta(seconds=registry.LEASE_SECONDS * 4 + 1)
    assert registry.begin_job('a', 'delayed', delivered['sequencer_epoch'], now=current)
    assert registry.get_owner('a')['lease_expires_at'] == current + timedelta(seconds=registry.LEASE_SECONDS)
    # A stale sweeper snapshot cannot redrive a worker that just began.
    assert registry.redrive_job('a', 'delayed', first['epoch'], now=current) is None
    assert registry.finish_job('a', 'delayed', first['epoch'], 'completed', now=current)
    for task in tasks.values():
        assert not registry.begin_job('a', 'delayed', task['sequencer_epoch'], now=current)
    assert registry.claim_next('a', now=current)['job_id'] == 'next'


def test_flag_switch_does_not_change_persisted_owner_or_legacy_task(db, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'on')
    assert registry.enabled()
    _register('a', 'sequenced', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'off')
    assert not registry.enabled()
    assert registry.begin_job('a', 'sequenced', first['epoch'], firestore_client=db, now=NOW)
    assert registry.finish_job('a', 'sequenced', first['epoch'], 'completed', firestore_client=db, now=NOW)
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'on')
    assert registry.claim_next('legacy', firestore_client=db, now=NOW) is None


def test_polling_cannot_stale_finalize_queued_or_running_sequenced_job():
    old = NOW.timestamp() - 3600
    for status in ('queued', 'processing'):
        assert not is_sync_job_stale(
            {'status': status, 'dispatch_mode': 'sequenced', 'created_at': old, 'updated_at': old},
            now=NOW.timestamp(),
        )


def test_burst_admission_also_creates_durable_idle_owner(db):
    with ThreadPoolExecutor(max_workers=20) as pool:
        assert all(pool.map(lambda index: _register('heavy', f'job-{index}', index, db=db), range(100)))
    assert not registry.get_owner('heavy', firestore_client=db).get('active_job_id')
    assert len(db.docs) == 101


def test_cutover_guard_honors_existing_deadline_and_per_uid_direct_work(db, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'on')
    monkeypatch.setattr(backfill_cutover.time, 'time', lambda: NOW.timestamp())
    backfill_cutover.r.set(backfill_cutover.LEGACY_QUIET_KEY, int(NOW.timestamp()) + 1800)
    _register('heavy', 'sequenced', 0, db=db)
    dispatched = []
    wakes = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(
        uid_sequencer, '_enqueue_wake', lambda uid, uid_hash, deadline: wakes.append((uid, uid_hash, deadline))
    )
    assert not uid_sequencer.kick('heavy')
    assert not dispatched
    assert wakes[0][0] == 'heavy'
    assert wakes[0][1] != 'heavy'
    monkeypatch.setattr(backfill_cutover.time, 'time', lambda: NOW.timestamp() + 1801)
    assert uid_sequencer.kick('heavy')
    assert dispatched[0]['job_id'] == 'sequenced'
    backfill_cutover.note_direct_admission('another', 'direct-job')
    _register('another', 'next', 0, db=db)
    assert not uid_sequencer.kick('another')


def test_pending_sweep_rotates_heavy_uid_and_reaches_light_uid(db, monkeypatch):
    for index in range(101):
        _register('heavy', f'a-{index:03d}', index, db=db)
    _register('light', 'z-light', 0, db=db)
    calls = []
    monkeypatch.setattr(uid_sequencer, 'kick', lambda uid, **_kwargs: calls.append(uid) or False)
    monkeypatch.setattr(registry, 'due_owners', lambda **_kwargs: [])
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: None)
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    # The first bounded page is dominated by the heavy UID. Deferred entries
    # leave the next page available to another UID on the next Scheduler tick.
    uid_sequencer.sweep(limit=100)
    uid_sequencer.sweep(limit=100)
    assert 'light' in calls


def test_flag_off_drain_waits_for_new_direct_work_of_same_uid(db, monkeypatch):
    _register('heavy', 'sequenced-waiting', 0, db=db)
    backfill_cutover.note_direct_admission('heavy', 'direct-job')
    backfill_cutover.refresh_direct_run('heavy', 'direct-job')
    assert backfill_cutover.direct_remaining_for_uid('heavy')[0] > 1700
    wakes = []
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', lambda *args: wakes.append(args))
    assert not uid_sequencer.kick('heavy')
    assert wakes and wakes[0][0] == 'heavy'
    assert not registry.get_owner('heavy', firestore_client=db).get('active_job_id')


def test_cutover_wake_uses_existing_sync_queue_and_oidc_route(monkeypatch):
    calls = []
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://backend-sync.example/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync')
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', lambda *args, **kwargs: calls.append((args, kwargs)))
    cloud_tasks.enqueue_sync_uid_wake('private-uid', 'hash123', 12345)
    args, kwargs = calls[0]
    assert args[:3] == ('sync', 'https://backend-sync.example/v2/sync-backfill-sequencer/wake', 'sbu-hash123-12345')
    assert args[3] == {'uid': 'private-uid'}
    assert kwargs['schedule_at'] == 12345


def test_named_wake_task_is_scheduled_for_cutover_deadline(monkeypatch):
    fake = MagicMock()
    fake.queue_path.return_value = 'projects/p/locations/l/queues/sync'
    fake.task_path.return_value = 'projects/p/locations/l/queues/sync/tasks/wake'
    monkeypatch.setattr(cloud_tasks, '_get_tasks_client', lambda: fake)
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'p')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'l')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.test')
    cloud_tasks.enqueue_named_task('sync', 'https://backend-sync.example/wake', 'wake', {'uid': 'u'}, schedule_at=12345)
    task = fake.create_task.call_args.kwargs['task']
    assert task.schedule_time.timestamp() == 12345


@pytest.fixture
def retirement(db, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'true')
    monkeypatch.setattr(uid_sequencer, 'sync_job_key_exists', lambda job_id: job_id == 'live')
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda job_id: 'retirement-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', MagicMock())
    return db


def test_expired_head_is_retired_then_live_job_claimed(retirement, monkeypatch, caplog):
    _register('a', 'expired', 0, db=retirement)
    _register('a', 'live', 1, db=retirement)
    with caplog.at_level('INFO'):
        claim = uid_sequencer._claim_next('a')
    assert claim['job_id'] == 'live'
    assert (registry.PENDING_COLLECTION, 'expired') not in retirement.docs
    assert 'event=sync_backfill_expired_retired' in caplog.text
    assert uid_sequencer.release_job_run_lock.call_count == 2
    uid_sequencer.release_job_run_lock.assert_any_call('expired', 'retirement-token')


@pytest.mark.parametrize('sequencer', ['on', 'off'])
def test_newest_sweep_retires_old_tail_without_touching_active_owner(retirement, monkeypatch, sequencer):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', sequencer)
    _register('a', 'expired', 0, db=retirement)
    _register('a', 'live', 100, db=retirement)
    retirement.docs[('users', 'a', 'sync_content_ledger', 'content')] = {'job_id': 'expired', 'status': 'processing'}
    retirement.docs[(registry.PENDING_COLLECTION, 'expired')]['payload']['content_id'] = 'content'
    claim = registry.claim_next('a', now=NOW)
    assert claim['job_id'] == 'live'
    assert registry.begin_job('a', 'live', claim['epoch'], now=NOW)
    owner = registry.get_owner('a')
    # Keep the active owner outside this tick; the tail cleanup uses only the
    # pending page even while the UID is busy with recent work.
    monkeypatch.setattr(registry, 'due_owners', lambda **kwargs: [])
    dispatch = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    assert uid_sequencer.sweep()['expired_retired'] == 1
    assert registry.get_owner('a') == owner
    assert (registry.PENDING_COLLECTION, 'expired') not in retirement.docs
    ledger = retirement.docs[('users', 'a', 'sync_content_ledger', 'content')]
    assert ledger['status'] == 'retryable' and 'job_id' not in ledger
    dispatch.assert_not_called()


@pytest.mark.parametrize('protected', ['key_present', 'run_lock', 'bound_ledger'])
def test_newest_tail_retirement_requires_exact_absence_and_unbound_ledger(retirement, monkeypatch, protected):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    _register('a', 'expired', 0, db=retirement)
    _register('a', 'live', 100, db=retirement)
    registry.claim_next('a', now=NOW)
    before_owner = registry.get_owner('a')
    monkeypatch.setattr(registry, 'due_owners', lambda **kwargs: [])
    if protected == 'key_present':
        monkeypatch.setattr(uid_sequencer, 'sync_job_key_exists', lambda job_id: True)
    elif protected == 'run_lock':
        monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda job_id: None)
    else:
        retirement.docs[(registry.PENDING_COLLECTION, 'expired')]['payload']['content_id'] = 'content'
        retirement.docs[('users', 'a', 'sync_content_ledger', 'content')] = {
            'job_id': 'expired',
            'status': 'processing',
            'ledger_run_epoch': 1,
        }
    uid_sequencer.sweep()
    assert (registry.PENDING_COLLECTION, 'expired') in retirement.docs
    assert registry.get_owner('a') == before_owner


def test_redis_failure_never_retires_or_claims(retirement, monkeypatch):
    _register('a', 'expired', 0, db=retirement)
    before = copy.deepcopy(retirement.docs)
    monkeypatch.setattr(uid_sequencer, 'sync_job_key_exists', MagicMock(side_effect=ConnectionError))
    with pytest.raises(ConnectionError):
        uid_sequencer._claim_next('a')
    assert retirement.docs == before


def test_present_key_and_held_run_lock_never_retire(retirement, monkeypatch):
    for job_id in ('live', 'locked'):
        _register(job_id, job_id, 0, db=retirement)
        monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda job: None)
        claim = uid_sequencer._claim_next(job_id)
        assert claim is None
        assert not registry.get_owner(job_id).get('active_job_id')
        assert registry.pending_head(job_id)['job_id'] == job_id
    uid_sequencer.release_job_run_lock.assert_not_called()


def test_redis_recheck_failure_releases_lock_and_preserves_pending(retirement, monkeypatch):
    _register('a', 'expired', 0, db=retirement)
    before = copy.deepcopy(retirement.docs)
    monkeypatch.setattr(uid_sequencer, 'sync_job_key_exists', MagicMock(side_effect=[False, ConnectionError()]))
    with pytest.raises(ConnectionError):
        uid_sequencer._claim_next('a')
    assert retirement.docs == before
    uid_sequencer.release_job_run_lock.assert_called_once()


def test_reappearing_job_is_not_retired(retirement, monkeypatch):
    _register('a', 'expired', 0, db=retirement)
    monkeypatch.setattr(uid_sequencer, 'sync_job_key_exists', MagicMock(side_effect=[False, True]))
    assert uid_sequencer._claim_next('a')['job_id'] == 'expired'
    assert registry.get_owner('a')['active_job_id'] == 'expired'


def test_retirement_loop_is_bounded_and_never_dispatches_expired_51st(retirement):
    for index in range(51):
        _register('a', f'old-{index:03}', index, db=retirement)
    assert uid_sequencer._claim_next('a') is None
    assert len(retirement.docs) == 2
    assert registry.pending_head('a')['job_id'] == 'old-050'
    assert not registry.get_owner('a').get('active_job_id')


@pytest.mark.parametrize(
    'claim,retired,released',
    [
        ({'status': 'processing', 'job_id': 'old'}, True, True),
        ({'status': 'processing', 'job_id': 'new'}, True, False),
        ({'status': 'completed', 'job_id': 'old'}, False, False),
        ({'status': 'processing', 'job_id': 'old', 'ledger_run_token': 'bound'}, False, False),
        ({'status': 'processing', 'job_id': 'old', 'ledger_run_epoch': 2}, False, False),
    ],
)
def test_retirement_only_releases_exact_unbound_claim(db, claim, retired, released):
    _register('a', 'old', 0, db=db)
    db.docs[(registry.PENDING_COLLECTION, 'old')]['payload']['content_id'] = 'content'
    path = ('users', 'a', 'sync_content_ledger', 'content')
    db.docs[path] = {**claim, 'partial_result': {'checkpoint': 'preserve'}}
    before = copy.deepcopy(db.docs[path])
    assert registry.retire_expired('a', 'old', firestore_client=db, now=NOW) is retired
    if released:
        assert db.docs[path]['status'] == 'retryable'
        assert 'job_id' not in db.docs[path]
        assert db.docs[path]['partial_result'] == before['partial_result']
    else:
        assert db.docs[path] == before
    assert ((registry.PENDING_COLLECTION, 'old') not in db.docs) is retired


def test_flag_off_keeps_claim_identity_and_skips_redis(db, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'false')
    _register('a', 'old', 0, db=db)
    monkeypatch.setattr(uid_sequencer, 'sync_job_key_exists', MagicMock(side_effect=AssertionError('Redis read')))
    claim = uid_sequencer._claim_next('a')
    assert claim['job_id'] == 'old' and claim['epoch'] == 1
    assert registry.get_owner('a')['active_state'] == 'dispatching'


def test_sweep_retires_missing_dispatching_owner_before_deadline(retirement, monkeypatch):
    _register('a', 'expired', 0, db=retirement)
    _register('a', 'live', 1, db=retirement)
    registry.claim_next('a', now=NOW)
    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    assert uid_sequencer.reconcile_uid('a', registry.get_owner('a'), now=NOW) == 'expired_retired'
    assert dispatched[0]['job_id'] == 'live'


def test_retirement_preserves_running_owner_and_stale_epoch(db):
    _register('a', 'old', 0, db=db)
    claim = registry.claim_next('a', now=NOW)
    assert not registry.retire_expired('a', 'old', epoch=claim['epoch'] + 1)
    assert registry.begin_job('a', 'old', claim['epoch'], now=NOW)
    assert not registry.retire_expired('a', 'old', epoch=claim['epoch'])
    assert registry.get_owner('a')['active_state'] == 'running'


def test_raw_job_existence_does_not_parse_corrupt_json(monkeypatch):
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    redis.set('sync_job:corrupt', b'{not-json')
    assert sync_jobs.sync_job_key_exists('corrupt')
    assert not sync_jobs.sync_job_key_exists('missing')


def test_competing_retirement_cannot_dispatch_an_expired_head(retirement, monkeypatch):
    _register('a', 'expired', 0, db=retirement)
    _register('a', 'live', 1, db=retirement)
    held = set()
    original_retire = registry.retire_expired
    interleaved = []

    def acquire(job_id):
        if job_id in held:
            return None
        held.add(job_id)
        return 'token'

    def retire(uid, job_id, **kwargs):
        # A competing kick arrives after the first claimant locked the head,
        # before its Firestore retirement transaction has committed.
        assert uid_sequencer._claim_next(uid) is None
        assert not registry.get_owner(uid).get('active_job_id')
        interleaved.append(job_id)
        return original_retire(uid, job_id, **kwargs)

    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', acquire)
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda job_id, token: held.remove(job_id))
    monkeypatch.setattr(registry, 'retire_expired', retire)
    assert uid_sequencer._claim_next('a')['job_id'] == 'live'
    assert interleaved == ['expired']
    assert not held


def test_claim_requires_the_same_head_as_the_redis_proof(db):
    _register('a', 'earlier', 0, db=db)
    _register('a', 'live', 10, db=db)
    before = copy.deepcopy(db.docs)
    assert registry.claim_next('a', expected_job_id='live', now=NOW) is None
    assert db.docs == before
    assert registry.claim_next('a', expected_job_id='earlier', now=NOW)['job_id'] == 'earlier'


def test_new_oldest_head_is_not_dispatched_without_its_redis_proof(retirement, monkeypatch):
    _register('a', 'live', 10, db=retirement)
    original_claim = registry.claim_next
    inserted = []

    def claim(uid, **kwargs):
        if not inserted:
            _register(uid, 'new-expired-head', 0, db=retirement)
            inserted.append(True)
        return original_claim(uid, **kwargs)

    monkeypatch.setattr(registry, 'claim_next', claim)
    # An earlier entry arrives after checking the live head's Redis key.
    assert uid_sequencer._claim_next('a') is None
    assert not registry.get_owner('a').get('active_job_id')
    assert registry.pending_head('a')['job_id'] == 'new-expired-head'
    # The next kick first proves/retire that expired head, then claims live.
    assert uid_sequencer._claim_next('a')['job_id'] == 'live'


@pytest.mark.parametrize(
    'ledger',
    [
        {'status': 'processing', 'job_id': 'old', 'ledger_run_token': 'bound'},
        {'status': 'processing', 'job_id': 'old', 'ledger_run_epoch': 1},
        {'status': 'completed', 'job_id': 'old'},
    ],
)
def test_refused_absent_head_is_never_reserved_or_woken(retirement, monkeypatch, ledger):
    _register('a', 'old', 0, db=retirement)
    retirement.docs[(registry.PENDING_COLLECTION, 'old')]['payload']['content_id'] = 'content'
    retirement.docs[('users', 'a', 'sync_content_ledger', 'content')] = ledger
    before = copy.deepcopy(retirement.docs)
    wake = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    assert uid_sequencer._claim_next('a') is None
    assert not uid_sequencer.kick('a')
    assert retirement.docs == before
    assert not registry.get_owner('a').get('active_job_id')
    wake.assert_not_called()


def test_51_expired_heads_schedule_one_continuation(retirement, monkeypatch):
    for index in range(51):
        _register('a', f'old-{index:03}', index, db=retirement)
    wake = MagicMock()
    dispatch = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    assert not uid_sequencer.kick('a')
    assert registry.pending_head('a')['job_id'] == 'old-050'
    assert not registry.get_owner('a').get('active_job_id')
    wake.assert_called_once()
    dispatch.assert_not_called()


def test_sweep_pending_retirement_counts_and_wakes_live_successor(retirement, monkeypatch, caplog):
    _register('a', 'expired', 0, db=retirement)
    _register('a', 'live', 1, db=retirement)
    wake = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    with caplog.at_level('INFO'):
        outcomes = uid_sequencer.sweep()
    assert outcomes['expired_retired'] == 1
    assert 'expired_retired=1' in caplog.text
    assert registry.pending_head('a')['job_id'] == 'live'
    wake.assert_called_once()


def test_continuation_wake_deduplicates_and_uses_a_future_bucket(retirement, monkeypatch):
    _register('a', 'live', 0, db=retirement)
    wake = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    monkeypatch.setattr(uid_sequencer.time, 'time', lambda: 1000)
    assert not uid_sequencer.kick('a', retire_limit=0)
    assert not uid_sequencer.kick('a', retire_limit=0)
    wake.assert_called_once_with('a', backfill_cutover.uid_hash('a'), 1005)
    monkeypatch.setattr(uid_sequencer.time, 'time', lambda: 1005)
    assert not uid_sequencer.kick('a', retire_limit=0)
    assert wake.call_count == 2
    assert wake.call_args.args[-1] == 1010


@pytest.mark.parametrize('locked', [False, True])
def test_empty_or_lock_held_never_wakes(retirement, monkeypatch, locked):
    if locked:
        _register('a', 'expired', 0, db=retirement)
        monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda job_id: None)
    wake = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    assert not uid_sequencer.kick('a')
    wake.assert_not_called()


def test_expected_head_fence_schedules_continuation(retirement, monkeypatch):
    _register('a', 'live', 10, db=retirement)
    original = registry.claim_next

    def claim(uid, **kwargs):
        _register(uid, 'earlier', 0, db=retirement)
        return original(uid, **kwargs)

    monkeypatch.setattr(registry, 'claim_next', claim)
    wake = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    assert not uid_sequencer.kick('a')
    assert registry.pending_head('a')['job_id'] == 'earlier'
    assert not registry.get_owner('a').get('active_job_id')
    wake.assert_called_once()


def test_sweep_counts_owner_and_pending_retirements(retirement, monkeypatch, caplog):
    _register('a', 'owner-expired', 0, db=retirement)
    registry.claim_next('a', now=NOW)
    _register('a', 'pending-expired', 1, db=retirement)
    _register('a', 'live', 2, db=retirement)
    wake = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    monkeypatch.setattr(uid_sequencer, '_dispatch', MagicMock())
    with caplog.at_level('INFO'):
        outcomes = uid_sequencer.sweep()
    assert outcomes['expired_retired'] == 2
    assert 'expired_retired=2' in caplog.text
    wake.assert_called_once()


def test_refused_dispatching_owner_never_falls_through_to_redrive(retirement, monkeypatch):
    _register('a', 'old', 0, db=retirement)
    retirement.docs[(registry.PENDING_COLLECTION, 'old')]['payload']['content_id'] = 'content'
    path = ('users', 'a', 'sync_content_ledger', 'content')
    retirement.docs[path] = {'status': 'processing', 'job_id': 'old', 'ledger_run_token': 'bound'}
    registry.claim_next('a', now=NOW)
    before = copy.deepcopy(retirement.docs[path])
    redrive = MagicMock(side_effect=AssertionError('refused owner redriven'))
    monkeypatch.setattr(registry, 'redrive_job', redrive)
    assert uid_sequencer.reconcile_uid('a', registry.get_owner('a'), now=NOW + timedelta(days=1)) == 'refused'
    assert retirement.docs[path] == before
    assert registry.get_owner('a')['active_job_id'] == 'old'
    redrive.assert_not_called()


def test_exact_retirement_budget_with_empty_queue_never_wakes(retirement, monkeypatch):
    _register('a', 'expired', 0, db=retirement)
    wake = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    assert not uid_sequencer.kick('a', retire_limit=1)
    assert registry.pending_head('a') is None
    wake.assert_not_called()


def test_failed_continuation_enqueue_releases_dedupe_claim(retirement, monkeypatch):
    _register('a', 'live', 0, db=retirement)
    wake = MagicMock(side_effect=[RuntimeError('enqueue failed'), None])
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    monkeypatch.setattr(uid_sequencer.time, 'time', lambda: 1000)
    with pytest.raises(RuntimeError, match='enqueue failed'):
        uid_sequencer.kick('a', retire_limit=0)
    assert not uid_sequencer.kick('a', retire_limit=0)
    assert wake.call_count == 2


def test_admission_creates_due_owner_in_same_transaction(db):
    assert _register('orphan', 'one', 0, db=db)
    assert registry.get_owner('orphan', firestore_client=db)['reconcile_at'] == NOW
    assert [owner['uid'] for owner in registry.due_owners(now=NOW)] == ['orphan']


def test_duplicate_admission_repairs_legacy_orphan_without_replacing_payload(db):
    _register('orphan', 'one', 0, db=db)
    del db.docs[(registry.COLLECTION, 'orphan')]
    before = copy.deepcopy(db.docs[(registry.PENDING_COLLECTION, 'one')])
    assert not _register('orphan', 'one', 5, db=db)
    assert registry.get_owner('orphan')['reconcile_at'] == NOW
    assert db.docs[(registry.PENDING_COLLECTION, 'one')] == before


@pytest.mark.parametrize('release', ['finish', 'retire'])
def test_releasing_active_owner_keeps_waiting_work_discoverable_without_kick(db, release):
    _register('a', 'active', 0, db=db)
    claim = registry.claim_next('a', now=NOW)
    _register('a', 'waiting', 1, db=db)
    if release == 'finish':
        assert registry.finish_job('a', 'active', claim['epoch'], 'completed', now=NOW)
    else:
        assert registry.retire_expired('a', 'active', epoch=claim['epoch'], now=NOW)
    owner = registry.get_owner('a')
    assert owner and not owner.get('active_job_id')
    assert owner['reconcile_at'] == NOW
    assert registry.has_pending('a')
    assert registry.due_owners(now=NOW)[0]['uid'] == 'a'
    assert registry.claim_next('a', now=NOW)['epoch'] > claim['epoch']


def test_waiting_retirement_repairs_legacy_owner_before_leaving_successor(db):
    _register('a', 'expired', 0, db=db)
    _register('a', 'next', 1, db=db)
    del db.docs[(registry.COLLECTION, 'a')]
    assert registry.retire_expired('a', 'expired', now=NOW)
    assert registry.has_pending('a') and registry.get_owner('a')['reconcile_at'] == NOW


def test_repair_is_read_only_in_dry_run_and_idempotent_when_applied(db, caplog):
    _register('orphan', 'one', 0, db=db)
    del db.docs[(registry.COLLECTION, 'orphan')]
    before = copy.deepcopy(db.docs)
    assert registry.repair_owner('orphan', dry_run=True, now=NOW)
    assert db.docs == before
    with caplog.at_level('INFO'):
        assert registry.repair_owner('orphan', now=NOW)
        assert not registry.repair_owner('orphan', now=NOW)
    assert caplog.text.count('event=sync_backfill_owner_repaired') == 1
    assert 'orphan' not in caplog.text
    assert NOW < registry.get_owner('orphan')['reconcile_at'] <= NOW + timedelta(minutes=30)
    assert not registry.repair_owner('empty', now=NOW)
    assert not registry.get_owner('empty')


def test_repair_preserves_active_owner(db):
    _register('a', 'one', 0, db=db)
    _register('a', 'two', 1, db=db)
    registry.claim_next('a', now=NOW)
    before = copy.deepcopy(db.docs)
    assert not registry.repair_owner('a', now=NOW)
    assert db.docs == before


def test_sweep_repairs_orphans_even_when_dispatch_cannot_progress(db, monkeypatch, caplog):
    _register('a', 'one', 0, db=db)
    _register('b', 'two', 0, db=db)
    del db.docs[(registry.COLLECTION, 'a')]
    del db.docs[(registry.COLLECTION, 'b')]
    monkeypatch.setattr(uid_sequencer, 'kick', lambda *args, **kwargs: False)
    with caplog.at_level('INFO'):
        outcome = uid_sequencer.sweep(limit=1)
    assert outcome['owner_repaired'] == 1
    assert not registry.due_owners()
    assert registry.has_pending('a') and registry.has_pending('b')
    assert 'event=sync_backfill_owner_repaired' in caplog.text
    assert uid_sequencer.sweep(limit=1)['owner_repaired'] == 1
    assert registry.get_owner('a') and registry.get_owner('b')


def test_empty_owner_is_parked_without_losing_epoch(db, monkeypatch):
    _register('a', 'one', 0, db=db)
    claim = registry.claim_next('a', now=NOW)
    registry.finish_job('a', 'one', claim['epoch'], 'completed', now=NOW)
    before = registry.get_owner('a')
    assert uid_sequencer.reconcile_uid('a', before, now=NOW) == 'empty'
    assert not registry.due_owners(now=NOW + timedelta(days=365))
    assert 'reconcile_at' not in registry.get_owner('a')
    assert registry.get_owner('a')['epoch'] == claim['epoch']


@pytest.mark.parametrize('apply', [False, True])
def test_operator_repair_pages_deduplicates_and_is_idempotent(db, monkeypatch, apply):
    _register('private-a', 'one', 0, db=db)
    _register('private-a', 'two', 1, db=db)
    _register('private-b', 'three', 0, db=db)
    del db.docs[(registry.COLLECTION, 'private-a')]
    del db.docs[(registry.COLLECTION, 'private-b')]
    before = copy.deepcopy(db.docs)
    sleeps = []
    monkeypatch.setattr(repair_script.time, 'monotonic', lambda: 0)
    monkeypatch.setattr(repair_script.time, 'sleep', lambda seconds: sleeps.append(seconds))
    counts = repair_script.repair(db, apply=apply, page_size=1)
    assert counts == {
        'scanned_entries': 3,
        'scanned_uids': 2,
        'missing_owners': 2,
        'repaired_owners': 2 if apply else 0,
        'errors': 0,
    }
    assert sleeps == [0.2]
    if apply:
        assert repair_script.repair(db, apply=True)['repaired_owners'] == 0
        assert registry.get_owner('private-a') and registry.get_owner('private-b')
    else:
        assert db.docs == before


def test_operator_repair_is_bounded_and_errors_never_print_identity(db, monkeypatch, capsys):
    _register('private-a', 'one', 0, db=db)
    _register('private-b', 'two', 0, db=db)
    monkeypatch.setattr(registry, 'repair_owner', MagicMock(side_effect=RuntimeError('private-a/private-b')))
    monkeypatch.setattr(repair_script.firestore, 'Client', lambda **kwargs: db)
    db.close = MagicMock()
    assert repair_script.main(['--project', 'demo-test', '--limit', '1']) == 1
    output = capsys.readouterr().out
    assert 'private' not in output
    assert '"errors": 1' in output and '"scanned_entries": 1' in output
    assert registry.repair_owner.call_args.kwargs['dry_run'] is True
    db.close.assert_called_once()


@pytest.mark.parametrize(
    'bounds', [{'limit': 0}, {'page_size': 501}, {'rate_per_second': 0}, {'rate_per_second': float('nan')}]
)
def test_operator_repair_rejects_invalid_bounds_before_reading(db, bounds):
    with pytest.raises(ValueError, match='invalid repair bounds'):
        repair_script.repair(db, **bounds)


@pytest.mark.parametrize('failure', ['scan', 'close', 'stage'])
def test_operator_repair_suppresses_all_cli_exception_payloads(db, monkeypatch, capsys, failure):
    db.close = MagicMock()
    monkeypatch.setattr(repair_script.firestore, 'Client', lambda **kwargs: db)
    run = MagicMock(return_value={'errors': 0})
    monkeypatch.setattr(repair_script, 'repair', run)
    if failure == 'scan':
        run.side_effect = RuntimeError('private-uid-in-exception')
    elif failure == 'close':
        db.close.side_effect = RuntimeError('private-uid-in-exception')
    else:
        monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert repair_script.main(['--project', 'demo-test']) == 1
    output = capsys.readouterr()
    assert output.out.strip() == '{"errors": 1}'
    assert 'private' not in output.out + output.err
    if failure == 'stage':
        run.assert_not_called()


@pytest.mark.parametrize('state', ['dispatching', 'running'])
def test_301_empty_owners_cannot_crowd_out_stuck_lease_from_one_page(db, monkeypatch, state):
    current = datetime.now(timezone.utc)
    for index in range(301):
        uid = f'empty-{index:03}'
        _register(uid, uid, 0, db=db)
        claim = registry.claim_next(uid, now=NOW)
        assert registry.finish_job(uid, uid, claim['epoch'], 'completed', now=NOW)
        # Even a stale deferred-owner attempt must not revive a parked row.
        registry.defer_owner(uid, 120, now=NOW)
        assert 'reconcile_at' not in registry.get_owner(uid)
    _register('stuck', 'stuck-job', 0, db=db)
    claim = registry.claim_next('stuck', now=current - timedelta(hours=2))
    if state == 'running':
        assert registry.begin_job('stuck', 'stuck-job', claim['epoch'], now=current - timedelta(hours=2))
    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda job: dispatched.append(job))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda jid: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda jid: {'status': 'queued'})
    page = registry.due_owners(limit=100)
    assert [row['uid'] for row in page] == ['stuck']
    outcomes = uid_sequencer.sweep(limit=100)
    assert outcomes['lease_expired'] == 1
    assert len(dispatched) == 1 and dispatched[0]['job_id'] == 'stuck-job'
    assert dispatched[0]['epoch'] == claim['epoch'] + int(state == 'running')


@pytest.mark.parametrize('release', ['finish', 'active_retire', 'pending_retire'])
def test_last_job_parks_owner_and_new_admission_wakes_with_monotonic_epoch(db, release):
    _register('a', 'one', 0, db=db)
    if release == 'pending_retire':
        epoch = 0
        assert registry.retire_expired('a', 'one', now=NOW)
    else:
        claim = registry.claim_next('a', now=NOW)
        epoch = claim['epoch']
        if release == 'finish':
            assert registry.finish_job('a', 'one', epoch, 'completed', now=NOW)
        else:
            assert registry.retire_expired('a', 'one', epoch=epoch, now=NOW)
    assert registry.get_owner('a')['epoch'] == epoch
    assert 'reconcile_at' not in registry.get_owner('a')
    assert not registry.due_owners(now=NOW + timedelta(days=365))
    assert _register('a', 'two', 0, db=db)
    assert registry.get_owner('a')['reconcile_at'] == NOW
    assert registry.claim_next('a', now=NOW)['epoch'] > epoch


def test_deferral_rechecks_work_and_cannot_park_a_new_active_reservation(db):
    _register('a', 'one', 0, db=db)
    stale_idle = registry.get_owner('a')
    claim = registry.claim_next('a', now=NOW)
    assert uid_sequencer.reconcile_uid('a', stale_idle, now=NOW) == 'empty'
    owner = registry.get_owner('a')
    assert owner['active_job_id'] == 'one' and owner['active_epoch'] == claim['epoch']
    assert owner['reconcile_at'] == NOW + timedelta(seconds=120)


def test_empty_claim_parks_legacy_idle_and_duplicate_admission_wakes_parked_owner(db):
    db.docs[(registry.COLLECTION, 'a')] = {'epoch': 9, 'reconcile_at': NOW}
    assert registry.claim_next('a', now=NOW) is None
    assert registry.get_owner('a') == {'epoch': 9, 'updated_at': NOW}
    _register('a', 'waiting', 0, db=db)
    db.docs[(registry.COLLECTION, 'a')].pop('reconcile_at')
    assert not _register('a', 'waiting', 0, db=db)
    assert registry.get_owner('a')['epoch'] == 9
    assert registry.get_owner('a')['reconcile_at'] == NOW


def test_repair_staggers_owners_and_pending_fallback_cannot_bypass_deadline(db, monkeypatch):
    for uid in ('a', 'b'):
        _register(uid, uid, 0, db=db)
        del db.docs[(registry.COLLECTION, uid)]
    offsets = iter([0, 1799])
    monkeypatch.setattr(registry.secrets, 'randbelow', lambda window: next(offsets))
    monkeypatch.setattr(registry, '_now', lambda: NOW)
    assert registry.repair_owner('a', now=NOW)
    assert registry.repair_owner('b', now=NOW)
    assert registry.get_owner('a')['reconcile_at'] == NOW + timedelta(seconds=1)
    assert registry.get_owner('b')['reconcile_at'] == NOW + timedelta(minutes=30)
    assert not registry.due_owners(now=NOW)
    assert registry.pending_head('a') is None
    assert registry.claim_next('a', now=NOW) is None
    assert not registry.retire_expired('a', 'a', now=NOW)
    assert not uid_sequencer.kick('a')
    assert not registry.due_owners(now=NOW)
    assert registry.claim_next('a', now=NOW + timedelta(seconds=1))['job_id'] == 'a'
    assert 'repair_not_before' not in registry.get_owner('a')


def test_self_heal_uses_shared_window_and_skips_immediate_kick(db, monkeypatch):
    _register('a', 'a', 0, db=db)
    del db.docs[(registry.COLLECTION, 'a')]
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_REPAIR_WINDOW_SECONDS', '600')
    monkeypatch.setattr(registry.secrets, 'randbelow', lambda window: window - 1)
    kick = MagicMock(return_value=False)
    monkeypatch.setattr(uid_sequencer, 'kick', kick)
    before = datetime.now(timezone.utc)
    assert uid_sequencer.sweep()['owner_repaired'] == 1
    owner = registry.get_owner('a')
    assert before + timedelta(seconds=600) <= owner['reconcile_at']
    assert owner['repair_not_before'] == owner['reconcile_at']
    kick.assert_not_called()
    registry.defer_owner('a', 120, now=before)
    assert registry.get_owner('a')['reconcile_at'] == owner['reconcile_at']


def test_operator_window_option_reaches_shared_helper_and_rejects_zero(db, monkeypatch, capsys):
    _register('a', 'a', 0, db=db)
    del db.docs[(registry.COLLECTION, 'a')]
    monkeypatch.setattr(repair_script.firestore, 'Client', lambda **kwargs: db)
    db.close = MagicMock()
    monkeypatch.setattr(registry.secrets, 'randbelow', lambda window: window - 1)
    before = datetime.now(timezone.utc)
    assert repair_script.main(['--project', 'demo-test', '--apply', '--repair-window-seconds', '60']) == 0
    assert registry.get_owner('a')['reconcile_at'] >= before + timedelta(seconds=60)
    assert '"repaired_owners": 1' in capsys.readouterr().out
    with pytest.raises(ValueError, match='repair window'):
        repair_script.repair(db, repair_window=0)


def test_sweep_defers_failing_owner_and_unblocks_healthy_owners(db, monkeypatch):
    current = datetime.now(timezone.utc)
    _register('failing', 'job-failing', 0, db=db)
    registry.claim_next('failing', now=current - timedelta(hours=1))

    _register('healthy', 'job-healthy', 0, db=db)
    registry.claim_next('healthy', now=current - timedelta(hours=1))

    orig_reconcile = uid_sequencer.reconcile_uid

    def mock_reconcile(uid, owner, **kwargs):
        if uid == 'failing':
            raise RuntimeError('Firestore document missing or corrupted')
        return orig_reconcile(uid, owner, **kwargs)

    monkeypatch.setattr(uid_sequencer, 'reconcile_uid', mock_reconcile)
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'queued'})
    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))

    # Tick 1 with limit=1: 'failing' encounters an error, but must be deferred
    outcomes1 = uid_sequencer.sweep(limit=1)
    assert outcomes1.get('error') == 1
    failing_owner = registry.get_owner('failing')
    assert failing_owner['reconcile_at'] >= current + timedelta(seconds=registry.HEARTBEAT_SECONDS - 5)

    # Tick 2 with limit=1: 'failing' is now deferred, so 'healthy' is reached and processed!
    outcomes2 = uid_sequencer.sweep(limit=1)
    assert outcomes2.get('lease_expired') == 1
    assert len(dispatched) == 1
    assert dispatched[0]['job_id'] == 'job-healthy'


def test_sweep_tolerates_due_owners_query_failure(db, monkeypatch):
    _register('a', 'job', 0, db=db)
    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(registry, 'due_owners', MagicMock(side_effect=RuntimeError('firestore unavailable')))
    assert uid_sequencer.sweep() == {'due_owners_error': 1, 'pending_dispatched': 1}
    assert dispatched[0]['job_id'] == 'job'


def test_sweep_tolerates_due_pending_query_failure(db, monkeypatch):
    _register('a', 'job', 0, db=db)
    monkeypatch.setattr(registry, 'due_pending', MagicMock(side_effect=RuntimeError('firestore unavailable')))
    outcomes = uid_sequencer.sweep()
    assert outcomes['due_pending_error'] == 1


def test_defer_owner_tolerates_missing_document(db, monkeypatch):
    from google.api_core.exceptions import NotFound

    def failing_commit(txn):
        raise NotFound('Document does not exist')

    monkeypatch.setattr(db, 'transaction', lambda **kwargs: MagicMock())
    monkeypatch.setattr(registry.firestore, 'transactional', lambda fn: failing_commit)
    # Must not raise NotFound
    registry.defer_owner('missing_uid', 120)


def test_redrive_job_tolerates_missing_document(db, monkeypatch):
    from google.api_core.exceptions import NotFound

    def failing_commit(txn):
        raise NotFound('Document does not exist')

    monkeypatch.setattr(db, 'transaction', lambda **kwargs: MagicMock())
    monkeypatch.setattr(registry.firestore, 'transactional', lambda fn: failing_commit)
    # Must return None instead of raising NotFound
    assert registry.redrive_job('missing_uid', 'job', 1) is None


@pytest.mark.parametrize('active', [False, True])
def test_dark_guard_transfers_expired_obligation_to_durable_custody(db, monkeypatch, active):
    from database import sync_redrive

    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
    _register('a', 'lost', 0, db=db)
    original = db.docs[(registry.PENDING_COLLECTION, 'lost')]['payload']
    epoch = registry.claim_next('a', now=NOW)['epoch'] if active else None
    assert registry.retire_expired('a', 'lost', epoch=epoch, now=NOW)
    custody = db.docs[(sync_redrive.COLLECTION, 'lost')]
    assert custody['status'] == 'redrive_required'
    assert custody['payload'] == original
    assert registry.pending_head('a') is None
    assert not registry.get_owner('a').get('active_job_id')
    assert db.docs[(sync_redrive.STATS_COLLECTION, 'backlog')]['count'] == 1
    sync_redrive.refresh_metrics(firestore_client=db)
    assert sync_redrive.BACKLOG._value.get() == 1
    assert sync_redrive.DEADLINE._value.get() > 0
    assert sync_redrive.UNKNOWN_DEADLINE._value.get() == 1


def test_dark_guard_keeps_partial_progress_and_counts_repeated_missing_job_once(db, monkeypatch):
    from database import sync_redrive

    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
    payload = {'uid': 'a', 'job_id': 'lost', 'content_id': 'content', 'raw_blob_paths': ['syncing/a/lost/pcm16.bin']}
    path = ('users', 'a', 'sync_content_ledger', 'content')
    partial = {'status': 'retryable', 'processed_segment_ids': ['segment'], 'partial_result': {'total_segments': 2}}
    db.docs[path] = copy.deepcopy(partial)
    assert sync_redrive.preserve_missing_job('a', 'lost', payload, firestore_client=db) == 'redrive_required'
    assert sync_redrive.preserve_missing_job('a', 'lost', payload, firestore_client=db) == 'redrive_required'
    assert db.docs[path] == partial
    assert db.docs[(sync_redrive.STATS_COLLECTION, 'backlog')]['count'] == 1


def test_dark_guard_completed_content_retires_without_creating_redrive(db, monkeypatch):
    from database import sync_redrive

    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
    _register('a', 'lost', 0, db=db)
    pending = db.docs[(registry.PENDING_COLLECTION, 'lost')]
    pending['payload']['content_id'] = 'content'
    db.docs[('users', 'a', 'sync_content_ledger', 'content')] = {
        'status': 'completed',
        'result': {'total_segments': 0, 'failed_segments': 0, 'errors': [], 'outcome': 'expected_silence'},
    }
    assert registry.retire_expired('a', 'lost', now=NOW)
    assert (sync_redrive.COLLECTION, 'lost') not in db.docs


def test_dark_guard_does_not_steal_bound_run_or_another_content_owner(db, monkeypatch):
    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
    for claim in (
        {'status': 'processing', 'job_id': 'other'},
        {'status': 'processing', 'job_id': 'lost', 'ledger_run_token': 'bound'},
    ):
        _register('a', 'lost', 0, db=db)
        db.docs[(registry.PENDING_COLLECTION, 'lost')]['payload']['content_id'] = 'content'
        db.docs[('users', 'a', 'sync_content_ledger', 'content')] = claim
        assert not registry.retire_expired('a', 'lost', now=NOW)
        assert (registry.PENDING_COLLECTION, 'lost') in db.docs


def test_guard_independent_of_old_retirement_switch(retirement, monkeypatch):
    from database import sync_redrive

    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
    monkeypatch.setenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'false')
    _register('a', 'expired', 0, db=retirement)
    _register('a', 'live', 1, db=retirement)
    assert uid_sequencer._claim_next('a')['job_id'] == 'live'
    assert retirement.docs[(sync_redrive.COLLECTION, 'expired')]['status'] == 'redrive_required'


def test_budget_deferral_count_survives_lease_expiry_redrive(db):
    """A budget-deferred sequenced job redrives from the owner's original
    ``active_payload``, which carries no chain count: without the owner-side
    copy persisted at deferral time, every lease-expiry redrive would restart
    ``budget_deferrals`` at zero and an over-budget job could defer forever."""
    _register('a', 'job', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    assert first['payload'].get(registry.BUDGET_DEFERRALS_PAYLOAD_KEY) is None

    # The handler defers the attempt (e.g. second whole-budget expiry) and
    # persists the incremented count on the running owner.
    registry.note_budget_deferral('a', 'job', first['epoch'], 2, firestore_client=db, now=NOW)

    # Lease expires before the delayed replacement begins; the sweep's redrive
    # must re-attach the persisted count to the epoch-original payload.
    redriven = registry.redrive_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=35))
    assert redriven is not None
    assert redriven['payload'][registry.BUDGET_DEFERRALS_PAYLOAD_KEY] == 2
    # The stored owner payload itself stays untouched: the count rides the
    # owner field, not a mutation of the durable original payload.
    owner = registry.get_owner('a', firestore_client=db)
    assert owner['active_payload'].get(registry.BUDGET_DEFERRALS_PAYLOAD_KEY) is None
    assert owner['active_budget_deferrals'] == 2


def test_note_budget_deferral_is_inert_for_released_or_mismatched_owner(db):
    """The owner write is epoch-fenced and must not resurrect an owner a
    completion has already released, nor pin a count to a different epoch."""
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    assert registry.finish_job('a', 'job', first['epoch'], 'completed', firestore_client=db, now=NOW)

    registry.note_budget_deferral('a', 'job', first['epoch'], 3, firestore_client=db, now=NOW)

    owner = registry.get_owner('a', firestore_client=db)
    assert 'active_budget_deferrals' not in owner
    assert 'active_job_id' not in owner

    # An epoch mismatch on a live owner is equally inert.
    second = registry.claim_next('a', firestore_client=db, now=NOW)
    assert second is not None
    assert registry.begin_job('a', second['job_id'], second['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', second['job_id'], second['epoch'] + 5, 4, firestore_client=db, now=NOW)
    assert 'active_budget_deferrals' not in registry.get_owner('a', firestore_client=db)


def test_sweep_stops_redriving_at_the_budget_deferral_cap(db, monkeypatch):
    """A sequenced job whose persisted budget-deferral count has reached the
    handler's own exhaustion threshold must not be redriven again: the redrive
    would copy the maxed count into a fresh epoch payload, run another
    full-budget attempt, 409, and redrive forever — and backfill allows one
    in-flight job per UID, so the loop also blocks every later capture. The
    sweep releases the owner (deadline-fenced) and kicks the next pending
    capture instead."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    # The handler deferred max-1 times; its next whole-budget run ends through
    # the 409/queue with no further replacement scheduled.
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'processing'})
    finalized_chains = []

    def _fenced_fail(job_id, _lock_token, _error, **kwargs):
        finalized_chains.append((job_id, kwargs.get('reason_code')))
        return sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )

    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _fenced_fail)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))
    redrives = []
    real_redrive = registry.redrive_job

    def _counting_redrive(uid, job_id, epoch, **kwargs):
        redrives.append((job_id, epoch))
        return real_redrive(uid, job_id, epoch, **kwargs)

    monkeypatch.setattr(registry, 'redrive_job', _counting_redrive)

    expired = NOW + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'budget_chain_exhausted'

    # No fresh full-budget attempt was dispatched for the exhausted job; the
    # next waiting capture was promoted instead, unblocking the per-UID lane.
    assert redrives == []
    assert [claim['job_id'] for claim in dispatched] == ['next']
    released = registry.get_owner('a', firestore_client=db)
    # The exhausted job's owner record is gone and the next capture has
    # already claimed the lane: the per-UID slot is no longer held hostage.
    assert released.get('active_job_id') == 'next'
    # The abandoned Redis job was terminalized (sequenced jobs are excluded
    # from stale polling, so the sweep itself must hand off the terminal
    # state) with a distinct failure reason for observability.
    assert finalized_chains == [('job', 'sync_budget_chain_exhausted')]

    # Below the cap the sweep keeps redriving with the persisted count
    # re-attached (existing contract, thread guard).
    assert registry.begin_job('a', 'next', dispatched[0]['epoch'], firestore_client=db, now=expired)
    registry.note_budget_deferral('a', 'next', dispatched[0]['epoch'], 2, firestore_client=db, now=expired)
    later = expired + timedelta(minutes=35)
    outcome = uid_sequencer.reconcile_uid('a', registry.get_owner('a', firestore_client=db), now=later)
    assert outcome == 'lease_expired'
    assert redrives == [('next', dispatched[0]['epoch'])]
    owner_after = registry.get_owner('a', firestore_client=db)
    assert owner_after['active_payload'].get(registry.BUDGET_DEFERRALS_PAYLOAD_KEY) is None


def test_sweep_finalizes_a_queued_budget_chain_job(db, monkeypatch):
    """The final whole-budget attempt can expire during staged-file download
    or another pre-pipeline step, before the attempt ever marked the job
    processing: the capped chain's Redis job then reads ``queued``. Sequenced
    jobs are exempt from stale polling and the owner is about to be released,
    so the sweep's finalizer must accept the queued job exactly like the
    processing one — otherwise it stays nonterminal (with its content claim)
    until the 24h Redis TTL."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    # The abandoned attempt expired before the processing transition.
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'queued'})
    finalized_chains = []

    def _fenced_fail(job_id, _lock_token, _error, **kwargs):
        finalized_chains.append((job_id, kwargs.get('reason_code')))
        return sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )

    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _fenced_fail)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    expired = NOW + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'budget_chain_exhausted'

    # The queued abandoned job was terminalized before the owner release, and
    # the lane advanced to the next waiting capture.
    assert finalized_chains == [('job', 'sync_budget_chain_exhausted')]
    assert [claim['job_id'] for claim in dispatched] == ['next']
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'next'


def test_sweep_keeps_owner_when_budget_chain_finalize_fails_transiently(db, monkeypatch):
    """The terminal handoff is required before the owner is released: after
    the release no sweep retains an identity for the job and status polling
    cannot stale-finalize sequenced dispatch, so a transient Redis failure
    must keep the owner on the books (deferred one heartbeat) for the next
    sweep to retry — never release the owner and advance the lane leaving the
    accepted job nonterminal until the TTL."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'processing'})
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)

    def _redis_write_fails(job_id, _lock_token, error, **kwargs):
        raise ConnectionError('redis unavailable')

    finalized_chains = []
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _redis_write_fails)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    expired = NOW + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'finalize_deferred'

    # The owner is retained for the retry: the lane did not advance and no
    # terminal write happened against the unreachable Redis job.
    assert finalized_chains == []
    assert dispatched == []
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'job'

    # The next sweep retries the whole sequence and completes it once Redis
    # is reachable again.
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'processing'})
    monkeypatch.setattr(
        uid_sequencer,
        'fenced_mark_job_failed',
        lambda job_id, _lock_token, error, **kwargs: finalized_chains.append((job_id, kwargs.get('reason_code')))
        or sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        ),
    )
    later = expired + timedelta(minutes=5)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=later) == 'budget_chain_exhausted'
    assert finalized_chains == [('job', 'sync_budget_chain_exhausted')]
    assert [claim['job_id'] for claim in dispatched] == ['next']
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'next'


def test_sweep_waits_for_the_final_scheduled_replacement(db, monkeypatch):
    """The persisted count at the cap denotes a successfully enqueued final
    replacement, not a completed attempt: that replacement is deliberately
    delayed past the owner lease (RUN_LOCK_TTL + 60s), so the sweep normally
    reaches the cap branch while the marker is still live. Terminalizing then
    would make the already paid-for final delivery a stale epoch the moment
    the lane advances — and sequenced jobs are exempt from stale polling, so
    nothing would ever finalize the job. A live marker must keep the owner
    until its horizon passes; only then does the handoff proceed."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    finalized_chains = []

    def _fenced_fail(job_id, _lock_token, _error, **kwargs):
        finalized_chains.append((job_id, kwargs.get('reason_code')))
        return sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )

    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _fenced_fail)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    live_marker = time.time() + 1800.0
    expired = NOW + timedelta(minutes=35)
    monkeypatch.setattr(
        uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'processing', 'deferred_until': live_marker}
    )
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'finalize_deferred'

    # The final replacement is still due: no terminal write, no lane advance.
    assert finalized_chains == []
    assert dispatched == []
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'job'

    # Past the marker horizon the final delivery ran (or was lost) and the
    # marker is gone: the handoff proceeds and the lane advances.
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'processing'})
    later = expired + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=later) == 'budget_chain_exhausted'
    assert finalized_chains == [('job', 'sync_budget_chain_exhausted')]
    assert [claim['job_id'] for claim in dispatched] == ['next']
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'next'


def test_sweep_retains_owner_while_a_live_writer_holds_the_run_lock(db, monkeypatch):
    """Thread: the finalization must acquire the run lock atomically instead
    of checking it and writing later. A final replacement (or a detached
    executor leaf) that acquired the lock between the reconcile-level check
    and this helper must not be treated as a successful terminal handoff:
    releasing the owner then would advance the lane while the old attempt
    still runs, and if that attempt times out it 409s without terminalizing
    and no owner remains to recover the job. An unacquirable lock retains
    the owner for the next sweep; the lock's holder keeps the right to its
    own terminal write or deferral."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'processing'})
    finalized_chains = []

    def _fenced_fail(job_id, _lock_token, _error, **kwargs):
        finalized_chains.append((job_id, kwargs.get('reason_code')))
        return sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )

    # The final replacement acquired the lock after the reconcile-level check.
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: None)
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _fenced_fail)
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    expired = NOW + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'finalize_deferred'

    # The owner is retained: no terminal write raced the live writer, the lane
    # did not advance, and the next capture stays queued.
    assert finalized_chains == []
    assert dispatched == []
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'job'

    # Once the lock is free again the next sweep completes the handoff and
    # advances the lane.
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    later = expired + timedelta(minutes=5)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=later) == 'budget_chain_exhausted'
    assert finalized_chains == [('job', 'sync_budget_chain_exhausted')]
    assert [claim['job_id'] for claim in dispatched] == ['next']
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'next'


def test_sweep_converges_a_durably_completed_ledger_before_failing_a_capped_job(db, monkeypatch):
    """Thread: budget cancellation can land after a detached pipeline leaf
    durably completed the content ledger but before the matching Redis
    terminal write. Failing such a job unconditionally would dead-letter
    transcription whose side effects already committed. A fence job whose
    ledger proves completion must converge that result instead of publishing
    sync_budget_chain_exhausted."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    # A fence-mode job whose durable ledger proves a completed result.
    monkeypatch.setattr(
        uid_sequencer,
        'get_sync_job',
        lambda _job_id: {'status': 'processing', 'ledger_fence_mode': sync_jobs.SyncLedgerFenceMode.ACTIVE.value},
    )
    monkeypatch.setattr(uid_sequencer, 'sync_job_uses_ledger_fence', lambda _job: True)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_sync_job_run_lock', lambda _job_id: '1:final-lock')
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)

    converged_calls = []
    monkeypatch.setattr(
        uid_sequencer,
        '_converge_capped_ledger_completion',
        lambda **kwargs: converged_calls.append(kwargs) or {'status': 'completed'},
    )
    finalized_chains = []

    def _fenced_fail(job_id, _lock_token, _error, **kwargs):
        finalized_chains.append((job_id, kwargs.get('reason_code')))
        return sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )

    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _fenced_fail)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    expired = NOW + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'budget_chain_exhausted'

    # The proven completion converged into the Redis result: no failure was
    # published, the owner released, and the lane advanced to the next capture.
    assert converged_calls and converged_calls[0]['job_id'] == 'job'
    assert finalized_chains == []
    assert [claim['job_id'] for claim in dispatched] == ['next']
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'next'


def test_sweep_retains_owner_when_terminal_cas_leaves_job_nonterminal(db, monkeypatch):
    """A lost CAS in mark_job_failed did not apply the terminal write; the
    finalizer must re-read and only accept a job that is now terminal or
    absent. Accepting the loss would release the only sequencer owner with
    the job still nonterminal — and polls never stale-finalize sequenced
    jobs, so it would strand until the Redis TTL despite the handoff claim."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    finalized_chains = []

    def _cas_lost(job_id, _lock_token, _error, **kwargs):
        finalized_chains.append((job_id, kwargs.get('reason_code')))
        return sync_jobs.FencedSyncJobMutation(outcome=sync_jobs.FencedSyncJobMutationOutcome.CONFLICT)

    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _cas_lost)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    expired = NOW + timedelta(minutes=35)
    # Re-read still shows the job nonterminal: retain the owner for retry.
    reads = iter(
        [
            {'status': 'processing'},  # reconcile-level read
            {'status': 'processing'},  # finalizer initial read
            {'status': 'processing'},  # finalizer CAS re-read (nonterminal)
        ]
    )
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: next(reads))
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'finalize_deferred'
    assert dispatched == []
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'job'

    # Next sweep: the CAS re-read now proves another writer terminalized the
    # job, so the lost CAS is accepted — owner releases, lane advances.
    reads = iter(
        [
            {'status': 'processing'},  # reconcile-level read
            {'status': 'processing'},  # finalizer initial read
            {'status': 'failed'},  # finalizer CAS re-read: terminality assured
        ]
    )
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: next(reads))
    later = expired + timedelta(minutes=5)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=later) == 'budget_chain_exhausted'
    assert [claim['job_id'] for claim in dispatched] == ['next']
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'next'


def test_finish_expired_job_refuses_a_live_lease(db):
    """The budget-cap release is fenced exactly like redrive_job: a delivery
    that began and renewed between the sweeper's read and the release write
    must never be released out from under its running worker."""

    _register('a', 'job', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)

    # Lease still live: release refused.
    assert (
        registry.finish_expired_job('a', 'job', first['epoch'], 'budget_chain_exhausted', firestore_client=db, now=NOW)
        is False
    )
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'job'

    # Lease expired: release succeeds and the owner is gone.
    assert (
        registry.finish_expired_job(
            'a', 'job', first['epoch'], 'budget_chain_exhausted', firestore_client=db, now=NOW + timedelta(minutes=35)
        )
        is True
    )
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') is None


def test_sweep_retains_owner_when_a_final_replacement_renewed_the_lease(db, monkeypatch):
    """Thread: the final replacement can begin after its marker horizon while
    still queued behind the lane's concurrency cap — it renews the Firestore
    lease in begin_job after the sweeper's expired-owner read but before its
    Redis run-lock acquire, so the finalizer can acquire the finalization
    lock in that gap. Its later finish_expired_job correctly refuses to
    release the renewed owner, but it cannot undo a failure already
    published against the live attempt. The finalizer must re-check the
    owner's release fence after acquiring the lock and retain the owner when
    a renewal landed; the replacement's own terminal write decides."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _job_id: {'status': 'processing'})
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)
    finalized_chains = []

    def _fenced_fail(job_id, _lock_token, _error, **kwargs):
        finalized_chains.append((job_id, kwargs.get('reason_code')))
        return sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )

    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _fenced_fail)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    expired = NOW + timedelta(minutes=35)

    # The final replacement renewed the lease after the sweeper's read: the
    # owner names the job but its lease deadline is in the future.
    real_release_due = registry.owner_release_due

    def _renewed_owner_release_due(uid, job_id, epoch, **kwargs):
        return real_release_due(uid, job_id, epoch, firestore_client=db, now=NOW)

    monkeypatch.setattr(registry, 'owner_release_due', _renewed_owner_release_due)
    owner = registry.get_owner('a', firestore_client=db)
    registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=expired)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'finalize_deferred'

    # No failure was published against the live attempt and the owner stays
    # on the books; the lane did not advance.
    assert finalized_chains == []
    assert dispatched == []
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'job'

    # Once the renewed lease has also expired, the fence re-check passes and
    # the handoff proceeds.
    later = expired + timedelta(minutes=35)
    monkeypatch.setattr(
        registry,
        'owner_release_due',
        lambda uid, job_id, epoch, **kwargs: real_release_due(uid, job_id, epoch, firestore_client=db, now=later),
    )
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=later) == 'budget_chain_exhausted'
    assert finalized_chains == [('job', 'sync_budget_chain_exhausted')]


def test_capped_chain_handoff_releases_slot_and_claim_before_owner_release(db, monkeypatch):
    """Thread: the capped chain's terminal handoff must finish the exact-job
    cleanup the redelivery's terminal branch would have run — the per-UID
    backfill slot and the failed job's durable content claim — before the
    caller releases the sequencer owner. Sequenced jobs are exempt from stale
    polling and the task's attempt contract is spent, so nothing else runs
    it: the slot would hold the lane for its ~2-day TTL and re-uploading the
    same content would deflect off the claim until its 45-day TTL."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    _register('a', 'next', 60, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(
        uid_sequencer,
        'get_sync_job',
        lambda _job_id: {
            'status': 'processing',
            'uid': 'a',
            'job_id': 'job',
            'lane': 'backfill',
            'content_id': 'content-1',
        },
    )
    monkeypatch.setattr(uid_sequencer, 'sync_job_uses_ledger_fence', lambda _job: False)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    released_slots = []
    released_claims = []
    monkeypatch.setattr(
        uid_sequencer, 'release_backfill_slot', lambda uid, job_id: released_slots.append((uid, job_id))
    )
    monkeypatch.setattr(
        uid_sequencer,
        'release_sync_content_claim_after_job_retired',
        lambda uid, content_id, job_id, **kwargs: released_claims.append((uid, content_id, job_id)),
    )

    def _fenced_fail(job_id, _lock_token, _error, **kwargs):
        return sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )

    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _fenced_fail)

    expired = NOW + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'budget_chain_exhausted'

    # The exact-job cleanup ran before the owner release: the lane's slot and
    # the failed job's content claim are freed alongside the terminal write.
    assert released_slots == [('a', 'job')]
    assert released_claims == [('a', 'content-1', 'job')]
    assert [claim['job_id'] for claim in dispatched] == ['next']
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'next'


def test_capped_chain_handoff_retains_owner_when_cleanup_fails(db, monkeypatch):
    """Thread (companion): the cleanup is part of the handoff's obligation —
    a transient failure releasing the slot/claim must retain the owner for
    the next sweep's retry, never release the lane's identity while the
    slot and claim stay held."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(
        uid_sequencer,
        'get_sync_job',
        lambda _job_id: {
            'status': 'processing',
            'uid': 'a',
            'job_id': 'job',
            'lane': 'backfill',
            'content_id': 'content-1',
        },
    )
    monkeypatch.setattr(uid_sequencer, 'sync_job_uses_ledger_fence', lambda _job: False)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda _job_id, _token: None)
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    cleanup_attempts = {'n': 0}

    def _slot_release_fails_once(uid, job_id):
        cleanup_attempts['n'] += 1
        if cleanup_attempts['n'] == 1:
            raise ConnectionError('redis unavailable')

    monkeypatch.setattr(uid_sequencer, 'release_backfill_slot', _slot_release_fails_once)
    released_claims = []
    monkeypatch.setattr(
        uid_sequencer,
        'release_sync_content_claim_after_job_retired',
        lambda uid, content_id, job_id, **kwargs: released_claims.append((uid, content_id, job_id)),
    )

    def _fenced_fail(job_id, _lock_token, _error, **kwargs):
        return sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )

    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', _fenced_fail)

    expired = NOW + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)

    # First sweep: the slot release fails, so the owner is retained even
    # though the terminal write applied.
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'finalize_deferred'
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'job'
    assert released_claims == []
    assert dispatched == []

    # Next sweep: the applied terminal write means the job now reads
    # terminal, so the sweep classifies it terminal_cleanup and redrives the
    # same epoch — the redelivery's terminal branch owns the cleanup retry
    # (slot, claim, epoch). That redrive only exists because the failed
    # cleanup retained the owner: a released owner would have advanced the
    # lane with no identity left to redispatch this job.
    later = expired + timedelta(minutes=5)
    monkeypatch.setattr(
        uid_sequencer,
        'get_sync_job',
        lambda _job_id: {
            'status': 'failed',
            'uid': 'a',
            'job_id': 'job',
            'lane': 'backfill',
            'content_id': 'content-1',
        },
    )
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=later) == 'terminal_cleanup'
    assert [claim['job_id'] for claim in dispatched] == ['job']
    # The sweep itself did not re-run the slot release (the redelivery's
    # terminal branch performs it); the claim likewise rides the redelivery.
    assert cleanup_attempts['n'] == 1
    assert released_claims == []


@pytest.mark.parametrize('recheck', ['owner_renewed', 'fence_recheck_failed'])
def test_capped_chain_handoff_drops_finalization_lock_on_recheck_exit(db, monkeypatch, recheck):
    """Thread: both post-acquire lease-recheck early returns (the owner was
    renewed by a final replacement that began behind the lane's concurrency
    cap, and the recheck read itself failed) must release the finalization
    lock they already hold. Leaking it keeps the lock for its full TTL —
    with the queue's 5–60s backoff every remaining attempt can exhaust
    before expiry, skipping a legitimate final attempt and blocking the
    one-in-flight UID lane until a later sweep fails the job."""

    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '5')
    _register('a', 'job', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first is not None and first['job_id'] == 'job'
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    registry.note_budget_deferral('a', 'job', first['epoch'], 4, firestore_client=db, now=NOW)

    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(
        uid_sequencer,
        'get_sync_job',
        lambda _job_id: {
            'status': 'processing',
            'uid': 'a',
            'job_id': 'job',
            'lane': 'backfill',
            'content_id': 'content-1',
        },
    )
    monkeypatch.setattr(uid_sequencer, 'sync_job_uses_ledger_fence', lambda _job: False)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _job_id: 'final-lock-token')
    released_locks = []
    monkeypatch.setattr(
        uid_sequencer,
        'release_job_run_lock',
        lambda job_id, token: released_locks.append((job_id, token)),
    )
    monkeypatch.setattr(backfill_cutover, 'quiet_remaining', lambda _uid: (0, ''))
    monkeypatch.setattr(backfill_cutover, 'direct_remaining_for_uid', lambda _uid: (0, ''))

    def _recheck_raises(*_args, **_kwargs):
        raise ConnectionError('redis unavailable')

    if recheck == 'owner_renewed':
        # A replacement renewed the Firestore lease after the sweep's
        # expired-owner read: the recheck reads the live owner and reports
        # the release fence no longer holds.
        monkeypatch.setattr(registry, 'owner_release_due', lambda *_args, **_kwargs: False)
    else:
        monkeypatch.setattr(registry, 'owner_release_due', _recheck_raises)

    terminal_writes = []
    monkeypatch.setattr(
        uid_sequencer,
        'fenced_mark_job_failed',
        lambda job_id, *_args, **_kwargs: terminal_writes.append(job_id),
    )

    expired = NOW + timedelta(minutes=35)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'finalize_deferred'

    # The owner is retained for the next sweep, no terminal write is made
    # against the renewed (or unreadable) lease, nothing is redispatched,
    # and the finalization lock the sweep did acquire is released instead
    # of living out its TTL against the live replacement.
    assert registry.get_owner('a', firestore_client=db).get('active_job_id') == 'job'
    assert dispatched == []
    assert terminal_writes == []
    assert released_locks == [('job', 'final-lock-token')]
