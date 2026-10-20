"""Fresh-first ordered merge (David's fresh bar, 2026-10-20) over the atomic snapshot store."""

from copy import deepcopy
from itertools import permutations
import logging
import random
from unittest.mock import AsyncMock, Mock

from google.api_core.exceptions import FailedPrecondition, ServiceUnavailable
import pytest

from config.batch_pipeline import MERGE_CATCH_UP_DEPTH_DEFAULT, merge_catch_up_depth
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_purge import _write_erased_result
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.batch_pipeline.serving import Serving

OWNER = owner_key('heavy')
NOW = 100_000.0
CATCH_UP = 'catch_up'
FRESH = 'fresh'


def admitted(rows, store=None):
    """``rows`` maps segment -> (capture_at, class); each row is leased. Catch-up audio is 2 h old."""
    store = store or MemoryStore()
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


def drain(merge, now=NOW):
    entries = []
    while entry := merge.commit_next('heavy', now):
        entries.append(entry)
    return entries


def project_through(store, segment):
    """ProjectionSession.persist: the owner's projection watermark reaches ``segment``."""
    store.rows['owners', OWNER]['projection_watermark'] = segment


def merge_for(store, depth=4, wait=0):
    return OrderedMerge(store, head_wait_seconds=wait, catch_up_depth=depth)


def test_ready_fresh_row_commits_ahead_of_an_unready_catch_up_head_without_waiting():
    store, queue, leases = admitted({'old': (1000, CATCH_UP), 'new': (90_000, FRESH)})
    complete(queue, leases, 'new')
    entry = merge_for(store, wait=60).commit_next('heavy', NOW)
    assert entry['segment_id'] == 'new' and entry['fresh_first'] is True
    assert entry['late_capture'] is False and entry['log_sequence'] == 1 and entry['previous_segment_id'] is None
    complete(queue, leases, 'old')
    late = merge_for(store).commit_next('heavy', NOW)
    assert late['segment_id'] == 'old' and late['late_capture'] is True and 'fresh_first' not in late
    assert late['previous_segment_id'] == 'new' and late['log_sequence'] == 2
    owner = store.rows['owners', OWNER]
    assert owner['watermark'] == {'capture_at': 90_000, 'segment_id': 'new'} and owner['log_tail'] == 'old'


def test_catch_up_commits_hold_at_the_depth_cap_until_projection_advances():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(6)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    merge = merge_for(store, depth=4)
    assert [e['segment_id'] for e in drain(merge)] == ['c0', 'c1', 'c2', 'c3']
    project_through(store, 'c1')
    assert [e['segment_id'] for e in drain(merge)] == ['c4', 'c5']


def test_fresh_row_passes_a_held_catch_up_backlog_and_lands_near_the_projection_head():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(6)} | {'f': (90_000, FRESH)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    entries = drain(merge_for(store, depth=4))
    # Catch-up fills the cap and holds; the ready fresh row still commits, at most the cap behind.
    assert [e['segment_id'] for e in entries] == ['c0', 'c1', 'c2', 'c3', 'f']
    assert entries[-1]['fresh_first'] is True and entries[-1]['late_capture'] is False
    assert not any(e['late_capture'] for e in entries[:-1])
    assert all(store.rows['jobs', s]['merge_pending'] for s in ('c4', 'c5'))
    project_through(store, 'f')
    late = drain(merge_for(store, depth=4))
    assert [e['segment_id'] for e in late] == ['c4', 'c5'] and all(e['late_capture'] for e in late)


def test_a_fresh_row_that_becomes_ready_behind_a_full_cap_commits_next():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(6)} | {'f': (90_000, FRESH)}
    store, queue, leases = admitted(rows)
    for segment in (f'c{n}' for n in range(6)):
        complete(queue, leases, segment)
    merge = merge_for(store, depth=4)
    assert len(drain(merge)) == 4
    complete(queue, leases, 'f')
    entry = merge.commit_next('heavy', NOW)
    assert entry['segment_id'] == 'f' and entry['fresh_first'] is True and entry['log_sequence'] == 5
    assert merge.commit_next('heavy', NOW) is None  # The catch-up rows still wait for projection.


def test_fresh_rows_keep_capture_order_among_themselves():
    store, queue, leases = admitted({'c': (1000, CATCH_UP), 'f1': (90_000, FRESH), 'f2': (90_010, FRESH)})
    complete(queue, leases, 'f2')
    merge = merge_for(store)
    assert merge.commit_next('heavy', NOW) is None  # f1 is the earliest pending fresh row and is still leased.
    complete(queue, leases, 'f1')
    assert [e['segment_id'] for e in drain(merge)] == ['f1', 'f2']


def test_an_erased_watermark_row_still_bounds_the_catch_up_depth():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(8)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    merge = merge_for(store, depth=4)
    assert len(drain(merge)) == 4
    project_through(store, 'c1')

    class _Writes:
        def set(self, ref, value):
            store.rows['results', ref] = value

        def update(self, ref, value):
            store.rows['owners', OWNER].update(value)

    _write_erased_result(_Writes(), 'c1', store.rows['results', 'c1'], None, store.rows['owners', OWNER])
    assert store.rows['results', 'c1']['projection_state'] == 'erased'
    assert 'result' not in store.rows['results', 'c1']
    # Purge keeps the log position, so the hold still counts from the erased watermark.
    assert [e['segment_id'] for e in drain(merge)] == ['c4', 'c5']
    assert store.rows['jobs', 'c6']['merge_pending'] and store.rows['jobs', 'c7']['merge_pending']


def test_a_stuck_fresh_head_releases_later_fresh_rows_after_the_head_wait():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(4)} | {'f1': (90_000, FRESH), 'f2': (90_010, FRESH)}
    store, queue, leases = admitted(rows)
    for segment in ('c0', 'c1', 'c2', 'c3'):
        complete(queue, leases, segment)
    merge = merge_for(store, depth=2, wait=60)
    assert len(drain(merge)) == 2 and merge.held_owners == {'heavy'}
    complete(queue, leases, 'f2', NOW)  # f1 stays leased (for example, a retry).
    assert merge.commit_next('heavy', NOW + 59) is None
    entry = merge.commit_next('heavy', NOW + 60)
    assert entry['segment_id'] == 'f2' and entry['fresh_first'] is True and entry['head_wait_bypass'] is True
    complete(queue, leases, 'f1', NOW + 61)
    late = merge.commit_next('heavy', NOW + 61)
    assert late['segment_id'] == 'f1' and late['late_capture'] is True and late['fresh_first'] is True


def test_missing_watermark_row_never_holds_a_commit():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(6)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    merge = merge_for(store, depth=4)
    assert len(drain(merge)) == 4
    project_through(store, 'c1')
    del store.rows['results', 'c1']  # Retention or erasure removed the watermark's result row.
    assert [e['segment_id'] for e in drain(merge)] == ['c4', 'c5']


def test_unclassified_rows_keep_the_plain_order():
    rows = {f'r{n}': (1000 + n, None) for n in range(6)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    entries = drain(merge_for(store, depth=2))
    assert [e['segment_id'] for e in entries] == [f'r{n}' for n in range(6)]
    assert not any(e.get('fresh_first') for e in entries)


class _PlainStore(MemoryStore):
    def fresh_pending(self, owner_key, limit):
        raise AssertionError('the kill switch must not issue the fresh-first query')


def test_kill_switch_restores_the_plain_merge_without_fresh_queries(monkeypatch):
    rows = {'old': (1000, CATCH_UP), 'new': (90_000, FRESH)} | {f'c{n}': (2000 + n, CATCH_UP) for n in range(5)}
    store, queue, leases = admitted(rows, _PlainStore())
    for segment in rows:
        if segment != 'old':
            complete(queue, leases, segment)
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH', 'off')
    merge = OrderedMerge(store, head_wait_seconds=0)
    assert merge.commit_next('heavy', NOW) is None  # Strict order: the leased head holds everyone.
    complete(queue, leases, 'old')
    assert [e['segment_id'] for e in drain(merge)] == ['old'] + [f'c{n}' for n in range(5)] + ['new']


class _NoFreshIndexStore(MemoryStore):
    def fresh_pending(self, owner_key, limit):
        raise FailedPrecondition('The query requires an index.')


class _InTransactionFreshQuery(MemoryTransaction):
    def fresh_pending(self, owner_key, limit):
        raise AssertionError('the fresh probe must stay outside the commit transaction')


class _ProbeOutsideStore(MemoryStore):
    def run(self, body):
        with self.lock:
            snapshot = deepcopy(self.rows)
            result = body(_InTransactionFreshQuery(snapshot))
            self.rows = snapshot
            return result


def test_fresh_probe_takes_no_transactional_query_lock():
    store, queue, leases = admitted({'old': (1000, CATCH_UP), 'new': (90_000, FRESH)}, _ProbeOutsideStore())
    complete(queue, leases, 'new')
    assert merge_for(store).commit_next('heavy', NOW)['segment_id'] == 'new'


class _FlakyFreshStore(MemoryStore):
    def fresh_pending(self, owner_key, limit):
        raise ServiceUnavailable('transient read')


def test_transient_fresh_probe_error_keeps_the_strict_result(caplog):
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(4)} | {'f': (90_000, FRESH)}
    store, queue, leases = admitted(rows, _FlakyFreshStore())
    for segment in rows:
        complete(queue, leases, segment)
    merge = merge_for(store, depth=2)
    with caplog.at_level(logging.WARNING):
        assert [e['segment_id'] for e in drain(merge)] == ['c0', 'c1']
    assert merge.held_owners == {'heavy'}
    assert 'outcome=fresh_first_probe_retry' in caplog.text and 'fresh_first_unavailable' not in caplog.text


def test_missing_fresh_index_falls_back_to_the_plain_order_and_logs(caplog):
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(6)}
    store, queue, leases = admitted(rows, _NoFreshIndexStore())
    for segment in rows:
        complete(queue, leases, segment)
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2)
    with caplog.at_level(logging.WARNING):
        entries = drain(merge)
    # Without the fresh query a hold would also hold fresh rows, so nothing is held.
    assert [e['segment_id'] for e in entries] == [f'c{n}' for n in range(6)]
    assert 'event=batch_merge outcome=fresh_first_unavailable source=ordered_merge count=1' in caplog.text
    assert caplog.text.count('fresh_first_unavailable') == 1  # Retried only after the back-off.


def test_fresh_first_logs_closed_labels_only(caplog):
    store, queue, leases = admitted({'old': (1000, CATCH_UP), 'new': (90_000, FRESH)})
    complete(queue, leases, 'new')
    with caplog.at_level(logging.INFO):
        merge_for(store).commit_next('heavy', NOW)
    lines = [r.getMessage() for r in caplog.records if 'outcome=fresh_first' in r.getMessage()]
    assert lines == ['event=batch_merge outcome=fresh_first source=ordered_merge head_state=leased count=1']


def _assert_owner_chain(store):
    rows = sorted((v for (table, _), v in store.rows.items() if table == 'results'), key=lambda r: r['log_sequence'])
    assert [r['log_sequence'] for r in rows] == list(range(1, len(rows) + 1))
    previous, high = None, None
    for row in rows:
        assert row['previous_segment_id'] == previous
        position = (row['capture_at'], row['segment_id'])
        assert bool(row['late_capture']) == (high is not None and position <= high)
        high = position if high is None or position > high else high
        previous = row['segment_id']
    assert store.rows['owners', OWNER]['watermark'] == {'capture_at': high[0], 'segment_id': high[1]}
    return rows


@pytest.mark.parametrize('seed', range(12))
def test_any_completion_and_projection_order_keeps_the_log_chain(seed):
    rng = random.Random(seed)
    rows = {f'c{n}': (1000 + n * 10, CATCH_UP) for n in range(8)}
    rows |= {f'f{n}': (90_000 + n * 10, FRESH) for n in range(4)}
    rows |= {f'u{n}': (50_000 + n * 10, None) for n in range(2)}
    store, queue, leases = admitted(rows)
    merge = merge_for(store, depth=3, wait=rng.choice((0, 60)))
    order = list(rows)
    rng.shuffle(order)
    committed = []
    for step, segment in enumerate(order):
        complete(queue, leases, segment, NOW + step)
        committed += drain(merge, NOW + step + rng.choice((0, 61)))
        if committed and rng.random() < 0.5:
            project_through(store, committed[rng.randrange(len(committed))]['segment_id'])
    while len(committed) < len(rows):
        project_through(store, committed[-1]['segment_id'])
        progress = drain(merge, NOW + 10_000)
        assert progress or len(committed) == len(rows)
        committed += progress
    chain = _assert_owner_chain(store)
    assert {r['segment_id'] for r in chain} == set(rows)


@pytest.mark.parametrize('order', list(permutations(['old', 'new', 'newer'])))
def test_fresh_rows_never_wait_on_catch_up_completion_order(order):
    store, queue, leases = admitted({'old': (1000, CATCH_UP), 'new': (90_000, FRESH), 'newer': (90_010, FRESH)})
    merge = merge_for(store, wait=60)
    for segment in order:
        complete(queue, leases, segment)
        drain(merge)
    fresh = [store.rows['results', s] for s in ('new', 'newer')]
    assert [r['log_sequence'] for r in fresh] == sorted(r['log_sequence'] for r in fresh)
    _assert_owner_chain(store)


@pytest.mark.parametrize(
    'value,expected',
    [(None, MERGE_CATCH_UP_DEPTH_DEFAULT), ('off', 0), ('0', 0), ('-3', 0), ('8', 8), ('1001', 16), ('x', 16)],
)
def test_catch_up_depth_config_is_bounded(monkeypatch, value, expected):
    monkeypatch.delenv('BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH', raising=False)
    if value is not None:
        monkeypatch.setenv('BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH', value)
    assert merge_catch_up_depth() == expected


def test_held_owners_are_remembered_until_a_commit_attempt_no_longer_holds():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(4)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    merge = merge_for(store, depth=2)
    assert len(drain(merge)) == 2 and merge.held_owners == {'heavy'}
    project_through(store, 'c1')
    assert len(drain(merge)) == 2 and merge.held_owners == set()


class _Leader:
    def __init__(self, leads):
        self.leads = leads

    def acquire(self):
        return self.leads


@pytest.mark.asyncio
@pytest.mark.parametrize('leads', [True, False])
async def test_every_pump_re_offers_held_owners_hidden_by_a_full_ready_page(leads):
    store = MemoryStore()
    pump = Pump(Scheduler(store), Mock(), leader=_Leader(leads), publish_concurrency=1, inline_metrics=False)
    pump.scheduler.store.due = Mock(return_value=[])  # The page shows nothing of the held owner.
    pump.merge.held_owners.add('held-owner')
    pump.drain_owner = AsyncMock()
    await pump._maintain()
    pump.drain_owner.assert_awaited_once_with('held-owner')


def test_serving_pass_re_offers_held_owners_after_projection():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(4)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    projector = Mock()
    projector.sweep.side_effect = lambda: project_through(store, 'c1')
    service = Serving(store, projector=projector)
    service.merge = merge_for(store, depth=2)
    assert len(drain(service.merge)) == 2 and service.merge.held_owners == {'heavy'}
    service.reconcile()
    assert all(not store.rows['jobs', s]['merge_pending'] for s in rows)
    assert service.merge.held_owners == set()


class _FencedFreshStore(MemoryStore):
    """Privacy flush refuses any transaction that would commit segment ``f``."""

    def run(self, body):
        with self.lock:
            snapshot = deepcopy(self.rows)
            result = body(MemoryTransaction(snapshot))
            if ('results', 'f') in snapshot and ('results', 'f') not in self.rows:
                raise BatchPrivacyBlocked('fenced')
            self.rows = snapshot
            return result


def test_a_fenced_fresh_row_does_not_stop_the_head_wait_for_other_ready_rows():
    rows = {'old': (1000, CATCH_UP), 'c': (2000, CATCH_UP), 'f': (90_000, FRESH)}
    store, queue, leases = admitted(rows, _FencedFreshStore())
    complete(queue, leases, 'c', NOW)
    complete(queue, leases, 'f', NOW)
    merge = merge_for(store, depth=16, wait=60)
    assert merge.commit_next('heavy', NOW + 30) is None  # Fresh fenced; head wait not yet due.
    entry = merge.commit_next('heavy', NOW + 60)
    assert entry['segment_id'] == 'c' and entry['head_wait_bypass'] is True and 'fresh_first' not in entry


def test_the_skipped_fresh_head_is_re_verified_inside_the_transaction():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(3)} | {'f1': (90_000, FRESH), 'f2': (90_010, FRESH)}
    store, queue, leases = admitted(rows)
    for segment in ('c0', 'c1', 'c2', 'f2'):
        complete(queue, leases, segment, NOW)
    merge = merge_for(store, depth=2, wait=60)
    assert len(drain(merge, NOW)) == 2
    stale = store.fresh_pending(OWNER, 32)  # The probe saw f1 still leased...
    complete(queue, leases, 'f1', NOW + 60)  # ...then it became ready before the transaction.
    store.fresh_pending = lambda key, limit: stale
    assert merge.commit_next('heavy', NOW + 60) is None
    del store.fresh_pending
    assert [e['segment_id'] for e in drain(merge, NOW + 61)] == ['f1', 'f2']


def test_a_durable_hold_marker_survives_a_restart_and_clears_once_released():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(4)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    assert len(drain(merge_for(store, depth=2))) == 2
    assert store.rows['merge_holds', OWNER]['held'] is True
    project_through(store, 'c1')
    restarted = merge_for(store, depth=2)  # A new process: its in-memory set is empty.
    assert restarted.held_owners == set()
    drained = []
    restarted.reoffer_marked(lambda owner_id: drained.extend(drain(restarted)))
    assert [e['segment_id'] for e in drained] == ['c2', 'c3']
    # Still two committed rows awaiting projection at a cap of 2: the marker stays.
    assert store.rows['merge_holds', OWNER]['held'] is True
    project_through(store, 'c3')
    restarted.reoffer_marked(lambda owner_id: drained.extend(drain(restarted)))
    assert store.rows['merge_holds', OWNER]['held'] is False
    assert store.held_merge_owners(50) == []


def test_an_unready_head_over_the_cap_keeps_the_owner_held_and_marked():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(4)}
    store, queue, leases = admitted(rows)
    for segment in rows:
        complete(queue, leases, segment)
    merge = merge_for(store, depth=2)
    assert len(drain(merge)) == 2
    queue.enqueue(item('older', capture=500, duration=10), 500 + 10 + 7200)  # A new, older catch-up head.
    assert [lease.item.segment_id for lease in queue.pull(NOW, 1)] == ['older']
    assert merge.commit_next('heavy', NOW) is None
    assert merge.held_owners == {'heavy'}
    merge.release_hold(OWNER)
    assert store.rows['merge_holds', OWNER]['held'] is True


def test_the_marker_page_rotates_through_every_held_owner():
    store = MemoryStore()
    for key in ('a', 'b', 'c'):
        store.rows['merge_holds', key] = {'held': True, 'held_at': NOW}
    merge = merge_for(store)
    assert [key for key, _ in merge.marked_page(2)] == ['a', 'b']
    assert [key for key, _ in merge.marked_page(2)] == ['c']
    assert [key for key, _ in merge.marked_page(2)] == ['a', 'b']


class _FencedHeadStore(MemoryStore):
    """Privacy flush refuses any transaction that would commit segment ``c0``."""

    def run(self, body):
        with self.lock:
            snapshot = deepcopy(self.rows)
            result = body(MemoryTransaction(snapshot))
            if ('results', 'c0') in snapshot and ('results', 'c0') not in self.rows:
                raise BatchPrivacyBlocked('fenced')
            self.rows = snapshot
            return result


def test_a_fenced_catch_up_head_still_lets_the_ready_fresh_row_commit():
    rows = {'c0': (1000, CATCH_UP), 'f': (90_000, FRESH)}
    store, queue, leases = admitted(rows, _FencedHeadStore())
    for segment in rows:
        complete(queue, leases, segment)
    merge = merge_for(store)
    entry = merge.commit_next('heavy', NOW)
    assert entry['segment_id'] == 'f' and entry['fresh_first'] is True
    with pytest.raises(BatchPrivacyBlocked):
        merge.commit_next('heavy', NOW)  # Nothing else to commit: the fence keeps strict behaviour.


def test_every_skipped_fresh_row_is_re_verified():
    rows = {f'c{n}': (1000 + n, CATCH_UP) for n in range(3)}
    rows |= {'f1': (90_000, FRESH), 'f2': (90_005, FRESH), 'f3': (90_010, FRESH)}
    store, queue, leases = admitted(rows)
    for segment in ('c0', 'c1', 'c2', 'f3'):
        complete(queue, leases, segment, NOW)
    merge = merge_for(store, depth=2, wait=60)
    assert len(drain(merge, NOW)) == 2
    stale = store.fresh_pending(OWNER, 32)  # f1 and f2 leased when probed...
    complete(queue, leases, 'f2', NOW + 60)  # ...then f2 became ready.
    store.fresh_pending = lambda key, limit: stale
    assert merge.commit_next('heavy', NOW + 60) is None
    del store.fresh_pending
    entry = merge.commit_next('heavy', NOW + 61)
    assert entry['segment_id'] == 'f2' and entry['head_wait_bypass'] is True


def test_a_stale_marker_without_pending_rows_is_cleared_without_a_drain():
    store = MemoryStore()
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': NOW}
    drain_calls = []
    merge_for(store).reoffer_marked(drain_calls.append)
    assert drain_calls == [] and store.rows['merge_holds', OWNER]['held'] is False


def test_a_fenced_unclassified_head_updates_hold_bookkeeping_before_raising():
    rows = {'c0': (1000, None)}  # No fresh_capture stamp: the strict fence re-raises.
    store, queue, leases = admitted(rows, _FencedHeadStore())
    complete(queue, leases, 'c0')
    merge = merge_for(store)
    merge.held_owners.add('heavy')
    with pytest.raises(BatchPrivacyBlocked):
        merge.commit_next('heavy', NOW)
    assert merge.held_owners == set()


def test_marker_re_offer_survives_a_failing_owner():
    store = MemoryStore()
    for key in ('a', 'b'):
        store.rows['merge_holds', key] = {'held': True, 'held_at': NOW}
    merge = merge_for(store)
    merge.marked_page = lambda limit: [('a', 'bad-owner'), ('b', 'good-owner')]
    drained = []

    def drain_owner(owner_id):
        if owner_id == 'bad-owner':
            raise BatchPrivacyBlocked('fenced')
        drained.append(owner_id)

    merge.reoffer_marked(drain_owner)
    assert drained == ['good-owner']


@pytest.mark.asyncio
async def test_pump_held_re_offer_isolates_each_owner():
    pump = Pump(Scheduler(MemoryStore()), Mock(), leader=_Leader(True), publish_concurrency=1, inline_metrics=False)
    pump.scheduler.store.due = Mock(return_value=[])
    pump._drain_ready_owners = AsyncMock(side_effect=BatchPrivacyBlocked('fenced page owner'))
    pump.merge.marked_page = lambda limit: [('a', 'bad-owner'), ('b', 'good-owner')]
    pump.merge.release_hold = Mock()
    pump.merge.held_owners.update({'bad-owner', 'good-owner'})
    drained = []

    async def drain_owner(owner_id):
        drained.append(owner_id)
        if owner_id == 'bad-owner':
            raise BatchPrivacyBlocked('fenced')

    pump.drain_owner = drain_owner
    await pump._maintain()
    assert drained.count('good-owner') == 2  # Marker page and in-memory set both reached it.
    pump.merge.release_hold.assert_called_once_with('b', force=False)
