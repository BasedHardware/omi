"""Immutable-clock urgency under mixed synthetic load; no providers or cloud IO."""

from collections import Counter
from copy import deepcopy

import pytest
from prometheus_client import CollectorRegistry

from config import batch_pipeline_protected_share as protected
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from tests.unit.test_batch_pipeline_pull_multi_lease import SnapshotStore, SnapshotTransaction, owners_in_shard
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline import scheduler as scheduler_module
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.serving import Serving

NOW = 2000000000.0


@pytest.fixture(autouse=True)
def explicit_scheduler_settings(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROTECTED_SHARE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROTECTED_SHARE_PERCENT', '25')
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')


def add(queue, segment, *, owner='owner', capture=None, duration=30, priority=Priority.RECENT):
    work = item(
        segment, owner=owner, capture=NOW - 1800 if capture is None else capture, duration=duration, priority=priority
    )
    queue.enqueue(work, NOW - 1)
    return work


def job():
    return dict(
        capture_at=NOW - 1800,
        duration_seconds=30,
        merge_pending=True,
        available_at=NOW,
        state='ready',
        compute_decision={'outcome': 'unattempted'},
    )


@pytest.mark.parametrize(
    'age,expected', [(0, True), (7199.999, True), (7200, True), (7200.001, False), (-0.001, False)]
)
def test_capture_end_deadline_is_inclusive_and_future_end_fails_closed(age, expected):
    row = job()
    row['capture_at'] = NOW - age - row['duration_seconds']
    assert protected.eligible(row, NOW) is expected


@pytest.mark.parametrize(
    'field,value',
    [
        ('capture_at', None),
        ('capture_at', 0),
        ('capture_at', -1),
        ('capture_at', True),
        ('capture_at', float('nan')),
        ('capture_at', float('inf')),
        ('capture_at', '2000000000'),
        ('duration_seconds', None),
        ('duration_seconds', 0),
        ('duration_seconds', -1),
        ('duration_seconds', True),
        ('duration_seconds', float('nan')),
        ('duration_seconds', float('inf')),
        ('duration_seconds', 7201),
        ('capture_time_trust', 'untrusted'),
        ('capture_time_trust', 'unknown'),
    ],
)
def test_missing_invalid_and_receipt_clocks_never_qualify(field, value):
    row = job()
    row[field] = value
    assert not protected.eligible(row, NOW)
    row.pop(field)
    if field in ('capture_at', 'duration_seconds'):
        assert not protected.eligible(row, NOW)


@pytest.mark.parametrize(
    'value', [None, '', 'invalid', 'tru', '2', 'off', 'false', '0', 'no', 'true', '1', 'on', 'yes', ' YES ']
)
def test_opt_in_and_share_setting_are_read_at_call_time(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('BATCH_PIPELINE_PROTECTED_SHARE_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_PROTECTED_SHARE_ENABLED', value)
    assert protected.enabled() is (value is not None and value.strip().lower() in {'true', '1', 'on', 'yes'})
    for raw, expected in [('1', 1), ('50', 50), ('0', 25), ('51', 25), ('bad', 25)]:
        monkeypatch.setenv('BATCH_PIPELINE_PROTECTED_SHARE_PERCENT', raw)
        assert protected.share_percent() == expected


@pytest.mark.parametrize("multi", [False, True])
def test_mixed_load_fresh_then_protected_and_both_residual_classes_progress(monkeypatch, multi):
    monkeypatch.setenv("BATCH_PULL_MULTI_LEASE_ENABLED", str(multi).lower())
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry=registry)
    store = CountStore()
    queue = Scheduler(store, metrics=metrics)
    for n in range(40):
        add(queue, f'old-recent-{n:03}', capture=NOW - 18000)
        add(queue, f'old-deep-{n:03}', owner='deep', capture=NOW - 86400, priority=Priority.DEEP)
    for n in range(40):
        add(queue, f'protected-{n:03}')
    for n in range(4):
        add(queue, f'fresh-{n}', owner='fresh', capture=NOW - 30, priority=Priority.FRESH)
    leases = queue.pull(NOW, 32)
    names = [lease.item.segment_id for lease in leases]
    assert names[:4] == [f'fresh-{n}' for n in range(4)]
    assert sum(name.startswith('protected-') for name in names) == 7
    assert sum(name.startswith('old-recent-') for name in names) >= 10
    assert sum(name.startswith('old-deep-') for name in names) >= 10
    assert registry.get_sample_value('omi_batch_pipeline_scheduler_leases_total', {'service': 'protected'}) == 7
    assert registry.get_sample_value('omi_batch_pipeline_protected_cohort_leases_total') == 11
    assert registry.get_sample_value('omi_batch_pipeline_protected_cohort_age_seconds_count') == 11
    assert len(names) == len(set(names)) == 32


def test_long_recording_uses_capture_end_and_does_not_change_priority_or_merge_stamp():
    store = MemoryStore()
    queue = Scheduler(store)
    add(queue, 'old', capture=NOW - 86400)
    work = add(queue, 'long', capture=NOW - 9000, duration=7200)
    before = deepcopy(store.rows['jobs', 'long'])
    assert queue.pull(NOW)[0].item.segment_id == 'long'
    after = store.rows['jobs', 'long']
    for field in ('capture_at', 'duration_seconds', 'priority', 'fresh_capture', 'enqueued_at', 'policy'):
        assert after[field] == before[field]
    assert work.priority == Priority.RECENT and not after['fresh_capture']


def test_owner_duration_fairness_is_shared_by_protected_and_residual_turns():
    owners = owners_in_shard(2)
    store = CountStore()
    queue = Scheduler(store)
    for n in range(150):
        for owner, duration in zip(owners, (30, 300)):
            add(queue, f'{owner}-{n:03}', owner=owner, duration=duration)
    seconds = Counter()
    for _ in range(5):
        for lease in queue.pull(NOW, 32):
            seconds[lease.item.owner_id] += lease.item.duration_seconds
    assert set(seconds) == set(owners)
    assert abs(seconds[owners[0]] - seconds[owners[1]]) <= 600


class OrderedDueStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.pages = []

    def due(self, state, now, limit):
        field = 'lease_until' if state == 'leased' else 'available_at'
        self.pages.append((state, limit))
        return [
            key
            for _, key in sorted(
                (row[field], key)
                for (table, key), row in self.rows.items()
                if table == 'jobs' and row['state'] == state and row[field] <= now
            )[:limit]
        ]


def detached_retry(queue, segment, **kwargs):
    work = add(queue, segment, **kwargs)
    lease = queue.pull(NOW)[0]
    assert lease.item.segment_id == segment
    assert queue.fail(segment, lease.token, NOW)
    return work


def test_due_retry_bypasses_oldest_due_stock_and_old_retries_keep_service():
    store = OrderedDueStore()
    queue = Scheduler(store)
    detached_retry(queue, 'eligible')
    for n in range(300):
        store.rows['jobs', f'old-{n:03}'] = {
            **deepcopy(store.rows['jobs', 'eligible']),
            'segment_id': f'old-{n:03}',
            'owner_id': f'old-owner-{n}',
            'owner_key': f'{n:064x}',
            'capture_at': NOW - 86400,
            'available_at': NOW - 10000,
        }
    assert queue.recover(NOW + 100, limit=8) == 7
    assert store.rows['jobs', 'eligible']['state'] == 'ready'
    assert sum(row['state'] == 'ready' for (table, _), row in store.rows.items() if table == 'jobs') == 7
    assert ('retry', 6) in store.pages
    progress = [queue.pull(NOW + 100)[0].item.segment_id for _ in range(4)]
    assert 'eligible' in progress
    assert any(segment.startswith('old-') for segment in progress)


def test_repeated_retries_requeue_and_duplicate_upload_never_restart_capture_budget():
    store = MemoryStore()
    queue = Scheduler(store)
    work = add(queue, 'retry', capture=NOW - 7100 - 30)
    original = deepcopy(store.rows['jobs', 'retry'])
    lease = queue.pull(NOW)[0]
    assert queue.fail('retry', lease.token, NOW)
    queue.recover(NOW + 61)
    assert not queue.enqueue(work, NOW + 61)
    second = queue.pull(NOW + 61)[0]
    assert queue.fail('retry', second.token, NOW + 61)
    queue.recover(NOW + 200)
    assert not protected.eligible(store.rows['jobs', 'retry'], NOW + 200)
    for field in ('capture_at', 'duration_seconds', 'enqueued_at', 'fresh_capture', 'priority'):
        assert store.rows['jobs', 'retry'][field] == original[field]


@pytest.mark.parametrize(
    'hold',
    [
        {'compute_decision': {'outcome': 'held', 'reason': 'allowance_exhausted'}},
        {'compute_decision': {'outcome': 'held', 'reason': 'fair_use'}},
        {'compute_decision': None, 'last_policy_hold': {'reason': 'allowance_exhausted'}},
        {'last_policy_hold': {'reason': 'fair_use'}},
    ],
)
def test_policy_held_rows_cannot_take_reserved_lease_or_discovery(hold):
    store = OrderedDueStore()
    queue = Scheduler(store)
    add(queue, 'old', capture=NOW - 86400)
    add(queue, 'held', capture=NOW - 100)
    add(queue, 'allowed')
    store.rows['jobs', 'held'].update(hold)
    assert queue.pull(NOW)[0].item.segment_id == 'allowed'
    held = deepcopy(store.rows['jobs', 'held'])
    held.update(state='retry', available_at=NOW - 1)
    assert not protected.eligible(held, NOW)


def test_privacy_held_candidate_cannot_consume_reserved_slot():
    class PrivateTransaction(MemoryTransaction):
        def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
            if 'private' in conversation_ids:
                raise BatchPrivacyBlocked('account_deleting')
            return 0

    class PrivateStore(MemoryStore):
        def run(self, body):
            rows = deepcopy(self.rows)
            result = body(PrivateTransaction(rows))
            self.rows = rows
            return result

    store = PrivateStore()
    queue = Scheduler(store)
    add(queue, 'old', capture=NOW - 86400)
    add(queue, 'private', capture=NOW - 100)
    add(queue, 'allowed')
    store.rows['jobs', 'private']['conversation_id'] = 'private'
    add(queue, 'other-allowed', owner='other')
    assert queue.pull(NOW)[0].item.segment_id == 'other-allowed'
    assert store.rows['jobs', 'private']['state'] == 'ready'


def populate_legacy(queue):
    add(queue, 'recent-old', capture=NOW - 20000)
    add(queue, 'recent-new')
    add(queue, 'deep', owner='deep', capture=NOW - 86400, priority=Priority.DEEP)
    add(queue, 'fresh', owner='fresh', capture=NOW - 30, priority=Priority.FRESH)


@pytest.mark.parametrize('value', [None, '', 'invalid', 'off', 'false', '0', 'no'])
def test_unset_invalid_and_off_preserve_legacy_selection_recovery_and_serving_factory(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('BATCH_PIPELINE_PROTECTED_SHARE_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_PROTECTED_SHARE_ENABLED', value)

    def forbidden(*args, **kwargs):
        pytest.fail('legacy mode issued a protected query before index readiness')

    monkeypatch.setattr(MemoryTransaction, 'protected_ready', forbidden)
    store = OrderedDueStore()
    monkeypatch.setattr(store, 'protected_retries', forbidden)
    service = Serving(store)
    first, second = service.queue(), service.queue()
    assert first is not second
    assert first.store is second.store is store
    assert first.pool == second.pool == 'batch'
    assert service.queue('live') is not service.queue('live')
    populate_legacy(first)
    leases = first.pull(NOW, 4)
    assert [lease.item.segment_id for lease in leases] == ['fresh', 'recent-old', 'recent-new', 'deep']
    assert first.fail('recent-new', leases[2].token, NOW)
    # Keep the real maintenance/reconcile -> queue -> recover path. Only the
    # unrelated expiry/allowance/merge sweeps are stubbed, not Scheduler IO.
    monkeypatch.setattr('utils.batch_pipeline.serving.time.time', lambda: NOW + 100)
    monkeypatch.setattr(service.held_dead_letter, 'tick', lambda now: None)
    monkeypatch.setattr(service.projection_held_dead_letter, 'tick', lambda now: None)
    monkeypatch.setattr(service.ready_discovery, 'page', lambda: None)
    monkeypatch.setattr(service, '_drain_ready_page', lambda: None)
    monkeypatch.setattr(service.merge, 'reoffer_marked', lambda drain: None)
    service.allowance_hold_due = float('inf')
    service.reconcile(periodic=True)
    assert store.pages == [('leased', 100), ('retry', 100)]
    assert store.rows['jobs', 'recent-new']['state'] == 'ready'
    assert not any('protected_after' in row for (table, _), row in store.rows.items() if table == 'queues')


def test_mixed_readers_drain_same_links_once_and_rollback_does_not_strand_rows(monkeypatch):
    store = MemoryStore()
    new, old = Scheduler(store), Scheduler(store)
    for n in range(24):
        add(new, f'old-{n:03}', capture=NOW - 20000)
        add(new, f'new-{n:03}')
    leases = []
    for n in range(12):
        monkeypatch.setenv('BATCH_PIPELINE_PROTECTED_SHARE_ENABLED', 'true' if n % 2 == 0 else 'off')
        leases.extend((new if n % 2 == 0 else old).pull(NOW, 4))
    names = [lease.item.segment_id for lease in leases]
    assert len(names) == len(set(names)) == 48
    assert sorted(names) == sorted([f'{kind}-{n:03}' for kind in ('old', 'new') for n in range(24)])
    assert all(row['priority'] in (0, 1, 2) for (table, _), row in store.rows.items() if table == 'jobs')


class CountTransaction(SnapshotTransaction):
    def protected_ready(self, owner_key, priority, now, *, after=None):
        self.counts['protected_queries'] += 1
        rows = super().protected_ready(owner_key, priority, now, after=after)
        self.counts['protected_reads'] += max(1, len(rows))
        return rows


class CountStore(SnapshotStore):
    def run(self, body):
        self.counts['transactions'] += 1
        tx = CountTransaction(self.rows, self.counts)
        result = body(tx)
        self.rows.update(deepcopy(tx.writes))
        assert len(tx.writes) <= 450
        return result


def test_protected_discovery_and_claim_budget_is_independent_of_fifo_depth():
    counts = []
    for depth in (1, 300):
        store = CountStore()
        queue = Scheduler(store)
        for n in range(depth):
            add(queue, f'old-{n:03}', capture=NOW - 20000)
        add(queue, 'eligible')
        store.counts.clear()
        assert queue.pull(NOW)[0].item.segment_id == 'eligible'
        assert store.counts['protected_queries'] == 1
        assert store.counts['protected_reads'] == 1
        assert store.counts['claims'] == 1
        counts.append(store.counts.copy())
    assert counts[0] == counts[1]


def test_retry_discovery_rotates_past_future_due_rows_with_fixed_read_budget():
    store = OrderedDueStore()
    service = Serving(store)
    queue = service.queue()
    detached_retry(queue, 'eligible', capture=NOW - 2000)
    template = deepcopy(store.rows['jobs', 'eligible'])
    for n in range(12):
        store.rows['jobs', f'future-{n:03}'] = {
            **template,
            'segment_id': f'future-{n:03}',
            'capture_at': NOW - n - 100,
            'available_at': NOW + 86400,
        }
    # Keep the ordinary oldest-due page occupied throughout the rotation.
    for n in range(64):
        store.rows['jobs', f'old-{n:03}'] = {
            **template,
            'segment_id': f'old-{n:03}',
            'capture_at': NOW - 86400,
            'available_at': NOW - 10000,
        }
    cycles = 0
    for _ in range(8):
        cycles += 1
        service.queue().recover(NOW + 100, limit=8)
        if store.rows['jobs', 'eligible']['state'] == 'ready':
            break
    assert cycles > 1
    assert store.rows['jobs', 'eligible']['state'] == 'ready'
    assert all(row['state'] == 'retry' for (table, key), row in store.rows.items() if key.startswith('future-'))


def test_metric_vocabulary_is_fixed_and_contains_no_identifiers():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry=registry)
    metrics.record_service('protected', age=7200)
    metrics.record_service('recent')
    metrics.record_service('deep')
    metrics.record_discovery('retry', 100)
    with pytest.raises(ValueError):
        metrics.record_service('owner-id')
    with pytest.raises(ValueError):
        metrics.record_discovery('row-id', 1)
    assert registry.get_sample_value('omi_batch_pipeline_protected_cohort_leases_total') == 1


def test_deadline_is_rechecked_after_discovery_before_lease(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: clock[0])

    class DelayedTransaction(MemoryTransaction):
        def protected_ready(self, *args, **kwargs):
            page = super().protected_ready(*args, **kwargs)
            clock[0] += 2
            return page

    class DelayedStore(MemoryStore):
        def run(self, body):
            rows = deepcopy(self.rows)
            result = body(DelayedTransaction(rows))
            self.rows = rows
            return result

    registry = CollectorRegistry()
    store = DelayedStore()
    queue = Scheduler(store, metrics=QueueMetrics(registry=registry))
    add(queue, 'old', capture=NOW - 20000)
    add(queue, 'expires-during-query', capture=NOW - 7199 - 30)
    assert queue.pull(NOW)[0].item.segment_id == 'old'
    assert registry.get_sample_value('omi_batch_pipeline_protected_cohort_leases_total') == 0


def test_scheduler_accepts_exact_deadline_on_symbolic_clock(monkeypatch):
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: 0.0)
    store = MemoryStore()
    queue = Scheduler(store)
    add(queue, 'old', capture=NOW - 20000)
    add(queue, 'boundary', capture=NOW - 7200 - 30)
    assert queue.pull(NOW)[0].item.segment_id == 'boundary'


def test_protected_budget_bounds_large_owner_ring_and_hold_prefix():
    store = CountStore()
    queue = Scheduler(store)
    for owner in owners_in_shard(40):
        add(queue, f'old-{owner}', owner=owner, capture=NOW - 20000)
        for n in range(9):
            add(queue, f'held-{owner}-{n}', owner=owner)
            store.rows['jobs', f'held-{owner}-{n}']['last_policy_hold'] = {'reason': 'fair_use'}
    store.counts.clear()
    lease = queue.pull(NOW)[0]
    assert lease.item.segment_id.startswith('old-')
    assert store.counts['protected_queries'] <= protected.READY_OWNER_BUDGET
    assert store.counts['protected_reads'] <= protected.READY_OWNER_BUDGET * protected.READY_PAGE_SIZE
    # Includes one ordinary claim after protected discovery exhausts its separate budget.
    assert store.counts['claims'] <= protected.READY_OWNER_BUDGET + 1


def test_retry_discovery_rechecks_hold_race_and_keeps_oldest_due_service():
    class RacedStore(OrderedDueStore):
        def protected_retries(self, *args, **kwargs):
            page = super().protected_retries(*args, **kwargs)
            for row in page:
                self.rows['jobs', row['segment_id']]['compute_decision'] = {
                    'outcome': 'held',
                    'reason': 'fair_use',
                }
            return page

    store = RacedStore()
    queue = Scheduler(store)
    detached_retry(queue, 'eligible')
    for n in range(10):
        store.rows['jobs', f'old-{n:03}'] = {
            **deepcopy(store.rows['jobs', 'eligible']),
            'segment_id': f'old-{n:03}',
            'capture_at': NOW - 86400,
            'available_at': NOW - 10000,
        }
    queue.recover(NOW + 100, limit=8)
    assert store.rows['jobs', 'eligible']['state'] == 'retry'
    assert sum(row['state'] == 'ready' for (table, _), row in store.rows.items() if table == 'jobs') == 6


def test_discovery_metric_counts_replayed_transaction_reads_once_per_attempt():
    class ReplayStore(CountStore):
        replay = False

        def run(self, body):
            if self.replay:
                self.replay = False
                body(CountTransaction(self.rows, self.counts))  # Discard all writes, as an aborted attempt.
            return super().run(body)

    registry = CollectorRegistry()
    store = ReplayStore()
    queue = Scheduler(store, metrics=QueueMetrics(registry=registry))
    add(queue, 'old', capture=NOW - 20000)
    add(queue, 'eligible')
    store.replay = True
    assert queue.pull(NOW)[0].item.segment_id == 'eligible'
    # Each attempt read one candidate and budgeted two predecessor matches.
    assert registry.get_sample_value('omi_batch_pipeline_protected_discovery_reads_sum', {'phase': 'ready'}) == 6


def test_single_residual_class_keeps_batched_drr_with_one_bounded_discovery_transaction():
    store = CountStore()
    queue = Scheduler(store)
    for n in range(40):
        add(queue, f'old-{n:03}', capture=NOW - 86400, priority=Priority.DEEP)
    store.counts.clear()
    leases = queue.pull(NOW, 32)
    assert len(leases) == len({lease.token for lease in leases}) == 32
    assert store.counts['transactions'] == 2  # One protected probe, one full residual batch.
    assert store.counts['claims'] == 2
    assert store.counts['protected_queries'] == 1


def test_single_recent_class_still_receives_its_full_protected_quota():
    store = CountStore()
    queue = Scheduler(store)
    for n in range(40):
        add(queue, f'old-{n:03}', capture=NOW - 86400)
    for n in range(40):
        add(queue, f'cohort-{n:03}')
    leases = queue.pull(NOW, 32)
    assert sum(lease.item.segment_id.startswith('cohort-') for lease in leases) == 8
    assert sum(lease.item.segment_id.startswith('old-') for lease in leases) == 24


def test_missing_input_repair_preserves_expired_capture_deadline():
    store = MemoryStore()
    queue = Scheduler(store)
    add(queue, 'repair', capture=NOW - 7201 - 30)
    lease = queue.pull(NOW)[0]
    assert queue.fail('repair', lease.token, NOW)
    row = store.rows['jobs', 'repair']
    row.update(
        state='quarantined',
        recovery_state='failed_held',
        merge_pending=False,
        artifact_disposition={'state': 'restored'},
    )
    original_clock = (row['capture_at'], row['duration_seconds'])
    store.run(lambda tx: Scheduler.restore_audio_in_transaction(tx, tx.get('jobs', 'repair'), NOW + 10))
    restored = store.rows['jobs', 'repair']
    assert restored['state'] == 'ready'
    assert (restored['capture_at'], restored['duration_seconds']) == original_clock
    assert not protected.eligible(restored, NOW + 10)


def test_serving_factory_preserves_small_pull_share_cadence_and_pool_isolation(monkeypatch):
    store = CountStore()
    service = Serving(store)
    for n in range(8):
        add(service.queue(), f'old-recent-{n}', capture=NOW - 86400)
        add(service.queue(), f'old-deep-{n}', owner='deep', capture=NOW - 86400, priority=Priority.DEEP)
    for n in range(8):
        add(service.queue(), f'cohort-{n}')
    names = [service.queue().pull(NOW)[0].item.segment_id for _ in range(4)]
    assert sum(name.startswith('cohort-') for name in names) == 1
    assert any(name.startswith('old-recent-') for name in names)
    assert any(name.startswith('old-deep-') for name in names)
    assert service.queue('batch') is not service.queue('live')
    with pytest.raises(ValueError, match='pool must'):
        service.queue('invalid')
    monkeypatch.setenv('BATCH_PIPELINE_PROTECTED_SHARE_ENABLED', 'off')
    assert service.queue() is not service.queue()
