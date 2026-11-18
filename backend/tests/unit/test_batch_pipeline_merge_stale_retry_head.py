"""A due retry row heading an owner's merge runs (or parks) at once instead of after global recovery.

Prod 2026-11-18: recovery requeues due retries oldest-first, 100 per pass, and was 94 h behind a
1.07M-row backlog. Owners' retry heads therefore held every new recording for the full head wait.
"""

import logging

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import merge as merge_module
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.merge import STALE_HEAD_PROMOTE_ROWS, OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key

OWNER = owner_key('heavy')
NOW = 100_000.0
W = 60


def admitted(captures):
    """Fresh-class rows for one owner, each leased at NOW."""
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, capture in captures.items():
        queue.enqueue(item(segment, capture=capture, duration=10), capture + 70)
    leases = {lease.item.segment_id: lease for lease in queue.pull(NOW, len(captures))}
    assert set(leases) == set(captures)
    assert all(store.rows['jobs', segment]['fresh_capture'] is True for segment in captures)
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


def test_due_retry_head_is_requeued_and_commits_in_order_without_bypass():
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    assert job(store, 'a')['state'] == 'retry' and job(store, 'a')['merge_pending'] is True
    complete(queue, leases['b'], NOW + 10)
    merge = OrderedMerge(store, head_wait_seconds=W)

    # Global recovery never runs here: the blocked drain itself promotes the due head.
    due_at = job(store, 'a')['available_at']
    assert merge.commit_next('heavy', due_at + 1) is None
    assert job(store, 'a')['state'] == 'ready'

    complete(queue, lease_of(queue, 'a', due_at + 2), due_at + 3)
    entries = drain(merge, due_at + 4)
    assert [entry['segment_id'] for entry in entries] == ['a', 'b']
    assert not any(entry.get('head_wait_bypass') or entry['late_capture'] for entry in entries)


def test_retry_head_in_backoff_is_left_for_its_due_time():
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    merge = OrderedMerge(store, head_wait_seconds=W)
    due_at = job(store, 'a')['available_at']
    assert due_at > NOW
    assert merge.commit_next('heavy', due_at - 1) is None
    assert job(store, 'a')['state'] == 'retry'
    assert merge.commit_next('heavy', due_at) is None
    assert job(store, 'a')['state'] == 'ready'


def test_allowance_hold_head_parks_and_frees_the_owner_at_once(monkeypatch):
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED', raising=False)
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    # An older worker refused admission and deferred instead of parking.
    job(store, 'a').update(
        attempt=0, compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted', 'at': NOW}, available_at=NOW
    )
    complete(queue, leases['b'], NOW + 1)
    merge = OrderedMerge(store, head_wait_seconds=W)

    assert merge.commit_next('heavy', NOW + 2) is None
    parked = job(store, 'a')
    assert parked['state'] == 'allowance_held' and parked['merge_pending'] is False
    assert store.rows['allowance_holds', OWNER]['held_count'] == 1

    # Well inside the head wait: nothing ahead of b any more.
    entry = merge.commit_next('heavy', NOW + 3)
    assert entry['segment_id'] == 'b' and not entry.get('head_wait_bypass')


def test_allowance_park_switch_off_requeues_instead(monkeypatch):
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    job(store, 'a').update(compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted'}, available_at=NOW)
    complete(queue, leases['b'], NOW + 1)
    assert OrderedMerge(store, head_wait_seconds=W).commit_next('heavy', NOW + 2) is None
    assert job(store, 'a')['state'] == 'ready' and job(store, 'a')['merge_pending'] is True


def test_a_head_that_keeps_failing_reaches_quarantine_and_releases_the_owner():
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    merge = OrderedMerge(store, head_wait_seconds=W)
    now = NOW
    for _ in range(10):
        if job(store, 'a')['state'] == 'quarantined':
            break
        now = max(now, job(store, 'a')['available_at']) + 1
        merge.commit_next('heavy', now)
        assert job(store, 'a')['state'] == 'ready'
        fail(queue, lease_of(queue, 'a', now + 1), now + 2)
    quarantined = job(store, 'a')
    assert quarantined['state'] == 'quarantined' and quarantined['merge_pending'] is False
    assert quarantined['attempt'] == 5
    # b may already have passed by the head wait; either way nothing is left ahead of the owner.
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
    assert 'heavy' not in merge._stale_owners


def test_another_owners_retry_row_is_never_promoted():
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    job(store, 'a')['owner_key'] = owner_key('someone-else')
    merge = OrderedMerge(store, head_wait_seconds=W)
    merge._promote_stale_heads('heavy', {'a': dict(job(store, 'a'))}, NOW + 10_000)
    assert job(store, 'a')['state'] == 'retry'


def test_a_failed_promotion_leaves_the_row_to_recovery_and_the_drain_continues(monkeypatch, caplog):
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)

    def refuse(tx, row, now):
        raise RuntimeError('active owner capacity exceeded; admission must retry')

    monkeypatch.setattr(merge_module, 'requeue_due_retry', refuse)
    merge = OrderedMerge(store, head_wait_seconds=W)
    with caplog.at_level(logging.WARNING, logger=merge_module.__name__):
        assert merge.commit_next('heavy', NOW + 30) is None
    assert job(store, 'a')['state'] == 'retry'
    assert 'event=batch_merge outcome=stale_head_promote_retry source=ordered_merge exception_type=RuntimeError' in (
        caplog.text
    )

    # Global recovery still owns it.
    assert Scheduler(store).recover(NOW + 30) >= 1
    assert job(store, 'a')['state'] == 'ready'


def test_promotion_logs_closed_outcome_counts(caplog):
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    fail(queue, leases['a'], NOW)
    complete(queue, leases['b'], NOW)
    with caplog.at_level(logging.INFO, logger=merge_module.__name__):
        OrderedMerge(store, head_wait_seconds=W).commit_next('heavy', NOW + 30)
    assert 'event=batch_merge outcome=stale_head_promoted action=requeued source=ordered_merge count=1' in caplog.text


@pytest.mark.parametrize('wait', [0, W])
def test_no_retry_head_means_no_promotion_reads(monkeypatch, wait):
    store, queue, leases = admitted({'a': NOW - 500, 'b': NOW - 100})
    complete(queue, leases['b'], NOW)
    calls = []
    monkeypatch.setattr(store, 'fresh_pending', lambda *args: calls.append(args) or [], raising=False)
    merge = OrderedMerge(store, head_wait_seconds=wait, catch_up_depth=0)
    merge.commit_next('heavy', NOW + 1)
    assert calls == [] and job(store, 'a')['state'] == 'leased'
