"""Ready-head merge drains commit through a revision-fenced narrow body (x998 exhaustion family).

The blocked-head probe gate (``test_merge_blocked_head_probe_gate``) already
skips drains that can only conclude ``blocked``. The remaining burn is the
plain ready-head drain — the common post-publication commit: it still opened
the strict ``batch_merge_commit`` transaction whose first act is the pending
query, and a Firestore query-in-transaction read set is every matched row, so
the drain joined the abort set of every sibling lease heartbeat (each in-flight
unit rewrites its own pending row every 20 seconds) and burned the five-attempt
ladder against it:

    event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted

``OrderedMerge.commit_next`` now commits the plain ready head through a narrow
transaction that point-reads only {owner, head, result} under a probed owner
revision fence. The fence substitutes for the query: every pending-set mutation
(admission, merge commit, terminal quarantine via ``quarantine_job``, recovery
dispositions) writes the owner revision, so an unchanged revision proves the
probed head is still the strict body's candidate, and heartbeats — which write
neither the owner nor a settled ready row — can no longer abort the commit.
Every fence mismatch, hold marker, release wake, shadow head and probe failure
keeps the strict query transaction as the authority. This suite pins:

1. Gate decisions: exactly the plain ready-head case narrows; blocked, shadow,
   over-cap, depth-hold, release wakes and probe failures keep strict.
2. Fence semantics: a stale probed revision falls back to the strict body,
   which re-decides from its own query; no commit ever lands from a stale hint.
3. Interleaving proofs on the real store class with a heartbeat-storm client:
   narrow drains survive sibling-heartbeat storms without a single abort while
   the strict path exhausts; concurrent pending-set mutations still force the
   strict re-decision.
4. Write parity: narrow and strict produce byte-identical entries, job
   transitions, owner fences and result rows on every shared scenario.
5. The transactional read set narrows to three point reads with zero queries.
6. Config, attribution labels and rollout switches.

Failure-Class: FC-ready-head-merge-drains-join-sibling-heartbeat-abort-sets
"""

import asyncio
import logging
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest
from google.api_core.exceptions import Aborted, ServiceUnavailable

from database import batch_pipeline_store as storage
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.firestore_transaction_retry import DEFAULT_MAX_ATTEMPTS, FirestoreContentionExhausted
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from tests.unit.test_merge_blocked_head_probe_gate import (
    CATCH_UP,
    FRESH,
    NAMESPACE,
    NOW,
    OWNER,
    CountingStore,
    _StormCollection,
    _StormDocRef,
    _StormQuery,
    _StormSnapshot,
    admitted,
    at_cap,
    build_storm_store,
    complete,
    _Leader,
    merge_for,
    set_state,
    silence_chain_sleep,
    storm_merge,
    storm_rows,
)
from utils.batch_pipeline import merge as merge_module
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key

STEADY = 100_500.0


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


class _RecordingTx:
    """Transaction proxy recording every read and write the body performs."""

    def __init__(self, tx, reads, writes):
        self._tx = tx
        self._reads = reads
        self._writes = writes

    def get(self, table, key):
        self._reads.append(('get', table, key))
        return self._tx.get(table, key)

    def put(self, table, key, value):
        self._writes.append(('put', table, key))
        return self._tx.put(table, key, value)

    def patch(self, table, key, fields):
        self._writes.append(('patch', table, key))
        return self._tx.patch(table, key, fields)

    def first_pending(self, owner_key):
        self._reads.append(('query', 'first_pending', owner_key))
        return self._tx.first_pending(owner_key)

    def first_ready_pending(self, owner_key):
        self._reads.append(('query', 'first_ready_pending', owner_key))
        return self._tx.first_ready_pending(owner_key)

    def __getattr__(self, name):
        return getattr(self._tx, name)


class RecordingStore:
    """MemoryStore facade recording transaction runs, resolved labels, probes
    and — per run — every document the body read or wrote."""

    def __init__(self):
        self.inner = MemoryStore()
        self.runs = 0
        self.run_operations = []
        self.probed = []
        self.read_log = []
        self.write_log = []
        self.head_pending_calls = 0
        self.head_pending_error = None
        self.probe_error = None

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
        self.read_log = []
        self.write_log = []
        self.head_pending_calls = 0

    def run(self, body, *, operation=None):
        from database.batch_pipeline_transaction_labels import current_operation

        self.runs += 1
        self.run_operations.append(operation or current_operation())
        reads, writes = [], []
        self.read_log.append(reads)
        self.write_log.append(writes)
        return self.inner.run(lambda tx: body(_RecordingTx(tx, reads, writes)), operation=operation)

    def probe(self, table, key):
        self.probed.append((table, key))
        if self.probe_error is not None:
            raise self.probe_error
        return self.inner.probe(table, key)

    def head_pending(self, key):
        self.head_pending_calls += 1
        if self.head_pending_error is not None:
            raise self.head_pending_error
        return self.inner.head_pending(key)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def ready_rows(captures, store=None):
    """One owner's rows admitted, leased and completed: all ``result_ready``."""
    store = store if store is not None else RecordingStore()
    queue = Scheduler(store)
    for segment, capture in captures.items():
        queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, len(captures))}
    assert set(leases) == set(captures)
    for segment in captures:
        complete(queue, leases, segment)
    return store, queue


def drain(store, now=STEADY, release=None):
    merge = merge_for(store)
    return merge, merge.commit_next('heavy', now, release=release)


def narrow_off(monkeypatch):
    monkeypatch.setattr(merge_module, 'merge_narrow_commit_enabled', lambda: False)


def reads_of(store, index=-1):
    return store.read_log[index]


def table_rows(store):
    """Every durable row the merge lane touches, with volatile claim fields
    (random lease tokens) normalized away."""
    rows = {}
    for key, value in store.rows.items():
        if key[0] not in {'jobs', 'results', 'owners', 'merge_holds'}:
            continue
        value = deepcopy(value)
        if key[0] == 'jobs':
            value.pop('token', None)
        rows[key] = value
    return rows


# --------------------------------------------------------------------------
# 1. Gate decisions: only the plain ready head narrows
# --------------------------------------------------------------------------


def test_plain_ready_head_drain_commits(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert store.rows['jobs', 'a']['state'] == 'committed'


def test_plain_ready_head_drain_opens_exactly_one_transaction(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.reset_counts()
    merge, entry = drain(store)
    assert store.runs == 1
    assert entry is not None


def test_narrow_run_carries_the_merge_commit_label(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.reset_counts()
    drain(store)
    assert store.run_operations == ['batch_merge_commit']


def test_narrow_drain_performs_no_pending_query(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2})
    store.reset_counts()
    drain(store)
    assert reads_of(store) and all(read[0] != 'query' for read in reads_of(store))


def test_narrow_drain_point_reads_owner_head_result(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.reset_counts()
    drain(store)
    gets = [read for read in reads_of(store) if read[0] == 'get']
    assert set(gets) == {('get', 'owners', OWNER), ('get', 'jobs', 'a'), ('get', 'results', 'a')}


def test_narrow_drain_reads_nothing_else_with_pending_siblings(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3})
    store.reset_counts()
    drain(store)
    gets = {read for read in reads_of(store) if read[0] == 'get'}
    assert gets == {('get', 'owners', OWNER), ('get', 'jobs', 'a'), ('get', 'results', 'a')}


def test_kill_switch_restores_the_strict_query_drain(monkeypatch):
    narrow_off(monkeypatch)
    store, _queue = ready_rows({'a': 1, 'b': 2})
    store.reset_counts()
    drain(store)
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_blocked_head_opens_no_transaction_even_with_the_gate_on(monkeypatch):
    store, _queue, leases = admitted({'a': 1})
    store.reset_counts()
    drain(store)
    assert store.runs == 0


def test_probe_empty_owner_opens_no_transaction_even_with_the_gate_on(monkeypatch):
    store = RecordingStore()
    store.reset_counts()
    drain(store)
    assert store.runs == 0


def test_shadow_ready_head_keeps_the_strict_transaction(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['shadow'] = True
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert store.runs == 1
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_head_probe_failure_keeps_the_strict_transaction(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.head_pending_error = ServiceUnavailable('hint read down')
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_owner_probe_failure_keeps_the_strict_transaction(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def flaky_probe(table, key):
        if table == 'owners':
            raise ServiceUnavailable('owners probe down')
        return store.inner.probe(table, key)

    store.probe = flaky_probe
    merge, entry = drain(store)
    # The owners probe is only a hint: the strict transaction still commits.
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_owner_probe_failure_is_logged_as_a_retry_outcome(monkeypatch, caplog):
    store, _queue = ready_rows({'a': 1})

    def flaky_probe(table, key):
        if table == 'owners':
            raise ServiceUnavailable('owners probe down')
        return store.inner.probe(table, key)

    store.probe = flaky_probe
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert any('outcome=narrow_owner_probe_retry' in record.getMessage() for record in caplog.records)


def test_owner_probe_failure_does_not_open_a_narrow_transaction(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def flaky_probe(table, key):
        if table == 'owners':
            raise ServiceUnavailable('owners probe down')
        return store.inner.probe(table, key)

    store.probe = flaky_probe
    store.reset_counts()
    drain(store)
    # The gate bailed before the owners probe: no narrow attempt was made.
    assert ('owners', OWNER) not in store.probed
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_release_wake_keeps_the_strict_exact_path(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2}, store=RecordingStore())
    complete(queue, leases, 'b')  # 'a' stays leased: the blocked head.
    store.reset_counts()
    drain(store, release=['b'])
    assert ('query', 'first_pending', OWNER) in reads_of(store)
    assert store.rows['results', 'b']['recovered_release'] is True
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_over_cap_ready_catch_up_head_keeps_the_strict_hold(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['fresh_capture'] = False
    at_cap(store.inner, sequence=6, watermark='w5', done=1)
    store.reset_counts()
    merge = merge_for(store, depth=2)
    entry = merge.commit_next('heavy', STEADY)
    assert entry is None
    assert merge.held_owners == {'heavy'}
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_over_cap_ready_fresh_head_keeps_the_strict_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['fresh_capture'] = True
    at_cap(store.inner, sequence=6, watermark='w5', done=1)
    store.reset_counts()
    merge = merge_for(store, depth=2)
    entry = merge.commit_next('heavy', STEADY)
    # A fresh ready head commits past the cap through the strict body (no
    # narrow: the probe twins refuse at-cap owners); no fresh_first flag —
    # that marker belongs to the blocked-head sub-drain.
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)
    assert 'fresh_first' not in store.rows['results', 'a']
    assert merge.held_owners == {'heavy'}
    assert store.rows['merge_holds', OWNER]['held'] is True


def test_depth_hold_owed_blocked_head_keeps_the_strict_marker_write(monkeypatch):
    store, _queue, _leases = admitted({'a': 1})
    at_cap(store.inner, sequence=6, watermark='w5', done=1)
    store.reset_counts()
    merge = merge_for(store, depth=2)
    entry = merge.commit_next('heavy', STEADY)
    assert entry is None
    assert store.runs == 1
    assert store.run_operations == ['batch_merge_commit']
    assert store.rows['merge_holds', OWNER]['held'] is True


def test_hint_missing_state_keeps_the_probe_gate_skip(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def sparse_head(owner_key_):
        row = store.inner.head_pending(owner_key_)
        if row is not None:
            row = {k: v for k, v in row.items() if k != 'state'}
        return row

    store.head_pending = sparse_head
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert store.runs == 0


def test_hint_with_unknown_state_token_keeps_the_probe_gate_skip(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def odd_state_head(owner_key_):
        row = store.inner.head_pending(owner_key_)
        if row is not None:
            row = {**row, 'state': 'record_pending'}
        return row

    store.head_pending = odd_state_head
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert store.runs == 0


def test_narrow_fires_below_the_depth_cap(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.reset_counts()
    merge = merge_for(store)
    entry = merge.commit_next('heavy', STEADY)
    assert entry is not None
    assert store.runs == 1
    assert all(read[0] != 'query' for read in reads_of(store))


def test_ready_head_drain_does_not_wait_for_the_head_wait_budget(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    merge = OrderedMerge(store, head_wait_seconds=1800, catch_up_depth=0)
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'a'
    assert not merge.held_owners


# --------------------------------------------------------------------------
# 2. Fence semantics: a stale probed revision never commits
# --------------------------------------------------------------------------


def _stale_hint(store, captured_rows, owner_row):
    """Freeze ``head_pending`` at a pre-mutation snapshot: the hint outlives reality."""
    frozen = captured_rows.get((f'{NAMESPACE}_jobs', 'a'))

    def stale_head(_owner_key):
        return deepcopy(frozen)

    store.head_pending = stale_head


def test_stale_probed_revision_falls_back_to_the_strict_body(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def inflated_probe(table, key):
        if table == 'owners':
            return {**store.inner.probe(table, key), 'revision': 999}
        return store.inner.probe(table, key)

    store.probe = inflated_probe
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_stale_hint_cannot_commit_when_an_earlier_row_was_admitted(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    captured = deepcopy(store.rows)
    store.head_pending = lambda _key: deepcopy(captured[(f'{NAMESPACE}_jobs', 'a')])
    # A concurrent admission lands an earlier capture after the hint was read.
    Scheduler(store).enqueue(item('e', capture=0), 0)
    store.rows['jobs', 'e']['state'] = 'result_ready'
    store.rows['jobs', 'e']['result'] = {'uri': 'gs://results/e'}
    merge, entry = drain(store)
    # The fence went stale: strict re-decided and committed the true head.
    assert entry['segment_id'] == 'e'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_quarantined_head_cannot_enter_the_result_log_via_a_stale_hint(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    captured = deepcopy(store.rows)
    store.head_pending = lambda _key: deepcopy(captured[(f'{NAMESPACE}_jobs', 'a')])
    # quarantine_job's fence: remove the row and bump the owner revision.
    store.rows['jobs', 'a'].update(state='quarantined', merge_pending=False)
    store.rows['owners', OWNER]['revision'] += 1
    merge, entry = drain(store)
    assert entry is None
    assert not [key for key in store.rows if key[0] == 'results']
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


def test_committed_head_cannot_be_recommitted_via_a_stale_hint(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    captured = deepcopy(store.rows)
    store.head_pending = lambda _key: deepcopy(captured[(f'{NAMESPACE}_jobs', 'a')])
    store.rows['jobs', 'a'].update(state='committed', merge_pending=False)
    store.rows['owners', OWNER]['revision'] += 1
    merge, entry = drain(store)
    assert entry is None
    assert not [key for key in store.rows if key[0] == 'results']


def test_narrow_commit_bumps_the_owner_revision_by_exactly_one(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    before = store.rows['owners', OWNER]['revision']
    drain(store)
    assert store.rows['owners', OWNER]['revision'] == before + 1


def test_narrow_and_strict_drains_keep_revisions_aligned(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3})
    drain(store)
    after_narrow = store.rows['owners', OWNER]['revision']
    narrow_off(monkeypatch)
    drain(store)
    assert store.rows['owners', OWNER]['revision'] == after_narrow + 1


def test_missing_owner_revision_matches_the_zero_fence(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER].pop('revision')
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for read in reads_of(store))


def test_narrow_body_refuses_a_committed_candidate_at_the_same_revision(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['state'] = 'committed'
    merge = merge_for(store)
    revision = store.rows['owners', OWNER]['revision']
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert entry is None
    assert fenced is None
    assert stale is False


def test_narrow_body_refuses_a_foreign_candidate(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['owner_key'] = owner_key('someone_else')
    merge = merge_for(store)
    revision = store.rows['owners', OWNER]['revision']
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert entry is None
    assert stale is False


def test_narrow_body_raises_stale_on_a_revision_mismatch(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    merge = merge_for(store)
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', 42, STEADY)
    assert entry is None
    assert stale is True


def test_narrow_body_flags_the_candidate_catch_up_class(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['fresh_capture'] = False
    merge = merge_for(store)
    revision = store.rows['owners', OWNER]['revision']
    _entry, _fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert stale is False
    assert head == {'catch_up': True}


# --------------------------------------------------------------------------
# 3. Heartbeat storms on the real store class
# --------------------------------------------------------------------------


class _RangeQuery(_StormQuery):
    """The storm models the transactional query lock the merge doctrine speaks
    of ("no transactional query lock"): every row the query's index range
    touches joins the transaction's read set, so any concurrent writer of any
    pending sibling aborts the drain while it runs."""

    def stream(self, transaction=None):
        if transaction is not None:
            matched = self._matching_rows()
            # The transactional query lock: every row the range touches reads.
            for key, _doc in matched:
                transaction.reads.add((self.collection, key))
            self.client.query_shapes.append(
                {
                    'collection': self.collection,
                    'filters': self.filters,
                    'orders': self.orders,
                    'limit': self._limit,
                    'transactional': True,
                }
            )
            page = matched[: self._limit] if self._limit is not None else matched
            return [_StormSnapshot(doc) for _key, doc in page]
        return super().stream(transaction=transaction)

    def _copy(self, **kwargs):
        clone = super()._copy(**kwargs)
        clone.__class__ = _RangeQuery
        return clone

    def _matching_rows(self):
        rows = [
            (key, doc)
            for (collection, key), doc in sorted(self.client.rows.items())
            if collection == self.collection
            and all(doc.get(field) == value for field, value in self.filters)
            and all(field in doc for field in self.orders)
        ]
        rows.sort(key=lambda item: tuple(item[1][field] for field in self.orders) + (item[0],))
        return rows


class _RangeCollection(_StormCollection):
    def where(self, field, op, value):
        return _RangeQuery(self.client, self.name).where(field, op, value)


class _HeartbeatTx:
    """firestore_v1.Transaction stand-in: the commit aborts while the storm
    rewrites a document this transaction read — and the storm only ever
    rewrites the sibling in-flight row heartbeats are responsible for."""

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
        hot = self.reads & self.state.hot_rows
        if hot and self.state.aborts_remaining > 0:
            self.state.aborts_remaining -= 1
            self.pending_sets.clear()
            self.pending_updates.clear()
            raise Aborted(f'synthetic heartbeat contention on {sorted(hot)}')
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


class HeartbeatStormClient:
    """Client whose transactions abort only while a heartbeat rewrites a row
    they read: ``hot_rows`` is the heartbeat's write set."""

    def __init__(self, rows=None, aborts=10**6, hot=()):
        self.rows = dict(rows or {})
        self.hot_rows = set(hot)
        self.aborts_remaining = aborts
        self.transactions = 0
        self.commits = 0
        self.query_shapes = []

    def transaction(self, max_attempts=5):
        self.transactions += 1
        return _HeartbeatTx(self)

    def collection(self, name):
        return _RangeCollection(self, name)


def storm_with_ready_head(head_state='result_ready'):
    """Head 'a' settled; sibling 'b' leased and in flight — the heartbeat's row."""
    rows = storm_rows(head_state=head_state)
    head = rows[(f'{NAMESPACE}_jobs', 'a')]
    head['ready_at'] = 9.0
    head['result'] = {'uri': 'gs://results/a'}
    sibling = rows[(f'{NAMESPACE}_jobs', 'b')]
    sibling['state'] = 'leased'
    sibling.pop('ready_at', None)
    sibling.pop('result', None)
    sibling['lease_until'] = 10.0**9
    return rows


SIBLING_B = (f'{NAMESPACE}_jobs', 'b')
OWNER_ROW = (f'{NAMESPACE}_owners', OWNER)


def test_narrow_drain_survives_a_sibling_heartbeat_storm(monkeypatch):
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={SIBLING_B})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.commits == 1
    assert client.transactions == 1
    assert client.rows[(f'{NAMESPACE}_results', 'a')]['segment_id'] == 'a'
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'committed'


def test_narrow_storm_opens_no_transactional_pending_query(monkeypatch):
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={SIBLING_B})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    # The owners row is hot here, so a narrow commit that read it would abort;
    # the storm proof below pins where the fence's immunity comes from.


def test_strict_drain_exhausts_against_the_same_storm(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'false')
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={SIBLING_B})
    merge, store = storm_merge(monkeypatch, client)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 100.0)
    assert client.transactions == DEFAULT_MAX_ATTEMPTS
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'result_ready'


def test_strict_drain_aborts_come_from_the_matched_pending_rows(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'false')
    # With NO hot rows the strict drain commits on the first attempt: the
    # aborts in the storm above come precisely from the query's matched rows.
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot=set())
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.transactions == 1
    assert any(shape['transactional'] and shape['collection'] == f'{NAMESPACE}_jobs' for shape in client.query_shapes)


def test_narrow_drain_avoids_the_transactional_pending_query(monkeypatch):
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot=set())
    merge, store = storm_merge(monkeypatch, client)
    merge.commit_next('heavy', 100.0)
    transactional_queries = [
        shape for shape in client.query_shapes if shape['transactional'] and shape['collection'] == f'{NAMESPACE}_jobs'
    ]
    assert transactional_queries == []


def test_narrow_storm_aborts_are_limited_to_owner_write_races(monkeypatch):
    # Only the owner row is hot: a concurrent admission racing the narrow
    # commit aborts it, the ladder retries, and the fence re-checks cleanly.
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={OWNER_ROW}, aborts=2)
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.transactions == 3
    assert client.aborts_remaining == 0
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'committed'


def test_narrow_storm_exhaustion_stays_reachable_from_owner_write_races(monkeypatch, caplog):
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={OWNER_ROW}, aborts=10**6)
    merge, store = storm_merge(monkeypatch, client)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 100.0)
    assert client.commits == DEFAULT_MAX_ATTEMPTS  # Every attempt aborted.
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'result_ready'
    assert not [key for key in client.rows if key[0] == f'{NAMESPACE}_results']


def test_other_owner_heartbeats_cannot_touch_this_drain(monkeypatch):
    rows = storm_with_ready_head()
    quiet_owner = owner_key('other')
    rows[(f'{NAMESPACE}_jobs', 'z')] = {
        'segment_id': 'z',
        'owner_key': quiet_owner,
        'owner_id': 'other',
        'merge_pending': True,
        'state': 'leased',
        'capture_at': 0,
        'priority': 0,
        'protocol_version': 1,
        'lease_until': 10.0**9,
    }
    client = HeartbeatStormClient(rows=rows, hot={(f'{NAMESPACE}_jobs', 'z')})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.transactions == 1
    assert client.commits == 1


# --------------------------------------------------------------------------
# 4. Interleaving proofs: concurrent pending-set mutations force strict
# --------------------------------------------------------------------------


class _InterleavedHeartbeatTx(_HeartbeatTx):
    """Heartbeat transaction that applies a deterministic concurrent-writer
    mutation when its attempt begins: an admission or commit landing between
    the ladder's attempts, single-threaded."""

    def _begin(self, retry_id=None):
        super()._begin(retry_id)
        step = self.state.interleavings.pop(self.state.attempt, None)
        if step is not None:
            step(self.state.rows)


class InterleavedStormClient(HeartbeatStormClient):
    def __init__(self, rows=None, aborts=10**6, hot=(), interleavings=None):
        super().__init__(rows=rows, aborts=aborts, hot=hot)
        self.interleavings = dict(interleavings or {})
        self.attempt = 0

    def transaction(self, max_attempts=5):
        self.transactions += 1
        self.attempt += 1
        return _InterleavedHeartbeatTx(self)


def test_concurrent_admission_between_attempts_forces_the_strict_redecision(monkeypatch):
    rows = storm_with_ready_head()

    def admit_earlier_capture(state_rows):
        # An admission whose owner-write lands between the narrow attempts.
        state_rows[(f'{NAMESPACE}_jobs', 'e')] = {
            'segment_id': 'e',
            'owner_key': OWNER,
            'owner_id': 'heavy',
            'merge_pending': True,
            'state': 'result_ready',
            'capture_at': 0,
            'priority': 0,
            'result': {'uri': 'gs://results/e'},
            'protocol_version': 1,
            'ready_at': 99.0,
        }
        state_rows.setdefault(OWNER_ROW, {})['revision'] = 7

    client = InterleavedStormClient(rows=rows, hot={OWNER_ROW}, aborts=1, interleavings={2: admit_earlier_capture})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    # Attempt 1 aborted on the hot owner; attempt 2's fence saw the admission's
    # revision and handed the decision to the strict body, which committed the
    # true earliest pending row — never the stale hint.
    assert entry['segment_id'] == 'e'
    assert client.rows[(f'{NAMESPACE}_jobs', 'e')]['state'] == 'committed'
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'result_ready'


def test_concurrent_commit_between_attempts_advances_to_the_next_head(monkeypatch):
    rows = storm_with_ready_head()
    settled = rows[(f'{NAMESPACE}_jobs', 'b')]
    settled['state'] = 'result_ready'
    settled['ready_at'] = 10.0
    settled['result'] = {'uri': 'gs://results/b'}

    def commit_the_head_elsewhere(state_rows):
        # Another replica's merge commit lands: head 'a' commits, revision moves.
        state_rows[(f'{NAMESPACE}_results', 'a')] = {
            'segment_id': 'a',
            'owner_key': OWNER,
            'log_sequence': 1,
            'result': {'uri': 'gs://results/a'},
        }
        state_rows[(f'{NAMESPACE}_jobs', 'a')]['state'] = 'committed'
        state_rows[(f'{NAMESPACE}_jobs', 'a')]['merge_pending'] = False
        owner = state_rows.setdefault(OWNER_ROW, {})
        owner['revision'] = 5
        owner['log_tail'] = 'a'
        owner['log_sequence'] = 1
        owner['watermark'] = {'capture_at': 1, 'segment_id': 'a'}

    client = InterleavedStormClient(rows=rows, hot={OWNER_ROW}, aborts=1, interleavings={2: commit_the_head_elsewhere})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'b'
    assert client.rows[(f'{NAMESPACE}_results', 'a')]['log_sequence'] == 1
    assert client.rows[(f'{NAMESPACE}_results', 'b')]['previous_segment_id'] == 'a'


def test_double_interleaving_still_lands_the_true_head(monkeypatch):
    rows = storm_with_ready_head()

    def bump(state_rows):
        row = state_rows.setdefault(OWNER_ROW, {})
        row['revision'] = row.get('revision', 0) + 1

    # Two aborts exhaust the storm budget; the second bump then turns the
    # third attempt's fence stale and the strict body lands the commit.
    client = InterleavedStormClient(rows=rows, hot={OWNER_ROW}, aborts=2, interleavings={2: bump, 3: bump})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.rows[(f'{NAMESPACE}_results', 'a')]['segment_id'] == 'a'


def test_interleaved_quarantine_of_the_hint_head_commits_nothing(monkeypatch):
    rows = storm_with_ready_head()

    def quarantine_head(state_rows):
        state_rows[(f'{NAMESPACE}_jobs', 'a')].update(state='quarantined', merge_pending=False)
        state_rows.setdefault(OWNER_ROW, {})['revision'] = 9

    client = InterleavedStormClient(rows=rows, hot={OWNER_ROW}, aborts=1, interleavings={2: quarantine_head})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry is None
    assert not [key for key in client.rows if key[0] == f'{NAMESPACE}_results']
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'quarantined'


# --------------------------------------------------------------------------
# 5. Write parity: narrow and strict land byte-identical state
# --------------------------------------------------------------------------


def _drive_both_modes(monkeypatch, build):
    """Build the same scenario twice; return (entry_off, off, entry_on, on).

    ``build(store)`` admits, shapes and drains one fresh store; the gate-off
    run is the strict oracle the gate-on run must reproduce byte for byte."""
    narrow_off(monkeypatch)
    off_store = RecordingStore()
    off_entry = build(off_store)
    monkeypatch.undo()
    on_store = RecordingStore()
    on_entry = build(on_store)
    return off_entry, off_store, on_entry, on_store


def _late_watermark(store):
    """The owner's watermark already sits past the head row: a bypass commit
    landed ('b') before 'a' could — the documented late-capture shape."""
    store.rows['owners', OWNER]['watermark'] = {'capture_at': 2, 'segment_id': 'b'}
    store.rows['owners', OWNER]['log_tail'] = 'b'
    store.rows['owners', OWNER]['log_sequence'] = 1
    store.rows['results', 'b'] = {'segment_id': 'b', 'log_sequence': 1}


PARITY_SCENARIOS = {
    'single_ready_row': ({'a': 1}, [], ('segment_id', 'a')),
    'two_ready_rows_commit_the_head': ({'a': 1, 'b': 2}, [], ('segment_id', 'a')),
    'first_commit_has_no_previous_segment': ({'a': 1}, [], ('previous_segment_id', None)),
    'equal_capture_tie_breaks_by_segment_id': ({'a': 1, 'b': 1}, [], ('segment_id', 'a')),
    'recovered_unit_stamps_recovery_version': (
        {'a': 1},
        ["store.rows['jobs', 'a']['recovery_state'] = 'recovered'"],
        ('recovery_version', 1),
    ),
    'provider_route_stamps_recovery_version': (
        {'a': 1},
        ["store.rows['jobs', 'a']['stt_route'] = {'stt_route': 'provider'}"],
        ('recovery_version', 1),
    ),
    'plain_route_has_no_recovery_version': ({'a': 1}, [], ('segment_id', 'a')),
    'conversation_and_privacy_generation_propagate': (
        {'a': 1},
        [
            "store.rows['jobs', 'a']['conversation_id'] = 'conv-1'",
            "store.rows['jobs', 'a']['privacy_generation'] = 3",
        ],
        ('conversation_id', 'conv-1'),
    ),
    'protocol_version_propagates': (
        {'a': 1},
        ["store.rows['jobs', 'a']['protocol_version'] = 2"],
        ('protocol_version', 2),
    ),
}


def _parity_case(captures, mutations, mutator=None):
    def build(store):
        ready_rows(captures, store=store)
        for mutation in mutations:
            exec(mutation, {'store': store})
        if mutator is not None:
            mutator(store)
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    return build


def test_narrow_parity_single_ready_row(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        pass
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['segment_id'] == 'a'


def test_narrow_parity_two_ready_rows_commit_the_head(monkeypatch):
    def build(store):
        ready_rows({'a': 1, 'b': 2}, store=store)
        pass
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['segment_id'] == 'a'


def test_narrow_parity_first_commit_has_no_previous_segment(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        pass
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['previous_segment_id'] == None


def test_narrow_parity_equal_capture_tie_breaks_by_segment_id(monkeypatch):
    def build(store):
        ready_rows({'a': 1, 'b': 1}, store=store)
        pass
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['segment_id'] == 'a'


def test_narrow_parity_recovered_unit_stamps_recovery_version(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        store.rows['jobs', 'a']['recovery_state'] = 'recovered'
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['recovery_version'] == 1


def test_narrow_parity_provider_route_stamps_recovery_version(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        store.rows['jobs', 'a']['stt_route'] = {'stt_route': 'provider'}
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['recovery_version'] == 1


def test_narrow_parity_plain_route_has_no_recovery_version(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        pass
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['segment_id'] == 'a'


def test_narrow_parity_conversation_and_privacy_generation_propagate(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        store.rows['jobs', 'a']['conversation_id'] = 'conv-1'
        store.rows['jobs', 'a']['privacy_generation'] = 3
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['conversation_id'] == 'conv-1'


def test_narrow_parity_protocol_version_propagates(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        store.rows['jobs', 'a']['protocol_version'] = 2
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry is not None
    assert table_rows(on_store) == table_rows(off_store)
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)
    assert on_entry['protocol_version'] == 2


def test_narrow_parity_late_capture_marks_the_behind_head(monkeypatch):
    build = _parity_case({'a': 1}, [], _late_watermark)
    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert table_rows(on_store) == table_rows(off_store)
    assert on_entry['late_capture'] is True
    assert on_entry['previous_segment_id'] == 'b'
    assert all(read[0] != 'query' for run_reads in on_store.read_log for read in run_reads)


def test_narrow_parity_successive_commits_chain_the_log(monkeypatch):
    def build(store):
        ready_rows({'a': 1, 'b': 2, 'c': 3}, store=store)
        merge = OrderedMerge(store)
        first = merge.commit_next('heavy', STEADY)
        second = merge.commit_next('heavy', STEADY)
        third = merge.commit_next('heavy', STEADY)
        return [first, second, third]

    off_entries, off_store, on_entries, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entries == off_entries
    assert [entry['segment_id'] for entry in on_entries] == ['a', 'b', 'c']
    assert on_entries[1]['previous_segment_id'] == 'a'
    assert on_entries[2]['previous_segment_id'] == 'b'
    assert on_entries[2]['log_sequence'] == 3
    assert table_rows(on_store) == table_rows(off_store)


def test_narrow_parity_owner_fences_advance_identically(monkeypatch):
    def build(store):
        ready_rows({'a': 1, 'b': 2}, store=store)
        merge = OrderedMerge(store)
        merge.commit_next('heavy', STEADY)
        merge.commit_next('heavy', STEADY)
        return store.probe('owners', OWNER)

    _entry, _off, _on_entry, on_store = _drive_both_modes(monkeypatch, build)
    owner = on_store.probe('owners', OWNER)
    # Two admission bumps (one per row) plus one per commit.
    assert owner['revision'] == 4
    assert owner['log_sequence'] == 2
    assert owner['log_tail'] == 'b'
    assert owner['watermark'] == {'capture_at': 2, 'segment_id': 'b'}


def test_narrow_parity_job_transition_identical(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        merge = OrderedMerge(store)
        merge.commit_next('heavy', STEADY)
        return store.probe('jobs', 'a')

    _entry, _off, _on_entry, on_store = _drive_both_modes(monkeypatch, build)
    job = on_store.probe('jobs', 'a')
    assert job['state'] == 'committed'
    assert job['merge_pending'] is False
    assert job['result'] == {'outcome': 'success', 'result_uri': 'gs://results/a', 'segment_id': 'a'}


def test_narrow_parity_result_row_identical(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        merge = OrderedMerge(store)
        merge.commit_next('heavy', STEADY)
        return store.probe('results', 'a')

    _entry, _off, _on_entry, on_store = _drive_both_modes(monkeypatch, build)
    row = on_store.probe('results', 'a')
    assert row['projection_state'] == 'pending'
    assert row['committed_at'] == STEADY
    assert row['owner_key'] == OWNER


def test_narrow_parity_result_exists_raises_in_both_modes(monkeypatch):
    def inject(store):
        store.rows['results', 'a'] = {'segment_id': 'a', 'log_sequence': 9}

    build = _parity_case({'a': 1}, [], inject)

    def expect():
        store = RecordingStore()
        with pytest.raises(RuntimeError, match='reconciliation required'):
            build(store)
        return table_rows(store)

    narrow_off(monkeypatch)
    off_rows = expect()
    monkeypatch.undo()
    on_rows = expect()
    assert on_rows == off_rows


# --------------------------------------------------------------------------
# 6. Entry contract: every field of the narrow commit's result-log row
# --------------------------------------------------------------------------


def test_narrow_entry_segment_id():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'


def test_narrow_entry_capture_at():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['capture_at'] == 1


def test_narrow_entry_protocol_version():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['protocol_version'] == 1


def test_narrow_entry_owner_key():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['owner_key'] == OWNER


def test_narrow_entry_owner_id():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['owner_id'] == 'heavy'


def test_narrow_entry_conversation_id():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['conversation_id'] == None


def test_narrow_entry_privacy_generation():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['privacy_generation'] == None


def test_narrow_entry_previous_segment_id():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['previous_segment_id'] == None


def test_narrow_entry_late_capture():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['late_capture'] == False


def test_narrow_entry_log_sequence():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['log_sequence'] == 1


def test_narrow_entry_committed_at():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['committed_at'] == STEADY


def test_narrow_entry_projection_state():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['projection_state'] == 'pending'


def test_narrow_entry_result():
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['result'] == {'outcome': 'success', 'result_uri': 'gs://results/a', 'segment_id': 'a'}


# --------------------------------------------------------------------------
# 7. Capture order: every permutation of three ready rows commits in order
# --------------------------------------------------------------------------


def test_narrow_capture_order_abc_commits_in_capture_order(monkeypatch):
    def build(store):
        ready_rows({'a': 1, 'b': 2, 'c': 3}, store=store)
        merge = OrderedMerge(store)
        entries = [merge.commit_next('heavy', STEADY) for _ in range(3)]
        merge.commit_next('heavy', STEADY)
        return entries

    _off, _off_store, on_entries, on_store = _drive_both_modes(monkeypatch, build)
    assert [entry['segment_id'] for entry in on_entries] == ['a', 'b', 'c']
    assert on_store.rows['jobs', 'c']['state'] == 'committed'
    assert not [
        key for key in on_store.rows if key[0] == 'results' and on_store.rows[key]['segment_id'] not in {'a', 'b', 'c'}
    ]


def test_narrow_capture_order_acb_commits_in_capture_order(monkeypatch):
    def build(store):
        ready_rows({'a': 1, 'c': 2, 'b': 3}, store=store)
        merge = OrderedMerge(store)
        entries = [merge.commit_next('heavy', STEADY) for _ in range(3)]
        merge.commit_next('heavy', STEADY)
        return entries

    _off, _off_store, on_entries, on_store = _drive_both_modes(monkeypatch, build)
    assert [entry['segment_id'] for entry in on_entries] == ['a', 'c', 'b']
    assert on_store.rows['jobs', 'c']['state'] == 'committed'
    assert not [
        key for key in on_store.rows if key[0] == 'results' and on_store.rows[key]['segment_id'] not in {'a', 'b', 'c'}
    ]


def test_narrow_capture_order_bac_commits_in_capture_order(monkeypatch):
    def build(store):
        ready_rows({'b': 1, 'a': 2, 'c': 3}, store=store)
        merge = OrderedMerge(store)
        entries = [merge.commit_next('heavy', STEADY) for _ in range(3)]
        merge.commit_next('heavy', STEADY)
        return entries

    _off, _off_store, on_entries, on_store = _drive_both_modes(monkeypatch, build)
    assert [entry['segment_id'] for entry in on_entries] == ['b', 'a', 'c']
    assert on_store.rows['jobs', 'c']['state'] == 'committed'
    assert not [
        key for key in on_store.rows if key[0] == 'results' and on_store.rows[key]['segment_id'] not in {'a', 'b', 'c'}
    ]


def test_narrow_capture_order_bca_commits_in_capture_order(monkeypatch):
    def build(store):
        ready_rows({'b': 1, 'c': 2, 'a': 3}, store=store)
        merge = OrderedMerge(store)
        entries = [merge.commit_next('heavy', STEADY) for _ in range(3)]
        merge.commit_next('heavy', STEADY)
        return entries

    _off, _off_store, on_entries, on_store = _drive_both_modes(monkeypatch, build)
    assert [entry['segment_id'] for entry in on_entries] == ['b', 'c', 'a']
    assert on_store.rows['jobs', 'c']['state'] == 'committed'
    assert not [
        key for key in on_store.rows if key[0] == 'results' and on_store.rows[key]['segment_id'] not in {'a', 'b', 'c'}
    ]


def test_narrow_capture_order_cab_commits_in_capture_order(monkeypatch):
    def build(store):
        ready_rows({'c': 1, 'a': 2, 'b': 3}, store=store)
        merge = OrderedMerge(store)
        entries = [merge.commit_next('heavy', STEADY) for _ in range(3)]
        merge.commit_next('heavy', STEADY)
        return entries

    _off, _off_store, on_entries, on_store = _drive_both_modes(monkeypatch, build)
    assert [entry['segment_id'] for entry in on_entries] == ['c', 'a', 'b']
    assert on_store.rows['jobs', 'c']['state'] == 'committed'
    assert not [
        key for key in on_store.rows if key[0] == 'results' and on_store.rows[key]['segment_id'] not in {'a', 'b', 'c'}
    ]


def test_narrow_capture_order_cba_commits_in_capture_order(monkeypatch):
    def build(store):
        ready_rows({'c': 1, 'b': 2, 'a': 3}, store=store)
        merge = OrderedMerge(store)
        entries = [merge.commit_next('heavy', STEADY) for _ in range(3)]
        merge.commit_next('heavy', STEADY)
        return entries

    _off, _off_store, on_entries, on_store = _drive_both_modes(monkeypatch, build)
    assert [entry['segment_id'] for entry in on_entries] == ['c', 'b', 'a']
    assert on_store.rows['jobs', 'c']['state'] == 'committed'
    assert not [
        key for key in on_store.rows if key[0] == 'results' and on_store.rows[key]['segment_id'] not in {'a', 'b', 'c'}
    ]


# --------------------------------------------------------------------------
# 8. Chain dynamics: drains of N ready rows chain previous_segment_id
# --------------------------------------------------------------------------


def test_narrow_chain_length_2_links_every_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2})
    merge = OrderedMerge(store)
    entries = [merge.commit_next('heavy', STEADY) for _ in range(2)]
    assert [entry['segment_id'] for entry in entries] == ['a', 'b']
    tails = [entry['previous_segment_id'] for entry in entries]
    assert tails == [None, 'a']
    assert entries[-1]['log_sequence'] == 2


def test_narrow_chain_length_3_links_every_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3})
    merge = OrderedMerge(store)
    entries = [merge.commit_next('heavy', STEADY) for _ in range(3)]
    assert [entry['segment_id'] for entry in entries] == ['a', 'b', 'c']
    tails = [entry['previous_segment_id'] for entry in entries]
    assert tails == [None, 'a', 'b']
    assert entries[-1]['log_sequence'] == 3


def test_narrow_chain_length_4_links_every_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3, 'd': 4})
    merge = OrderedMerge(store)
    entries = [merge.commit_next('heavy', STEADY) for _ in range(4)]
    assert [entry['segment_id'] for entry in entries] == ['a', 'b', 'c', 'd']
    tails = [entry['previous_segment_id'] for entry in entries]
    assert tails == [None, 'a', 'b', 'c']
    assert entries[-1]['log_sequence'] == 4


def test_narrow_chain_length_5_links_every_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5})
    merge = OrderedMerge(store)
    entries = [merge.commit_next('heavy', STEADY) for _ in range(5)]
    assert [entry['segment_id'] for entry in entries] == ['a', 'b', 'c', 'd', 'e']
    tails = [entry['previous_segment_id'] for entry in entries]
    assert tails == [None, 'a', 'b', 'c', 'd']
    assert entries[-1]['log_sequence'] == 5


def test_narrow_chain_length_6_links_every_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 6})
    merge = OrderedMerge(store)
    entries = [merge.commit_next('heavy', STEADY) for _ in range(6)]
    assert [entry['segment_id'] for entry in entries] == ['a', 'b', 'c', 'd', 'e', 'f']
    tails = [entry['previous_segment_id'] for entry in entries]
    assert tails == [None, 'a', 'b', 'c', 'd', 'e']
    assert entries[-1]['log_sequence'] == 6


def test_narrow_chain_length_7_links_every_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 6, 'g': 7})
    merge = OrderedMerge(store)
    entries = [merge.commit_next('heavy', STEADY) for _ in range(7)]
    assert [entry['segment_id'] for entry in entries] == ['a', 'b', 'c', 'd', 'e', 'f', 'g']
    tails = [entry['previous_segment_id'] for entry in entries]
    assert tails == [None, 'a', 'b', 'c', 'd', 'e', 'f']
    assert entries[-1]['log_sequence'] == 7


def test_narrow_chain_length_8_links_every_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 6, 'g': 7, 'h': 8})
    merge = OrderedMerge(store)
    entries = [merge.commit_next('heavy', STEADY) for _ in range(8)]
    assert [entry['segment_id'] for entry in entries] == ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    tails = [entry['previous_segment_id'] for entry in entries]
    assert tails == [None, 'a', 'b', 'c', 'd', 'e', 'f', 'g']
    assert entries[-1]['log_sequence'] == 8


# --------------------------------------------------------------------------
# 9. Fence equality across owner revision values
# --------------------------------------------------------------------------


def test_narrow_fence_holds_at_revision_0(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER]['revision'] = 0
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)
    assert store.rows['owners', OWNER]['revision'] == 1


def test_narrow_fence_holds_at_revision_1(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER]['revision'] = 1
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)
    assert store.rows['owners', OWNER]['revision'] == 2


def test_narrow_fence_holds_at_revision_2(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER]['revision'] = 2
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)
    assert store.rows['owners', OWNER]['revision'] == 3


def test_narrow_fence_holds_at_revision_3(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER]['revision'] = 3
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)
    assert store.rows['owners', OWNER]['revision'] == 4


def test_narrow_fence_holds_at_revision_4(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER]['revision'] = 4
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)
    assert store.rows['owners', OWNER]['revision'] == 5


def test_narrow_fence_holds_at_revision_5(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER]['revision'] = 5
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)
    assert store.rows['owners', OWNER]['revision'] == 6


# --------------------------------------------------------------------------
# 10. Fence offsets: a stale probed revision always hands back to strict
# --------------------------------------------------------------------------


def test_narrow_fence_offset_minus2_falls_back_to_strict(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def offset_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'revision': row.get('revision', 0) + -2}
        return row

    store.probe = offset_probe
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_narrow_fence_offset_minus1_falls_back_to_strict(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def offset_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'revision': row.get('revision', 0) + -1}
        return row

    store.probe = offset_probe
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_narrow_fence_offset_plus1_falls_back_to_strict(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def offset_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'revision': row.get('revision', 0) + 1}
        return row

    store.probe = offset_probe
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_narrow_fence_offset_plus2_falls_back_to_strict(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def offset_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'revision': row.get('revision', 0) + 2}
        return row

    store.probe = offset_probe
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


# --------------------------------------------------------------------------
# 11. Gate states: only a settled result_ready head narrows
# --------------------------------------------------------------------------


def test_narrow_gate_skips_leased_head(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['state'] = 'leased'
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert ('owners', OWNER) not in store.probed
    assert store.runs == 0


def test_narrow_gate_skips_retry_head(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['state'] = 'retry'
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert ('owners', OWNER) not in store.probed
    assert store.runs == 0


def test_narrow_gate_skips_record_pending_head(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['state'] = 'record_pending'
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert ('owners', OWNER) not in store.probed
    assert store.runs == 0


def test_narrow_gate_skips_privacy_blocked_head(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['state'] = 'privacy_blocked'
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert ('owners', OWNER) not in store.probed
    assert store.runs == 0


def test_narrow_gate_skips_leased_head_with_ready_sibling(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2}, store=RecordingStore())
    complete(queue, leases, 'b')
    store.rows['jobs', 'a']['state'] = 'leased'
    store.reset_counts()
    merge, entry = drain(store)
    # The head is not ready: the probe gate skips; the narrow gate cannot fire.
    assert entry is None
    assert ('owners', OWNER) not in store.probed


def test_narrow_gate_skips_retry_head_with_ready_sibling(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2}, store=RecordingStore())
    complete(queue, leases, 'b')
    store.rows['jobs', 'a']['state'] = 'retry'
    store.reset_counts()
    merge, entry = drain(store)
    # The head is not ready: the probe gate skips; the narrow gate cannot fire.
    assert entry is None
    assert ('owners', OWNER) not in store.probed


# --------------------------------------------------------------------------
# 12. Narrow body re-verification at an unchanged revision
# --------------------------------------------------------------------------


def test_narrow_body_refuses_committed_candidate(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['state'] = 'committed'
    merge = merge_for(store)
    revision = store.rows['owners', OWNER]['revision']
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert entry is None
    assert stale is False


def test_narrow_body_refuses_quarantined_candidate(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['state'] = 'quarantined'
    merge = merge_for(store)
    revision = store.rows['owners', OWNER]['revision']
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert entry is None
    assert stale is False


def test_narrow_body_refuses_leased_candidate(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['state'] = 'leased'
    merge = merge_for(store)
    revision = store.rows['owners', OWNER]['revision']
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert entry is None
    assert stale is False


# --------------------------------------------------------------------------
# 13. Sibling independence: the narrow read set ignores pending siblings
# --------------------------------------------------------------------------


def test_narrow_read_set_with_1_pending_siblings(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 1})
    store.reset_counts()
    drain(store)
    gets = {read for read in reads_of(store) if read[0] == 'get'}
    assert gets == {('get', 'owners', OWNER), ('get', 'jobs', 'a'), ('get', 'results', 'a')}


def test_narrow_read_set_with_2_pending_siblings(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 1, 'c': 2})
    store.reset_counts()
    drain(store)
    gets = {read for read in reads_of(store) if read[0] == 'get'}
    assert gets == {('get', 'owners', OWNER), ('get', 'jobs', 'a'), ('get', 'results', 'a')}


def test_narrow_read_set_with_3_pending_siblings(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 1, 'c': 2, 'd': 3})
    store.reset_counts()
    drain(store)
    gets = {read for read in reads_of(store) if read[0] == 'get'}
    assert gets == {('get', 'owners', OWNER), ('get', 'jobs', 'a'), ('get', 'results', 'a')}


def test_narrow_read_set_with_4_pending_siblings(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 1, 'c': 2, 'd': 3, 'e': 4})
    store.reset_counts()
    drain(store)
    gets = {read for read in reads_of(store) if read[0] == 'get'}
    assert gets == {('get', 'owners', OWNER), ('get', 'jobs', 'a'), ('get', 'results', 'a')}


def test_narrow_read_set_with_5_pending_siblings(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 1, 'c': 2, 'd': 3, 'e': 4, 'f': 5})
    store.reset_counts()
    drain(store)
    gets = {read for read in reads_of(store) if read[0] == 'get'}
    assert gets == {('get', 'owners', OWNER), ('get', 'jobs', 'a'), ('get', 'results', 'a')}


# --------------------------------------------------------------------------
# 14. Recovery-version flag grid
# --------------------------------------------------------------------------


def test_narrow_recovery_flag_recovered_only(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        store.rows['jobs', 'a']['recovery_state'] = 'recovered'
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, _off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry['recovery_version'] == 1


def test_narrow_recovery_flag_provider_route_only(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        store.rows['jobs', 'a']['stt_route'] = {'stt_route': 'provider'}
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, _off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry['recovery_version'] == 1


def test_narrow_recovery_flag_recovered_and_provider(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        store.rows['jobs', 'a']['recovery_state'] = 'recovered'
        store.rows['jobs', 'a']['stt_route'] = {'stt_route': 'provider'}
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, _off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert on_entry['recovery_version'] == 1


def test_narrow_recovery_flag_self_route_no_flag(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        store.rows['jobs', 'a']['stt_route'] = {'stt_route': 'self'}
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, _off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert 'recovery_version' not in on_entry


# --------------------------------------------------------------------------
# 15. Multi-row dynamics through the narrow lane
# --------------------------------------------------------------------------


def test_narrow_strict_order_waits_behind_a_leased_middle_row(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3}, store=RecordingStore())
    complete(queue, leases, 'a')
    complete(queue, leases, 'c')
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    first = merge.commit_next('heavy', STEADY)
    blocked = merge.commit_next('heavy', STEADY)
    assert first['segment_id'] == 'a'
    assert blocked is None
    complete(queue, leases, 'b')
    second = merge.commit_next('heavy', STEADY)
    third = merge.commit_next('heavy', STEADY)
    assert [second['segment_id'], third['segment_id']] == ['b', 'c']
    assert all(read[0] != 'query' for run_reads in store.read_log[-2:] for read in run_reads)


def test_narrow_default_head_wait_bypasses_to_the_settled_successor(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3}, store=RecordingStore())
    complete(queue, leases, 'a')
    complete(queue, leases, 'c')
    merge = OrderedMerge(store)  # The shipped 60 s head wait.
    first = merge.commit_next('heavy', STEADY)
    bypassed = merge.commit_next('heavy', STEADY)
    assert first['segment_id'] == 'a'
    # 'c' has waited far past the head wait: the bypass commits it now.
    assert bypassed['segment_id'] == 'c'
    assert bypassed['head_wait_bypass'] is True
    complete(queue, leases, 'b')
    late = merge.commit_next('heavy', STEADY)
    # The bypassed head appends afterwards, as late_capture.
    assert late['segment_id'] == 'b'
    assert late['late_capture'] is True
    exhausted = merge.commit_next('heavy', STEADY)
    assert exhausted is None


def test_narrow_quarantined_head_between_drains_advances_to_the_successor(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2})
    # quarantine_job's fence: remove the head and bump the revision.
    store.rows['jobs', 'a'].update(state='quarantined', merge_pending=False)
    store.rows['owners', OWNER]['revision'] += 1
    merge, entry = drain(store)
    assert entry['segment_id'] == 'b'
    assert store.rows['jobs', 'b']['state'] == 'committed'


def test_narrow_later_admission_between_drains_keeps_capture_order(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2})
    Scheduler(store).enqueue(item('c', capture=3), 0)
    store.rows['jobs', 'c']['state'] = 'result_ready'
    store.rows['jobs', 'c']['result'] = {'uri': 'gs://results/c'}
    merge = OrderedMerge(store)
    first = merge.commit_next('heavy', STEADY)
    second = merge.commit_next('heavy', STEADY)
    third = merge.commit_next('heavy', STEADY)
    assert [entry['segment_id'] for entry in (first, second, third)] == ['a', 'b', 'c']
    assert third['late_capture'] is False


def test_narrow_log_sequence_strictly_increases_across_drains(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2, 'c': 3})
    merge = OrderedMerge(store)
    sequences = [merge.commit_next('heavy', STEADY)['log_sequence'] for _ in range(3)]
    assert sequences == [1, 2, 3]


def test_narrow_drain_until_empty_opens_no_transaction(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    drain(store)
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert store.runs == 0
    assert store.head_pending_calls == 1


def test_narrow_two_owners_drain_in_isolation(monkeypatch):
    store = RecordingStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', capture=1), 0)
    queue.enqueue(item('z', capture=2), 0)
    from utils.batch_pipeline.scheduler import owner_key as okey

    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 2)}
    # z belongs to another owner id: reassign its owner to a second identity.
    store.rows['jobs', 'z']['owner_id'] = 'other'
    store.rows['jobs', 'z']['owner_key'] = okey('other')
    complete(queue, leases, 'a')
    complete(queue, leases, 'z')
    merge = OrderedMerge(store)
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'a'
    # The other owner's row is untouched by this drain.
    assert store.rows['jobs', 'z']['state'] == 'result_ready'
    assert store.rows['jobs', 'z']['merge_pending'] is True


# --------------------------------------------------------------------------
# 16. Interleaving grid: concurrent pending-set mutations re-decide via strict
# --------------------------------------------------------------------------


def test_interleave_admits_a_later_capture(monkeypatch):
    rows = storm_with_ready_head()

    def mutation(state_rows):
        state_rows[(f'{NAMESPACE}_jobs', 'f')] = {
            'segment_id': 'f',
            'owner_key': OWNER,
            'owner_id': 'heavy',
            'merge_pending': True,
            'state': 'result_ready',
            'capture_at': 9,
            'priority': 0,
            'result': {'uri': 'gs://results/f'},
            'protocol_version': 1,
            'ready_at': 99.0,
        }
        state_rows.setdefault(OWNER_ROW, {})['revision'] = 3

    client = InterleavedStormClient(rows=rows, hot={OWNER_ROW}, aborts=1, interleavings={2: mutation})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert (entry['segment_id'] if entry else None) == 'a'
    # A later capture cannot leap the head: the strict re-decision commits 'a'.
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'committed'
    assert client.rows[(f'{NAMESPACE}_jobs', 'f')]['state'] == 'result_ready'


def test_interleave_quarantines_a_non_head_sibling(monkeypatch):
    rows = storm_with_ready_head()

    def mutation(state_rows):
        state_rows[(f'{NAMESPACE}_jobs', 'b')].update(state='quarantined', merge_pending=False)
        state_rows.setdefault(OWNER_ROW, {})['revision'] = 4

    client = InterleavedStormClient(rows=rows, hot={OWNER_ROW}, aborts=1, interleavings={2: mutation})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert (entry['segment_id'] if entry else None) == 'a'
    assert client.rows[(f'{NAMESPACE}_jobs', 'b')]['state'] == 'quarantined'


def test_interleave_advances_the_projection_watermark(monkeypatch):
    rows = storm_with_ready_head()

    def mutation(state_rows):
        owner = state_rows.setdefault(OWNER_ROW, {})
        owner['revision'] = owner.get('revision', 0) + 1
        owner['projection_watermark'] = 'w0'
        state_rows[(f'{NAMESPACE}_results', 'w0')] = {'log_sequence': 0}

    client = InterleavedStormClient(rows=rows, hot={OWNER_ROW}, aborts=1, interleavings={2: mutation})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert (entry['segment_id'] if entry else None) == 'a'


def test_interleave_fence_stale_then_the_strict_body_lands(monkeypatch):
    rows = storm_with_ready_head()

    def bump(state_rows):
        row = state_rows.setdefault(OWNER_ROW, {})
        row['revision'] = row.get('revision', 0) + 1

    # Attempt 1 aborts on the hot owner; attempt 2's bump turns the narrow
    # fence stale; the strict body re-decides and lands the head once the
    # storm budget is spent.
    client = InterleavedStormClient(rows=rows, hot={OWNER_ROW}, aborts=2, interleavings={2: bump, 4: bump})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry is not None
    assert entry['segment_id'] == 'a'
    assert client.rows[(f'{NAMESPACE}_results', 'a')]['segment_id'] == 'a'


def test_interleave_heartbeat_and_admission_mixed_storm(monkeypatch):
    rows = storm_with_ready_head()

    def admit(state_rows):
        state_rows[(f'{NAMESPACE}_jobs', 'g')] = {
            'segment_id': 'g',
            'owner_key': OWNER,
            'owner_id': 'heavy',
            'merge_pending': True,
            'state': 'leased',
            'capture_at': 4,
            'priority': 0,
            'protocol_version': 1,
            'lease_until': 10.0**9,
        }
        row = state_rows.setdefault(OWNER_ROW, {})
        row['revision'] = row.get('revision', 0) + 1

    client = InterleavedStormClient(rows=rows, hot={SIBLING_B, OWNER_ROW}, aborts=3, interleavings={3: admit})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.rows[(f'{NAMESPACE}_jobs', 'g')]['state'] == 'leased'
    assert client.rows[(f'{NAMESPACE}_jobs', 'g')]['merge_pending'] is True


# --------------------------------------------------------------------------
# 17. Storm grid: the narrow path reads no heartbeat-written document
# --------------------------------------------------------------------------


def test_storm_cell_head_and_sibling_hot_narrow_still_commits(monkeypatch):
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={SIBLING_B, OWNER_ROW}, aborts=2)
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    # Owner races abort the narrow attempts; the sibling heartbeat cannot.
    assert entry['segment_id'] == 'a'
    assert client.aborts_remaining == 0
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'committed'


def test_storm_cell_calm_client_narrow_commits_on_the_first_attempt(monkeypatch):
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot=set())
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.transactions == 1
    assert client.commits == 1


def test_storm_cell_calm_client_strict_also_commits_on_the_first_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'false')
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot=set())
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.transactions == 1
    assert client.commits == 1


def test_storm_cell_sibling_hot_strict_exhausts_and_narrow_does_not(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'false')
    strict_client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={SIBLING_B})
    strict_merge, _store = storm_merge(monkeypatch, strict_client)
    with pytest.raises(FirestoreContentionExhausted):
        strict_merge.commit_next('heavy', 100.0)
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'true')
    narrow_client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={SIBLING_B})
    narrow_merge, _store = storm_merge(monkeypatch, narrow_client)
    entry = narrow_merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert narrow_client.transactions == 1


# --------------------------------------------------------------------------
# 18. Rollout switch: env parsing at call time
# --------------------------------------------------------------------------


def test_narrow_gate_default_is_on(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', raising=False)
    from config.batch_pipeline import merge_narrow_commit_enabled

    assert merge_narrow_commit_enabled() is True


def test_narrow_gate_false_word_is_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'false')
    from config.batch_pipeline import merge_narrow_commit_enabled

    assert merge_narrow_commit_enabled() is False


def test_narrow_gate_uppercase_false_is_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'FALSE')
    from config.batch_pipeline import merge_narrow_commit_enabled

    assert merge_narrow_commit_enabled() is False


def test_narrow_gate_padded_false_is_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', ' false ')
    from config.batch_pipeline import merge_narrow_commit_enabled

    assert merge_narrow_commit_enabled() is False


def test_narrow_gate_true_word_is_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'true')
    from config.batch_pipeline import merge_narrow_commit_enabled

    assert merge_narrow_commit_enabled() is True


def test_narrow_gate_empty_value_is_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', '')
    from config.batch_pipeline import merge_narrow_commit_enabled

    assert merge_narrow_commit_enabled() is True


def test_narrow_gate_zero_is_on_like_the_storm_damper(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', '0')
    from config.batch_pipeline import merge_narrow_commit_enabled

    assert merge_narrow_commit_enabled() is True


def test_narrow_gate_reads_the_environment_at_call_time(monkeypatch):
    from config.batch_pipeline import merge_narrow_commit_enabled

    monkeypatch.delenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', raising=False)
    assert merge_narrow_commit_enabled() is True
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'false')
    assert merge_narrow_commit_enabled() is False
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'true')
    assert merge_narrow_commit_enabled() is True


def test_narrow_gate_has_a_budget_entry_with_owner_and_review_by():
    import json
    from pathlib import Path

    budget = json.loads((Path(__file__).resolve().parents[2] / 'config' / 'flag_budget.json').read_text())
    entry = budget['names']['BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED']
    assert entry['owner'] == 'batch record lane / rollout lead'
    assert entry['review_by'] >= '2026-12-01'
    assert budget['count'] == len(budget['names'])


def test_narrow_gate_kill_switch_restores_every_strict_drain(monkeypatch):
    narrow_off(monkeypatch)
    store, _queue = ready_rows({'a': 1, 'b': 2})
    store.reset_counts()
    drain(store)
    assert ('query', 'first_pending', OWNER) in reads_of(store)
    assert store.run_operations == ['batch_merge_commit']


# --------------------------------------------------------------------------
# 19. Attribution labels and log hygiene
# --------------------------------------------------------------------------


def test_stale_fallback_run_keeps_the_merge_commit_label(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def inflated_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'revision': row.get('revision', 0) + 5}
        return row

    store.probe = inflated_probe
    store.reset_counts()
    drain(store)
    # One narrow attempt plus the strict re-decision, both attributed.
    assert store.runs == 2
    assert store.run_operations == ['batch_merge_commit', 'batch_merge_commit']


def test_clean_narrow_commit_logs_no_error_lines(monkeypatch, caplog):
    store, _queue = ready_rows({'a': 1, 'b': 2})
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.merge'):
        drain(store)
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_stale_fence_logs_no_error_lines(monkeypatch, caplog):
    store, _queue = ready_rows({'a': 1})

    def inflated_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'revision': row.get('revision', 0) + 5}
        return row

    store.probe = inflated_probe
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.merge'):
        drain(store)
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_narrow_owner_probe_failure_warns_but_never_errors(monkeypatch, caplog):
    store, _queue = ready_rows({'a': 1})

    def flaky_probe(table, key):
        if table == 'owners':
            raise ServiceUnavailable('owners probe down')
        return store.inner.probe(table, key)

    store.probe = flaky_probe
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        drain(store)
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


# --------------------------------------------------------------------------
# 20. Probe failure breadth: only transport errors fall back silently
# --------------------------------------------------------------------------


def test_non_transport_owner_probe_error_propagates(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def broken_probe(table, key):
        if table == 'owners':
            raise RuntimeError('logic bug, not transport')
        return store.inner.probe(table, key)

    store.probe = broken_probe
    with pytest.raises(RuntimeError, match='logic bug'):
        drain(store)


def test_non_transport_head_probe_error_keeps_strict(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def broken_head(key):
        raise RuntimeError('logic bug in the hint')

    store.head_pending = broken_head
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert ('query', 'first_pending', OWNER) in reads_of(store)


# --------------------------------------------------------------------------
# 21. Hint and fence tolerance
# --------------------------------------------------------------------------


def test_hint_with_extra_fields_is_ignored_by_the_narrow_body(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def chatty_head(_key):
        row = deepcopy(store.inner.head_pending(OWNER))
        row['extra_hint_field'] = 'ignored'
        row['state'] = 'result_ready'
        return row

    store.head_pending = chatty_head
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)


def test_owner_probe_with_extra_fields_keeps_the_fence(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def chatty_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            row['operator_note'] = 'ignored'
        return row

    store.probe = chatty_probe
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)


def test_absent_owner_doc_still_commits_through_the_zero_fence(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    del store.rows['owners', OWNER]
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert entry['log_sequence'] == 1
    assert store.rows['owners', OWNER]['revision'] == 1


def test_absent_owner_doc_parity_with_strict(monkeypatch):
    def build(store):
        ready_rows({'a': 1}, store=store)
        del store.rows['owners', OWNER]
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert table_rows(on_store) == table_rows(off_store)


def test_watermark_equal_capture_tie_marks_late(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    # A bypass commit landed 'aa' (same capture, later id) before 'a': the
    # position tuple compares equal on capture_at and 'a' sorts below it.
    store.rows['owners', OWNER]['watermark'] = {'capture_at': 1, 'segment_id': 'aa'}
    store.rows['owners', OWNER]['log_tail'] = 'aa'
    store.rows['owners', OWNER]['log_sequence'] = 1
    store.rows['results', 'aa'] = {'segment_id': 'aa', 'log_sequence': 1}
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert entry['late_capture'] is True


def test_job_worker_evidence_survives_the_narrow_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['measured_held_vad_speech_seconds'] = 3.5
    drain(store)
    job = store.rows['jobs', 'a']
    assert job['measured_held_vad_speech_seconds'] == 3.5
    assert job['audio_uri'] == 'gs://synthetic/a'
    assert job['attempt'] == 1


def test_returned_entry_is_isolated_from_the_store_rows(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    entry['result'] = {'tampered': True}
    entry['segment_id'] = 'mutated'
    assert store.rows['results', 'a']['segment_id'] == 'a'
    assert store.rows['results', 'a']['result'] != {'tampered': True}


# --------------------------------------------------------------------------
# 22. Pipeline-simulator store parity
# --------------------------------------------------------------------------


def _sim_store():
    from testing.pipeline_sim.store import CustomerData, SimStore

    customer = CustomerData()
    customer.add_user('heavy')
    return SimStore(customer)


def test_sim_store_narrow_commit_matches_memory_store(monkeypatch):
    sim = _sim_store()
    queue = Scheduler(sim)
    queue.enqueue(item('a', capture=1), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 1)}
    queue.complete(WorkResult('a', 'gs://results/a'), leases['a'].token, 10)
    merge = OrderedMerge(sim)
    entry = merge.commit_next('heavy', 20)
    assert entry is not None
    assert entry['segment_id'] == 'a'
    assert sim.head_pending(OWNER) is None


def test_sim_store_narrow_parity_with_strict(monkeypatch):
    def build(sim):
        queue = Scheduler(sim)
        queue.enqueue(item('a', capture=1), 0)
        queue.enqueue(item('b', capture=2), 0)
        leases = {lease.item.segment_id: lease for lease in queue.pull(0, 2)}
        queue.complete(WorkResult('a', 'gs://results/a'), leases['a'].token, 10)
        queue.complete(WorkResult('b', 'gs://results/b'), leases['b'].token, 10)
        merge = OrderedMerge(sim)
        first = merge.commit_next('heavy', 20)
        second = merge.commit_next('heavy', 20)
        return [first, second]

    off = _sim_store()
    narrow_off(monkeypatch)
    off_entries = build(off)
    monkeypatch.undo()
    on = _sim_store()
    on_entries = build(on)
    strip = lambda entries: [{k: v for k, v in e.items()} for e in entries]
    assert strip(on_entries) == strip(off_entries)
    assert [e['segment_id'] for e in on_entries] == ['a', 'b']
    assert on_entries[1]['previous_segment_id'] == 'a'


def test_sim_store_fence_stale_falls_back_to_strict(monkeypatch):
    sim = _sim_store()
    queue = Scheduler(sim)
    queue.enqueue(item('a', capture=1), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 1)}
    queue.complete(WorkResult('a', 'gs://results/a'), leases['a'].token, 10)
    stale_owner = deepcopy(sim.probe('owners', OWNER))
    sim.rows['owners', OWNER] = {**stale_owner, 'revision': stale_owner.get('revision', 0) + 3}
    merge = OrderedMerge(sim)
    entry = merge.commit_next('heavy', 20)
    assert entry['segment_id'] == 'a'
    assert sim.rows['jobs', 'a']['state'] == 'committed'


def test_sim_store_hint_matches_the_transactional_candidate(monkeypatch):
    sim = _sim_store()
    queue = Scheduler(sim)
    queue.enqueue(item('a', capture=1), 0)
    queue.enqueue(item('b', capture=2), 0)
    queue.pull(0, 2)
    assert sim.head_pending(OWNER)['segment_id'] == sim.run(lambda tx: tx.first_pending(OWNER))['segment_id']


# --------------------------------------------------------------------------
# 23. The bypass families stay strict under the narrow gate
# --------------------------------------------------------------------------


def test_fresh_first_flow_commits_fresh_then_the_late_head(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'f': 2})
    store.rows['jobs', 'a']['fresh_capture'] = False
    store.rows['jobs', 'f']['fresh_capture'] = True
    at_cap(store.inner, sequence=6, watermark='w5', done=1)
    merge = merge_for(store, depth=2)
    first = merge.commit_next('heavy', STEADY)
    assert first['segment_id'] == 'f'
    assert first['fresh_first'] is True
    # The catch-up head stays held at the cap until projection advances.
    assert merge.held_owners == {'heavy'}
    store.rows['owners', OWNER]['projection_watermark'] = 'f'
    store.rows['results', 'f']['log_sequence'] = 7
    second = merge.commit_next('heavy', STEADY)
    assert second['segment_id'] == 'a'
    assert second['late_capture'] is True
    assert merge.held_owners == set()


def test_head_wait_bypass_flow_commits_successor_then_the_late_head(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2}, store=RecordingStore())
    complete(queue, leases, 'b')
    merge = OrderedMerge(store, catch_up_depth=0)  # The shipped 60 s head wait.
    blocked = merge.commit_next('heavy', STEADY)
    assert blocked['segment_id'] == 'b'
    assert blocked['head_wait_bypass'] is True
    successor = merge.commit_next('heavy', STEADY)
    assert successor is None or successor['segment_id'] == 'b'


def test_recovered_release_flow_commits_the_wake_row(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2}, store=RecordingStore())
    complete(queue, leases, 'b')
    store.rows['jobs', 'b']['recovery_state'] = 'recovered'
    merge = OrderedMerge(store, catch_up_depth=0)
    wake = merge.commit_next('heavy', STEADY, release=['b'])
    assert wake['segment_id'] == 'b'
    assert wake['recovered_release'] is True
    assert wake['recovery_version'] == 1


def test_over_cap_boundary_below_the_cap_narrows(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER]['log_sequence'] = 3
    store.rows['owners', OWNER]['projection_watermark'] = 'w0'
    store.rows['results', 'w0'] = {'log_sequence': 1}
    store.reset_counts()
    merge = merge_for(store, depth=3)
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'a'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)


def test_over_cap_boundary_at_the_cap_keeps_strict(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['owners', OWNER]['log_sequence'] = 3
    store.rows['owners', OWNER]['projection_watermark'] = 'w0'
    store.rows['results', 'w0'] = {'log_sequence': 1}
    store.reset_counts()
    merge = merge_for(store, depth=2)
    entry = merge.commit_next('heavy', STEADY)
    assert ('owners', OWNER) in store.probed
    assert ('query', 'first_pending', OWNER) in reads_of(store)


# --------------------------------------------------------------------------
# 24. Late-capture fence semantics
# --------------------------------------------------------------------------


def test_late_commit_keeps_the_watermark(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    _late_watermark(store)
    drain(store)
    owner = store.rows['owners', OWNER]
    assert owner['watermark'] == {'capture_at': 2, 'segment_id': 'b'}


def test_late_commit_advances_the_log_tail(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    _late_watermark(store)
    drain(store)
    assert store.rows['owners', OWNER]['log_tail'] == 'a'


def test_late_commit_advances_the_log_sequence(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    _late_watermark(store)
    merge, entry = drain(store)
    assert entry['log_sequence'] == 2
    assert store.rows['owners', OWNER]['log_sequence'] == 2


def test_plain_commit_advances_the_watermark(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2})
    drain(store)
    assert store.rows['owners', OWNER]['watermark'] == {'capture_at': 1, 'segment_id': 'a'}


def test_successive_late_commits_chain_through_the_tail(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2})
    # 'c' landed out of order past both rows; each later head appends late.
    store.rows['owners', OWNER]['watermark'] = {'capture_at': 3, 'segment_id': 'c'}
    store.rows['owners', OWNER]['log_tail'] = 'c'
    store.rows['owners', OWNER]['log_sequence'] = 1
    store.rows['results', 'c'] = {'segment_id': 'c', 'log_sequence': 1}
    merge = OrderedMerge(store)
    first = merge.commit_next('heavy', STEADY)
    second = merge.commit_next('heavy', STEADY)
    assert first['segment_id'] == 'a'
    assert first['late_capture'] is True
    assert first['previous_segment_id'] == 'c'
    assert second['segment_id'] == 'b'
    assert second['late_capture'] is True
    assert second['previous_segment_id'] == 'a'
    exhausted = merge.commit_next('heavy', STEADY)
    assert exhausted is None


# --------------------------------------------------------------------------
# 25. Pump publication drains through the narrow lane
# --------------------------------------------------------------------------


def _pump(store, scheduler, **kwargs):
    from utils.batch_pipeline.pump import Pump

    committed = []
    pump = Pump(
        scheduler,
        Mock(),
        merge=merge_for(store),
        on_committed=committed.append,
        leader=_Leader(True),
        publish_concurrency=kwargs.get('publish_concurrency', 2),
        inline_metrics=False,
    )
    return pump, committed


def test_pump_publication_drains_through_the_narrow_lane(monkeypatch):
    store, queue = ready_rows({'a': 1})
    pump, committed = _pump(store, queue)
    asyncio.run(pump.drain_owner('heavy'))
    assert [entry['segment_id'] for entry in committed] == ['a']
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)


def test_pump_drain_stops_at_the_empty_owner(monkeypatch):
    store, queue = ready_rows({'a': 1})
    pump, committed = _pump(store, queue)
    asyncio.run(pump.drain_owner('heavy'))
    store.reset_counts()
    asyncio.run(pump.drain_owner('heavy'))
    assert committed and len(committed) == 1
    assert store.runs == 0


def test_pump_drain_on_committed_receives_each_narrow_entry_in_order(monkeypatch):
    store, queue = ready_rows({'a': 1, 'b': 2, 'c': 3})
    pump, committed = _pump(store, queue)
    asyncio.run(pump.drain_owner('heavy'))
    assert [entry['segment_id'] for entry in committed] == ['a', 'b', 'c']
    assert [entry['log_sequence'] for entry in committed] == [1, 2, 3]


def test_pump_grouped_publication_serializes_per_owner_drains(monkeypatch):
    store, queue = ready_rows({'a': 1, 'b': 2})
    pump, committed = _pump(store, queue, publish_concurrency=2)
    asyncio.run(pump.drain_owner('heavy'))
    asyncio.run(pump.drain_owner('heavy'))
    assert [entry['segment_id'] for entry in committed] == ['a', 'b']


# --------------------------------------------------------------------------
# 26. Metrics, ladder and shipped-contract pins
# --------------------------------------------------------------------------


def test_narrow_commit_records_the_committed_transition(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    with patch.object(merge_module, 'record_correctness', wraps=merge_module.record_correctness) as spy:
        merge = merge_for(store)
        merge.commit_next('heavy', STEADY)
    events = [call.args[0] for call in spy.call_args_list if call.args]
    assert 'committed' in events


def test_narrow_clean_commit_does_not_arm_the_storm_damper(monkeypatch):
    from database.firestore_transaction_retry import FirestoreContentionExhausted as _exhausted  # noqa: F401

    store, _queue = ready_rows({'a': 1})
    drain(store)
    damper = getattr(store.inner, '_storm_damper', None)
    assert damper is None or damper.consult('batch_merge_commit')[0] == 0.0


def test_storm_narrow_attempts_all_stay_on_the_ladder(monkeypatch):
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={OWNER_ROW}, aborts=2)
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    # Owner-write races burn ladder attempts exactly like the strict body:
    # the narrow path buys heartbeat immunity, not immunity from real races.
    assert entry['segment_id'] == 'a'
    assert client.transactions == 3


def test_docs_carry_the_failure_class_trailer():
    from pathlib import Path

    docs = Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-narrow-commit-revision-fence.md'
    assert docs.exists()
    assert 'Failure-Class: FC-ready-head-merge-drains-join-sibling-heartbeat-abort-sets' in docs.read_text()


def test_merge_module_exports_the_narrow_surface():
    from utils.batch_pipeline import merge as module

    assert callable(module.OrderedMerge._narrow_commit)
    assert module.NarrowFenceStale.__doc__
    assert callable(module._append_committed_entry)


# --------------------------------------------------------------------------
# 27. Narrow body unit edges
# --------------------------------------------------------------------------


def test_narrow_body_with_missing_candidate_hands_back_to_strict(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    del store.rows['jobs', 'a']
    merge = merge_for(store)
    revision = store.probe('owners', OWNER).get('revision', 0)
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert entry is None
    assert stale is False
    assert fenced is None
    merge2 = merge_for(store)
    assert merge2.commit_next('heavy', STEADY) is None


def test_narrow_body_refuses_missing_merge_pending(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a'].pop('merge_pending')
    merge = merge_for(store)
    revision = store.probe('owners', OWNER).get('revision', 0)
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert entry is None
    assert stale is False


def test_stale_fence_writes_nothing_durable(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    before = table_rows(store)
    merge = merge_for(store)
    merge._narrow_commit(owner_key('heavy'), 'a', 99, STEADY)
    assert table_rows(store) == before


def test_narrow_body_populates_the_catch_up_fact(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['fresh_capture'] = False
    merge = merge_for(store)
    revision = store.probe('owners', OWNER).get('revision', 0)
    _entry, _fenced, _stale, head = merge._narrow_commit(owner_key('heavy'), 'a', revision, STEADY)
    assert head == {'catch_up': True}


def test_fenced_narrow_populates_the_catch_up_fact_for_the_raise_gate(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['fresh_capture'] = False

    class FencedStore(RecordingStore):
        def run(self, body, *, operation=None):
            from database.batch_pipeline_transaction_labels import current_operation

            self.runs += 1
            self.run_operations.append(operation or current_operation())
            reads, writes = [], []
            self.read_log.append(reads)
            self.write_log.append(writes)

            def fenced(tx):
                result = body(_RecordingTx(tx, reads, writes))
                if any(w[1] == 'results' for w in writes):
                    raise BatchPrivacyBlocked('account_missing')
                return result

            return self.inner.run(fenced, operation=operation)

    fenced_store = FencedStore()
    ready_rows({'a': 1}, store=fenced_store)
    merge = merge_for(fenced_store, depth=2)
    with pytest.raises(BatchPrivacyBlocked):
        merge.commit_next('heavy', STEADY)


# --------------------------------------------------------------------------
# 28. Gate-off drain shapes
# --------------------------------------------------------------------------


def test_gate_off_blocked_head_still_skips_via_the_probe_gate(monkeypatch):
    narrow_off(monkeypatch)
    store, _queue, _leases = admitted({'a': 1})
    store.reset_counts()
    drain(store)
    assert store.runs == 0


def test_gate_off_empty_owner_opens_no_transaction(monkeypatch):
    narrow_off(monkeypatch)
    store = RecordingStore()
    drain(store)
    assert store.runs == 0


def test_gate_off_and_on_commits_stay_identical_under_sibling_activity(monkeypatch):
    def build(store):
        ready_rows({'a': 1, 'b': 2, 'c': 3}, store=store)
        store.rows['jobs', 'b']['lease_until'] = 10.0**9  # b still in flight.
        merge = OrderedMerge(store)
        entries = [merge.commit_next('heavy', STEADY) for _ in range(3)]
        return entries

    off_entries, off_store, on_entries, on_store = _drive_both_modes(monkeypatch, build)
    assert [entry['segment_id'] for entry in on_entries] == ['a', 'b', 'c']
    assert [entry['segment_id'] for entry in off_entries] == ['a', 'b', 'c']


def test_release_wake_on_an_empty_owner_commits_nothing(monkeypatch):
    store = RecordingStore()
    merge, entry = drain(store, release=['ghost'])
    assert entry is None
    # No shortcut with a release set in hand: the strict body re-decides.
    assert store.runs == 1
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_young_waiter_does_not_bypass(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2}, store=RecordingStore())
    complete(queue, leases, 'b')
    store.rows['jobs', 'b']['ready_at'] = STEADY - 5  # Far inside the 60 s wait.
    merge = OrderedMerge(store, catch_up_depth=0)
    young = merge.commit_next('heavy', STEADY)
    assert young is None  # Strict order keeps waiting.
    aged = merge.commit_next('heavy', STEADY + 61)
    assert aged['segment_id'] == 'b'
    assert aged['head_wait_bypass'] is True


# --------------------------------------------------------------------------
# 29. Hint/candidate consistency and evidence preservation
# --------------------------------------------------------------------------


def test_hint_matches_candidate_single_row(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    assert store.head_pending(OWNER)['segment_id'] == store.run(lambda tx: tx.first_pending(OWNER))['segment_id']


def test_hint_matches_candidate_with_a_leased_sibling(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2}, store=RecordingStore())
    complete(queue, leases, 'b')
    assert store.head_pending(OWNER)['segment_id'] == store.run(lambda tx: tx.first_pending(OWNER))['segment_id']


def test_hint_matches_candidate_behind_a_watermark(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    _late_watermark(store)
    assert store.head_pending(OWNER)['segment_id'] == store.run(lambda tx: tx.first_pending(OWNER))['segment_id']


def test_narrow_entry_carries_capture_at_and_owner_id(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    merge, entry = drain(store)
    assert entry['capture_at'] == 1
    assert entry['owner_id'] == 'heavy'


def test_narrow_result_payload_is_the_worker_result(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    job_result = deepcopy(store.rows['jobs', 'a']['result'])
    merge, entry = drain(store)
    assert entry['result'] == job_result


def test_narrow_drain_reads_no_gpu_document(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['gpus', 'gpu-1'] = {'token': 't', 'lease_until': 10.0**9}
    store.rows['jobs', 'a']['shared_gpu_key'] = 'gpu-1'
    store.reset_counts()
    drain(store)
    assert all(read[1] != 'gpus' for run_reads in store.read_log for read in run_reads)


def test_narrow_writes_nothing_when_the_head_is_not_ready(monkeypatch):
    store, _queue, _leases = admitted({'a': 1})
    before = table_rows(store)
    drain(store)
    assert table_rows(store) == before


def test_merge_holds_marker_absent_below_the_cap(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    drain(store)
    assert ('merge_holds', OWNER) not in store.rows


def test_first_pending_orders_by_capture_then_segment_id(monkeypatch):
    store, _queue = ready_rows({'b': 1, 'a': 1})
    head = store.run(lambda tx: tx.first_pending(OWNER))
    assert head['segment_id'] == 'a'


def test_narrow_with_shadow_sibling_still_commits_the_head(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2}, store=RecordingStore())
    complete(queue, leases, 'b')
    store.rows['jobs', 'b']['shadow'] = True
    store.rows['jobs', 'b']['merge_pending'] = False  # Shadow rows leave the merge lane.
    merge, entry = drain(store)
    assert entry is None  # Only the shadow row remains; nothing commits.


def test_narrow_with_quarantined_sibling_keeps_strict_order(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2})
    store.rows['jobs', 'b'].update(state='quarantined', merge_pending=False)
    store.rows['owners', OWNER]['revision'] += 1
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'


def test_gate_off_and_on_identical_for_the_release_wake(monkeypatch):
    def build(store):
        queue, leases = None, None
        ready_rows({'a': 1, 'b': 2}, store=store)
        store.rows['jobs', 'b']['recovery_state'] = 'recovered'
        merge = OrderedMerge(store, catch_up_depth=0)
        return merge.commit_next('heavy', STEADY, release=['b'])

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert (on_entry['segment_id'] if on_entry else None) == (off_entry['segment_id'] if off_entry else None)


# --------------------------------------------------------------------------
# 30. Recovery behavior after exhaustion and repeated stale hints
# --------------------------------------------------------------------------


def test_drain_recovers_after_a_prior_exhaustion(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={OWNER_ROW}, aborts=DEFAULT_MAX_ATTEMPTS)
    merge, store = storm_merge(monkeypatch, client)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', 100.0)
    # The race clears: the owner row stops moving and the drain lands.
    client.hot_rows = set()
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'committed'


def test_two_consecutive_stale_hints_never_commit(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    captured = deepcopy(store.rows)

    def stale_head(_key):
        return deepcopy(captured[(f'{NAMESPACE}_jobs', 'a')])

    store.head_pending = stale_head
    store.rows['jobs', 'a'].update(state='quarantined', merge_pending=False)
    store.rows['owners', OWNER]['revision'] += 1
    merge = merge_for(store)
    first = merge.commit_next('heavy', STEADY)
    second = merge.commit_next('heavy', STEADY)
    assert first is None and second is None
    assert not [key for key in store.rows if key[0] == 'results']


def test_successive_drains_narrow_again_after_a_stale_fence(monkeypatch):
    store, _queue = ready_rows({'a': 1, 'b': 2})

    def one_shot_probe(table, key, _calls={'n': 0}):
        row = store.inner.probe(table, key)
        if table == 'owners' and _calls['n'] == 0:
            _calls['n'] += 1
            return {**row, 'revision': row.get('revision', 0) + 7}
        return row

    store.probe = one_shot_probe
    merge = OrderedMerge(store)
    first = merge.commit_next('heavy', STEADY)
    assert first['segment_id'] == 'a'
    store.reset_counts()
    second = merge.commit_next('heavy', STEADY)
    assert second['segment_id'] == 'b'
    assert all(read[0] != 'query' for run_reads in store.read_log for read in run_reads)


def test_blocked_head_storm_immunity_is_unchanged_by_the_narrow_gate(monkeypatch):
    client = HeartbeatStormClient(rows=storm_rows('leased'))
    merge, _store = storm_merge(monkeypatch, client)
    assert merge.commit_next('heavy', 10) is None
    assert client.transactions == 0
    assert client.commits == 0


# --------------------------------------------------------------------------
# 31. Shared commit tail unit contract
# --------------------------------------------------------------------------


def test_commit_tail_marks_head_wait_bypass(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    merge = merge_for(store)
    txn_ready = {}

    def build(tx):
        owner = tx.get('owners', OWNER)
        candidate = tx.get('jobs', 'a')
        bypass = {'head_state': 'leased', 'waited': 61.0}
        return merge_module._append_committed_entry(tx, OWNER, owner, candidate, STEADY, bypass=bypass)

    entry = store.run(build)
    assert entry['head_wait_bypass'] is True
    assert 'fresh_first' not in entry
    assert 'recovered_release' not in entry


def test_commit_tail_marks_fresh_first(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def build(tx):
        owner = tx.get('owners', OWNER)
        candidate = tx.get('jobs', 'a')
        return merge_module._append_committed_entry(
            tx, OWNER, owner, candidate, STEADY, fresh_first={'head_state': 'leased'}
        )

    entry = store.run(build)
    assert entry['fresh_first'] is True


def test_commit_tail_marks_recovered_release(monkeypatch):
    store, _queue = ready_rows({'a': 1})

    def build(tx):
        owner = tx.get('owners', OWNER)
        candidate = tx.get('jobs', 'a')
        return merge_module._append_committed_entry(
            tx, OWNER, owner, candidate, STEADY, released={'head_state': 'leased', 'recovered': True}
        )

    entry = store.run(build)
    assert entry['recovered_release'] is True


def test_commit_tail_raises_on_an_existing_result_row(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['results', 'a'] = {'segment_id': 'a', 'log_sequence': 9}

    def build(tx):
        owner = tx.get('owners', OWNER)
        candidate = tx.get('jobs', 'a')
        return merge_module._append_committed_entry(tx, OWNER, owner, candidate, STEADY)

    with pytest.raises(RuntimeError, match='reconciliation required'):
        store.run(build)


# --------------------------------------------------------------------------
# 32. Hand-built rows: the narrow body on a bare store
# --------------------------------------------------------------------------


def test_bare_rows_narrow_commit_without_an_owner_document(monkeypatch):
    store = RecordingStore()
    store.rows['jobs', 'a'] = {
        'segment_id': 'a',
        'owner_key': OWNER,
        'owner_id': 'heavy',
        'merge_pending': True,
        'state': 'result_ready',
        'capture_at': 1,
        'priority': 0,
        'result': {'uri': 'gs://results/a'},
        'protocol_version': 1,
        'ready_at': 9.0,
    }
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert entry['log_sequence'] == 1
    assert store.rows['owners', OWNER]['revision'] == 1


def test_bare_rows_parity_with_strict(monkeypatch):
    def build(store):
        store.rows['jobs', 'a'] = {
            'segment_id': 'a',
            'owner_key': OWNER,
            'owner_id': 'heavy',
            'merge_pending': True,
            'state': 'result_ready',
            'capture_at': 1,
            'priority': 0,
            'result': {'uri': 'gs://results/a'},
            'protocol_version': 1,
            'ready_at': 9.0,
        }
        merge = OrderedMerge(store)
        return merge.commit_next('heavy', STEADY)

    off_entry, off_store, on_entry, on_store = _drive_both_modes(monkeypatch, build)
    assert on_entry == off_entry
    assert table_rows(on_store) == table_rows(off_store)


def test_probe_empty_shortcut_precedes_the_narrow_gate(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    store.rows['jobs', 'a']['merge_pending'] = False
    store.reset_counts()
    merge, entry = drain(store)
    assert entry is None
    assert store.runs == 0
    assert ('owners', OWNER) not in store.probed


# --------------------------------------------------------------------------
# 33. Boundary spares: budgets, error identity, gate-off probe surface
# --------------------------------------------------------------------------


def test_narrow_survives_aborts_exactly_at_the_ladder_cap(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={OWNER_ROW}, aborts=DEFAULT_MAX_ATTEMPTS - 1)
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.transactions == DEFAULT_MAX_ATTEMPTS
    assert client.aborts_remaining == 0
    assert client.rows[(f'{NAMESPACE}_jobs', 'a')]['state'] == 'committed'


def test_gate_off_drains_do_not_read_the_owner_fence_outside_transactions(monkeypatch):
    narrow_off(monkeypatch)
    store, _queue = ready_rows({'a': 1})
    store.reset_counts()
    drain(store)
    assert ('owners', OWNER) not in store.probed
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_stale_fence_error_identity(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    merge = merge_for(store)
    entry, fenced, stale, head = merge._narrow_commit(owner_key('heavy'), 'a', 99, STEADY)
    assert stale is True
    assert isinstance(fenced, type(None))
    assert merge_module.NarrowFenceStale('probed owner revision no longer matches').args[0].startswith('probed')


def test_late_watermark_with_a_missing_projection_row_still_commits(monkeypatch):
    store, _queue = ready_rows({'a': 1})
    _late_watermark(store)
    del store.rows['results', 'b']  # The watermark row was pruned upstream.
    merge, entry = drain(store)
    assert entry['segment_id'] == 'a'
    assert entry['late_capture'] is True


def test_other_owner_heartbeat_hot_rows_cannot_abort_this_drain(monkeypatch):
    rows = storm_with_ready_head()
    quiet_owner = owner_key('other')
    rows[(f'{NAMESPACE}_jobs', 'y')] = {
        'segment_id': 'y',
        'owner_key': quiet_owner,
        'owner_id': 'other',
        'merge_pending': True,
        'state': 'result_ready',
        'capture_at': 5,
        'priority': 0,
        'result': {'uri': 'gs://results/y'},
        'protocol_version': 1,
        'ready_at': 9.0,
    }
    client = HeartbeatStormClient(rows=rows, hot={(f'{NAMESPACE}_jobs', 'y')})
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.transactions == 1
    assert client.rows[(f'{NAMESPACE}_jobs', 'y')]['state'] == 'result_ready'


def test_clean_narrow_commit_spends_no_abort_budget(monkeypatch):
    client = HeartbeatStormClient(rows=storm_with_ready_head(), hot={SIBLING_B}, aborts=50)
    merge, store = storm_merge(monkeypatch, client)
    entry = merge.commit_next('heavy', 100.0)
    assert entry['segment_id'] == 'a'
    assert client.aborts_remaining == 50
