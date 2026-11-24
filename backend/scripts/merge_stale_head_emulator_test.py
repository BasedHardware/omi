# LIFECYCLE: permanent
"""Stale merge-head promotion through real Store transactions (sim + Firestore emulator).

The ordered merge requeues or parks an owner's due retry head instead of waiting for global
recovery. These proofs run the production Scheduler, OrderedMerge and FirestoreStore transaction,
privacy fence and missing-document read; only audio and results are synthetic. Unit coverage of
the bounds lives in tests/unit/test_batch_pipeline_merge_stale_retry_head.py.
Require OMI_REQUIRE_STORE_BACKENDS=sim,emulator for a full proof.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import pytest

from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import merge as merge_module
from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.batch_pipeline.merge import STALE_HEAD_SWITCH, OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration
NOW = 2_000_000.0
W = 60


@pytest.fixture
def h(store_backend, monkeypatch):  # noqa: F811
    monkeypatch.delenv(STALE_HEAD_SWITCH, raising=False)
    monkeypatch.setattr(merge_module, '_PROMOTIONS', merge_module._TokenBucket(1000.0, 1000))
    store_backend.seed_user('owner')
    return store_backend


def work(h, segment, capture, priority=Priority.FRESH):
    uid = h.uid('owner')
    return WorkItem(
        segment,
        uid,
        capture,
        f'sim://audio/{segment}',
        10.0,
        priority,
        conversation_id=f'conv-{segment}',
        privacy_generation=0,
    )


def row(h, segment):
    return h.store.run(lambda tx: tx.get('jobs', segment))


def stale_head(h, capture_a=NOW - 500):
    """``a`` failed once and is a due retry; ``b`` is ready behind it."""
    queue = Scheduler(h.store)
    for segment, capture in (('a', capture_a), ('b', NOW - 100)):
        h.customer.add_conversation(h.uid('owner'), f'conv-{segment}')
        assert queue.enqueue(work(h, segment, capture), NOW - 50)
    leases = {lease.item.segment_id: lease for lease in queue.pull(NOW, 2)}
    assert set(leases) == {'a', 'b'}
    assert queue.fail('a', leases['a'].token, NOW)
    assert queue.complete(WorkResult('b', 'gs://synthetic/results/b'), leases['b'].token, NOW)
    return queue, row(h, 'a')['available_at']


def test_due_retry_head_is_promoted_and_commits_in_order(h):
    queue, due_at = stale_head(h)
    merge = OrderedMerge(h.store, head_wait_seconds=W)
    assert merge.commit_next(h.uid('owner'), due_at + 1) is None
    promoted = row(h, 'a')
    assert promoted['state'] == 'ready' and promoted['stale_head_promotions'] == 1

    lease = {lease.item.segment_id: lease for lease in queue.pull(due_at + 2, 2)}['a']
    assert queue.complete(WorkResult('a', 'gs://synthetic/results/a'), lease.token, due_at + 3)
    first = merge.commit_next(h.uid('owner'), due_at + 4)
    second = merge.commit_next(h.uid('owner'), due_at + 4)
    assert [first['segment_id'], second['segment_id']] == ['a', 'b']
    assert not first.get('head_wait_bypass') and not second.get('head_wait_bypass')


def test_a_hint_read_before_another_lease_never_promotes(h):
    queue, due_at = stale_head(h)
    hint = row(h, 'a')
    # Another process's recovery requeues and leases the row after this drain read its hint.
    assert Scheduler(h.store).recover(due_at + 1) >= 1
    lease = {lease.item.segment_id: lease for lease in queue.pull(due_at + 1, 2)}['a']
    OrderedMerge(h.store, head_wait_seconds=W)._promote_stale_heads(h.uid('owner'), {'a': hint}, due_at + 2)
    current = row(h, 'a')
    assert current['state'] == 'leased' and current['token'] == lease.token
    assert 'stale_head_promotions' not in current


def test_a_privacy_fenced_head_takes_recoverys_disposition(h):
    _, due_at = stale_head(h)
    h.customer.delete_conversation(h.uid('owner'), 'conv-a')
    OrderedMerge(h.store, head_wait_seconds=W)._promote_stale_heads(h.uid('owner'), {'a': row(h, 'a')}, due_at + 1)
    fenced = row(h, 'a')
    assert fenced['state'] == 'privacy_blocked' and fenced['token'] == '' and fenced['lease_until'] == 0.0
    assert 'stale_head_promotions' not in fenced


def test_a_missing_job_is_a_no_op(h):
    _, due_at = stale_head(h)
    # A hint for a deleted row, read while ``a`` is still backing off (so only the ghost is due).
    ghost = {**row(h, 'a'), 'segment_id': 'ghost', 'available_at': NOW - 1}
    assert due_at > NOW
    OrderedMerge(h.store, head_wait_seconds=W)._promote_stale_heads(h.uid('owner'), {'ghost': ghost}, NOW)
    assert row(h, 'ghost') == {}
    assert row(h, 'a')['state'] == 'retry'


def test_promoted_priority_drops_by_age_and_keeps_admission_identity(h):
    queue, due_at = stale_head(h, capture_a=NOW - 2 * 86400)
    merge = OrderedMerge(h.store, head_wait_seconds=W)
    # ``a`` is catch-up class: fresh ``b`` commits ahead first, then the blocked call promotes ``a``.
    while merge.commit_next(h.uid('owner'), due_at + 1):
        pass
    promoted = row(h, 'a')
    assert promoted['state'] == 'ready'
    assert promoted['priority'] == int(Priority.RECENT) and promoted['admitted_priority'] == int(Priority.FRESH)
    queued = h.store.run(lambda tx: tx.get('queues', f'{int(Priority.RECENT)}_{owner_key(h.uid("owner"))}'))
    assert queued['head'] == 'a'
    assert queue.enqueue(work(h, 'a', NOW - 2 * 86400), due_at + 2) is False
