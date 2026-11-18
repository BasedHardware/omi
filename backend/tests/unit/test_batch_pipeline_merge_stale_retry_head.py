"""A due retry row heading an owner's merge runs (or parks) at once instead of after global recovery.

Prod 2026-11-18: recovery requeues due retries oldest-first, 100 per pass, and was 94 h behind a
1.07M-row backlog. Owners' retry heads therefore held every new recording for the full head wait.
Emulator coverage of the same paths: scripts/merge_stale_head_emulator_test.py.
"""

from copy import deepcopy
import logging

import pytest

from config.batch_pipeline import Priority
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import merge as merge_module
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.merge import (
    STALE_HEAD_PROMOTE_ROWS,
    STALE_HEAD_PROMOTIONS_PER_ROW,
    STALE_HEAD_SWITCH,
    OrderedMerge,
)
from utils.batch_pipeline.scheduler import Scheduler, owner_key

OWNER = owner_key('heavy')
NOW = 100_000_000.0
W = 60
DAY = 86400


@pytest.fixture(autouse=True)
def fresh_budget(monkeypatch):
    monkeypatch.delenv(STALE_HEAD_SWITCH, raising=False)
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED', raising=False)
    monkeypatch.setattr(merge_module, '_PROMOTIONS', merge_module._TokenBucket(1000.0, 1000))


def admitted(captures, priority=Priority.FRESH, store=None):
    """Rows for one owner, each leased at NOW; captures within the last 10 min stay FRESH on promotion."""
    store = store or MemoryStore()
    queue = Scheduler(store)
    for segment, capture in captures.items():
        queue.enqueue(item(segment, capture=capture, duration=10, priority=priority), capture + 70)
    leases = {lease.item.segment_id: lease for lease in queue.pull(NOW, len(captures))}
    assert set(leases) == set(captures)
    return store, queue, leases


def complete(queue, lease, now):
    queue.store.rows['jobs', lease.item.segment_id]['lease_until'] = now + 1
    assert queue.complete(WorkResult(lease.item.segment_id, f'gs://results/{lease.item.segment_id}'), lease.token, now)


def fail(queue, lease, now):
    queue.store.rows['jobs', lease.item.segment_id]['lease_until'] = now + 1
    assert queue.fail(lease.item.segment_id, lease.token, now)


def lease_of(queue, segment, now):
    leases = {lease.item.segment_id: lease for lease in queue.pull(now, 10)}
    return leases[segment]


def drain(merge, now):
    entries = []
    while entry := merge.commit_next('heavy', now):
        entries.append(entry)
    return entries


def job(store, segment):
    return store.rows['jobs', segment]


def stale_head(captures=None):
    """``a`` failed once (retry, due at the returned time); ``b`` is ready behind it."""
    store, queue, leases = admitted(captures or {'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    return store, queue, leases, job(store, 'a')['available_at']


def counting_fresh_pending(monkeypatch, store):
    calls = []
    real = store.fresh_pending
    monkeypatch.setattr(store, 'fresh_pending', lambda *args: calls.append(args) or real(*args), raising=False)
    return calls


def test_due_retry_head_is_requeued_and_commits_in_order_without_bypass():
    store, queue, _, due_at = stale_head()
    merge = OrderedMerge(store, head_wait_seconds=W)
    # Global recovery never runs here: the blocked drain itself promotes the due head.
    assert merge.commit_next('heavy', due_at + 1) is None
    assert job(store, 'a')['state'] == 'ready' and job(store, 'a')['stale_head_promotions'] == 1

    complete(queue, lease_of(queue, 'a', due_at + 2), due_at + 3)
    entries = drain(merge, due_at + 4)
    assert [entry['segment_id'] for entry in entries] == ['a', 'b']
    assert not any(entry.get('head_wait_bypass') or entry['late_capture'] for entry in entries)


def test_retry_head_in_backoff_is_left_for_its_due_time():
    store, _, _, due_at = stale_head()
    merge = OrderedMerge(store, head_wait_seconds=W)
    assert due_at > NOW
    assert merge.commit_next('heavy', due_at - 1) is None
    assert job(store, 'a')['state'] == 'retry'
    assert merge.commit_next('heavy', due_at) is None
    assert job(store, 'a')['state'] == 'ready'


def test_allowance_hold_head_parks_and_frees_the_owner_at_once():
    store, _, _, _ = stale_head()
    # An older worker refused admission and deferred instead of parking.
    job(store, 'a').update(
        attempt=0, compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted', 'at': NOW}, available_at=NOW
    )
    merge = OrderedMerge(store, head_wait_seconds=W)
    assert merge.commit_next('heavy', NOW + 2) is None
    parked = job(store, 'a')
    assert parked['state'] == 'allowance_held' and parked['merge_pending'] is False
    assert store.rows['allowance_holds', OWNER]['held_count'] == 1
    # Well inside the head wait: nothing ahead of b any more.
    entry = merge.commit_next('heavy', NOW + 3)
    assert entry['segment_id'] == 'b' and not entry.get('head_wait_bypass')


def test_allowance_hold_with_parking_off_is_left_to_recovery(monkeypatch):
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    store, _, _, _ = stale_head()
    job(store, 'a').update(compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted'}, available_at=NOW)
    calls = counting_fresh_pending(monkeypatch, store)
    merge = OrderedMerge(store, head_wait_seconds=W)
    assert merge.commit_next('heavy', NOW + 2) is None
    assert merge.commit_next('heavy', NOW + 3) is None
    assert job(store, 'a')['state'] == 'retry' and calls == []


@pytest.mark.parametrize(
    'fields',
    [
        {'compute_decision': {'outcome': 'held', 'reason': 'fair_use_exhausted'}},
        {'compute_decision': {'outcome': 'held', 'reason': 'budget_exhausted'}},
        {'admission_refusals': 2},  # Unevaluated refusal: the decision was cleared, the attempt refunded.
    ],
)
def test_a_refused_head_is_not_promoted_and_costs_no_repeat_reads(monkeypatch, fields):
    store, _, _, _ = stale_head()
    row = job(store, 'a')
    row.pop('compute_decision', None)
    row.update(available_at=NOW, **fields)
    calls = counting_fresh_pending(monkeypatch, store)
    merge = OrderedMerge(store, head_wait_seconds=W)
    for offset in (1, 2, 3):
        assert merge.commit_next('heavy', NOW + offset) is None
    assert job(store, 'a')['state'] == 'retry' and 'stale_head_promotions' not in job(store, 'a')
    assert calls == [] and not merge._stale_pending('heavy')
    # The head wait still releases b exactly as before.
    assert merge.commit_next('heavy', NOW + W)['head_wait_bypass'] is True


def test_promotion_stops_after_its_per_row_bound_and_recovery_reaches_quarantine():
    store, queue, _, _ = stale_head()
    merge = OrderedMerge(store, head_wait_seconds=W, catch_up_depth=0)
    now = NOW
    for _ in range(STALE_HEAD_PROMOTIONS_PER_ROW):
        now = max(now, job(store, 'a')['available_at']) + 1
        merge.commit_next('heavy', now)
        assert job(store, 'a')['state'] == 'ready'
        fail(queue, lease_of(queue, 'a', now + 1), now + 2)
    assert job(store, 'a')['stale_head_promotions'] == STALE_HEAD_PROMOTIONS_PER_ROW
    now = job(store, 'a')['available_at'] + 1
    merge.commit_next('heavy', now)
    assert job(store, 'a')['state'] == 'retry'  # Bound reached: recovery owns the row again.
    assert Scheduler(store).recover(now) >= 1
    fail(queue, lease_of(queue, 'a', now + 1), now + 2)
    quarantined = job(store, 'a')
    assert quarantined['state'] == 'quarantined' and quarantined['merge_pending'] is False
    assert quarantined['attempt'] == 5
    drain(merge, now + 3)
    assert job(store, 'b')['state'] == 'committed'


def test_owner_stale_prefix_is_promoted_in_bounded_capture_order_pages():
    rows = {f's{n:02d}': NOW - 1000 + n for n in range(STALE_HEAD_PROMOTE_ROWS + 4)}
    store, queue, leases = admitted({**rows, 'z': NOW - 10})
    for segment in rows:
        fail(queue, leases[segment], NOW)
    complete(queue, leases['z'], NOW)
    merge = OrderedMerge(store, head_wait_seconds=W)
    later = max(job(store, segment)['available_at'] for segment in rows) + 1

    assert merge.commit_next('heavy', later) is None
    states = [job(store, segment)['state'] for segment in sorted(rows)]
    assert states == ['ready'] * STALE_HEAD_PROMOTE_ROWS + ['retry'] * 4
    # The head is now a promoted (ready) row; the bounded remainder still follows on the next drain.
    assert merge.commit_next('heavy', later) is None
    assert {job(store, segment)['state'] for segment in rows} == {'ready'}
    assert not merge._stale_pending('heavy')


def test_process_token_bucket_bounds_promotions_and_the_owner_resumes(monkeypatch):
    rows = {f's{n}': NOW - 1000 + n for n in range(5)}
    store, queue, leases = admitted({**rows, 'z': NOW - 10})
    for segment in rows:
        fail(queue, leases[segment], NOW)
    complete(queue, leases['z'], NOW)
    later = max(job(store, segment)['available_at'] for segment in rows) + 1
    monkeypatch.setattr(merge_module, '_PROMOTIONS', merge_module._TokenBucket(0.0, 2))
    merge = OrderedMerge(store, head_wait_seconds=W)
    for _ in range(3):  # A drain calls commit_next repeatedly; the bucket, not the call, is the bound.
        merge.commit_next('heavy', later)
    assert [job(store, segment)['state'] for segment in sorted(rows)] == ['ready'] * 2 + ['retry'] * 3
    assert merge._stale_pending('heavy')
    monkeypatch.setattr(merge_module, '_PROMOTIONS', merge_module._TokenBucket(0.0, 10))
    merge.commit_next('heavy', later)
    assert {job(store, segment)['state'] for segment in rows} == {'ready'}


def test_token_bucket_refills_at_its_rate():
    clock = [0.0]
    bucket = merge_module._TokenBucket(2.0, 3, clock=lambda: clock[0])
    assert [bucket.take() for _ in range(4)] == [True, True, True, False]
    clock[0] = 0.5
    assert [bucket.take() for _ in range(2)] == [True, False]
    clock[0] = 100.0
    assert sum(bucket.take() for _ in range(10)) == 3  # Never more than the burst.


def test_continued_owners_are_lru_capped_and_expire(monkeypatch):
    merge = OrderedMerge(MemoryStore())
    monkeypatch.setattr(merge_module, 'STALE_OWNERS_TRACKED', 2)
    for owner in ('o1', 'o2', 'o3'):
        merge._mark_stale(owner, True)
    assert list(merge._stale_owners) == ['o2', 'o3']
    merge._mark_stale('o2', False)
    assert list(merge._stale_owners) == ['o3']
    monkeypatch.setattr(merge_module, 'STALE_OWNER_TTL_SECONDS', -1.0)
    assert not merge._stale_pending('o3') and not merge._stale_owners


@pytest.mark.parametrize(
    'age,expected',
    [(300, Priority.FRESH), (2 * 3600, Priority.RECENT), (6 * DAY, Priority.RECENT), (8 * DAY, Priority.DEEP)],
)
def test_promoted_priority_drops_by_capture_age_and_keeps_its_admission_identity(age, expected):
    capture = NOW - age - 10
    store, queue, leases = admitted({'a': capture, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    due_at = job(store, 'a')['available_at']
    assert OrderedMerge(store, head_wait_seconds=W).commit_next('heavy', due_at) is None
    row = job(store, 'a')
    assert row['state'] == 'ready' and row['priority'] == int(expected)
    assert store.rows['queues', f'{int(expected)}_{OWNER}']['head'] == 'a'
    if expected == Priority.FRESH:
        assert 'admitted_priority' not in row
    else:
        assert row['admitted_priority'] == int(Priority.FRESH)
    # An idempotent re-admission of the same work is still recognised, not refused as different work.
    assert queue.enqueue(item('a', capture=capture, duration=10, priority=Priority.FRESH), NOW) is False
    with pytest.raises(ValueError, match='different immutable work'):
        queue.enqueue(item('a', capture=capture, duration=10, priority=Priority.DEEP), NOW)


def test_a_deep_row_is_never_raised_to_a_fresher_class():
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100}, priority=Priority.DEEP)
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    OrderedMerge(store, head_wait_seconds=W).commit_next('heavy', job(store, 'a')['available_at'])
    assert job(store, 'a')['priority'] == int(Priority.DEEP) and 'admitted_priority' not in job(store, 'a')


@pytest.mark.parametrize('change', ['leased', 'parked'])
def test_a_stale_hint_never_promotes_a_row_that_moved(change):
    store, _, _, due_at = stale_head()
    hint = deepcopy(job(store, 'a'))
    if change == 'leased':
        # Another process requeued and leased it after this drain read its hint.
        job(store, 'a').update(state='leased', token='other', lease_until=due_at + 900, attempt=2)
    else:
        job(store, 'a').update(state='allowance_held', merge_pending=False)
    before = deepcopy(store.rows)
    OrderedMerge(store, head_wait_seconds=W)._promote_stale_heads('heavy', {'a': hint}, due_at + 1)
    assert store.rows == before


def test_deleted_and_no_longer_pending_rows_are_no_ops():
    store, _, _, due_at = stale_head()
    hint = deepcopy(job(store, 'a'))
    merge = OrderedMerge(store, head_wait_seconds=W)
    job(store, 'a')['merge_pending'] = False
    before = deepcopy(store.rows)
    merge._promote_stale_heads('heavy', {'a': hint}, due_at + 1)
    assert store.rows == before
    del store.rows['jobs', 'a']
    before = deepcopy(store.rows)
    merge._promote_stale_heads('heavy', {'a': hint}, due_at + 1)
    assert store.rows == before


def test_another_owners_retry_row_is_never_promoted():
    store, _, _, due_at = stale_head()
    job(store, 'a')['owner_key'] = owner_key('someone-else')
    OrderedMerge(store, head_wait_seconds=W)._promote_stale_heads('heavy', {'a': dict(job(store, 'a'))}, due_at + 1)
    assert job(store, 'a')['state'] == 'retry'


class FencedStore(MemoryStore):
    """The promotion transaction meets the commit-boundary privacy fence."""

    def __init__(self):
        super().__init__()
        self.fenced = []

    def run(self, body):
        if getattr(body, '__name__', '') == 'promote':
            raise BatchPrivacyBlocked('privacy changed')
        return super().run(body)

    def quarantine_fenced(self, segment_id, now):
        # FirestoreStore's disposition (store conformance): detach the retry, keep its identity.
        self.fenced.append(segment_id)
        self.rows['jobs', segment_id].update(state='privacy_blocked', token='', lease_until=0.0, privacy_blocked_at=now)
        return True


def test_a_privacy_fenced_head_is_quarantined_like_recovery_does(monkeypatch, caplog):
    fenced = FencedStore()
    _, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100}, store=fenced)
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    due_at = job(fenced, 'a')['available_at']
    calls = counting_fresh_pending(monkeypatch, fenced)
    merge = OrderedMerge(fenced, head_wait_seconds=W)
    with caplog.at_level(logging.INFO, logger=merge_module.__name__):
        assert merge.commit_next('heavy', due_at + 1) is None
    assert fenced.fenced == ['a'] and job(fenced, 'a')['state'] == 'privacy_blocked'
    assert 'outcome=stale_head_promoted action=privacy_fenced source=ordered_merge count=1' in caplog.text
    assert 'stale_head_promote_retry' not in caplog.text
    # Erasure owns it now; later drains neither re-read nor retry it, and the head wait applies as before.
    reads = len(calls)
    for offset in (2, 3):
        assert merge.commit_next('heavy', due_at + offset) is None
    assert len(calls) == reads and fenced.fenced == ['a'] and not merge._stale_pending('heavy')


def test_a_failed_promotion_leaves_the_row_to_recovery_and_the_drain_continues(monkeypatch, caplog):
    store, _, _, due_at = stale_head()

    def refuse(tx, row, now, **kwargs):
        raise RuntimeError('active owner capacity exceeded; admission must retry')

    monkeypatch.setattr(merge_module, 'requeue_due_retry', refuse)
    merge = OrderedMerge(store, head_wait_seconds=W)
    with caplog.at_level(logging.WARNING, logger=merge_module.__name__):
        assert merge.commit_next('heavy', due_at + 1) is None
    assert job(store, 'a')['state'] == 'retry' and 'stale_head_promotions' not in job(store, 'a')
    assert 'event=batch_merge outcome=stale_head_promote_retry source=ordered_merge exception_type=RuntimeError' in (
        caplog.text
    )
    assert Scheduler(store).recover(due_at + 1) >= 1
    assert job(store, 'a')['state'] == 'ready'


def test_promotion_logs_closed_outcome_counts(caplog):
    store, _, _, due_at = stale_head()
    with caplog.at_level(logging.INFO, logger=merge_module.__name__):
        OrderedMerge(store, head_wait_seconds=W).commit_next('heavy', due_at + 1)
    assert 'event=batch_merge outcome=stale_head_promoted action=requeued source=ordered_merge count=1' in caplog.text


@pytest.mark.parametrize('value', ['false', 'off', '0'])
def test_switch_off_is_the_previous_behaviour(monkeypatch, value):
    monkeypatch.setenv(STALE_HEAD_SWITCH, value)
    store, _, _, due_at = stale_head()
    calls = counting_fresh_pending(monkeypatch, store)
    merge = OrderedMerge(store, head_wait_seconds=W)

    def never(*args, **kwargs):
        raise AssertionError('promotion must not run with the switch off')

    monkeypatch.setattr(merge, '_promote_stale_heads', never)
    ready_at = job(store, 'b')['ready_at']
    assert merge.commit_next('heavy', max(due_at, ready_at + W - 1)) is None
    assert job(store, 'a')['state'] == 'retry' and calls == []
    entry = merge.commit_next('heavy', max(due_at, ready_at + W))
    assert entry['segment_id'] == 'b' and entry['head_wait_bypass'] is True


@pytest.mark.parametrize('wait', [0, W])
def test_no_retry_head_means_no_promotion_reads(monkeypatch, wait):
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    complete(queue, leases['b'], NOW)
    calls = counting_fresh_pending(monkeypatch, store)
    merge = OrderedMerge(store, head_wait_seconds=wait, catch_up_depth=0)
    merge.commit_next('heavy', NOW + 1)
    assert calls == [] and job(store, 'a')['state'] == 'leased'


def test_a_spent_process_budget_skips_the_probe_read_and_keeps_the_owner_marked(monkeypatch):
    store, _, _, due_at = stale_head()
    monkeypatch.setattr(merge_module, '_PROMOTIONS', merge_module._TokenBucket(0.0, 0))
    calls = counting_fresh_pending(monkeypatch, store)
    merge = OrderedMerge(store, head_wait_seconds=W)
    merge.commit_next('heavy', due_at + 1)
    assert calls == [] and job(store, 'a')['state'] == 'retry'
    assert merge._stale_pending('heavy')


class UnfencedStore(FencedStore):
    def quarantine_fenced(self, segment_id, now):
        self.fenced.append(segment_id)
        return False


def test_an_unapplied_privacy_fence_is_not_counted_as_fenced(caplog):
    store = UnfencedStore()
    _, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100}, store=store)
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    due_at = job(store, 'a')['available_at']
    merge = OrderedMerge(store, head_wait_seconds=W)
    with caplog.at_level(logging.INFO, logger=merge_module.__name__):
        merge.commit_next('heavy', due_at + 1)
    assert store.fenced == ['a'] and job(store, 'a')['state'] == 'retry'
    assert 'action=privacy_fenced' not in caplog.text
