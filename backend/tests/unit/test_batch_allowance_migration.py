"""Page barriers, owner isolation and attempt pacing for the operator migration.

Orchestration tests use a bounded metadata query stub and the strict transaction
fixture; real commit/rollback/retry behavior is covered by the emulator suite.
"""

from collections import Counter
from concurrent.futures import Future
from copy import deepcopy
from threading import Barrier, Event, Lock, Thread
from types import SimpleNamespace
import time

import pytest

from database import batch_pipeline_allowance_migration as migration
from database.batch_pipeline_allowance_hold import OWNERS, STATE
from database.batch_pipeline_store import FirestoreStore, FirestoreTransaction
from database.batch_pipeline_transaction_attempt import prepare_transaction
from scripts import batch_pipeline_allowance_migration as cli
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot


class Page:
    def __init__(self, store):
        self.store = store
        self.after = ''

    def order_by(self, field):
        assert field == '__name__'
        return self

    def start_after(self, cursor):
        self.after = cursor['__name__'].id
        return self

    def limit(self, size):
        self.size = size
        return self

    def select(self, fields):
        assert fields in ([], ['owner_key'])
        self.fields = fields
        return self

    def stream(self):
        rows = []
        for (collection, key), value in sorted(self.store.client.rows.items()):
            if collection != 'batch_pipeline_dev_jobs' or key <= self.after or value['state'] != 'retry':
                continue
            snapshot = StrictFirestoreSnapshot({field: value[field] for field in self.fields})
            snapshot.reference = self.store.client.collection(collection).document(key)
            rows.append(snapshot)
        return iter(rows[: self.size])


@pytest.fixture
def h(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED', raising=False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_generation_memo":0,"privacy_negative_lookup_cache":0}')
    client = StrictFirestore()
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    monkeypatch.setattr(migration, 'candidates', lambda store: Page(store))

    def seed(key, owner='owner'):
        client.rows['users', owner] = {'data_protection_level': 'standard'}
        client.rows['batch_pipeline_dev_jobs', key] = {
            'segment_id': key,
            'owner_id': owner,
            'owner_key': owner,
            'state': 'retry',
            'compute_decision': {'outcome': 'held', 'reason': 'allowance_exhausted'},
            'retry_started_at': 2,
            'privacy_generation': 0,
            'audio_uri': f'gs://synthetic/{key}',
        }

    return SimpleNamespace(
        store=store, client=client, seed=seed, marker=('batch_pipeline_dev_migrations', migration.KEY)
    )


def test_default_order_and_checkpoint_cursor(h, monkeypatch):
    for key in ('c', 'a', 'b'):
        h.seed(key)
    seen = []
    original = migration.park

    def park(tx, job, now):
        assert h.marker not in h.client.rows
        seen.append(job['segment_id'])
        return original(tx, job, now)

    monkeypatch.setattr(migration, 'park', park)
    assert migration.apply_page(h.store, 10, size=2) == {'examined': 2, 'parked': 2, 'fenced': 0, 'complete': False}
    assert seen == ['a', 'b']
    assert h.client.rows[h.marker]['after'] == 'b'
    monkeypatch.setattr(migration, 'park', original)
    assert migration.apply_page(h.store, 11, size=2)['parked'] == 1
    assert h.client.rows[h.marker]['after'] is None


def test_concurrent_owners_serialize_through_commit_and_checkpoint_waits(h, monkeypatch):
    for key, owner in [('a', 'one'), ('b', 'two'), ('c', 'one'), ('d', 'two')]:
        h.seed(key, owner)
    first_rows = Barrier(2, timeout=5)
    lock = Lock()
    active = Counter()
    seen = []
    original = h.store.run

    def run(body, **options):
        owner = []

        def wrapped(tx):
            result = body(tx)
            key = next(key for table, key in tx.writes if table == 'jobs')
            value = tx.writes['jobs', key]
            owner.append(value['owner_key'])
            with lock:
                active[owner[0]] += 1
                assert active[owner[0]] == 1
                seen.append(key)
            if key in ('a', 'b'):
                first_rows.wait()
            assert h.marker not in h.client.rows
            return result

        try:
            return original(wrapped, **options)  # Includes flush and commit, not just park().
        finally:
            if owner:
                with lock:
                    active[owner[0]] -= 1

    monkeypatch.setattr(h.store, 'run', run)
    report = migration.apply_page(h.store, 10, size=4, concurrency=2)
    assert report == {'examined': 4, 'parked': 4, 'fenced': 0, 'complete': False}
    assert seen.index('a') < seen.index('c') and seen.index('b') < seen.index('d')
    assert h.client.rows[h.marker]['after'] == 'd'
    for owner in ('one', 'two'):
        assert h.client.rows['batch_pipeline_dev_allowance_holds', owner]['held_count'] == 2


def test_first_error_stops_new_rows_drains_inflight_and_never_checkpoints(h, monkeypatch):
    for key in ('a', 'b', 'c', 'd'):
        h.seed(key, key)
    entered = Barrier(2, timeout=5)
    release = Event()
    failed = Event()
    finished = Future()
    seen = []
    original = migration.park

    def park(tx, job, now):
        key = job['segment_id']
        seen.append(key)
        entered.wait()
        if key == 'a':
            failed.set()
            raise RuntimeError('synthetic failure')
        assert release.wait(5)
        return original(tx, job, now)

    monkeypatch.setattr(migration, 'park', park)

    def apply():
        try:
            with pytest.raises(RuntimeError, match='synthetic failure'):
                migration.apply_page(h.store, 10, concurrency=2)
            finished.set_result(None)
        except BaseException as error:
            finished.set_exception(error)

    thread = Thread(target=apply)
    thread.start()
    try:
        assert failed.wait(5)
        assert not finished.done() and h.marker not in h.client.rows
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    finished.result(timeout=1)
    assert sorted(seen) == ['a', 'b']
    assert h.marker not in h.client.rows


def test_fenced_rows_still_report_and_advance(h, monkeypatch):
    h.seed('a', 'one')
    h.seed('b', 'two')
    h.client.rows['account_deletions', 'one'] = {'wipe_status': 'pending'}
    assert migration.apply_page(h.store, 10, concurrency=2) == {
        'examined': 2,
        'parked': 1,
        'fenced': 1,
        'complete': True,
    }
    assert h.client.rows['batch_pipeline_dev_jobs', 'a']['state'] == 'retry'
    assert ('batch_pipeline_dev_allowance_holds', 'one') not in h.client.rows


def test_replaying_already_committed_rows_is_a_noop(h):
    h.seed('a')
    h.seed('b')
    snapshots = list(Page(h.store).limit(100).select(['owner_key']).stream())
    limiter = migration.RowRateLimiter()
    assert migration._apply_rows(h.store, snapshots, 10, 2, limiter) == (2, 0)
    before = deepcopy(h.client.rows)
    assert migration._apply_rows(h.store, snapshots, 11, 2, limiter) == (0, 0)
    assert h.client.rows == before
    assert h.client.rows['batch_pipeline_dev_allowance_holds', 'owner']['held_count'] == 2
    assert all(h.client.rows['batch_pipeline_dev_jobs', key]['state'] == STATE for key in ('a', 'b'))


def test_discovery_owner_is_only_a_hint_and_is_rechecked(h):
    h.seed('a', 'one')
    snapshots = list(Page(h.store).limit(100).select(['owner_key']).stream())
    h.client.rows['batch_pipeline_dev_jobs', 'a']['owner_key'] = 'two'
    with pytest.raises(RuntimeError, match='owner changed'):
        migration._apply_rows(h.store, snapshots, 10, 2, migration.RowRateLimiter())
    assert h.marker not in h.client.rows
    assert h.client.rows['batch_pipeline_dev_jobs', 'a']['state'] == 'retry'


def test_owner_change_is_a_typed_page_replay_stop(h):
    h.seed('a', 'one')
    snapshots = list(Page(h.store).limit(100).select(['owner_key']).stream())
    h.client.rows['batch_pipeline_dev_jobs', 'a']['owner_key'] = 'two'
    with pytest.raises(migration.MigrationOwnerChanged):
        migration._apply_rows(h.store, snapshots, 10, 2, migration.RowRateLimiter())


def test_concurrent_page_failure_keeps_every_owner_groups_error(h, monkeypatch):
    h.seed('a', 'one')
    h.seed('b', 'two')
    snapshots = list(Page(h.store).limit(100).select(['owner_key']).stream())
    both = Barrier(2, timeout=10)

    def park(tx, job, now):
        both.wait()
        raise (KeyError if job['owner_key'] == 'one' else ValueError)('synthetic')

    monkeypatch.setattr(migration, 'park', park)
    with pytest.raises((KeyError, ValueError)) as stop:
        migration._apply_rows(h.store, snapshots, 10, 2, migration.RowRateLimiter())
    siblings = stop.value.migration_sibling_errors
    assert {type(stop.value), *map(type, siblings)} == {KeyError, ValueError}
    assert len(siblings) == 1
    assert h.marker not in h.client.rows


def test_concurrent_page_siblings_reach_the_operator_stop_line(h, monkeypatch):
    h.seed('a', 'one')
    h.seed('b', 'two')
    snapshots = list(Page(h.store).limit(100).select(['owner_key']).stream())
    both = Barrier(2, timeout=10)

    def park(tx, job, now):
        both.wait()
        if job['owner_key'] == 'one':
            raise migration.MigrationOwnerChanged('retry the page')
        raise ValueError('synthetic')

    monkeypatch.setattr(migration, 'park', park)
    with pytest.raises((migration.MigrationOwnerChanged, ValueError)) as stop:
        migration._apply_rows(h.store, snapshots, 10, 2, migration.RowRateLimiter())
    report = cli.error_report(stop.value)
    assert report['errors'] == 2
    assert report['retryable'] is False
    assert len(report['sibling_types']) == 1


def test_prefetch_maps_unordered_batchget_and_preserves_absence_and_copies(h):
    h.seed('a')
    tx = FirestoreTransaction(h.client, h.store.namespace, h.client.transaction())
    migration._prefetch_row(tx, 'a', 'owner')
    assert tx.get_existing(OWNERS, 'owner') is None
    first = tx.get('jobs', 'a')
    first['state'] = 'mutated'
    assert tx.get('jobs', 'a')['state'] == 'retry'
    tx.put(OWNERS, 'owner', {'held_count': 1})
    assert tx.get_existing(OWNERS, 'owner') == {'held_count': 1}


def test_rate_bucket_is_shared_across_pages_retries_and_has_no_idle_burst(h):
    clock = [0.0]

    class Stop:
        def is_set(self):
            return False

        def wait(self, delay):
            clock[0] += delay + 1e-12

    limiter = migration.RowRateLimiter(50, clock=lambda: clock[0])
    stop = Stop()
    starts = []
    for _page in range(2):
        for _attempt in range(4):
            limiter.acquire(stop)
            starts.append(clock[0])
    assert starts == pytest.approx([index / 50 for index in range(8)])
    clock[0] += 10  # Idle time cannot refill more than one token.
    limiter.acquire(stop)
    previous = clock[0]
    limiter.acquire(stop)
    assert clock[0] - previous == pytest.approx(1 / 50)


def test_each_transaction_retry_takes_a_permit(h, monkeypatch):
    h.seed('a')
    limiter = migration.RowRateLimiter()
    starts = []
    monkeypatch.setattr(limiter, 'acquire', lambda stopped: starts.append(True))
    original = h.store.run

    def retry(body, **options):
        # Discard the first attempt before flush; the emulator test proves real retries.
        options['before_attempt']()
        body(FirestoreTransaction(h.client, h.store.namespace, h.client.transaction()))
        return original(body, **options)

    monkeypatch.setattr(h.store, 'run', retry)
    assert migration.apply_page(h.store, 10, concurrency=2, rate_limiter=limiter)['parked'] == 1
    assert len(starts) == 2


def test_stop_interrupts_rate_wait():
    limiter = migration.RowRateLimiter(0.001)
    stopped = Event()
    limiter.acquire(stopped)
    stopped.set()
    with pytest.raises(migration._Stopped):
        limiter.acquire(stopped)


def test_low_rate_waits_before_begin_on_every_sdk_attempt(h):
    clock = [0.0]
    starts = []

    class Stop:
        def is_set(self):
            return False

        def wait(self, delay):
            assert transaction._id is None
            clock[0] += delay + 1e-9

    limiter = migration.RowRateLimiter(0.001, clock=lambda: clock[0])

    def permit():
        assert transaction._id is None
        limiter.acquire(Stop())
        starts.append(clock[0])

    transaction = prepare_transaction(h.client, permit)
    for _attempt in range(3):
        transaction._clean_up()  # The pinned SDK does this before every _begin.
        transaction._begin()
    assert starts == pytest.approx([0, 1000, 2000])


def test_cancel_before_begin_is_not_masked_by_sdk_rollback(h):
    stopped = Event()
    stopped.set()
    limiter = migration.RowRateLimiter(50)
    transaction = prepare_transaction(h.client, lambda: limiter.acquire(stopped))
    with pytest.raises(migration._Stopped):
        migration.firestore.transactional(lambda tx: pytest.fail('cancelled body ran'))(transaction)
    assert transaction._id is None


def test_concurrent_workers_share_one_bucket():
    limiter = migration.RowRateLimiter(50)
    barrier = Barrier(9, timeout=5)
    stopped = Event()
    finished = []

    def acquire():
        barrier.wait()
        limiter.acquire(stopped)
        finished.append(time.monotonic())

    threads = [Thread(target=acquire) for _ in range(8)]
    for thread in threads:
        thread.start()
    before = time.monotonic()
    barrier.wait()
    for thread in threads:
        thread.join(5)
    assert all(not thread.is_alive() for thread in threads)
    assert len(finished) == 8
    assert max(finished) - before >= 7 / 50 - 0.005


@pytest.mark.parametrize('rate', [0, -1, float('nan'), float('inf')])
def test_invalid_rate(rate):
    with pytest.raises(ValueError):
        migration.RowRateLimiter(rate)


@pytest.mark.parametrize('concurrency', [0, 33])
def test_invalid_concurrency(h, concurrency):
    with pytest.raises(ValueError, match='concurrency'):
        migration.apply_page(h.store, 10, concurrency=concurrency)
