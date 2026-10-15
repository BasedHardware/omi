"""Durable UID ownership and bounded recovery for backfill Cloud Tasks."""

import copy
import threading
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

    def where(self, field, op, maximum):
        if op == '==':
            return _Query(
                self.client, self.path, self.field, self.maximum, self.order, self.maximum_results, (field, maximum)
            )
        assert op == '<='
        return _Query(self.client, self.path, field, maximum, self.order, self.maximum_results, self.equals)

    def order_by(self, field):
        return _Query(self.client, self.path, self.field, self.maximum, field, self.maximum_results, self.equals)

    def limit(self, count):
        return _Query(self.client, self.path, self.field, self.maximum, self.order, count, self.equals)

    def stream(self, transaction=None):
        if transaction is not None:
            assert not transaction.wrote, "query after transaction write"
        rows = [(path, value) for path, value in self.client.docs.items() if path[:-1] == self.path]
        if self.field:
            rows = [(path, value) for path, value in rows if value.get(self.field) <= self.maximum]
        if self.equals:
            rows = [(path, value) for path, value in rows if value.get(self.equals[0]) == self.equals[1]]
        rows.sort(key=lambda row: (row[1].get(self.order), row[0]) if self.order else row[0])
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

    def transaction(self):
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
    assert dispatched[0]['epoch'] == first['epoch'] + 1
    assert registry.finish_job('a', 'lost', dispatched[0]['epoch'], 'failed', firestore_client=db, now=expired)
    assert uid_sequencer.kick('a')
    assert dispatched[-1]['job_id'] == 'next'


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


def test_burst_admission_only_writes_append_only_pending_documents(db):
    with ThreadPoolExecutor(max_workers=20) as pool:
        assert all(pool.map(lambda index: _register('heavy', f'job-{index}', index, db=db), range(100)))
    assert registry.get_owner('heavy', firestore_client=db) == {}
    assert len(db.docs) == 100


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
    assert registry.get_owner('heavy', firestore_client=db) == {}


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
        assert registry.get_owner(job_id) == {}
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
    assert len(retirement.docs) == 1
    assert registry.pending_head('a')['job_id'] == 'old-050'
    assert registry.get_owner('a') == {}


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
        assert registry.get_owner(uid) == {}
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
    assert registry.get_owner('a') == {}
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
    assert registry.get_owner('a') == {}
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
    assert registry.get_owner('a') == {}
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
    assert registry.get_owner('a') == {}
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
