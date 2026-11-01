"""Bounded ordered-merge head wait (David, 2026-10-20) over the atomic snapshot store."""

from copy import deepcopy
from itertools import permutations
import logging

from google.api_core.exceptions import DeadlineExceeded, FailedPrecondition
import pytest

from config.batch_pipeline import MERGE_HEAD_WAIT_DEFAULT, merge_head_wait_seconds
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline import merge as merge_module
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key

W = 60
OWNER = owner_key('heavy')


def admitted(captures):
    """One owner's rows, all leased; ``captures`` maps segment -> capture_at."""
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, capture in captures.items():
        queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, len(captures))}
    assert set(leases) == set(captures)
    return store, queue, leases


def complete(queue, leases, segment, now):
    # The worker heartbeated its lease up to completion.
    queue.store.rows['jobs', segment]['lease_until'] = now + 1
    assert queue.complete(WorkResult(segment, f'gs://results/{segment}'), leases[segment].token, now)


def drain(merge, now):
    entries = []
    while entry := merge.commit_next('heavy', now):
        entries.append(entry)
    return entries


def test_ready_row_waits_behind_a_leased_head_until_w():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    merge = OrderedMerge(store, head_wait_seconds=W)
    complete(queue, leases, 'b', 10)
    assert store.rows['jobs', 'b']['ready_at'] == 10
    assert merge.commit_next('heavy', 10 + W - 1) is None


def test_at_w_the_later_row_commits_and_the_head_appends_late():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    merge = OrderedMerge(store, head_wait_seconds=W)
    complete(queue, leases, 'b', 10)
    bypass = merge.commit_next('heavy', 10 + W)
    assert bypass['segment_id'] == 'b' and bypass['head_wait_bypass'] is True
    assert bypass['late_capture'] is False and bypass['log_sequence'] == 1 and bypass['previous_segment_id'] is None
    owner = store.rows['owners', OWNER]
    assert owner['watermark'] == {'capture_at': 2, 'segment_id': 'b'} and owner['log_tail'] == 'b'
    assert merge.commit_next('heavy', 10 + W) is None  # The head is still leased.

    complete(queue, leases, 'a', 100)
    late = merge.commit_next('heavy', 101)
    assert late['segment_id'] == 'a' and late['late_capture'] is True and 'head_wait_bypass' not in late
    assert late['previous_segment_id'] == 'b' and late['log_sequence'] == 2
    owner = store.rows['owners', OWNER]
    assert owner['watermark'] == {'capture_at': 2, 'segment_id': 'b'} and owner['log_tail'] == 'a'


def test_longest_waiter_releases_ready_rows_in_capture_order():
    # Newest-first upload: d is ready first, then c, then b; the head a never arrives.
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5})
    merge = OrderedMerge(store, head_wait_seconds=W)
    complete(queue, leases, 'd', 5)
    complete(queue, leases, 'c', 20)
    complete(queue, leases, 'b', 40)
    assert drain(merge, 5 + W - 1) == []
    # d has waited W; b and c have not, but they are captured before d.
    released = drain(merge, 5 + W)
    assert [entry['segment_id'] for entry in released] == ['b', 'c', 'd']
    assert [entry['late_capture'] for entry in released] == [False, False, False]
    complete(queue, leases, 'e', 70)
    assert drain(merge, 70 + W - 1) == []
    assert [entry['segment_id'] for entry in drain(merge, 70 + W)] == ['e']


def test_head_ready_keeps_strict_capture_order_without_bypass():
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3})
    merge = OrderedMerge(store, head_wait_seconds=W)
    for segment in ('c', 'b', 'a'):
        complete(queue, leases, segment, 1)
    entries = drain(merge, 1000)
    assert [entry['segment_id'] for entry in entries] == ['a', 'b', 'c']
    assert not any('head_wait_bypass' in entry or entry['late_capture'] for entry in entries)


def test_rows_without_ready_at_never_start_a_bypass():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    merge = OrderedMerge(store, head_wait_seconds=W)
    complete(queue, leases, 'b', 10)
    del store.rows['jobs', 'b']['ready_at']  # Written by a pre-change worker.
    assert merge.commit_next('heavy', 10**6) is None


def test_recovered_reentry_row_uses_its_stamped_ready_at():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    merge = OrderedMerge(store, head_wait_seconds=W)
    # The recovery writers stamp ready_at as they re-enter merge_pending.
    store.rows['jobs', 'b'].update(
        state='result_ready', merge_pending=True, recovery_state='recovered', ready_at=500, result={'r': 'b'}
    )
    assert merge.commit_next('heavy', 500 + W - 1) is None
    entry = merge.commit_next('heavy', 500 + W)
    assert entry['segment_id'] == 'b' and entry['recovery_version'] == 1 and entry['head_wait_bypass'] is True


def test_quarantined_head_is_not_a_blocker_and_needs_no_bypass():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    merge = OrderedMerge(store, head_wait_seconds=W)
    complete(queue, leases, 'b', 10)
    store.rows['jobs', 'a'].update(state='quarantined', merge_pending=False)
    entry = merge.commit_next('heavy', 11)
    assert entry['segment_id'] == 'b' and 'head_wait_bypass' not in entry


class _NoHeadWaitQueries(MemoryTransaction):
    def first_ready_pending(self, owner_key):
        raise AssertionError('no transactional head-wait query expected')


class _StrictStore(MemoryStore):
    probes = 0

    def run(self, body):
        with self.lock:
            snapshot = deepcopy(self.rows)
            result = body(_NoHeadWaitQueries(snapshot))
            self.rows = snapshot
            return result

    def longest_ready_pending(self, owner_key):
        raise AssertionError('strict order must not probe for a waiter')


class _ProbeOnlyStore(_StrictStore):
    def longest_ready_pending(self, owner_key):
        self.probes += 1
        return MemoryStore.longest_ready_pending(self, owner_key)


def test_blocked_owner_under_w_takes_no_transactional_head_wait_query():
    # The emulator (and Firestore contention) locks on transactional queries;
    # a still-waiting owner costs one non-transactional probe and nothing else.
    store = _ProbeOnlyStore()
    queue = Scheduler(store)
    for segment, capture in {'a': 1, 'b': 2}.items():
        queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 2)}
    complete(queue, leases, 'b', 10)
    assert OrderedMerge(store, head_wait_seconds=W).commit_next('heavy', 10 + W - 1) is None
    assert store.probes == 1


class _StaleProbeStore(MemoryStore):
    def longest_ready_pending(self, owner_key):
        waiter = super().longest_ready_pending(owner_key)
        return {**waiter, 'ready_at': waiter['ready_at'] - 1000} if waiter else None


def test_stale_probe_is_reverified_inside_the_bypass_transaction():
    store = _StaleProbeStore()
    queue = Scheduler(store)
    for segment, capture in {'a': 1, 'b': 2}.items():
        queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 2)}
    complete(queue, leases, 'b', 10)
    # The hint claims b waited 1000 s more than it did; the durable row disagrees.
    assert OrderedMerge(store, head_wait_seconds=W).commit_next('heavy', 11) is None
    assert ('results', 'b') not in store.rows


@pytest.mark.parametrize('value', ['off', 'OFF', '0', '-5'])
def test_kill_switch_restores_strict_order_without_new_queries(monkeypatch, value):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS', value)
    store = _StrictStore()
    queue = Scheduler(store)
    for segment, capture in {'a': 1, 'b': 2}.items():
        queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 2)}
    merge = OrderedMerge(store)
    complete(queue, leases, 'b', 10)
    assert merge.commit_next('heavy', 10**6) is None
    complete(queue, leases, 'a', 10**6)
    assert [entry['segment_id'] for entry in drain(merge, 10**6)] == ['a', 'b']


def _committed_log(store):
    return {key: row for (table, key), row in store.rows.items() if table == 'results'}


@pytest.mark.parametrize('order', list(permutations('abcd')))
def test_kill_switch_zero_is_byte_identical_to_strict_order(order):
    """W=0 and a W the run never reaches write the same result log and owner state."""
    captures = {'a': 1, 'b': 2, 'c': 3, 'd': 4}
    logs = []
    for wait in (0, 10**9):
        store, queue, leases = admitted(captures)
        merge = OrderedMerge(store, head_wait_seconds=wait)
        for step, segment in enumerate(order):
            complete(queue, leases, segment, 100 * step)
            drain(merge, 100 * step + 1)
        logs.append((_committed_log(store), store.rows['owners', OWNER]))
    assert logs[0] == logs[1]
    results, owner = logs[0]
    assert [results[s]['log_sequence'] for s in 'abcd'] == [1, 2, 3, 4]
    assert not any('head_wait_bypass' in row or row['late_capture'] for row in results.values())
    assert owner['watermark'] == {'capture_at': 4, 'segment_id': 'd'}


def _check_chain(results, watermark):
    by_sequence = sorted(results.values(), key=lambda row: row['log_sequence'])
    assert [row['log_sequence'] for row in by_sequence] == list(range(1, len(by_sequence) + 1))
    previous, high = None, None
    for row in by_sequence:
        assert row['previous_segment_id'] == previous
        position = (row['capture_at'], row['segment_id'])
        # Late exactly when a later capture committed first; the watermark never regresses.
        assert row['late_capture'] == (high is not None and position <= high)
        high = position if high is None or position > high else high
        previous = row['segment_id']
    assert watermark == {'capture_at': high[0], 'segment_id': high[1]}


@pytest.mark.parametrize('order', list(permutations('abcde')))
def test_any_completion_order_converges_to_the_strict_result_set(order):
    """Permutation proof: every bypass interleaving keeps the chain and converges.

    Each row completes 45 s after the previous one, so rows that wait behind an
    unready head cross W and bypass it in some permutations.
    """
    captures = {'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5}
    final = {}
    for wait in (0, W):
        store, queue, leases = admitted(captures)
        merge = OrderedMerge(store, head_wait_seconds=wait)
        for step, segment in enumerate(order):
            now = 45 * step
            drain(merge, now)
            complete(queue, leases, segment, now)
            drain(merge, now)
        drain(merge, 10**6)
        results = _committed_log(store)
        owner = store.rows['owners', OWNER]
        assert set(results) == set(captures)
        assert all(store.rows['jobs', s]['state'] == 'committed' for s in captures)
        _check_chain(results, owner['watermark'])
        if wait == W and any(row['late_capture'] for row in results.values()):
            assert any(row.get('head_wait_bypass') for row in results.values())
        final[wait] = (
            {s: (row['result'], row['capture_at'], row['owner_id']) for s, row in results.items()},
            owner['watermark'],
        )
    assert final[0] == final[W]


def test_permutation_schedule_crosses_w_behind_an_unready_head():
    # Reverse completion under the 45 s schedule above: e waits two steps (90 s).
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3})
    merge = OrderedMerge(store, head_wait_seconds=W)
    complete(queue, leases, 'c', 0)
    assert drain(merge, 45) == []
    complete(queue, leases, 'b', 45)
    assert [entry['segment_id'] for entry in drain(merge, 90)] == ['b', 'c']
    complete(queue, leases, 'a', 90)
    late = drain(merge, 90)
    assert [(entry['segment_id'], entry['late_capture']) for entry in late] == [('a', True)]


class _OwnerFencedStore(MemoryStore):
    """Models the flush privacy guard: an owner-wide fence refuses every write for ``heavy``."""

    fenced = False

    def run(self, body):
        with self.lock:
            snapshot = deepcopy(self.rows)
            result = body(MemoryTransaction(snapshot))
            written = {key for (table, key), row in snapshot.items() if table == 'results'} - {
                key for (table, key) in self.rows if table == 'results'
            }
            if self.fenced and any(snapshot['jobs', key]['owner_id'] == 'heavy' for key in written):
                raise BatchPrivacyBlocked('account_deleted')
            self.rows = snapshot
            return result


def test_owner_wide_privacy_fence_behind_a_blocked_head_leaves_the_owner_blocked():
    # quarantine_fenced leaves the head privacy_blocked with merge_pending set.
    store = _OwnerFencedStore()
    queue = Scheduler(store)
    for segment, owner, capture in (('a', 'heavy', 1), ('b', 'heavy', 2), ('x', 'other', 1)):
        queue.enqueue(item(segment, owner=owner, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 3)}
    complete(queue, leases, 'b', 10)
    complete(queue, leases, 'x', 10)
    store.rows['jobs', 'a'].update(state='privacy_blocked', token='', lease_until=0.0)
    store.fenced = True
    merge = OrderedMerge(store, head_wait_seconds=W)
    assert merge.commit_next('heavy', 10 + W) is None
    assert ('results', 'b') not in store.rows
    assert merge.commit_next('other', 10 + W)['segment_id'] == 'x'


class _FlakyProbeStore(MemoryStore):
    failures = 1

    def longest_ready_pending(self, owner_key):
        if self.failures:
            self.failures -= 1
            raise DeadlineExceeded('synthetic probe timeout')
        return super().longest_ready_pending(owner_key)


def test_transient_probe_error_returns_strict_result_without_backoff():
    store = _FlakyProbeStore()
    queue = Scheduler(store)
    for segment, capture in {'a': 1, 'b': 2}.items():
        queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 2)}
    complete(queue, leases, 'b', 10)
    merge = OrderedMerge(store, head_wait_seconds=W)
    assert merge.commit_next('heavy', 10 + W) is None  # Maintenance keeps draining other owners.
    assert merge.commit_next('heavy', 10 + W)['segment_id'] == 'b'


class _MissingIndex(MemoryTransaction):
    def first_ready_pending(self, owner_key):
        _MissingIndex.calls += 1
        raise FailedPrecondition('The query requires an index.')


_MissingIndex.calls = 0


class _MissingTransactionIndexStore(MemoryStore):
    def run(self, body):
        with self.lock:
            snapshot = deepcopy(self.rows)
            result = body(_MissingIndex(snapshot))
            self.rows = snapshot
            return result


class _MissingProbeIndexStore(MemoryStore):
    def longest_ready_pending(self, owner_key):
        _MissingIndex.calls += 1
        raise FailedPrecondition('The query requires an index.')


@pytest.mark.parametrize('store_class', [_MissingProbeIndexStore, _MissingTransactionIndexStore])
def test_missing_index_falls_back_to_strict_order_and_backs_off(caplog, store_class):
    store = store_class()
    queue = Scheduler(store)
    for segment, capture in {'a': 1, 'b': 2}.items():
        queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 2)}
    complete(queue, leases, 'b', 10)
    merge = OrderedMerge(store, head_wait_seconds=W)
    _MissingIndex.calls = 0
    with caplog.at_level(logging.WARNING, logger=merge_module.__name__):
        assert merge.commit_next('heavy', 10**6) is None
        assert merge.commit_next('heavy', 10**6) is None
    assert _MissingIndex.calls == 1  # Backed off; the second call never queried.
    assert 'event=batch_merge outcome=head_wait_unavailable source=ordered_merge count=1' in caplog.text
    assert ('results', 'b') not in store.rows
    complete(queue, leases, 'a', 10**6)
    assert [entry['segment_id'] for entry in drain(merge, 10**6)] == ['a', 'b']


def test_bypass_log_has_closed_labels_and_no_ids(caplog):
    store, queue, leases = admitted({'head-segment': 1, 'later-segment': 2})
    merge = OrderedMerge(store, head_wait_seconds=W, commit_source='gpu_pump')
    complete(queue, leases, 'later-segment', 10)
    with caplog.at_level(logging.INFO, logger=merge_module.__name__):
        assert merge.commit_next('heavy', 10 + 150)['segment_id'] == 'later-segment'
    lines = [record.getMessage() for record in caplog.records if record.name == merge_module.__name__]
    assert lines == [
        'event=batch_merge outcome=head_wait_bypass source=gpu_pump head_state=leased wait_bucket=lt300 count=1'
    ]


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        (None, MERGE_HEAD_WAIT_DEFAULT),
        ('', MERGE_HEAD_WAIT_DEFAULT),
        ('off', 0.0),
        (' Off ', 0.0),
        ('0', 0.0),
        ('-1', 0.0),
        ('30', 30.0),
        ('90.5', 90.5),
        ('3600', 3600.0),
        ('3601', MERGE_HEAD_WAIT_DEFAULT),
        ('soon', MERGE_HEAD_WAIT_DEFAULT),
        ('nan', MERGE_HEAD_WAIT_DEFAULT),
        ('inf', MERGE_HEAD_WAIT_DEFAULT),
    ],
)
def test_head_wait_setting_parses_closed(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS', raw)
    assert merge_head_wait_seconds() == expected


def test_default_merge_reads_the_setting_on_each_commit(monkeypatch):
    store, queue, leases = admitted({'a': 1, 'b': 2})
    merge = OrderedMerge(store)
    complete(queue, leases, 'b', 10)
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS', 'off')
    assert merge.commit_next('heavy', 10 + W) is None
    monkeypatch.delenv('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS')
    assert merge.commit_next('heavy', 10 + W)['segment_id'] == 'b'
