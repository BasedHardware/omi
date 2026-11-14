"""Allowance parking/release on the shared sim, Firestore and Postgres matrix."""

from unittest.mock import Mock

import pytest

from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline.allowance_hold import AllowanceHolds
from database.batch_pipeline_allowance_hold import OWNERS, STATE, park
from utils.batch_pipeline.contracts import WorkItem, WorkResult, Priority
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration


@pytest.fixture
def h(store_backend, monkeypatch):
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED', raising=False)
    store_backend.seed_user('owner')
    return store_backend


def enqueue(h, segment='a', capture=1):
    queue = Scheduler(h.store)
    queue.enqueue(WorkItem(segment, h.uid('owner'), capture, f'gs://synthetic/{segment}', 30, Priority.DEEP), 0)
    return queue


def get(h, segment='a'):
    return h.store.run(lambda tx: tx.get('jobs', segment))


def hold(h, segment='a', capture=1, now=2):
    queue = enqueue(h, segment, capture)
    lease = queue.pull(now - 1)[0]
    assert queue.defer(segment, lease.token, now, held_reason='allowance_exhausted', admission_refused=True)
    return queue


def test_held_is_absent_from_retry_pending_and_age_scans_and_retains_audio(h):
    queue = hold(h)
    row = get(h)
    assert row['state'] == STATE and row['attempt'] == 0 and not row['merge_pending']
    assert row['audio_uri'] == 'gs://synthetic/a'
    assert h.store.due('retry', 10000, 100) == []
    assert h.store.oldest(2, ready_only=False) is None
    assert h.store.run(lambda tx: tx.first_pending(owner_key(h.uid('owner')))) is None
    assert queue.recover(10000) == 0
    assert get(h) == row


def test_owner_checked_once_then_generation_releases_oldest_first(h):
    hold(h, 'z', capture=1)
    hold(h, 'b', capture=2, now=4)
    current = ['month1', False]
    checks = []

    def entitlement(uid, now, previous):
        if current[0] != previous:
            checks.append(current[0])
        return tuple(current)

    service = AllowanceHolds(h.store, entitlement)
    assert service.tick(10) == 0
    assert service.tick(400) == 0
    assert checks == ['month1']
    current[:] = ['month2', True]
    assert service.tick(800, page_size=1) == 1
    # New controller object resumes the durable page without another entitlement evaluation.
    assert AllowanceHolds(h.store, Mock(side_effect=AssertionError('rechecked page'))).tick(801, page_size=1) == 1
    assert get(h, 'z')['state'] == get(h, 'b')['state'] == 'ready'
    qkey = f'2_{owner_key(h.uid("owner"))}'
    queue = h.store.run(lambda tx: tx.get('queues', qkey))
    assert queue['head'] == 'z' and get(h, 'z')['next'] == 'b'
    assert get(h, 'z')['compute_decision']['outcome'] == 'unattempted'


def test_held_head_does_not_block_later_entitled_result(h):
    queue = hold(h)
    enqueue(h, 'later', capture=2)
    lease = queue.pull(4)[0]
    assert queue.complete(WorkResult('later', 'gs://synthetic/result'), lease.token, 5)
    assert OrderedMerge(h.store).commit_next(h.uid('owner'), 6)['segment_id'] == 'later'
    assert get(h)['state'] == STATE


@pytest.mark.parametrize('held_fresh', [False, True], ids=['backlog-held', 'fresh-stamped-held'])
@pytest.mark.parametrize('transactional', [False, True], ids=['probe', 'transactional'])
def test_parking_forty_allowance_retries_reaches_ready_fresh_in_capture_order(
    h, monkeypatch, held_fresh, transactional
):
    """The migration's transition removes policy stock from both pending selectors."""
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', str(transactional).lower())
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED', 'off')
    uid = h.uid('owner')
    for index in range(40):
        segment = f'held-{index:02d}'
        enqueue(h, segment, capture=index + 1)

        def legacy_retry(tx):
            job = tx.get('jobs', segment)
            job.update(
                state='retry',
                fresh_capture=held_fresh,
                available_at=0,
                compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted'},
            )
            tx.put('jobs', segment, job)

        h.store.run(legacy_retry)

    for segment, capture, fresh in [('provider-backlog', 0, False)] + [(f'fresh-{i}', 41 + i, True) for i in range(3)]:
        enqueue(h, segment, capture=capture)

        def ready(tx):
            job = tx.get('jobs', segment)
            job.update(
                state='result_ready',
                fresh_capture=fresh,
                ready_at=100,
                stt_route={'stt_route': 'provider'},
                result=f'gs://synthetic/{segment}-result',
            )
            tx.put('jobs', segment, job)

        h.store.run(ready)

    for index in range(40):
        segment = f'held-{index:02d}'
        assert h.store.run(lambda tx: park(tx, tx.get('jobs', segment), 100))
        assert get(h, segment)['state'] == STATE
        assert get(h, segment)['merge_pending'] is False
    assert h.store.fresh_pending(owner_key(uid), 32)[0]['segment_id'] == 'fresh-0'
    merge = OrderedMerge(h.store, head_wait_seconds=0, catch_up_depth=10)
    entries = [merge.commit_next(uid, 101 + i) for i in range(3)]
    assert [entry['segment_id'] for entry in entries] == ['fresh-0', 'fresh-1', 'fresh-2']
    assert [entry['log_sequence'] for entry in entries] == [1, 2, 3]
    assert entries[1]['previous_segment_id'] == 'fresh-0'
    assert entries[2]['previous_segment_id'] == 'fresh-1'
    assert merge.commit_next(uid, 105) is None
    assert get(h, 'provider-backlog')['state'] == 'result_ready'
    assert not h.store.run(lambda tx: tx.get('results', 'provider-backlog'))


@pytest.mark.parametrize('reason', [None, 'fair_use_restricted', 'budget_exhausted'])
def test_other_refusals_keep_recovery(h, reason):
    queue = enqueue(h)
    lease = queue.pull(1)[0]
    assert queue.defer('a', lease.token, 2, held_reason=reason, admission_refused=True)
    assert get(h)['state'] == 'retry'
    assert queue.recover(100) == 1
    assert get(h)['state'] == 'ready'


@pytest.mark.parametrize('decision', [None, {'outcome': 'allowed', 'reason': 'funded'}])
def test_sticky_hold_does_not_park_a_decisionless_or_allowed_retry(h, decision):
    queue = enqueue(h)
    lease = queue.pull(1)[0]
    assert queue.defer('a', lease.token, 2)

    def change(tx):
        row = tx.get('jobs', 'a')
        row['compute_decision'] = decision
        row['last_policy_hold'] = {'reason': 'allowance_exhausted'}
        tx.put('jobs', 'a', row)

    h.store.run(change)
    assert queue.recover(100) == 1
    assert get(h)['state'] == 'ready'


def test_real_worker_failure_keeps_retry_budget_and_recovery(h):
    queue = enqueue(h)
    lease = queue.pull(1)[0]
    assert queue.fail('a', lease.token, 2)
    assert get(h)['state'] == 'retry' and get(h)['attempt'] == 1
    assert queue.recover(100) == 1
    assert queue.pull(101)[0].attempt == 2


def test_old_worker_retry_is_parked_by_new_recovery_and_migration_is_idempotent(h, monkeypatch):
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    queue = hold(h)
    assert get(h)['state'] == 'retry'
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    assert queue.recover(100) == 1
    assert get(h)['state'] == STATE
    assert not h.store.run(lambda tx: park(tx, tx.get('jobs', 'a'), 101))
    key = owner_key(h.uid('owner'))
    assert h.store.run(lambda tx: tx.get(OWNERS, key))['revision'] == 1


def test_kill_switch_returns_old_retry_semantics(h, monkeypatch):
    queue = hold(h)
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    assert AllowanceHolds(h.store, Mock(side_effect=AssertionError('must not authorize'))).tick(5) == 1
    assert get(h)['state'] == 'retry' and get(h)['merge_pending']
    assert queue.recover(6) == 1


def test_new_worker_hold_is_safe_under_legacy_recovery_then_upgrade_releases(h, monkeypatch):
    queue = hold(h)
    before = get(h)
    # With parking disabled, recover uses exactly the pre-change leased/retry
    # discovery and transition path. It must not steal a new worker's hold.
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    assert queue.recover(10000) == 0
    assert get(h) == before
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    assert AllowanceHolds(h.store, lambda *args: ('new-plan', True)).tick(10001) == 1
    assert queue.pull(10002)[0].item.segment_id == 'a'


def test_entitlement_read_failure_retries_without_acknowledging_generation(h):
    hold(h)
    resolver = Mock(side_effect=[RuntimeError('unavailable'), ('new-period', True)])
    service = AllowanceHolds(h.store, resolver)
    assert service.tick(10) == 0
    mark = h.store.run(lambda tx: tx.get(OWNERS, owner_key(h.uid('owner'))))
    assert 'generation' not in mark and get(h)['state'] == STATE
    assert service.tick(11) == 0 and resolver.call_count == 1
    assert service.tick(131) == 1 and resolver.call_count == 2


def test_historical_retry_clock_leaves_live_index_and_rollback_restores_it(h, monkeypatch):
    queue = enqueue(h)
    lease = queue.pull(1)[0]
    assert queue.fail('a', lease.token, 2)
    assert queue.recover(100) == 1
    lease = queue.pull(101)[0]
    assert queue.defer('a', lease.token, 102, held_reason='allowance_exhausted')
    assert 'retry_started_at' not in get(h)
    assert get(h)['allowance_retry_started_at'] == 2
    assert h.store.oldest_retry(2) is None
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    assert AllowanceHolds(h.store, Mock()).tick(103) == 1
    assert get(h)['retry_started_at'] == 2


def test_new_refusal_during_generation_drain_is_not_released_again(h):
    queue = hold(h, 'a', capture=1)
    hold(h, 'b', capture=2, now=4)
    service = AllowanceHolds(h.store, lambda *args: ('generation', True))
    assert service.tick(10, page_size=1) == 1
    lease = queue.pull(11)[0]
    assert queue.defer('a', lease.token, 12, held_reason='allowance_exhausted')
    assert service.tick(13, page_size=1) == 1
    assert service.tick(14, page_size=1) == 0
    assert service.tick(400, page_size=1) == 0
    assert get(h)['state'] == STATE


def test_privacy_fence_prevents_release_without_resurrecting_work(h):
    hold(h)
    h.customer.block_privacy(h.uid('owner'))
    service = AllowanceHolds(h.store, lambda *args: ('generation', True))
    assert service.tick(10) == 0
    assert get(h)['state'] == 'privacy_blocked'
    assert not get(h)['merge_pending']
    assert h.store.allowance_owners(10000, 100) == []


def test_migration_count_only_resume_and_cas(h, monkeypatch):
    if h.name != 'emulator':
        pytest.skip('Firestore migration queries require the actual emulator')
    from database.batch_pipeline_allowance_migration import apply_page, counts

    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    hold(h, 'a')
    hold(h, 'b', capture=2, now=4)
    queue = hold(h, 'c', capture=3, now=6)
    assert counts(h.store) == {'retry': 3, 'allowance_retry': 3, 'policy_held': 0}
    assert get(h)['state'] == 'retry'  # Dry-run cannot mutate rows.
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    assert apply_page(h.store, 10, size=1)['parked'] == 1
    # The scheduler can race the migration's next page. Its state CAS and the
    # migration predicate must neither append nor count a parked row twice.
    assert queue.recover(100) == 2
    assert apply_page(h.store, 101, size=1)['complete']
    assert counts(h.store) == {'retry': 0, 'allowance_retry': 0, 'policy_held': 3}
    assert apply_page(h.store, 102, size=1)['parked'] == 0


def test_migration_failure_preserves_checkpoint(h, monkeypatch):
    if h.name != 'emulator':
        pytest.skip('Firestore migration queries require the actual emulator')
    from database.batch_pipeline_allowance_migration import KEY, apply_page

    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    hold(h, 'a')
    hold(h, 'b', capture=2, now=4)
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    assert apply_page(h.store, 10, size=1)['parked'] == 1
    marker = h.store.client.collection(f'{h.namespace}_migrations').document(KEY)
    before = marker.get().to_dict()
    original = h.store.run
    monkeypatch.setattr(h.store, 'run', Mock(side_effect=RuntimeError('injected failure')))
    with pytest.raises(RuntimeError, match='injected failure'):
        apply_page(h.store, 11, size=1)
    assert marker.get().to_dict() == before
    monkeypatch.setattr(h.store, 'run', original)
    assert apply_page(h.store, 12, size=1)['parked'] == 1
