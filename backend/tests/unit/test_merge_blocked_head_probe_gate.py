"""Blocked-head merge drains probe before they transact (x2239/x998 exhaustion family).

Every ordered-merge drain used to open a strict ``batch_merge_commit``
transaction whose first act was a query for the owner's earliest pending row.
While any capture of that owner is still in flight, that head is a leased row
whose document every lease heartbeat keeps rewriting, so the drain joined the
hot row's abort set just to conclude ``blocked`` — and under load burned its
whole five-attempt ladder against it:

    firestore_transaction_contention operation=batch_merge_commit attempt=5/5 outcome=exhausted
    event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted

``OrderedMerge.commit_next`` now probes the head outside any transaction
(``Store.head_pending``) and only opens the strict transaction when it can
commit or owes the durable depth-cap hold marker. This suite pins:

1. Gate decisions: plain blocked heads and probe-empty owners open no
   transaction and return ``None`` with the exact ``blocked``/``held`` facts
   the strict body would have recorded; ready heads and catch-up heads
   (fresh-first, depth marker) still transact exactly as before.
2. Probe failures keep the transaction as the authority: every
   ``GoogleAPICallError`` abandons the gate and the strict query raises or
   decides exactly as it did before the gate existed.
3. The depth-cap hold marker is still written transactionally, only when the
   probe twins say it is owed, and the in-memory ``held_owners`` hint parity
   is preserved on every path.
4. Head-wait bypass and recovered-release flows through the gate keep their
   re-verify contracts, entry flags, log taxonomy and ordering.
5. On the real store class with a heartbeat-storm client, blocked-head drains
   survive without a single transaction attempt or ladder sleep; exhaustion
   stays reachable only from genuine commits.
6. The new probe surface behaves identically across the Firestore store, the
   state-machine fake and the pipeline simulator.

Failure-Class: FC-blocked-head-merge-drains-join-the-hot-row-abort-set
"""

import asyncio
import logging
from copy import deepcopy
from itertools import permutations
from unittest.mock import AsyncMock, Mock

import pytest
from google.api_core.exceptions import Aborted, DeadlineExceeded, FailedPrecondition, ServiceUnavailable

from database import batch_pipeline_store as storage
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.firestore_transaction_retry import FirestoreContentionExhausted
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline import merge as merge_module
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.batch_pipeline.serving import Serving

W = 60
NOW = 100_000.0
OWNER = owner_key('heavy')
CATCH_UP = 'catch_up'
FRESH = 'fresh'
NAMESPACE = 'batch_pipeline_dev'


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


class CountingStore:
    """MemoryStore facade counting transaction runs (with resolved labels) and probe reads."""

    def __init__(self, inner=None):
        self.inner = inner if inner is not None else MemoryStore()
        self.runs = 0
        self.run_operations = []
        self.probed = []
        self.head_pending_error = None
        self.longest_ready_error = None

    @property
    def rows(self):
        return self.inner.rows

    @rows.setter
    def rows(self, value):
        self.inner.rows = value

    def reset_counts(self):
        self.runs = 0
        self.run_operations = []
        self.probed = []

    def run(self, body, *, operation=None):
        from database.batch_pipeline_transaction_labels import current_operation

        self.runs += 1
        self.run_operations.append(operation or current_operation())
        return self.inner.run(body, operation=operation)

    def probe(self, table, key):
        self.probed.append((table, key))
        return self.inner.probe(table, key)

    def head_pending(self, key):
        self.probed.append(('jobs', key))
        if self.head_pending_error is not None:
            raise self.head_pending_error
        return self.inner.head_pending(key)

    def longest_ready_pending(self, key):
        if self.longest_ready_error is not None:
            raise self.longest_ready_error
        return self.inner.longest_ready_pending(key)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def admitted(captures, store=None):
    """One owner's rows, all leased; ``captures`` maps segment -> capture_at."""
    store = store or CountingStore()
    queue = Scheduler(store)
    for segment, capture in captures.items():
        queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, len(captures))}
    assert set(leases) == set(captures)
    return store, queue, leases


def admitted_by_class(rows, store=None):
    """``rows`` maps segment -> (capture_at, class); fresh rows lag 60 s, catch-up 2 h."""
    store = store or CountingStore()
    queue = Scheduler(store)
    for segment, (capture, kind) in rows.items():
        lag = 7200 if kind == CATCH_UP else 60
        queue.enqueue(item(segment, capture=capture, duration=10), capture + 10 + lag)
        if kind is None:
            store.rows['jobs', segment].pop('fresh_capture')  # Admitted before the stamp, or record lane.
    leases = {lease.item.segment_id: lease for lease in queue.pull(NOW, len(rows))}
    assert set(leases) == set(rows)
    return store, queue, leases


def complete(queue, leases, segment, now=NOW):
    queue.store.rows['jobs', segment]['lease_until'] = now + 1
    assert queue.complete(WorkResult(segment, f'gs://results/{segment}'), leases[segment].token, now)


def merge_for(store, depth=0, wait=0):
    return OrderedMerge(store, head_wait_seconds=wait, catch_up_depth=depth)


def set_state(store, segment, state):
    store.rows['jobs', segment]['state'] = state


def at_cap(store, sequence=6, watermark='w5', done=1):
    """Fabricate the owner row so probe and transaction read ``sequence - done`` unprojected rows."""
    store.rows['owners', OWNER] = {'log_sequence': sequence, 'projection_watermark': watermark}
    if watermark is not None:
        store.rows['results', watermark] = {'log_sequence': done}


class _AbortTx:
    """Minimal firestore_v1.Transaction: commits abort while a heartbeat storm is
    invalidating any document this transaction read. Staged writes land only on
    a successful commit, exactly like the real transaction."""

    _max_attempts = 1
    _read_only = False
    _id = None

    def __init__(self, state):
        self.state = state
        self.reads = set()
        self.commits = 0
        self.pending_sets = {}
        self.pending_updates = {}

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _address(self, ref):
        return (ref.collection_name, ref.key)

    def set(self, ref, value):
        self.pending_sets[self._address(ref)] = deepcopy(value)

    def update(self, ref, fields):
        self.pending_updates.setdefault(self._address(ref), {}).update(deepcopy(fields))

    def _commit(self):
        self.commits += 1
        self.state.commits += 1
        if self.reads and self.state.aborts_remaining > 0:
            self.state.aborts_remaining -= 1
            self.pending_sets.clear()
            self.pending_updates.clear()
            raise Aborted('synthetic heartbeat contention on a read document')
        for (collection, key), value in self.pending_sets.items():
            self.state.rows[(collection, key)] = deepcopy(value)
        for (collection, key), fields in self.pending_updates.items():
            self.state.rows.setdefault((collection, key), {}).update(deepcopy(fields))
        self.pending_sets.clear()
        self.pending_updates.clear()
        self._id = None

    def _rollback(self):
        self.pending_sets.clear()
        self.pending_updates.clear()
        self._id = None


class _StormSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return deepcopy(self._data) if self._data is not None else {}


class _StormDocRef:
    def __init__(self, client, collection_name, key):
        self.client = client
        self.collection_name = collection_name
        self.key = key

    def get(self, transaction=None):
        if transaction is not None:
            transaction.reads.add((self.collection_name, self.key))
        return _StormSnapshot(self.client.rows.get((self.collection_name, self.key)))


class _StormQuery:
    def __init__(self, client, collection, filters=(), orders=(), limit=None):
        self.client = client
        self.collection = collection
        self.filters = filters
        self.orders = orders
        self._limit = limit

    def _copy(self, **kwargs):
        params = {'filters': self.filters, 'orders': self.orders, 'limit': self._limit}
        params.update(kwargs)
        return _StormQuery(self.client, self.collection, **params)

    def where(self, field, op, value):
        assert op == '==', 'the merge queries are equality-only'
        return self._copy(filters=self.filters + ((field, value),))

    def order_by(self, field):
        return self._copy(orders=self.orders + (field,))

    def limit(self, count):
        return self._copy(limit=count)

    def stream(self, transaction=None):
        rows = [
            (key, doc)
            for (collection, key), doc in sorted(self.client.rows.items())
            if collection == self.collection
            and all(doc.get(field) == value for field, value in self.filters)
            and all(field in doc for field in self.orders)
        ]
        rows.sort(key=lambda item: tuple(item[1][field] for field in self.orders) + (item[0],))
        page = rows[: self._limit] if self._limit is not None else rows
        if transaction is not None:
            for key, _doc in page:  # Firestore query-in-transaction read set: the matched documents.
                transaction.reads.add((self.collection, key))
        self.client.query_shapes.append(
            {
                'collection': self.collection,
                'filters': self.filters,
                'orders': self.orders,
                'limit': self._limit,
                'transactional': transaction is not None,
            }
        )
        return [_StormSnapshot(doc) for _key, doc in page]


class _StormCollection:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def document(self, key):
        return _StormDocRef(self.client, self.name, key)

    def where(self, field, op, value):
        return _StormQuery(self.client, self.name).where(field, op, value)

    def order_by(self, field):
        return _StormQuery(self.client, self.name).order_by(field)

    def limit(self, count):
        return _StormQuery(self.client, self.name).limit(count)


class StormClient:
    """Firestore client whose transactions abort while a heartbeat storm writes the
    documents they read. Point reads (no transaction) always succeed."""

    def __init__(self, rows=None, aborts=10**6):
        self.rows = dict(rows or {})
        self.aborts_remaining = aborts
        self.transactions = 0
        self.commits = 0
        self.query_shapes = []

    def transaction(self, max_attempts=5):
        self.transactions += 1
        return _AbortTx(self)

    def collection(self, name):
        return _StormCollection(self, name)


def storm_rows(head_state='leased'):
    """Two pending rows: ``a`` the hot in-flight head, ``b`` ready behind it."""
    return {
        (f'{NAMESPACE}_jobs', 'a'): {
            'segment_id': 'a',
            'owner_key': OWNER,
            'owner_id': 'heavy',
            'merge_pending': True,
            'state': head_state,
            'capture_at': 1,
            'priority': 0,
            'protocol_version': 1,
        },
        (f'{NAMESPACE}_jobs', 'b'): {
            'segment_id': 'b',
            'owner_key': OWNER,
            'owner_id': 'heavy',
            'merge_pending': True,
            'state': 'result_ready',
            'capture_at': 2,
            'priority': 0,
            'ready_at': 10.0,
            'result': {'uri': 'gs://results/b'},
            'protocol_version': 1,
        },
    }


class FakeClock:
    def __init__(self, now=100.0, jitter=0.0):
        self.now = now
        self.jitter = jitter
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def random_value(self):
        return self.jitter


def build_storm_store(monkeypatch, client, damper=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore(NAMESPACE, firestore_client=client, storm_damper=damper)


def silence_chain_sleep(monkeypatch):
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', lambda _seconds: None)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


class _Leader:
    def __init__(self, leads):
        self.leads = leads

    def acquire(self):
        return self.leads


class _FencedResultsStore(CountingStore):
    """Privacy flush refuses any transaction that would commit result row ``f``."""

    def run(self, body, *, operation=None):
        from database.batch_pipeline_transaction_labels import current_operation

        self.runs += 1
        self.run_operations.append(operation or current_operation())
        with self.inner.lock:
            snapshot = deepcopy(self.inner.rows)
            result = body(MemoryTransaction(snapshot))
            if ('results', 'f') in snapshot and ('results', 'f') not in self.inner.rows:
                raise BatchPrivacyBlocked('fenced')
            self.inner.rows = snapshot
            return result


class StaleWaiterStore(CountingStore):
    """The head-wait probe reports a stale ``ready_at``; the transaction must re-verify."""

    def longest_ready_pending(self, key):
        row = self.inner.longest_ready_pending(key)
        if row:
            return {**row, 'ready_at': row['ready_at'] - 1000}
        return row


# --------------------------------------------------------------------------
# Section A — gate decisions: blocked heads open no transaction
# --------------------------------------------------------------------------


def blocked_head_setup(state='leased', captures=None):
    """Rows where ``a`` is a blocked head and ``b`` is ready behind it."""
    store, queue, leases = admitted(captures or {'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    set_state(store, 'a', state)
    return store, queue, leases


def test_blocked_leased_head_opens_no_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_blocked_leased_head_returns_none_without_writes():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    before = deepcopy(store.rows)
    assert merge.commit_next('heavy', 10) is None
    assert store.rows == before


def test_blocked_queued_head_opens_no_transaction():
    store, _queue, _leases = admitted({'a': 1, 'b': 2})  # Never pulled: the head is queued.
    complete(_queue, _leases, 'b', 10)
    merge = merge_for(store)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_blocked_retry_head_opens_no_transaction():
    store, _queue, _leases = blocked_head_setup('retry')
    merge = merge_for(store)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_blocked_record_pending_head_opens_no_transaction():
    store, _queue, _leases = blocked_head_setup('record_pending')
    merge = merge_for(store)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_blocked_head_drain_discards_the_held_owner_hint():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    merge.held_owners.add('heavy')
    assert merge.commit_next('heavy', 10) is None
    assert merge.held_owners == set()


def test_blocked_head_drain_emits_no_log_lines(caplog):
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    store.reset_counts()
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.merge'):
        assert merge.commit_next('heavy', 10) is None
    assert caplog.records == []


def test_blocked_head_drain_makes_no_probe_writes():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    before = deepcopy(store.rows)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.rows == before
    assert ('merge_holds', OWNER) not in store.probed


def test_blocked_head_drain_reads_only_hint_surfaces():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert [table for table, _key in store.probed] == ['jobs']


def test_blocked_head_drain_does_not_touch_the_owner_document():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert ('owners', OWNER) not in store.probed


def test_ready_head_opens_exactly_one_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    complete(_queue, _leases, 'a', 20)
    merge = merge_for(store)
    store.reset_counts()
    entry = merge.commit_next('heavy', 20)
    assert entry['segment_id'] == 'a'
    assert store.runs == 1


def test_two_ready_commits_land_across_separate_drains():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'b', 20)
    merge = merge_for(store)
    first = merge.commit_next('heavy', 20)
    assert first['segment_id'] == 'a'
    store.reset_counts()
    second = merge.commit_next('heavy', 20)
    assert second['segment_id'] == 'b' and store.runs == 1


def test_newly_leased_head_after_a_commit_takes_the_gate_not_the_transaction():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'b', 20)
    merge = merge_for(store)
    merge.commit_next('heavy', 20)  # Commits a.
    store.rows['jobs', 'c'] = dict(
        store.rows['jobs', 'b'], segment_id='c', capture_at=0, state='leased', result={}
    )  # A redriven earlier capture is in flight again: it is now the hot head.
    tail = store.rows['owners', OWNER]['log_tail']
    store.reset_counts()
    assert merge.commit_next('heavy', 20) is None
    assert store.runs == 0 and store.rows['owners', OWNER]['log_tail'] == tail


def test_ready_head_entry_shape_parity():
    store, _queue, _leases = blocked_head_setup('leased')
    complete(_queue, _leases, 'a', 20)
    merge = merge_for(store)
    entry = merge.commit_next('heavy', 20)
    assert entry['log_sequence'] == 1 and entry['previous_segment_id'] is None
    assert 'head_wait_bypass' not in entry and 'fresh_first' not in entry and 'recovered_release' not in entry
    assert entry['late_capture'] is False


def test_ready_head_drain_labels_its_transaction_batch_merge_commit():
    store, _queue, _leases = blocked_head_setup('leased')
    complete(_queue, _leases, 'a', 20)
    merge = merge_for(store)
    store.reset_counts()
    merge.commit_next('heavy', 20)
    assert store.run_operations == ['batch_merge_commit']


def test_two_ready_commits_advance_sequence_tail_and_revision():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'b', 20)
    merge = merge_for(store)
    merge.commit_next('heavy', 20)
    entry = merge.commit_next('heavy', 20)
    owner = store.rows['owners', OWNER]
    assert entry['log_sequence'] == 2 and entry['previous_segment_id'] == 'a'
    # The scheduler's completion and the merge commit each advance the owner revision.
    assert owner['log_tail'] == 'b' and owner['revision'] == 4


def test_shadow_ready_head_still_opens_the_strict_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    complete(_queue, _leases, 'a', 20)
    store.rows['jobs', 'a']['shadow'] = True
    merge = merge_for(store)
    store.reset_counts()
    assert merge.commit_next('heavy', 20) is None
    assert store.runs == 1


def test_shadow_blocked_head_opens_no_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    store.rows['jobs', 'a']['shadow'] = True
    merge = merge_for(store)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_probe_empty_owner_opens_no_transaction():
    store = CountingStore()
    merge = merge_for(store)
    assert merge.commit_next('heavy', NOW) is None
    assert store.runs == 0


def test_probe_empty_owner_discards_the_held_hint():
    store = CountingStore()
    merge = merge_for(store)
    merge.held_owners.add('heavy')
    merge.commit_next('heavy', NOW)
    assert merge.held_owners == set()


def test_probe_empty_owner_with_release_still_runs_the_strict_path():
    store = CountingStore()
    merge = merge_for(store)
    assert merge.commit_next('heavy', NOW, release=['zz']) is None
    assert store.runs == 1


def test_probe_empty_owner_with_release_pops_the_unknown_row():
    store = CountingStore()
    merge = merge_for(store)
    release = ['zz']
    assert merge.commit_next('heavy', NOW, release=release) is None
    assert release == []


def test_probe_empty_after_all_rows_committed_opens_no_transaction():
    store, queue, leases = admitted({'a': 1})
    complete(queue, leases, 'a', 10)
    merge = merge_for(store)
    merge.commit_next('heavy', 10)  # Commits; the row leaves merge_pending.
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_quarantined_head_stops_being_pending_for_probe_and_transaction_alike():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    store.rows['jobs', 'a']['merge_pending'] = False  # Terminal quarantine removed it.
    merge = merge_for(store)
    store.reset_counts()
    entry = merge.commit_next('heavy', 10)
    assert entry['segment_id'] == 'b'
    assert store.runs == 1


def test_blocked_head_state_from_the_probe_matches_the_body_conclusion():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    head = store.head_pending(OWNER)
    assert head['segment_id'] == 'a' and head['state'] == 'leased'


# --------------------------------------------------------------------------
# Section B — probe failures keep the transaction as the authority
# --------------------------------------------------------------------------


def probe_error_setup(error):
    store, _queue, _leases = blocked_head_setup('leased')
    store.head_pending_error = error
    merge = merge_for(store)
    store.reset_counts()
    return store, merge


def test_probe_service_unavailable_falls_back_to_the_strict_transaction():
    store, merge = probe_error_setup(ServiceUnavailable('probe down'))
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 1


def test_probe_deadline_exceeded_falls_back_to_the_strict_transaction():
    store, merge = probe_error_setup(DeadlineExceeded('probe slow'))
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 1


def test_probe_failed_precondition_falls_back_to_the_strict_transaction():
    store, merge = probe_error_setup(FailedPrecondition('index missing'))
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 1


def test_probe_failure_with_ready_head_still_commits():
    store, _queue, _leases = blocked_head_setup('leased')
    complete(_queue, _leases, 'a', 20)
    store.head_pending_error = ServiceUnavailable('probe down')
    merge = merge_for(store)
    entry = merge.commit_next('heavy', 20)
    assert entry['segment_id'] == 'a'


def test_probe_failure_does_not_arm_or_sleep_anything():
    store, merge = probe_error_setup(ServiceUnavailable('probe down'))
    merge.commit_next('heavy', 10)
    assert store.run_operations == ['batch_merge_commit']


def test_probe_failure_on_empty_owner_still_opens_the_strict_path():
    store = CountingStore()
    store.head_pending_error = ServiceUnavailable('probe down')
    merge = merge_for(store)
    assert merge.commit_next('heavy', NOW) is None
    assert store.runs == 1


# --------------------------------------------------------------------------
# Section C — the durable depth-cap hold marker stays transactional
# --------------------------------------------------------------------------


def test_under_cap_blocked_head_opens_no_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=2, done=1)  # Awaiting 1 < depth 4.
    merge = merge_for(store, depth=4)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_under_cap_blocked_head_writes_no_marker():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=2, done=1)
    merge = merge_for(store, depth=4)
    merge.commit_next('heavy', 10)
    assert store.rows.get(('merge_holds', OWNER)) is None


def test_under_cap_blocked_head_discards_the_held_hint():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=2, done=1)
    merge = merge_for(store, depth=4)
    merge.held_owners.add('heavy')
    merge.commit_next('heavy', 10)
    assert merge.held_owners == set()


def test_at_cap_unmarked_blocked_head_runs_the_marker_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)  # Awaiting 5 >= depth 4.
    merge = merge_for(store, depth=4)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 1


def test_at_cap_unmarked_blocked_head_writes_the_durable_marker():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    merge.commit_next('heavy', 10)
    assert store.rows['merge_holds', OWNER]['held'] is True


def test_at_cap_unmarked_blocked_head_adds_the_held_owner_hint():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    merge.commit_next('heavy', 10)
    assert merge.held_owners == {'heavy'}


def test_at_cap_marked_blocked_head_opens_no_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    merge = merge_for(store, depth=4)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_at_cap_marked_blocked_head_still_adds_the_held_owner_hint():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    merge = merge_for(store, depth=4)
    merge.commit_next('heavy', 10)
    assert merge.held_owners == {'heavy'}


def test_at_cap_marked_blocked_head_keeps_the_marker_untouched():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    merge = merge_for(store, depth=4)
    merge.commit_next('heavy', 10)
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_missing_watermark_result_row_counts_nothing_unprojected():
    """Parity with the strict body: a missing watermark row reads as zero done,
    so the probe twin also reports the owner under the depth cap."""
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, watermark='w5')
    store.rows.pop(('results', 'w5'))  # The watermark row was purged.
    merge = merge_for(store, depth=4)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0
    assert store.rows.get(('merge_holds', OWNER)) is None


def test_missing_watermark_field_counts_everything_unprojected():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, watermark=None)
    merge = merge_for(store, depth=4)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.runs == 1


def test_missing_owner_document_is_under_cap():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store, depth=4)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_depth_cap_boundary_exactly_at_cap_owes_the_marker():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=4, done=1)  # Awaiting 3 == depth 3.
    merge = merge_for(store, depth=3)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.rows['merge_holds', OWNER]['held'] is True


def test_depth_cap_boundary_below_cap_skips():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=4, done=2)  # Awaiting 2 < depth 3.
    merge = merge_for(store, depth=3)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_depth_cap_zero_disables_the_marker_guard():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store, depth=0)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0
    assert store.rows.get(('merge_holds', OWNER)) is None


def test_marker_guard_decides_from_probe_reads_only():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert ('owners', OWNER) in store.probed
    assert ('results', 'w5') in store.probed
    assert ('merge_holds', OWNER) in store.probed


def test_probe_staleness_undershoot_delays_the_marker_one_drain():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    # The owners probe lags: it still reports the pre-commit sequence.
    store.rows['owners', OWNER]['log_sequence'] = 2
    merge = merge_for(store, depth=4)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0
    assert store.rows.get(('merge_holds', OWNER)) is None


def test_marker_guard_never_damps_the_commit_path():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'b', 20)
    at_cap(store, sequence=9, done=1)
    merge = merge_for(store, depth=4)
    store.reset_counts()
    entry = merge.commit_next('heavy', 20)
    assert entry['segment_id'] == 'a'
    assert store.runs == 1


def test_release_hold_clears_the_marker_below_the_cap():
    store = CountingStore()
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    store.rows['owners', OWNER] = {'log_sequence': 1}
    merge = merge_for(store, depth=4)
    merge.release_hold(OWNER)
    assert store.rows['merge_holds', OWNER]['held'] is False


def test_release_hold_force_clears_at_the_cap():
    store = CountingStore()
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    store.rows['owners', OWNER] = {'log_sequence': 9}
    merge = merge_for(store, depth=4)
    merge.release_hold(OWNER, force=True)
    assert store.rows['merge_holds', OWNER]['held'] is False


# --------------------------------------------------------------------------
# Section D — the head-wait bypass through the gate
# --------------------------------------------------------------------------


def bypass_setup():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)  # Head a stays leased; b has waited since 10.
    merge = merge_for(store, wait=W)
    store.reset_counts()
    return store, merge


def test_blocked_head_waits_until_w_before_any_bypass():
    store, merge = bypass_setup()
    assert merge.commit_next('heavy', 10 + W - 1) is None
    assert store.runs == 0


def test_blocked_head_bypass_at_w_opens_only_the_waiter_transaction():
    store, merge = bypass_setup()
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['segment_id'] == 'b'
    assert store.runs == 1


def test_bypass_entry_carries_the_head_wait_bypass_flag():
    store, merge = bypass_setup()
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['head_wait_bypass'] is True


def test_bypass_entry_is_not_late_capture():
    store, merge = bypass_setup()
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['late_capture'] is False and entry['log_sequence'] == 1


def test_bypass_advances_owner_tail_and_watermark():
    store, merge = bypass_setup()
    merge.commit_next('heavy', 10 + W)
    owner = store.rows['owners', OWNER]
    assert owner['log_tail'] == 'b' and owner['watermark'] == {'capture_at': 2, 'segment_id': 'b'}


def test_bypass_log_line_keeps_the_taxonomy(caplog):
    store, merge = bypass_setup()
    with caplog.at_level(logging.INFO, logger='utils.batch_pipeline.merge'):
        merge.commit_next('heavy', 10 + W)
    messages = [record.getMessage() for record in caplog.records]
    assert any("outcome=head_wait_bypass" in message and "wait_bucket=lt120" in message for message in messages)


def test_bypass_wait_bucket_reaches_the_ge1800_bucket(caplog):
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    merge = merge_for(store, wait=W)
    with caplog.at_level(logging.INFO, logger='utils.batch_pipeline.merge'):
        merge.commit_next('heavy', 10 + 3600)
    assert any('wait_bucket=ge1800' in record.getMessage() for record in caplog.records)


def test_waiter_probe_failure_falls_back_to_strict_order_warning(caplog):
    store, merge = bypass_setup()
    store.longest_ready_error = FailedPrecondition('index missing')
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        assert merge.commit_next('heavy', 10 + W) is None
    assert any('outcome=head_wait_unavailable' in record.getMessage() for record in caplog.records)


def test_waiter_probe_transient_failure_logs_probe_retry_and_returns_none(caplog):
    store, merge = bypass_setup()
    store.longest_ready_error = ServiceUnavailable('probe down')
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        assert merge.commit_next('heavy', 10 + W) is None
    assert any('outcome=head_wait_probe_retry' in record.getMessage() for record in caplog.records)


def test_head_wait_zero_disables_the_bypass():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store, wait=0)
    assert merge.commit_next('heavy', 10**6) is None


def test_waiter_must_still_be_pending_and_ready_when_the_transaction_reverifies():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    store.rows['jobs', 'b']['ready_at'] = 99  # Moved after the probe stamped its copy.
    merge = merge_for(store, wait=W)
    assert merge.commit_next('heavy', 10 + W) is None


def test_stale_probe_ready_at_never_commits_the_waiter():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    merge = merge_for(StaleWaiterStore(store), wait=W)
    assert merge.commit_next('heavy', 10 + W) is None


def test_rows_without_ready_at_never_start_a_bypass():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    del store.rows['jobs', 'b']['ready_at']  # Written by a pre-change worker.
    merge = merge_for(store, wait=W)
    assert merge.commit_next('heavy', 10**6) is None


def test_bypass_releases_ready_rows_in_capture_order():
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3, 'd': 4})
    complete(queue, leases, 'd', 5)
    complete(queue, leases, 'c', 20)
    complete(queue, leases, 'b', 40)
    merge = merge_for(store, wait=W)
    assert [entry['segment_id'] for entry in [merge.commit_next('heavy', 5 + W)]] == ['b']
    assert [entry['segment_id'] for entry in [merge.commit_next('heavy', 5 + W)]] == ['c']
    assert [entry['segment_id'] for entry in [merge.commit_next('heavy', 5 + W)]] == ['d']


def test_each_bypass_release_opens_exactly_one_transaction():
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3})
    complete(queue, leases, 'c', 5)
    complete(queue, leases, 'b', 20)
    merge = merge_for(store, wait=W)
    store.reset_counts()
    merge.commit_next('heavy', 5 + W)
    assert store.runs == 1
    store.reset_counts()
    merge.commit_next('heavy', 5 + W)
    assert store.runs == 1


def test_bypassed_head_appends_late_once_ready():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    merge = merge_for(store, wait=W)
    merge.commit_next('heavy', 10 + W)
    complete(queue, leases, 'a', 100)
    late = merge.commit_next('heavy', 101)
    assert late['segment_id'] == 'a' and late['late_capture'] is True and 'head_wait_bypass' not in late
    assert late['previous_segment_id'] == 'b' and late['log_sequence'] == 2


def test_recovered_reentry_row_uses_its_stamped_ready_at_through_the_gate():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    store.rows['jobs', 'b'].update(
        state='result_ready', merge_pending=True, recovery_state='recovered', ready_at=500, result={'r': 'b'}
    )
    merge = merge_for(store, wait=W)
    assert merge.commit_next('heavy', 500 + W - 1) is None
    entry = merge.commit_next('heavy', 500 + W)
    assert entry['segment_id'] == 'b' and entry['recovery_version'] == 1 and entry['head_wait_bypass'] is True


def test_bypass_at_cap_with_catchup_waiter_holds_the_row():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    store.rows['jobs', 'b']['fresh_capture'] = False  # The waiter itself is catch-up.
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4, wait=W)
    assert merge.commit_next('heavy', 10 + W) is None
    assert merge.held_owners == {'heavy'}


def test_bypass_at_cap_with_fresh_waiter_still_commits():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    store.rows['jobs', 'b']['fresh_capture'] = True
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4, wait=W)
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['segment_id'] == 'b' and entry['head_wait_bypass'] is True


def test_blocked_head_bypass_still_labels_its_transaction():
    store, merge = bypass_setup()
    merge.commit_next('heavy', 10 + W)
    assert store.run_operations == ['batch_merge_commit']


# --------------------------------------------------------------------------
# Section E — fresh-first stays confined to catch-up heads
# --------------------------------------------------------------------------


def fresh_rows_setup():
    return admitted_by_class({'old': (1000, CATCH_UP), 'fresh': (90_000, FRESH)})


def test_plain_fresh_blocked_head_never_triggers_fresh_first():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)  # Both rows fresh-classified; the head is leased.
    merge = merge_for(store, depth=4, wait=0)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_plain_blocked_head_fresh_row_appends_once_the_head_resolves():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    merge = merge_for(store, depth=4, wait=0)
    assert merge.commit_next('heavy', 10) is None
    complete(queue, leases, 'a', 20)
    entries = []
    while entry := merge.commit_next('heavy', 20):
        entries.append(entry['segment_id'])
    assert entries == ['a', 'b']


def test_catchup_blocked_head_still_runs_strict_for_fresh_first():
    store, queue, leases = fresh_rows_setup()
    complete(queue, leases, 'fresh', NOW)
    merge = merge_for(store, depth=4, wait=0)
    store.reset_counts()
    entry = merge.commit_next('heavy', NOW)
    assert entry['segment_id'] == 'fresh'
    assert store.runs == 2  # Strict probe transaction, then the fresh-first transaction.


def test_catchup_blocked_head_fresh_entry_carries_the_flag():
    store, queue, leases = fresh_rows_setup()
    complete(queue, leases, 'fresh', NOW)
    merge = merge_for(store, depth=4, wait=0)
    entry = merge.commit_next('heavy', NOW)
    assert entry['fresh_first'] is True


def test_fresh_first_bypasses_the_depth_cap():
    store, queue, leases = fresh_rows_setup()
    complete(queue, leases, 'fresh', NOW)
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4, wait=0)
    entry = merge.commit_next('heavy', NOW)
    assert entry['segment_id'] == 'fresh' and entry['fresh_first'] is True


def test_fresh_first_probe_unavailable_falls_back_to_plain_order(caplog):
    store, queue, leases = fresh_rows_setup()
    complete(queue, leases, 'fresh', NOW)
    store.fresh_pending = Mock(side_effect=FailedPrecondition('index missing'))
    merge = merge_for(store, depth=4, wait=0)
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        assert merge.commit_next('heavy', NOW) is None
    assert any('outcome=fresh_first_unavailable' in record.getMessage() for record in caplog.records)


def test_fresh_first_probe_transient_keeps_the_strict_result(caplog):
    store, queue, leases = fresh_rows_setup()
    complete(queue, leases, 'fresh', NOW)
    store.fresh_pending = Mock(side_effect=ServiceUnavailable('probe down'))
    merge = merge_for(store, depth=4, wait=0)
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        assert merge.commit_next('heavy', NOW) is None
    assert any('outcome=fresh_first_probe_retry' in record.getMessage() for record in caplog.records)


def test_fresh_skipped_rows_reverify_inside_the_transaction():
    """A skipped earlier fresh row that has become ready blocks the bypass: the
    fresh-first transaction re-verifies every skipped row and refuses."""

    class StaleFreshProbeStore(CountingStore):
        """The fresh probe still reports ``mid`` as unready; the row became ready."""

        def fresh_pending(self, key, limit):
            rows = self.inner.fresh_pending(key, limit)
            return [{**row, 'state': 'leased'} if row['segment_id'] == 'mid' else row for row in rows]

    store, queue, leases = admitted_by_class({'old': (1000, CATCH_UP), 'mid': (2000, FRESH), 'late': (90_000, FRESH)})
    complete(queue, leases, 'late', NOW)
    complete(queue, leases, 'mid', NOW)  # The earlier fresh row became ready after the probe.
    merge = merge_for(StaleFreshProbeStore(store), depth=4, wait=W)
    entry = merge.commit_next('heavy', NOW + W)
    # The fresh-first re-verify refused (mid is ready), so capture order won instead:
    # the committed row carries the head-wait flag, never the fresh_first one.
    assert entry['segment_id'] == 'mid' and entry['head_wait_bypass'] is True
    assert 'fresh_first' not in entry


def test_fenced_fresh_row_does_not_block_the_later_head_wait():
    store, queue, leases = admitted_by_class({'old': (1000, CATCH_UP), 'c': (2000, CATCH_UP), 'f': (90_000, FRESH)})
    complete(queue, leases, 'c', NOW)
    complete(queue, leases, 'f', NOW)
    merge = merge_for(_FencedResultsStore(store), depth=16, wait=W)
    assert merge.commit_next('heavy', NOW + 30) is None
    entry = merge.commit_next('heavy', NOW + W)
    assert entry['segment_id'] == 'c' and entry['head_wait_bypass'] is True


def test_fenced_catchup_head_raises_when_no_fresh_row_can_rescue_it():
    """A fenced catch-up head raises once no ready fresh row exists (parity with
    the pre-gate raise: fresh-first is the only rescue, and there is none)."""

    class FencedOld(_FencedResultsStore):
        def run(self, body, *, operation=None):
            real_body = body

            def fenced(tx):
                result = real_body(tx)
                if result is not None and result.get('segment_id') == 'old':
                    raise BatchPrivacyBlocked('fenced')
                return result

            return CountingStore.run(self, fenced, operation=operation)

    store, queue, leases = admitted_by_class({'old': (1000, CATCH_UP)})
    complete(queue, leases, 'old', NOW)
    merge = merge_for(FencedOld(store), depth=4, wait=0)
    with pytest.raises(BatchPrivacyBlocked):
        merge.commit_next('heavy', NOW)


def test_fenced_catchup_head_with_a_ready_fresh_row_commits_the_fresh_row_instead():
    class FencedOld(_FencedResultsStore):
        def run(self, body, *, operation=None):
            real_body = body

            def fenced(tx):
                result = real_body(tx)
                if result is not None and result.get('segment_id') == 'old':
                    raise BatchPrivacyBlocked('fenced')
                return result

            return CountingStore.run(self, fenced, operation=operation)

    store, queue, leases = admitted_by_class({'old': (1000, CATCH_UP), 'fresh': (90_000, FRESH)})
    complete(queue, leases, 'fresh', NOW)
    complete(queue, leases, 'old', NOW)
    merge = merge_for(FencedOld(store), depth=4, wait=0)
    entry = merge.commit_next('heavy', NOW)
    assert entry['segment_id'] == 'fresh' and entry['fresh_first'] is True


# --------------------------------------------------------------------------
# Section F — recovered release wakes through the gate
# --------------------------------------------------------------------------


def wake_setup():
    store, queue, leases = admitted({'a': 1, 'r': 2})
    complete(queue, leases, 'r', 10)
    store.rows['jobs', 'r'].update(state='result_ready', recovery_state='recovered', ready_at=500)
    merge = merge_for(store, wait=W)
    return store, merge, ['r']


def test_blocked_head_wake_commits_the_recovered_row():
    store, merge, release = wake_setup()
    store.reset_counts()
    entry = merge.commit_next('heavy', 10, release=release)
    assert entry['segment_id'] == 'r'
    assert store.runs == 1  # The strict blocked-head transaction is skipped.


def test_wake_entry_carries_the_recovered_release_flag():
    store, merge, release = wake_setup()
    entry = merge.commit_next('heavy', 10, release=release)
    assert entry['recovered_release'] is True


def test_wake_entry_appends_at_the_tail_with_recovery_version():
    store, merge, release = wake_setup()
    entry = merge.commit_next('heavy', 10, release=release)
    assert entry['recovery_version'] == 1 and entry['previous_segment_id'] is None


def test_wake_row_consumed_from_the_release_list():
    store, merge, release = wake_setup()
    merge.commit_next('heavy', 10, release=release)
    assert release == []


def test_wake_skipped_when_the_row_is_no_longer_pending():
    store, merge, release = wake_setup()
    store.rows['jobs', 'r']['merge_pending'] = False
    assert merge.commit_next('heavy', 10, release=release) is None
    assert release == []


def test_wake_skipped_when_the_row_lost_its_result():
    store, merge, release = wake_setup()
    store.rows['jobs', 'r']['state'] = 'leased'
    assert merge.commit_next('heavy', 10, release=release) is None
    assert release == []


def test_wake_skipped_when_the_row_belongs_to_another_owner():
    store, merge, release = wake_setup()
    store.rows['jobs', 'r']['owner_key'] = owner_key('other')
    assert merge.commit_next('heavy', 10, release=release) is None
    assert release == []


def test_wake_skips_a_head_that_the_strict_path_would_still_block():
    store, merge, release = wake_setup()
    # Head 'a' leased; the wake's row must still be this owner's pending ready row — it is,
    # so the gate must not stand in the wake's way even when the strict path already ran.
    entry = merge.commit_next('heavy', 10, release=release)
    assert entry is not None and entry['segment_id'] == 'r'


def test_wake_release_only_when_enabled(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERED_MERGE_RELEASE_ENABLED', 'false')
    store, merge, release = wake_setup()
    store.reset_counts()
    assert merge.commit_next('heavy', 10, release=release) is None
    assert store.runs == 0


def test_ready_head_commits_before_a_wake_release():
    store, queue, leases = admitted({'a': 1, 'r': 2})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'r', 20)
    store.rows['jobs', 'r'].update(state='result_ready', recovery_state='recovered', ready_at=20)
    merge = merge_for(store, wait=W)
    first = merge.commit_next('heavy', 20, release=['r'])
    assert first['segment_id'] == 'a'  # Strict order commits the ready head first.
    second = merge.commit_next('heavy', 20, release=['r'])
    # The recovered row is now this owner's plain head: the strict path commits it.
    assert second['segment_id'] == 'r' and 'recovered_release' not in second


def test_wake_with_blocked_head_under_a_depth_cap_still_commits_the_recovered_unit():
    store, merge, release = wake_setup()
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4, wait=W)
    entry = merge.commit_next('heavy', 10, release=release)
    assert entry['segment_id'] == 'r'  # The recovered unit passes the depth hold.
    assert entry['recovered_release'] is True
    # The blocked strict pass ran first and wrote the owed marker.
    assert store.rows['merge_holds', OWNER]['held'] is True


# --------------------------------------------------------------------------
# Section G — heartbeat-storm elimination on the real store class
# --------------------------------------------------------------------------


def storm_merge(monkeypatch, client, *, depth=0, wait=0, damper=None, silence=True):
    """Real FirestoreStore + OrderedMerge; the privacy fence is orthogonal to the
    contention contract here, so it reads its expected generation deterministically."""
    if silence:
        silence_chain_sleep(monkeypatch)
    monkeypatch.setattr(
        storage.FirestoreTransaction,
        'check_privacy',
        lambda self, uid, **kwargs: kwargs.get('expected_generation') or 0,
    )
    store = build_storm_store(monkeypatch, client, damper=damper)
    return OrderedMerge(store, head_wait_seconds=wait, catch_up_depth=depth), store


def test_blocked_head_drain_survives_a_heartbeat_storm_without_a_transaction(monkeypatch):
    client = StormClient(storm_rows('leased'))
    merge, _store = storm_merge(monkeypatch, client)
    assert merge.commit_next('heavy', 10) is None
    assert client.transactions == 0
    assert client.commits == 0


def test_blocked_head_drain_under_storm_never_enters_the_ladder(monkeypatch):
    clock = FakeClock()
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = StormClient(storm_rows('leased'))
    merge, _store = storm_merge(monkeypatch, client, damper=damper)
    assert merge.commit_next('heavy', 10) is None
    assert clock.sleeps == []
    assert client.aborts_remaining == 10**6  # No attempt was spent.


def test_blocked_head_exhaustion_is_unreachable_under_storm(monkeypatch):
    client = StormClient(storm_rows('leased'))  # Aborts forever, as a live storm does.
    merge, _store = storm_merge(monkeypatch, client)
    assert merge.commit_next('heavy', 10) is None  # No FirestoreContentionExhausted.


def test_blocked_head_storm_drain_does_not_arm_the_storm_damper(monkeypatch):
    clock = FakeClock()
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = StormClient(storm_rows('leased'))
    merge, store = storm_merge(monkeypatch, client, damper=damper)
    merge.commit_next('heavy', 10)
    waited, _generation = damper.consult('batch_merge_commit')
    assert waited == 0.0 and clock.sleeps == []


def test_blocked_head_drain_registers_no_transactional_query(monkeypatch):
    client = StormClient(storm_rows('leased'))
    merge, _store = storm_merge(monkeypatch, client)
    merge.commit_next('heavy', 10)
    assert all(not shape['transactional'] for shape in client.query_shapes)


def test_blocked_head_drain_keeps_the_point_read_cheap(monkeypatch):
    client = StormClient(storm_rows('leased'))
    merge, _store = storm_merge(monkeypatch, client)
    merge.commit_next('heavy', 10)
    shapes = [shape for shape in client.query_shapes if shape['collection'] == f'{NAMESPACE}_jobs']
    assert len(shapes) == 1 and shapes[0]['limit'] == 1


def test_probe_reads_succeed_while_the_storm_aborts_every_commit(monkeypatch):
    client = StormClient(storm_rows('leased'))
    merge, store = storm_merge(monkeypatch, client)
    assert store.head_pending(OWNER)['segment_id'] == 'a'
    assert client.commits == 0


def test_ready_head_commit_retries_through_the_storm_and_lands(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'a']['state'] = 'result_ready'
    rows[f'{NAMESPACE}_jobs', 'a']['ready_at'] = 5.0
    rows[f'{NAMESPACE}_jobs', 'a']['result'] = {'uri': 'gs://results/a'}
    client = StormClient(rows, aborts=4)  # Four heartbeats land, then the commit goes through.
    merge, _store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 10)
    assert entry['segment_id'] == 'a' and entry['log_sequence'] == 1
    assert client.commits == 5


def test_ready_head_exhaustion_under_still_storm_raises(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'a']['state'] = 'result_ready'
    rows[f'{NAMESPACE}_jobs', 'a']['ready_at'] = 5.0
    rows[f'{NAMESPACE}_jobs', 'a']['result'] = {'uri': 'gs://results/a'}
    client = StormClient(rows)  # Aborts forever.
    merge, _store = storm_merge(monkeypatch, client)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 10)


def test_ready_head_exhaustion_still_arms_the_storm_damper(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'a']['state'] = 'result_ready'
    rows[f'{NAMESPACE}_jobs', 'a']['ready_at'] = 5.0
    rows[f'{NAMESPACE}_jobs', 'a']['result'] = {'uri': 'gs://results/a'}
    clock = FakeClock()
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = StormClient(rows)
    merge, _store = storm_merge(monkeypatch, client, damper=damper)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 10)
    waited, _generation = damper.consult('batch_merge_commit')
    assert waited > 0  # The damper armed; the gate did not touch commit-path parity.


def test_marker_owed_blocked_head_writes_the_marker_through_a_quiet_store(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_owners', OWNER] = {'log_sequence': 6, 'projection_watermark': 'w5'}
    rows[f'{NAMESPACE}_results', 'w5'] = {'log_sequence': 1}
    client = StormClient(rows, aborts=0)
    merge, _store = storm_merge(monkeypatch, client, depth=4)
    assert merge.commit_next('heavy', 10) is None
    assert client.rows[f'{NAMESPACE}_merge_holds', OWNER]['held'] is True


def test_marker_owed_blocked_head_still_runs_under_storm(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_owners', OWNER] = {'log_sequence': 6, 'projection_watermark': 'w5'}
    rows[f'{NAMESPACE}_results', 'w5'] = {'log_sequence': 1}
    client = StormClient(rows, aborts=2)  # Two heartbeats, then the marker transaction lands.
    merge, _store = storm_merge(monkeypatch, client, depth=4)
    assert merge.commit_next('heavy', 10) is None
    assert client.rows[f'{NAMESPACE}_merge_holds', OWNER]['held'] is True
    assert client.commits == 3


def test_bypass_under_storm_commits_the_waiter(monkeypatch):
    client = StormClient(storm_rows('leased'), aborts=0)
    merge, _store = storm_merge(monkeypatch, client, wait=W)
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['segment_id'] == 'b' and entry['head_wait_bypass'] is True


def test_wake_under_storm_commits_the_exact_row(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'b']['recovery_state'] = 'recovered'
    client = StormClient(rows, aborts=0)
    merge, _store = storm_merge(monkeypatch, client, wait=W)
    entry = merge.commit_next('heavy', 10, release=['b'])
    assert entry['segment_id'] == 'b' and entry['recovered_release'] is True


def test_store_level_storm_damper_still_backs_off_real_exhaustion(monkeypatch):
    """The t266 damper keeps its contract: the gate only removes doomed drains."""
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'a']['state'] = 'result_ready'
    rows[f'{NAMESPACE}_jobs', 'a']['ready_at'] = 5.0
    rows[f'{NAMESPACE}_jobs', 'a']['result'] = {'uri': 'gs://results/a'}
    clock = FakeClock()
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = StormClient(rows)
    merge, _store = storm_merge(monkeypatch, client, damper=damper)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 10)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 10)
    assert clock.sleeps  # The second entry waited out the armed window.


# --------------------------------------------------------------------------
# Section H — kill-switch and label interplay
# --------------------------------------------------------------------------


def test_gate_runs_before_the_contention_kill_switch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_kill_switch_ready_head_runs_one_unladdered_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    store, _queue, _leases = blocked_head_setup('leased')
    complete(_queue, _leases, 'a', 20)
    merge = merge_for(store)
    store.reset_counts()
    entry = merge.commit_next('heavy', 20)
    assert entry['segment_id'] == 'a' and store.runs == 1


def test_gate_skip_paths_never_require_a_store_label():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.run_operations == []


def test_gate_paths_keep_the_batch_merge_commit_label_when_they_transact():
    store, merge, release = wake_setup()
    store.reset_counts()
    merge.commit_next('heavy', 10, release=release)
    assert store.run_operations == ['batch_merge_commit']


# --------------------------------------------------------------------------
# Section I — the probe surface across store backends
# --------------------------------------------------------------------------


def test_store_protocol_declares_head_pending():
    assert 'head_pending' in vars(storage.Store)


def test_head_pending_signatures_match_across_backends():
    import inspect

    reference = inspect.signature(storage.FirestoreStore.head_pending)
    for backend in (storage.Store, storage.FirestoreTransaction):
        if hasattr(backend, 'head_pending'):
            assert inspect.signature(getattr(backend, 'head_pending')).parameters.keys() == reference.parameters.keys()


def test_memory_head_pending_matches_the_transactional_query():
    for order in permutations(['a', 'b', 'c']):
        store = MemoryStore()
        queue = Scheduler(store)
        for segment in order:
            queue.enqueue(item(segment, capture=1), 0)  # Ties on capture_at; name breaks them.
        via_tx = store.run(lambda tx: tx.first_pending(OWNER))
        assert store.head_pending(OWNER) == via_tx
        assert store.head_pending(OWNER) is not None


def test_memory_head_pending_orders_by_capture_then_segment():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('late', owner='heavy', capture=9), 0)
    queue.enqueue(item('early', owner='heavy', capture=1), 0)
    assert store.head_pending(OWNER)['segment_id'] == 'early'


def test_memory_head_pending_ignores_committed_rows():
    store, queue, leases = admitted({'a': 1})
    complete(queue, leases, 'a', 10)
    merge = merge_for(store)
    assert merge.commit_next('heavy', 10) is not None  # The merge commit retires the row.
    assert store.head_pending(OWNER) is None


def test_memory_head_pending_is_a_deep_copy():
    store = CountingStore()
    store.rows['jobs', 'a'] = {
        'segment_id': 'a',
        'owner_key': OWNER,
        'merge_pending': True,
        'state': 'leased',
        'capture_at': 1,
    }
    head = store.head_pending(OWNER)
    head['state'] = 'mutated'
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_memory_head_pending_empty_store_returns_none():
    assert MemoryStore().head_pending(OWNER) is None


def test_owner_key_is_the_probe_and_query_shared_address():
    store, _queue, _leases = admitted({'a': 1})
    assert store.head_pending(owner_key('heavy'))['owner_key'] == owner_key('heavy')


def test_sim_store_head_pending_matches_first_pending():
    from testing.pipeline_sim.store import CustomerData, SimStore

    customer = CustomerData()
    customer.add_user('heavy')
    sim = SimStore(customer)
    queue = Scheduler(sim)
    queue.enqueue(item('a', capture=2), 0)
    queue.enqueue(item('b', capture=1), 0)
    queue.pull(0, 2)
    assert sim.head_pending(OWNER)['segment_id'] == 'b'
    via_tx = sim.run(lambda tx: tx.first_pending(OWNER))
    assert sim.head_pending(OWNER) == via_tx


def test_sim_store_head_pending_ignores_committed_rows():
    from testing.pipeline_sim.store import CustomerData, SimStore

    customer = CustomerData()
    customer.add_user('heavy')
    sim = SimStore(customer)
    queue = Scheduler(sim)
    queue.enqueue(item('a'), 0)
    leases = queue.pull(0, 1)
    queue.complete(WorkResult('a', 'gs://results/a'), leases[0].token, 10)
    merge = OrderedMerge(sim)
    assert merge.commit_next('heavy', 10) is not None
    assert sim.head_pending(OWNER) is None


def test_sim_store_head_pending_empty_store_returns_none():
    from testing.pipeline_sim.store import CustomerData, SimStore

    assert SimStore(CustomerData()).head_pending(OWNER) is None


def test_firestore_store_head_pending_uses_the_shared_document_layout(monkeypatch):
    client = StormClient(storm_rows('leased'))
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore(NAMESPACE, firestore_client=client)
    assert store.head_pending(OWNER)['segment_id'] == 'a'


def test_firestore_head_pending_query_shape_is_the_first_pending_twin(monkeypatch):
    client = StormClient(storm_rows('leased'))
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore(NAMESPACE, firestore_client=client)
    store.head_pending(OWNER)
    shape = client.query_shapes[0]
    assert shape['collection'] == f'{NAMESPACE}_jobs'
    assert shape['filters'] == (('owner_key', OWNER), ('merge_pending', True))
    assert shape['orders'] == ('capture_at', 'segment_id')
    assert shape['limit'] == 1
    assert shape['transactional'] is False


def test_firestore_head_pending_missing_rows_read_none(monkeypatch):
    client = StormClient({})
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore(NAMESPACE, firestore_client=client)
    assert store.head_pending(OWNER) is None


def test_firestore_head_pending_takes_no_ladder_and_no_transaction(monkeypatch):
    client = StormClient(storm_rows('leased'))
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore(NAMESPACE, firestore_client=client)
    store.head_pending(OWNER)
    assert client.transactions == 0 and client.commits == 0


def test_jobstore_postgres_head_pending_source_contract():
    import ast
    from pathlib import Path

    source = Path(storage.__file__).parents[0] / 'jobstore' / 'postgres_store.py'
    tree = ast.parse(source.read_text())
    found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'head_pending']
    assert len(found) == 1
    text = ast.get_source_segment(source.read_text(), found[0])
    assert '_read_conn' in text and 'merge_pending' in text
    assert 'ORDER BY capture_at' in text and 'LIMIT 1' in text
    assert 'transaction=' not in text  # A hint read: the query runs outside any transaction.


def test_pg_sim_store_head_pending_delegates_non_transactionally():
    import ast
    from pathlib import Path

    source = Path(merge_module.__file__).parents[2] / 'testing' / 'pipeline_sim' / 'postgres_store.py'
    tree = ast.parse(source.read_text())
    found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'head_pending']
    assert len(found) == 1
    text = ast.get_source_segment(source.read_text(), found[0])
    assert 'self.pg.head_pending' in text and 'self.pg.run' not in text


def _probe_helpers():
    """Lazy import: the helpers are new on this branch, so the suite still
    COLLECTS on the parent commit and shows per-test RED there."""
    from utils.batch_pipeline.merge import _awaiting_projection, _unprojected

    return _awaiting_projection, _unprojected


def test_unprojected_without_watermark_is_the_whole_sequence():
    _awaiting_projection, _unprojected = _probe_helpers()
    assert _unprojected(7, None, lambda key: {}) == 7


def test_unprojected_subtracts_the_done_watermark():
    _awaiting_projection, _unprojected = _probe_helpers()
    assert _unprojected(7, 'w6', lambda key: {'log_sequence': 3}) == 4


def test_unprojected_missing_done_row_counts_nothing_done():
    """Parity with the strict body: without the watermark's result row the
    unprojected count is zero, never the whole sequence."""
    _awaiting_projection, _unprojected = _probe_helpers()
    assert _unprojected(7, 'w6', lambda key: {}) == 0


def test_unprojected_caught_up_is_zero():
    _awaiting_projection, _unprojected = _probe_helpers()
    assert _unprojected(7, 'w6', lambda key: {'log_sequence': 7}) == 0


def test_unprojected_zero_sequence_stays_zero():
    _awaiting_projection, _unprojected = _probe_helpers()
    assert _unprojected(0, None, lambda key: {'log_sequence': 5}) == 0


def test_awaiting_projection_parity_between_transaction_and_probe_reads():
    _awaiting_projection, _unprojected = _probe_helpers()
    rows = {
        ('owners', OWNER): {'log_sequence': 7, 'projection_watermark': 'w6'},
        ('results', 'w6'): {'log_sequence': 3},
    }
    store = CountingStore()
    store.rows.update(rows)
    tx_view = _awaiting_projection(MemoryTransaction(deepcopy(store.rows)), store.rows['owners', OWNER])
    probe_view = _unprojected(7, 'w6', lambda key: store.probe('results', key))
    assert tx_view == probe_view == 4


def test_awaiting_projection_missing_watermark_parity():
    _awaiting_projection, _unprojected = _probe_helpers()
    rows = {('owners', OWNER): {'log_sequence': 7}}
    store = CountingStore()
    store.rows.update(rows)
    tx_view = _awaiting_projection(MemoryTransaction(deepcopy(store.rows)), store.rows['owners', OWNER])
    probe_view = _unprojected(7, None, lambda key: store.probe('results', key))
    assert tx_view == probe_view == 7


# --------------------------------------------------------------------------
# Section J — pump and serving drains through the gate
# --------------------------------------------------------------------------


def test_pump_drain_owner_blocked_head_opens_no_transaction():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    pump = Pump(
        queue,
        Mock(),
        merge=merge_for(store),
        leader=_Leader(True),
        publish_concurrency=1,
        inline_metrics=False,
    )
    store.reset_counts()
    asyncio.run(pump.drain_owner('heavy'))
    assert store.runs == 0


def test_pump_drain_owner_blocked_head_calls_no_projection():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    on_committed = Mock()
    pump = Pump(
        queue,
        Mock(),
        merge=merge_for(store),
        on_committed=on_committed,
        leader=_Leader(True),
        publish_concurrency=1,
        inline_metrics=False,
    )
    asyncio.run(pump.drain_owner('heavy'))
    assert on_committed.call_count == 0


def test_pump_drain_owner_ready_head_projects_each_commit():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'b', 20)
    on_committed = Mock()
    pump = Pump(
        queue,
        Mock(),
        merge=merge_for(store),
        on_committed=on_committed,
        leader=_Leader(True),
        publish_concurrency=1,
        inline_metrics=False,
    )
    asyncio.run(pump.drain_owner('heavy'))
    assert on_committed.call_count == 2


def test_serving_drain_blocked_head_opens_no_transaction():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    service = Serving(store)
    service.merge = merge_for(store, wait=0, depth=0)  # Pin the knobs; real time stays.
    store.reset_counts()
    service.drain_owner('heavy')
    assert store.runs == 0


def test_serving_drain_ready_head_commits():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'b', 20)
    service = Serving(store)
    service.merge = merge_for(store, wait=0, depth=0)
    service.drain_owner('heavy')
    assert store.rows['jobs', 'b']['state'] == 'committed'


def test_serving_wake_through_the_gate_commits_the_recovered_row():
    store, queue, leases = admitted({'a': 1, 'r': 2})
    complete(queue, leases, 'r', 10)
    store.rows['jobs', 'r'].update(state='result_ready', recovery_state='recovered', ready_at=500)
    service = Serving(store)
    service.merge = merge_for(store, wait=0, depth=0)
    service.drain_owner('heavy', recovered='r')
    assert store.rows['jobs', 'r']['state'] == 'committed'


def test_maintenance_held_owner_reoffer_drains_through_the_gate():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    merge.commit_next('heavy', 10)
    assert merge.held_owners == {'heavy'}
    # Maintenance re-offer: the drain runs again; the durable marker keeps it held.
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.runs == 0 and merge.held_owners == {'heavy'}


# --------------------------------------------------------------------------
# Section K — log taxonomy and skip-path quietness
# --------------------------------------------------------------------------


def test_skip_path_keeps_the_merge_logger_silent_on_both_bypass_off_paths(caplog):
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store, wait=W)
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.merge'):
        assert merge.commit_next('heavy', 10) is None  # Bypass not yet due.
    assert caplog.records == []


def test_strict_commit_path_stays_silent_on_success(caplog):
    store, _queue, _leases = blocked_head_setup('leased')
    complete(_queue, _leases, 'a', 20)
    merge = merge_for(store)
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.merge'):
        merge.commit_next('heavy', 20)
    assert caplog.records == []


def test_gate_does_not_disturb_the_store_backoff_taxonomy():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.probed == [('jobs', OWNER)]


def test_blocked_head_state_names_flow_only_into_the_internal_record():
    store, _queue, _leases = blocked_head_setup('record_pending')
    merge = merge_for(store)
    assert merge.commit_next('heavy', 10) is None
    assert merge.held_owners == set()


def test_blocked_head_drain_is_idempotent_across_repeated_calls():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    for _ in range(3):
        assert merge.commit_next('heavy', 10) is None
    assert merge.held_owners == set()


def test_drain_loop_terminates_immediately_on_a_blocked_head():
    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    entries = []
    while entry := merge.commit_next('heavy', 10):
        entries.append(entry)
    assert entries == []


# --------------------------------------------------------------------------
# Section L — owner isolation: the gate is strictly per-owner
# --------------------------------------------------------------------------


def two_owner_setup():
    """Owner heavy has a blocked head; owner light has a ready row."""
    store, heavy_queue, heavy_leases = admitted({'a': 1, 'b': 2})
    light_queue = Scheduler(store)
    light_queue.enqueue(item('x', owner='light', capture=5), 0)
    light_leases = {lease.item.segment_id: lease for lease in light_queue.pull(NOW, 1)}
    assert set(light_leases) == {'x'}
    complete(heavy_queue, heavy_leases, 'b', 10)
    set_state(store, 'a', 'leased')
    light_queue.store.rows['jobs', 'x']['lease_until'] = NOW + 1
    assert light_queue.complete(WorkResult('x', 'gs://results/x'), light_leases['x'].token, NOW)
    return store, heavy_queue, light_queue


def test_blocked_head_on_one_owner_does_not_block_another_owners_drain():
    store, _heavy, _light = two_owner_setup()
    merge = merge_for(store)
    assert merge.commit_next('light', NOW)['segment_id'] == 'x'


def test_other_owner_drain_opens_its_own_transaction_only():
    store, _heavy, _light = two_owner_setup()
    merge = merge_for(store)
    store.reset_counts()
    merge.commit_next('light', NOW)
    assert store.runs == 1  # Only the light owner's commit transaction.


def test_probe_empty_other_owner_opens_no_transaction():
    store, _heavy, _light = two_owner_setup()
    merge = merge_for(store)
    store.reset_counts()
    assert merge.commit_next('ghost', NOW) is None
    assert store.runs == 0


def test_depth_marker_is_written_per_owner_only():
    store, _heavy, _light = two_owner_setup()
    at_cap(store, sequence=6, done=1)
    heavy_owner = owner_key('heavy')
    merge = merge_for(store, depth=4)
    merge.commit_next('light', NOW)  # Light owner is under any cap: its drain commits.
    assert store.rows.get(('merge_holds', owner_key('light'))) is None
    merge.commit_next('heavy', NOW)  # Heavy owner is at cap with a blocked head.
    assert store.rows['merge_holds', heavy_owner]['held'] is True


def test_held_owner_hint_tracks_only_the_cap_owner():
    store, _heavy, _light = two_owner_setup()
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    merge.commit_next('light', NOW)
    merge.commit_next('heavy', NOW)
    assert merge.held_owners == {'heavy'}


def test_probe_reads_target_only_the_drained_owner():
    store, _heavy, _light = two_owner_setup()
    merge = merge_for(store)
    store.reset_counts()
    merge.commit_next('light', NOW)
    probed_keys = [key for _table, key in store.probed]
    assert all(key == owner_key('light') for key in probed_keys)


# --------------------------------------------------------------------------
# Section M — blocked states at the depth cap (marker guard per state)
# --------------------------------------------------------------------------


def test_leased_head_at_cap_unmarked_runs_the_marker_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.runs == 1 and store.rows['merge_holds', OWNER]['held'] is True


def test_queued_head_at_cap_unmarked_runs_the_marker_transaction():
    store, _queue, _leases = admitted({'a': 1, 'b': 2})
    complete(_queue, _leases, 'b', 10)
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.runs == 1 and store.rows['merge_holds', OWNER]['held'] is True


def test_retry_head_at_cap_unmarked_runs_the_marker_transaction():
    store, _queue, _leases = blocked_head_setup('retry')
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.runs == 1 and store.rows['merge_holds', OWNER]['held'] is True


def test_record_pending_head_at_cap_unmarked_runs_the_marker_transaction():
    store, _queue, _leases = blocked_head_setup('record_pending')
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    store.reset_counts()
    merge.commit_next('heavy', 10)
    assert store.runs == 1 and store.rows['merge_holds', OWNER]['held'] is True


def test_leased_head_at_cap_marked_opens_no_transaction():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    merge = merge_for(store, depth=4)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_queued_head_at_cap_marked_opens_no_transaction():
    store, _queue, _leases = admitted({'a': 1, 'b': 2})
    complete(_queue, _leases, 'b', 10)
    at_cap(store, sequence=6, done=1)
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    merge = merge_for(store, depth=4)
    store.reset_counts()
    assert merge.commit_next('heavy', 10) is None
    assert store.runs == 0


def test_catchup_head_at_cap_writes_the_marker_through_the_strict_body():
    """A catch-up head is exempt from the gate; the body writes the marker itself."""
    store, queue, leases = admitted_by_class({'old': (1000, CATCH_UP), 'b': (2000, FRESH)})
    complete(queue, leases, 'b', NOW)
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4, wait=0)
    merge.commit_next('heavy', NOW)
    assert store.rows['merge_holds', OWNER]['held'] is True
    assert merge.held_owners == {'heavy'}


def test_ready_head_at_cap_with_catchup_row_holds_the_commit():
    """At the cap, even a ready catch-up head is held by the body, not the gate."""
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    store.rows['jobs', 'a']['fresh_capture'] = False
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4, wait=0)
    assert merge.commit_next('heavy', 10) is None
    assert store.rows['merge_holds', OWNER]['held'] is True
    assert merge.held_owners == {'heavy'}


# --------------------------------------------------------------------------
# Section N — wait buckets and entry flags
# --------------------------------------------------------------------------


def bypass_entry_at(waited):
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    merge = merge_for(store, wait=W)
    return merge.commit_next('heavy', 10 + waited)


def test_wait_bucket_lt60():
    from utils.batch_pipeline.merge import _wait_bucket

    assert _wait_bucket(0) == 'lt60' and _wait_bucket(59.9) == 'lt60'
    assert bypass_entry_at(W) is not None  # The bypass itself fires only at the full wait.


def test_wait_bucket_lt120():
    from utils.batch_pipeline.merge import _wait_bucket

    assert _wait_bucket(60) == 'lt120' and _wait_bucket(119.9) == 'lt120'


def test_wait_bucket_lt300():
    from utils.batch_pipeline.merge import _wait_bucket

    assert _wait_bucket(120) == 'lt300' and _wait_bucket(299) == 'lt300'


def test_wait_bucket_lt600():
    from utils.batch_pipeline.merge import _wait_bucket

    assert _wait_bucket(300) == 'lt600' and _wait_bucket(599) == 'lt600'


def test_wait_bucket_lt1800():
    from utils.batch_pipeline.merge import _wait_bucket

    assert _wait_bucket(600) == 'lt1800' and _wait_bucket(1799) == 'lt1800'


def test_wait_bucket_ge1800():
    from utils.batch_pipeline.merge import _wait_bucket

    assert _wait_bucket(1800) == 'ge1800' and _wait_bucket(10**6) == 'ge1800'


def test_provider_routed_commit_carries_the_recovery_version():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    store.rows['jobs', 'a']['stt_route'] = {'stt_route': 'provider'}
    merge = merge_for(store)
    entry = merge.commit_next('heavy', 10)
    assert entry['segment_id'] == 'a' and entry['recovery_version'] == 1


def test_plain_commit_has_no_recovery_version():
    store, queue, leases = admitted({'a': 1})
    complete(queue, leases, 'a', 10)
    entry = merge_for(store).commit_next('heavy', 10)
    assert 'recovery_version' not in entry


# --------------------------------------------------------------------------
# Section O — config-driven knobs
# --------------------------------------------------------------------------


def test_head_wait_from_config_drives_the_gate_bypass(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS', '45')
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    merge = OrderedMerge(store, catch_up_depth=0)  # head_wait_seconds=None reads the config.
    assert merge.commit_next('heavy', 10 + 44) is None
    assert merge.commit_next('heavy', 10 + 45)['segment_id'] == 'b'


def test_catch_up_depth_from_config_keeps_catchup_heads_on_the_strict_path(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH', '4')
    store, queue, leases = admitted_by_class({'old': (1000, CATCH_UP), 'fresh': (90_000, FRESH)})
    complete(queue, leases, 'fresh', NOW)
    merge = OrderedMerge(store, head_wait_seconds=0)  # catch_up_depth=None reads the config.
    store.reset_counts()
    entry = merge.commit_next('heavy', NOW)
    assert entry['segment_id'] == 'fresh' and entry['fresh_first'] is True
    assert store.runs == 2  # Strict, then fresh-first: the catch-up exemption held.


def test_catch_up_depth_config_zero_puts_catchup_heads_through_the_gate(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH', '0')
    store, queue, leases = admitted_by_class({'old': (1000, CATCH_UP), 'b': (2000, FRESH)})
    complete(queue, leases, 'b', NOW)
    merge = OrderedMerge(store, head_wait_seconds=0)
    store.reset_counts()
    assert merge.commit_next('heavy', NOW) is None
    assert store.runs == 0


# --------------------------------------------------------------------------
# Section P — storm realism extras
# --------------------------------------------------------------------------


def test_partial_storm_budget_changes_nothing_for_blocked_heads(monkeypatch):
    client = StormClient(storm_rows('leased'), aborts=4)
    merge, _store = storm_merge(monkeypatch, client)
    for _ in range(3):
        assert merge.commit_next('heavy', 10) is None
    assert client.commits == 0 and client.aborts_remaining == 4


def test_ready_head_first_try_commit_with_a_quiet_store(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'a']['state'] = 'result_ready'
    rows[f'{NAMESPACE}_jobs', 'a']['ready_at'] = 5.0
    rows[f'{NAMESPACE}_jobs', 'a']['result'] = {'uri': 'gs://results/a'}
    client = StormClient(rows, aborts=0)
    merge, _store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 10)
    assert entry['segment_id'] == 'a'
    assert client.commits == 1 and client.transactions == 1


def test_probe_failure_falls_back_to_a_working_strict_path(monkeypatch):
    """A probe failure falls back to the strict transaction, which decides exactly
    as before: on this quiet store the blocked head still concludes ``blocked``."""
    rows = storm_rows('leased')

    class ProbeDownStore(storage.FirestoreStore):
        def head_pending(self, key):
            raise ServiceUnavailable('probe down')

    silence_chain_sleep(monkeypatch)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = ProbeDownStore(NAMESPACE, firestore_client=StormClient(rows, aborts=0))
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    assert merge.commit_next('heavy', 10) is None


def test_blocked_drains_log_no_contention_lines(monkeypatch, caplog):
    client = StormClient(storm_rows('leased'))
    merge, _store = storm_merge(monkeypatch, client)
    with caplog.at_level(logging.WARNING, logger='database.firestore_transaction_retry'):
        merge.commit_next('heavy', 10)
    assert caplog.records == []


def test_ready_head_drain_under_storm_logs_the_attempt_lines(monkeypatch, caplog):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'a']['state'] = 'result_ready'
    rows[f'{NAMESPACE}_jobs', 'a']['ready_at'] = 5.0
    rows[f'{NAMESPACE}_jobs', 'a']['result'] = {'uri': 'gs://results/a'}
    client = StormClient(rows)
    merge, _store = storm_merge(monkeypatch, client)
    with caplog.at_level(logging.WARNING, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            merge.commit_next('heavy', 10)
    messages = [record.getMessage() for record in caplog.records]
    assert any('attempt=1/5' in message for message in messages)
    assert any('attempt=5/5' in message and 'outcome=exhausted' in message for message in messages)


def test_marker_transaction_under_storm_exhaustion_raises_and_arms(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_owners', OWNER] = {'log_sequence': 6, 'projection_watermark': 'w5'}
    rows[f'{NAMESPACE}_results', 'w5'] = {'log_sequence': 1}
    clock = FakeClock()
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = StormClient(rows)  # Aborts forever.
    merge, _store = storm_merge(monkeypatch, client, depth=4, damper=damper)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 10)
    waited, _generation = damper.consult('batch_merge_commit')
    assert waited > 0
    assert client.rows.get((f'{NAMESPACE}_merge_holds', OWNER)) is None  # Nothing was written.


def test_wake_commit_under_storm_can_still_lose(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'b']['recovery_state'] = 'recovered'
    client = StormClient(rows)  # Aborts forever.
    merge, _store = storm_merge(monkeypatch, client, wait=W)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 10, release=['b'])


# --------------------------------------------------------------------------
# Section Q — pump loop shapes through the gate
# --------------------------------------------------------------------------


def test_pump_drain_loop_terminates_on_probe_empty_owner():
    store = CountingStore()
    pump = Pump(
        Scheduler(store),
        Mock(),
        merge=merge_for(store),
        leader=_Leader(True),
        publish_concurrency=1,
        inline_metrics=False,
    )
    store.reset_counts()
    asyncio.run(pump.drain_owner('nobody'))
    assert store.runs == 0


def test_pump_drain_loop_drains_exactly_one_transaction_per_ready_row():
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3})
    for segment, at in (('a', 10), ('b', 20), ('c', 30)):
        complete(queue, leases, segment, at)
    pump = Pump(
        queue,
        Mock(),
        merge=merge_for(store),
        leader=_Leader(True),
        publish_concurrency=1,
        inline_metrics=False,
    )
    store.reset_counts()
    asyncio.run(pump.drain_owner('heavy'))
    assert store.runs == 3
    assert all(store.rows['jobs', segment]['state'] == 'committed' for segment in ('a', 'b', 'c'))


def test_pump_drain_loop_stops_after_the_blocked_head():
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'c', 30)
    set_state(store, 'b', 'leased')  # The head of what remains is in flight.
    pump = Pump(
        queue,
        Mock(),
        merge=merge_for(store),
        leader=_Leader(True),
        publish_concurrency=1,
        inline_metrics=False,
    )
    store.reset_counts()
    asyncio.run(pump.drain_owner('heavy'))
    assert store.runs == 1  # Only the ready head committed; the drain stopped at the gate.
    assert store.rows['jobs', 'a']['state'] == 'committed'
    assert store.rows['jobs', 'c']['state'] == 'result_ready'  # Behind the leased head, untouched.


# --------------------------------------------------------------------------
# Section R — docs and naming contracts
# --------------------------------------------------------------------------


def test_docs_name_the_new_probe_surface():
    from pathlib import Path

    docs = Path(merge_module.__file__).parents[2] / 'docs' / 'batch-merge-blocked-head-probe-gate.md'
    text = docs.read_text()
    assert (
        'Store.head_pending' in text
        and 'Failure-Class: FC-blocked-head-merge-drains-join-the-hot-row-abort-set' in text
    )


def test_probe_surface_documented_as_a_hint_read():
    from pathlib import Path

    docs = Path(merge_module.__file__).parents[2] / 'docs' / 'batch-merge-blocked-head-probe-gate.md'
    text = docs.read_text()
    assert 're-verifies' in text  # The hint contract: the acting transaction re-verifies.


# --------------------------------------------------------------------------
# Section S — bypass, late capture and re-offer extras
# --------------------------------------------------------------------------


def test_bypassed_head_appends_late_relative_to_the_watermark():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    merge = merge_for(store, wait=W)
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['late_capture'] is False  # The bypass row is ahead of any watermark.
    assert 'late_capture' not in entry or entry['late_capture'] is False


def test_late_capture_when_a_committed_predecessor_is_ahead():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    complete(queue, leases, 'b', 20)
    merge = merge_for(store, wait=W)
    merge.commit_next('heavy', 20)  # a commits; its capture position moves the watermark.
    entry = merge.commit_next('heavy', 20)
    assert entry['segment_id'] == 'b' and entry['late_capture'] is False  # b is still ahead.
    assert entry['previous_segment_id'] == 'a'


def test_reoffer_marked_drains_and_clears_a_stale_marker():
    store = CountingStore()
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}  # Nothing pending: stale.
    merge = merge_for(store)
    drains = []
    merge.reoffer_marked(lambda owner: drains.append(owner))
    assert drains == []  # No owner id on a stale marker: force-cleared, no drain.
    assert store.rows['merge_holds', OWNER]['held'] is False


def test_reoffer_marked_drains_a_held_backlog_owner():
    store, _queue, _leases = blocked_head_setup('leased')
    at_cap(store, sequence=6, done=1)
    merge = merge_for(store, depth=4)
    merge.commit_next('heavy', 10)  # Writes the durable marker and holds the owner.
    assert store.rows['merge_holds', OWNER]['held'] is True
    drains = []
    merge.reoffer_marked(lambda owner: drains.append(owner))
    assert drains == ['heavy']


def test_release_set_prefers_the_recovered_unit_then_content_siblings():
    store = CountingStore()
    store.rows['jobs', 'r'] = {
        'segment_id': 'r',
        'owner_key': OWNER,
        'merge_pending': True,
        'state': 'result_ready',
        'projection_binding': {'segment_ids': ['s1', 'r', 's2']},
    }
    release = merge_for(store).release_set('r')
    assert release[0] == 'r'
    assert release[1:] == ['s1', 's2']  # The unit itself is not repeated; order preserved, bounded.


def test_release_set_bounded_to_32_siblings():
    store = CountingStore()
    siblings = [f's{index}' for index in range(50)]
    store.rows['jobs', 'r'] = {
        'segment_id': 'r',
        'owner_key': OWNER,
        'merge_pending': True,
        'state': 'result_ready',
        'projection_binding': {'segment_ids': siblings},
    }
    release = merge_for(store).release_set('r')
    assert release[0] == 'r'
    assert len(release[1:]) == 32  # The unit plus RELEASE_SIBLINGS_MAX content siblings.


def test_release_set_orders_the_unit_first():
    store = CountingStore()
    store.rows['jobs', 'r'] = {
        'segment_id': 'r',
        'owner_key': OWNER,
        'merge_pending': True,
        'state': 'result_ready',
        'projection_binding': {'segment_ids': ['s1', 's2', 'r']},
    }
    assert merge_for(store).release_set('r')[0] == 'r'


def test_release_set_missing_job_yields_just_the_unit():
    store = CountingStore()
    assert merge_for(store).release_set('gone') == ['gone']


def test_blocked_head_with_wait_but_no_waiter_stays_quiet():
    store, queue, leases = admitted({'a': 1})  # Only the leased head; nothing ready.
    assert store.head_pending(OWNER) is not None
    merge = merge_for(store, wait=W)
    store.reset_counts()
    assert merge.commit_next('heavy', 10 + 10**6) is None
    assert store.runs == 0  # No ready row: the expired-wait probe is empty, no bypass either.


def test_queued_head_bypass_after_the_wait():
    store, _queue, _leases = admitted({'a': 1, 'b': 2})  # a queued, never pulled.
    complete(_queue, _leases, 'b', 10)
    merge = merge_for(store, wait=W)
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['segment_id'] == 'b' and entry['head_wait_bypass'] is True


def test_retry_head_bypass_after_the_wait():
    store, _queue, _leases = blocked_head_setup('retry')
    merge = merge_for(store, wait=W)
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['segment_id'] == 'b' and entry['head_wait_bypass'] is True


def test_record_pending_head_bypass_after_the_wait():
    store, _queue, _leases = blocked_head_setup('record_pending')
    merge = merge_for(store, wait=W)
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['segment_id'] == 'b' and entry['head_wait_bypass'] is True


def test_head_wait_unavailable_suppresses_later_bypass_attempts():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'b', 10)
    merge = merge_for(store, wait=W)
    store.longest_ready_error = FailedPrecondition('index missing')
    assert merge.commit_next('heavy', 10 + W) is None  # Fallback to strict order.
    store.longest_ready_error = None
    assert merge.commit_next('heavy', 10 + 10**6) is None  # The retry window keeps strict order.


def test_two_merge_instances_keep_their_own_held_hints():
    store, _queue, _leases = blocked_head_setup('leased')
    first = merge_for(store)
    second = merge_for(store)
    first.held_owners.add('heavy')
    assert second.held_owners == set()  # Instance-scoped, never class-global.


def test_two_merge_instances_share_the_underlying_rows():
    store, queue, leases = admitted({'a': 1})
    complete(queue, leases, 'a', 10)
    first = merge_for(store)
    second = merge_for(store)
    assert first.commit_next('heavy', 10)['segment_id'] == 'a'
    assert second.commit_next('heavy', 10) is None  # The row is already committed.


# --------------------------------------------------------------------------
# Section T — storm and flag interplay extras
# --------------------------------------------------------------------------


def test_damper_flag_off_leaves_blocked_drains_untouched(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    clock = FakeClock()
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = StormClient(storm_rows('leased'))
    merge, _store = storm_merge(monkeypatch, client, damper=damper)
    assert merge.commit_next('heavy', 10) is None
    assert clock.sleeps == [] and client.transactions == 0


def test_retry_flag_off_ready_head_lands_on_a_quiet_store(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'a']['state'] = 'result_ready'
    rows[f'{NAMESPACE}_jobs', 'a']['ready_at'] = 5.0
    rows[f'{NAMESPACE}_jobs', 'a']['result'] = {'uri': 'gs://results/a'}
    client = StormClient(rows, aborts=0)
    merge, _store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 10)  # One unladdered attempt still lands.
    assert entry['segment_id'] == 'a'
    assert client.commits == 1


def test_retry_flag_off_loses_the_ladder_the_sdk_own_retry_raises(monkeypatch):
    """With the ladder off, aborts are retried (and eventually raised) by the SDK's
    own transaction retry — never converted into FirestoreContentionExhausted."""
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_jobs', 'a']['state'] = 'result_ready'
    rows[f'{NAMESPACE}_jobs', 'a']['ready_at'] = 5.0
    rows[f'{NAMESPACE}_jobs', 'a']['result'] = {'uri': 'gs://results/a'}
    client = StormClient(rows, aborts=10**6)
    merge, _store = storm_merge(monkeypatch, client)
    with pytest.raises(ValueError):  # The SDK transaction's own attempt cap, not the ladder.
        merge.commit_next('heavy', 10)
    assert client.commits == 1  # One attempt: the fake transaction caps itself at one.


def test_blocked_drain_repeated_ten_times_costs_zero_transactions(monkeypatch):
    client = StormClient(storm_rows('leased'))
    merge, _store = storm_merge(monkeypatch, client)
    for _ in range(10):
        assert merge.commit_next('heavy', 10) is None
    assert client.transactions == 0 and client.commits == 0


def test_bypass_under_a_partial_storm_retries_then_lands(monkeypatch):
    client = StormClient(storm_rows('leased'), aborts=1)
    merge, _store = storm_merge(monkeypatch, client, wait=W)
    entry = merge.commit_next('heavy', 10 + W)
    assert entry['segment_id'] == 'b' and entry['head_wait_bypass'] is True
    assert client.commits == 2  # One heartbeat abort, then the commit.


def test_gate_records_no_committed_metric_on_the_skip_path():
    store, _queue, _leases = blocked_head_setup('leased')
    metrics = Mock()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0, metrics=metrics)
    merge.commit_next('heavy', 10)
    metrics.record.assert_not_called()


def test_gate_records_no_correctness_metric_on_the_skip_path():
    from utils.batch_pipeline import correctness_metrics

    store, _queue, _leases = blocked_head_setup('leased')
    merge = merge_for(store)
    before = dict(correctness_metrics.SAMPLES) if hasattr(correctness_metrics, 'SAMPLES') else None
    merge.commit_next('heavy', 10)
    after = dict(correctness_metrics.SAMPLES) if hasattr(correctness_metrics, 'SAMPLES') else None
    assert before == after


def test_committed_metric_recorded_on_the_ready_path():
    store, queue, leases = admitted({'a': 1})
    complete(queue, leases, 'a', 10)
    metrics = Mock()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0, metrics=metrics)
    merge.commit_next('heavy', 10)
    metrics.record.assert_called_once_with('committed')


def test_entry_is_a_snapshot_not_store_state():
    store, queue, leases = admitted({'a': 1})
    complete(queue, leases, 'a', 10)
    entry = merge_for(store).commit_next('heavy', 10)
    entry['result'] = {'tampered': True}
    assert store.rows['results', 'a']['result'] != {'tampered': True}


def test_marker_probe_staleness_on_the_real_store_skips_the_marker(monkeypatch):
    """The documented divergence: a stale owners probe undershoots the cap, the
    marker write waits for a later drain."""
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_owners', OWNER] = {'log_sequence': 2, 'projection_watermark': 'w1'}
    rows[f'{NAMESPACE}_results', 'w1'] = {'log_sequence': 1}
    client = StormClient(rows, aborts=0)
    merge, _store = storm_merge(monkeypatch, client, depth=4)
    assert merge.commit_next('heavy', 10) is None
    assert client.rows.get((f'{NAMESPACE}_merge_holds', OWNER)) is None


def test_marker_probe_on_the_real_store_matches_the_body_at_the_cap(monkeypatch):
    rows = storm_rows('leased')
    rows[f'{NAMESPACE}_owners', OWNER] = {'log_sequence': 6, 'projection_watermark': 'w5'}
    rows[f'{NAMESPACE}_results', 'w5'] = {'log_sequence': 1}
    client = StormClient(rows, aborts=0)
    merge, _store = storm_merge(monkeypatch, client, depth=4)
    assert merge.commit_next('heavy', 10) is None
    assert client.rows[f'{NAMESPACE}_merge_holds', OWNER]['held'] is True
    assert client.transactions == 1  # Only the marker transaction.


def test_firestore_store_head_pending_requires_no_transaction_object(monkeypatch):
    client = StormClient(storm_rows('leased'))
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore(NAMESPACE, firestore_client=client)
    row = store.head_pending(OWNER)
    row['state'] = 'mutated'
    assert client.rows[f'{NAMESPACE}_jobs', 'a']['state'] == 'leased'  # Point read returned a copy.
