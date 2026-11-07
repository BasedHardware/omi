"""PL-100/101/102: queue age proxy and capacity-count conformance across Store backends.

Verify that ``SimStore``, ``FirestoreStore`` and ``PostgresStore`` share one contract for:
- PL-100: ``oldest(priority, ready_only=False)`` walks a bounded FIFO prefix past durable
  allowance policy holds (both a current ``allowance_exhausted`` decision and a retained
  ``last_policy_hold`` marker during an unevaluated/BLIND recheck), keeps raw
  ``oldest(priority, ready_only=True)`` diagnostic, lets a current decision override a
  stale marker, and preserves the conservative ``OLDEST_POLICY_HOLD_SCAN_LIMIT + 1``
  truncation sentinel (``NaN`` when truncated, ``None`` at or below the bound).
- PL-101: ``ready_for_capacity(priority, now)`` counts only available ``state == 'ready'``,
  ``merge_pending is True`` units with ``compute_decision.outcome in ('unattempted', 'allowed')``
  and ``available_at <= now``, excluding parked/held/decisionless legacy debt.
- PL-102: ``QueueMetrics(capacity_sampling=True).refresh`` samples all three priorities
  atomically and keeps ``omi_batch_pipeline_capacity_refreshed_at_seconds`` unobserved/stale
  when any priority query fails or returns a malformed response.
"""

from __future__ import annotations

from dataclasses import replace
import math

from prometheus_client import CollectorRegistry
import pytest

from database.batch_pipeline_store import OLDEST_POLICY_HOLD_SCAN_LIMIT
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler, owner_key as scheduler_owner_key

pytestmark = pytest.mark.integration

T0 = 1_000.0


@pytest.fixture
def h(store_backend):  # noqa: F811
    store_backend.seed_user('o')
    return store_backend


def job(h, segment: str, **fields) -> dict:
    uid = h.uid('o')
    base = {
        'segment_id': segment,
        'owner_id': uid,
        'owner_key': scheduler_owner_key(uid),
        'priority': int(Priority.DEEP),
        'state': 'ready',
        'capture_at': T0,
        'enqueued_at': T0,
        'available_at': T0,
        'merge_pending': True,
    }
    base.update(fields)
    return base


def put_jobs(h, rows: list[tuple[str, dict]]) -> None:
    def body(tx):
        for key, doc in rows:
            tx.put('jobs', key, doc)

    h.store.run(body)


def allowance_hold_decision(at: float = T0 + 10) -> dict:
    return {'outcome': 'held', 'reason': 'allowance_exhausted', 'at': at}


def allowed_decision(at: float = T0 + 10) -> dict:
    return {'outcome': 'allowed', 'reason': 'batch', 'at': at}


def unattempted_decision(at: float = T0) -> dict:
    return {'outcome': 'unattempted', 'reason': 'admitted', 'at': at}


# -- PL-100: oldest() allowance-hold classification and bounded-scan truncation ----------------------
@pytest.mark.parametrize(
    ('case', 'rows', 'expected_uncommitted', 'expected_ready'),
    [
        (
            'current_allowance_hold_before_real_commitment',
            [
                ('h1', {'enqueued_at': 10.0, 'compute_decision': allowance_hold_decision()}),
                ('c1', {'enqueued_at': 25.0, 'compute_decision': unattempted_decision()}),
            ],
            25.0,
            10.0,
        ),
        (
            'only_current_allowance_holds_returns_none',
            [
                ('h1', {'enqueued_at': 10.0, 'compute_decision': allowance_hold_decision()}),
                ('h2', {'enqueued_at': 20.0, 'state': 'retry', 'compute_decision': allowance_hold_decision()}),
            ],
            None,
            10.0,
        ),
        (
            'blind_recheck_last_policy_hold_before_real_commitment',
            [
                ('h1', {'enqueued_at': 12.0, 'last_policy_hold': {'reason': 'allowance_exhausted', 'at': 15.0}}),
                ('c1', {'enqueued_at': 30.0}),
            ],
            30.0,
            12.0,
        ),
        (
            'only_blind_recheck_last_policy_hold_returns_none',
            [
                ('h1', {'enqueued_at': 12.0, 'last_policy_hold': {'reason': 'allowance_exhausted', 'at': 15.0}}),
            ],
            None,
            12.0,
        ),
        (
            'non_allowance_hold_reason_remains_measured_commitment',
            [
                (
                    'f1',
                    {
                        'enqueued_at': 14.0,
                        'compute_decision': {'outcome': 'held', 'reason': 'fair_use_restricted', 'at': 15.0},
                    },
                ),
                ('c1', {'enqueued_at': 40.0}),
            ],
            14.0,
            14.0,
        ),
        (
            'current_allowed_decision_overrides_stale_allowance_hold_marker',
            [
                (
                    'reauthorized',
                    {
                        'enqueued_at': 16.0,
                        'last_policy_hold': {'reason': 'allowance_exhausted', 'at': 15.0},
                        'compute_decision': allowed_decision(20.0),
                    },
                ),
                ('later', {'enqueued_at': 50.0}),
            ],
            16.0,
            16.0,
        ),
        (
            'current_non_allowance_hold_overrides_stale_allowance_hold_marker',
            [
                (
                    'reclassified',
                    {
                        'enqueued_at': 18.0,
                        'last_policy_hold': {'reason': 'allowance_exhausted', 'at': 15.0},
                        'compute_decision': {'outcome': 'held', 'reason': 'privacy_blocked', 'at': 20.0},
                    },
                ),
            ],
            18.0,
            18.0,
        ),
        (
            'non_allowance_last_policy_hold_marker_is_not_skipped',
            [
                ('p1', {'enqueued_at': 19.0, 'last_policy_hold': {'reason': 'fair_use_restricted', 'at': 15.0}}),
            ],
            19.0,
            19.0,
        ),
    ],
    ids=lambda val: val if isinstance(val, str) else '',
)
def test_pl100_oldest_skips_allowance_holds_and_preserves_diagnostic_ready_age(
    h, case, rows, expected_uncommitted, expected_ready
):
    put_jobs(h, [(key, job(h, key, **fields)) for key, fields in rows])
    assert h.store.oldest(int(Priority.DEEP), ready_only=False) == expected_uncommitted
    assert h.store.oldest(int(Priority.DEEP), ready_only=True) == expected_ready


@pytest.mark.parametrize(
    ('hold_count', 'expect_nan'),
    [
        (OLDEST_POLICY_HOLD_SCAN_LIMIT + 1, True),
        (OLDEST_POLICY_HOLD_SCAN_LIMIT, False),
    ],
    ids=['truncated_past_bound_returns_nan', 'exact_bound_returns_none'],
)
def test_pl100_oldest_bounded_scan_truncation_contract(h, hold_count, expect_nan):
    uid = h.uid('o')
    ok = scheduler_owner_key(uid)
    docs = [
        (
            f'hold-{index:04d}',
            {
                'segment_id': f'hold-{index:04d}',
                'owner_id': uid,
                'owner_key': ok,
                'priority': int(Priority.DEEP),
                'state': 'ready',
                'capture_at': float(index),
                'enqueued_at': float(index + 1),
                'available_at': float(index + 1),
                'merge_pending': True,
                'compute_decision': allowance_hold_decision(float(index + 1)),
            },
        )
        for index in range(hold_count)
    ]
    # Batch writes inside Firestore's 450-op transaction budget.
    for start in range(0, len(docs), 200):
        put_jobs(h, docs[start : start + 200])

    sample = h.store.oldest(int(Priority.DEEP), ready_only=False)
    if expect_nan:
        assert sample is not None and math.isnan(sample)
    else:
        assert sample is None
    assert h.store.oldest(int(Priority.DEEP), ready_only=True) == 1.0


def test_pl100_scheduler_hold_recover_unevaluated_recheck_keeps_oldest_age_zero(h):
    uid = h.uid('o')
    queue = Scheduler(h.store)
    work = WorkItem(
        'held-seg',
        uid,
        T0,
        'gs://synthetic/held-seg',
        30.0,
        Priority.DEEP,
        requires_compute_admission=True,
    )
    assert queue.enqueue(work, T0)
    (lease,) = queue.pull(T0 + 10)
    assert queue.defer(
        'held-seg',
        lease.token,
        T0 + 20,
        60.0,
        held_reason='allowance_exhausted',
        admission_refused=True,
    )
    queue.recover(T0 + 100)
    (lease,) = queue.pull(T0 + 100)
    # Unevaluated RPC failure during recheck clears compute_decision (BLIND) while retaining last_policy_hold.
    assert queue.defer('held-seg', lease.token, T0 + 110, 60.0, admission_refused=True)
    stored = h.store.run(lambda tx: tx.get('jobs', 'held-seg'))
    assert 'compute_decision' not in stored
    assert stored['last_policy_hold'] == {'reason': 'allowance_exhausted', 'at': T0 + 20}

    registry = CollectorRegistry()
    metrics = QueueMetrics(registry, worker_release='rel', namespace=h.namespace)
    metrics.refresh(h.store, T0 + 50_000)
    labels = {'priority': 'deep', 'worker_release': 'rel', 'namespace': h.namespace}
    assert registry.get_sample_value('omi_batch_pipeline_oldest_age_seconds', labels) == 0.0


# -- PL-101 & PL-102: ready_for_capacity and QueueMetrics atomic capacity sampling -------------------
def test_pl101_ready_for_capacity_empty_store_returns_exact_int_zero(h):
    count = h.store.ready_for_capacity(int(Priority.DEEP), T0)
    assert count == 0 and type(count) is int


def test_pl101_ready_for_capacity_counts_only_due_ready_pending_unattempted_or_allowed(h):
    put_jobs(
        h,
        [
            ('elig-unattempted', job(h, 'elig-unattempted', available_at=T0 - 5, compute_decision=unattempted_decision())),
            ('elig-allowed', job(h, 'elig-allowed', available_at=T0, compute_decision=allowed_decision())),
            ('held-allowance', job(h, 'held-allowance', available_at=T0 - 5, compute_decision=allowance_hold_decision())),
            (
                'held-fair-use',
                job(
                    h,
                    'held-fair-use',
                    available_at=T0 - 5,
                    compute_decision={'outcome': 'held', 'reason': 'fair_use_restricted', 'at': T0},
                ),
            ),
            ('legacy-no-decision', job(h, 'legacy-no-decision', available_at=T0 - 5)),
            (
                'blind-with-marker',
                job(
                    h,
                    'blind-with-marker',
                    available_at=T0 - 5,
                    last_policy_hold={'reason': 'allowance_exhausted', 'at': T0},
                ),
            ),
            ('future-available', job(h, 'future-available', available_at=T0 + 0.5, compute_decision=unattempted_decision())),
            ('null-available', job(h, 'null-available', available_at=None, compute_decision=unattempted_decision())),
            (
                'not-merge-pending',
                job(h, 'not-merge-pending', merge_pending=False, available_at=T0 - 5, compute_decision=unattempted_decision()),
            ),
            ('leased-row', job(h, 'leased-row', state='leased', available_at=T0 - 5, compute_decision=allowed_decision())),
            ('retry-row', job(h, 'retry-row', state='retry', available_at=T0 - 5, compute_decision=unattempted_decision())),
            (
                'other-priority',
                job(
                    h,
                    'other-priority',
                    priority=int(Priority.FRESH),
                    available_at=T0 - 5,
                    compute_decision=unattempted_decision(),
                ),
            ),
        ],
    )
    assert h.store.ready_for_capacity(int(Priority.DEEP), T0) == 2
    assert h.store.ready_for_capacity(int(Priority.DEEP), T0 + 1.0) == 3
    assert h.store.ready_for_capacity(int(Priority.FRESH), T0) == 1
    assert h.store.ready_for_capacity(int(Priority.RECENT), T0) == 0


def test_pl101_scheduler_lifecycle_updates_ready_for_capacity_authoritatively(h):
    uid = h.uid('o')
    queue = Scheduler(h.store)
    work = WorkItem(
        'cap-seg',
        uid,
        T0,
        'gs://synthetic/cap-seg',
        30.0,
        Priority.RECENT,
        requires_compute_admission=True,
    )
    assert queue.enqueue(work, T0)
    assert h.store.ready_for_capacity(int(Priority.RECENT), T0) == 1

    (lease,) = queue.pull(T0 + 1)
    assert h.store.ready_for_capacity(int(Priority.RECENT), T0 + 1) == 0

    assert queue.defer(
        'cap-seg',
        lease.token,
        T0 + 2,
        60.0,
        held_reason='allowance_exhausted',
        admission_refused=True,
    )
    assert h.store.ready_for_capacity(int(Priority.RECENT), T0 + 100) == 0

    # Recover puts the job back in state='ready', but its held compute_decision still excludes it from capacity.
    queue.recover(T0 + 100)
    assert h.store.ready_for_capacity(int(Priority.RECENT), T0 + 100) == 0

    # An unevaluated refusal clears compute_decision (BLIND); recovered back to ready, it still cannot buy GPUs.
    (lease,) = queue.pull(T0 + 101)
    assert queue.defer('cap-seg', lease.token, T0 + 102, 60.0, admission_refused=True)
    queue.recover(T0 + 200)
    assert h.store.ready_for_capacity(int(Priority.RECENT), T0 + 200) == 0


def test_pl102_queue_metrics_refreshes_three_priority_capacity_sample_atomically(h):
    put_jobs(
        h,
        [
            ('f1', job(h, 'f1', priority=int(Priority.FRESH), compute_decision=unattempted_decision())),
            ('r1', job(h, 'r1', priority=int(Priority.RECENT), compute_decision=allowed_decision())),
            ('r2', job(h, 'r2', priority=int(Priority.RECENT), compute_decision=unattempted_decision())),
            ('d-held', job(h, 'd-held', priority=int(Priority.DEEP), compute_decision=allowance_hold_decision())),
        ],
    )
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry, worker_release='rel', namespace=h.namespace, capacity_sampling=True)
    metrics.refresh(h.store, T0 + 10)
    scope = {'worker_release': 'rel', 'namespace': h.namespace}
    assert registry.get_sample_value('omi_batch_pipeline_admissible_ready_units', {**scope, 'priority': 'fresh'}) == 1
    assert registry.get_sample_value('omi_batch_pipeline_admissible_ready_units', {**scope, 'priority': 'recent'}) == 2
    assert registry.get_sample_value('omi_batch_pipeline_admissible_ready_units', {**scope, 'priority': 'deep'}) == 0
    assert registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope) == T0 + 10


def test_pl102_partial_capacity_query_failure_keeps_capacity_sample_stale_without_failing_age_refresh(h, monkeypatch):
    put_jobs(h, [('f1', job(h, 'f1', priority=int(Priority.FRESH), compute_decision=unattempted_decision()))])
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry, worker_release='rel', namespace=h.namespace, capacity_sampling=True)
    scope = {'worker_release': 'rel', 'namespace': h.namespace}
    metrics.refresh(h.store, T0 + 10)
    assert registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope) == T0 + 10

    real_sampler = h.store.ready_for_capacity

    def flaky_sampler(priority: int, now: float) -> int:
        if priority == int(Priority.DEEP):
            raise RuntimeError('synthetic deep capacity query timeout')
        return 99

    monkeypatch.setattr(h.store, 'ready_for_capacity', flaky_sampler)
    metrics.refresh(h.store, T0 + 50)
    # Age refresh succeeds, but capacity gauges and capacity_refreshed_at stay at T0 + 10 with no partial 99 written.
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', scope) == T0 + 50
    assert registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope) == T0 + 10
    assert registry.get_sample_value('omi_batch_pipeline_admissible_ready_units', {**scope, 'priority': 'fresh'}) == 1

    monkeypatch.setattr(h.store, 'ready_for_capacity', real_sampler)
    metrics.refresh(h.store, T0 + 60)
    assert registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope) == T0 + 60


@pytest.mark.parametrize('malformed', [None, -1, 1.5, '0', True], ids=['none', 'negative', 'float', 'str', 'bool'])
def test_pl102_malformed_capacity_response_remains_unobserved_never_fresh_zero(h, monkeypatch, malformed):
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry, worker_release='rel', namespace=h.namespace, capacity_sampling=True)
    scope = {'worker_release': 'rel', 'namespace': h.namespace}
    monkeypatch.setattr(
        h.store,
        'ready_for_capacity',
        lambda priority, now: malformed if priority == int(Priority.RECENT) else 0,
    )
    metrics.refresh(h.store, T0 + 10)
    assert not registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope)
    assert registry.get_sample_value('omi_batch_pipeline_admissible_ready_units', {**scope, 'priority': 'fresh'}) is None
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', scope) == T0 + 10
