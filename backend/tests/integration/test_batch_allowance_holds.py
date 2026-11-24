"""Allowance parking/release on the shared sim, Firestore and Postgres matrix."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from threading import Barrier, Lock
import time

import pytest
from google.api_core.exceptions import Aborted, NotFound

from testing.store_fixtures import store_backend  # noqa: F401
from database import batch_pipeline_allowance_migration as migration
from database import batch_pipeline_store as store_module
from database.batch_pipeline_allowance_migration import KEY, apply_page, counts
from database.batch_pipeline_intake import admit
from database.outbox import Claim, OutboxKind
from database.outbox_provider_stt import TABLE, FirestoreProviderSttOutbox
from tests.unit.test_batch_provider_stt import Artifacts, JA, Vendor, stage
from utils.batch_pipeline.provider_stt_admission import enqueue_in_transaction, resolve_route
from utils.conversations.transcribing_hold import _admission
from config.batch_pipeline import scheduler_control_key
from config.policy import BatchUnitPolicy
from utils.batch_pipeline.allowance_hold import AllowanceHolds
from utils.batch_pipeline.input_retention import LIFECYCLE_DAYS, STAGING_BUCKET, staged_enqueue
from database.batch_pipeline_allowance_hold import IntakeRefusal, OWNERS, STATE, park
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, WorkResult, Priority
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration


@pytest.fixture
def h(store_backend, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_ALLOWANCE_INTAKE_PARK_ENABLED', raising=False)
    store_backend.seed_user('owner')
    return store_backend


def enqueue(h, segment='a', capture=1, owner='owner'):
    queue = Scheduler(h.store)
    queue.enqueue(WorkItem(segment, h.uid(owner), capture, f'gs://synthetic/{segment}', 30, Priority.DEEP), 0)
    return queue


def get(h, segment='a'):
    return h.store.run(lambda tx: tx.get('jobs', segment))


def hold(h, segment='a', capture=1, now=2, owner='owner'):
    queue = enqueue(h, segment, capture, owner)
    lease = queue.pull(now - 1)[0]
    assert queue.defer(segment, lease.token, now, held_reason='allowance_exhausted', admission_refused=True)
    return queue


def admit_intake(h, now, refusal, segments=('z', 'a')):
    uid = h.uid('owner')
    items = [
        WorkItem(
            segment,
            uid,
            now - 600 + offset,
            f'gs://synthetic/{segment}',
            30,
            Priority.DEEP,
            privacy_generation=0,
            requires_compute_admission=True,
        )
        for offset, segment in enumerate(segments)
    ]
    binding = ProjectionBinding(uid, 'bp_intake', 'content', segments)
    return admit(
        h.store,
        items,
        binding,
        now,
        namespace=h.namespace,
        policy=BatchUnitPolicy(batch_enabled=True),
        intake={'owner_id': uid, 'lane': 'backfill', 'segment_ids': list(segments)},
        intake_refusal=refusal,
    )


def test_intake_parks_before_queueing_and_releases_in_capture_order(h):
    now = time.time()
    refusal = IntakeRefusal(now, (None, None))
    key = owner_key(h.uid('owner'))
    receipt = admit_intake(h, now, refusal)
    assert admit_intake(h, now, refusal) == receipt
    owner = h.store.run(lambda tx: tx.get(OWNERS, key))
    assert owner['held_count'] == owner['revision'] == 2 and owner['active']

    for segment in ('z', 'a'):
        row = get(h, segment)
        assert row['state'] == STATE and row['allowance_held_at'] == now
        assert row['compute_decision'] == {'outcome': 'held', 'reason': 'allowance_exhausted', 'at': now}
        assert row['last_policy_hold'] == {'reason': 'allowance_exhausted', 'at': now}
        assert not row['merge_pending'] and not row['token'] and not row['lease_until']
        assert row['next'] == '' and row['attempt'] == 0
        assert 'retry_started_at' not in row and 'admission_refusals' not in row

    queue = Scheduler(h.store)
    assert h.store.run(lambda tx: (tx.first_pending(key), tx.fresh_first_pending(key))) == (None, None)
    assert not h.store.run(lambda tx: tx.get('queues', f'2_{key}'))
    # Frozen GPU recovery discovers only leased/retry rows, and pull follows ready owner queues.
    for state in ('leased', 'retry'):
        assert h.store.due(state, now + 10000, 100) == []
    assert queue.pull(now + 1) == []
    assert h.store.oldest(2) is None

    current = ['exhausted', False]
    service = AllowanceHolds(h.store, lambda *args: tuple(current))
    assert service.tick(now + 2) == 0
    current[:] = ['upgraded', True]
    assert service.tick(now + 400, page_size=1) == 1
    assert service.tick(now + 401, page_size=1) == 1
    assert service.tick(now + 402, page_size=1) == 0
    assert [lease.item.segment_id for lease in queue.pull(now + 403, limit=2)] == ['z', 'a']
    for segment in ('z', 'a'):
        row = get(h, segment)
        assert row['compute_decision'] == {'outcome': 'unattempted'} and not row.get('compute_admission_token')
    owner = h.store.run(lambda tx: tx.get(OWNERS, key))
    assert owner['held_count'] == 0 and not owner['active']


def test_probe_crossing_owner_release_falls_back_to_worker(h):
    now = time.time()
    key = owner_key(h.uid('owner'))
    h.store.run(
        lambda tx: tx.put(
            OWNERS,
            key,
            {'owner_id': h.uid('owner'), 'owner_key': key, 'generation': 'upgraded', 'cutoff': now},
        )
    )
    admit_intake(h, now, IntakeRefusal(now, (None, None)), segments=('z',))
    assert get(h, 'z')['state'] == 'ready'
    assert 'held_count' not in h.store.run(lambda tx: tx.get(OWNERS, key))


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


@pytest.mark.parametrize('concurrency', [1, 4])
def test_migration_count_only_resume_and_cas(h, monkeypatch, concurrency):
    if h.name != 'emulator':
        pytest.skip('Firestore migration queries require the actual emulator')
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    hold(h, 'a')
    hold(h, 'b', capture=2, now=4)
    queue = hold(h, 'c', capture=3, now=6)
    assert counts(h.store) == {'retry': 3, 'allowance_retry': 3, 'policy_held': 0}
    assert get(h)['state'] == 'retry'  # Dry-run cannot mutate rows.
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    assert apply_page(h.store, 10, size=1, concurrency=concurrency)['parked'] == 1
    # The scheduler can race the migration's next page. Its state CAS and the
    # migration predicate must neither append nor count a parked row twice.
    assert queue.recover(100) == 2
    assert apply_page(h.store, 101, size=1, concurrency=concurrency)['complete']
    assert counts(h.store) == {'retry': 0, 'allowance_retry': 0, 'policy_held': 3}
    assert apply_page(h.store, 102, size=1, concurrency=concurrency)['parked'] == 0


@pytest.mark.parametrize('concurrency', [1, 4])
def test_migration_failure_preserves_checkpoint(h, monkeypatch, concurrency):
    if h.name != 'emulator':
        pytest.skip('Firestore migration queries require the actual emulator')
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    hold(h, 'a')
    hold(h, 'b', capture=2, now=4)
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    assert apply_page(h.store, 10, size=1, concurrency=concurrency)['parked'] == 1
    marker = h.store.client.collection(f'{h.namespace}_migrations').document(KEY)
    before = marker.get().to_dict()
    original = h.store.run
    monkeypatch.setattr(h.store, 'run', Mock(side_effect=RuntimeError('injected failure')))
    with pytest.raises(RuntimeError, match='injected failure'):
        apply_page(h.store, 11, size=1, concurrency=concurrency)
    assert marker.get().to_dict() == before
    monkeypatch.setattr(h.store, 'run', original)
    assert apply_page(h.store, 12, size=1, concurrency=concurrency)['parked'] == 1


def test_migration_parallel_commit_fences_and_stale_page_replay(h, monkeypatch):
    if h.name != 'emulator':
        pytest.skip('Firestore migration requires actual transaction commits')
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    h.seed_user('other')
    h.seed_user('blocked')
    for index, (key, owner) in enumerate([('a', 'owner'), ('b', 'other'), ('c', 'owner'), ('d', 'blocked')]):
        hold(h, key, capture=index + 1, now=index * 2 + 2, owner=owner)
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    # Capture exactly the discovery hints a driver could have seen before a crash.
    rows = list(migration.candidates(h.store).order_by('__name__').limit(100).select(['owner_key']).stream())
    h.customer.block_privacy(h.uid('blocked'))  # Fresh fence after discovery.
    barrier = Barrier(2, timeout=10)
    active, seen = set(), []
    lock = Lock()
    original = h.store.run
    marker = h.store.client.collection(f'{h.namespace}_migrations').document(migration.KEY)

    def run(body, **options):
        identity = []

        def wrapped(tx):
            result = body(tx)
            if result:
                job = next(value for (table, _), value in tx.writes.items() if table == 'jobs')
                owner = job['owner_key']
                identity.append(owner)
                with lock:
                    assert owner not in active
                    active.add(owner)
                    seen.append(job['segment_id'])
                if job['segment_id'] in ('a', 'b'):
                    barrier.wait()
                assert not marker.get().exists
            return result

        try:
            return original(wrapped, **options)
        finally:
            if identity:
                with lock:
                    active.remove(identity[0])

    monkeypatch.setattr(h.store, 'run', run)
    report = migration.apply_page(h.store, 20, concurrency=2)
    assert report == {'examined': 4, 'parked': 3, 'fenced': 1, 'complete': True}
    assert seen.index('a') < seen.index('c')
    monkeypatch.setattr(h.store, 'run', original)
    before = {key: get(h, key) for key in ('a', 'b', 'c', 'd')}
    owners = h.store.client.collection(f'{h.namespace}_allowance_holds')
    marks = {label: owners.document(owner_key(h.uid(label))).get().to_dict() for label in ('owner', 'other')}
    # Re-examine already parked rows from the stale page: zero new holds/writes.
    assert migration._apply_rows(h.store, rows, 21, 4, migration.RowRateLimiter(50)) == (0, 1)
    assert {key: get(h, key) for key in before} == before
    assert {label: owners.document(owner_key(h.uid(label))).get().to_dict() for label in marks} == marks
    assert marks['owner']['held_count'] == 2 and marks['other']['held_count'] == 1
    assert get(h, 'd')['state'] == 'retry'


@pytest.mark.parametrize('retry_kind', ['outer_read', 'sdk_commit'])
def test_migration_sdk_retry_is_rate_limited(h, monkeypatch, retry_kind):
    if h.name != 'emulator':
        pytest.skip('Actual Firestore SDK transaction retry required')
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    hold(h)
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    limiter = migration.RowRateLimiter(50)
    api = h.store.client._firestore_api
    begin = Mock(wraps=api.begin_transaction)
    monkeypatch.setattr(api, 'begin_transaction', begin)
    original_acquire = limiter.acquire
    permits = []

    def permit(stopped):
        assert begin.call_count == len(permits)  # Permit must precede BeginTransaction.
        permits.append(True)
        original_acquire(stopped)

    acquire = Mock(side_effect=permit)
    monkeypatch.setattr(limiter, 'acquire', acquire)
    attempts = []
    original = h.store.run
    monkeypatch.setattr(store_module, 'contention_retry_enabled', lambda: retry_kind == 'outer_read')
    if retry_kind == 'sdk_commit':
        commit = api.commit
        aborted = []

        def commit_after_abort(*args, **kwargs):
            if not aborted:
                aborted.append(True)
                # A real Aborted response releases the attempt's locks. Model
                # that server-side effect before injecting the SDK response.
                request = kwargs['request']
                api.rollback(
                    request={'database': request['database'], 'transaction': request['transaction']},
                    metadata=kwargs.get('metadata', ()),
                )
                raise Aborted('synthetic commit abort')
            return commit(*args, **kwargs)

        monkeypatch.setattr(api, 'commit', commit_after_abort)

    def run(body, **options):
        def retry_once(tx):
            result = body(tx)
            attempts.append(True)
            if len(attempts) == 1 and retry_kind == 'outer_read':
                raise Aborted('synthetic abort before flush')
            return result

        return original(retry_once, **options)

    monkeypatch.setattr(h.store, 'run', run)
    assert migration.apply_page(h.store, 10, concurrency=2, rate_limiter=limiter)['parked'] == 1
    assert len(attempts) == acquire.call_count == 2
    monkeypatch.setattr(h.store, 'run', original)
    assert get(h)['state'] == STATE
    assert h.store.run(lambda tx: tx.get(OWNERS, owner_key(h.uid('owner'))))['held_count'] == 1


@pytest.mark.parametrize('concurrency,row_reads', [(1, 5), (2, 4)])
def test_migration_rpc_envelope_keeps_fences_and_batches_only_job_owner(h, monkeypatch, concurrency, row_reads):
    if h.name != 'emulator':
        pytest.skip('Measure actual SDK RPCs against loopback Firestore')
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    hold(h)
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_generation_memo":0,"privacy_negative_lookup_cache":0}')
    api = h.store.client._firestore_api
    calls = {}
    for name in ('begin_transaction', 'batch_get_documents', 'commit', 'run_query'):
        calls[name] = Mock(wraps=getattr(api, name))
        monkeypatch.setattr(api, name, calls[name])
    assert apply_page(h.store, 10, concurrency=concurrency)['parked'] == 1
    # Page overhead: initial progress get + query + begin/get/commit checkpoint.
    assert calls['begin_transaction'].call_count == 2
    assert calls['batch_get_documents'].call_count == row_reads + 2
    assert calls['commit'].call_count == 2
    assert calls['run_query'].call_count == 1


def admit_provider(h, segment='provider-unit', now=100, route=JA, *, audio_uri=None):
    uid = h.uid('owner')
    item = WorkItem(
        segment, uid, now - 10, audio_uri or f'gs://synthetic/{segment}', 5, Priority.FRESH, privacy_generation=0
    )

    def enqueue_provider(tx, item, now, *, policy):
        return enqueue_in_transaction(tx, item, now, route=route, policy=policy)

    binding = ProjectionBinding(uid, f'bp_{segment}', f'content-{segment}', (segment,), language='ja')
    assert (
        admit(
            h.store,
            [item],
            binding,
            now,
            namespace=h.namespace,
            policy=BatchUnitPolicy(batch_enabled=True),
            enqueue=enqueue_provider,
        )['outcome']
        == 'batch'
    )

    def claim_legacy_row(tx):
        job = tx.get('jobs', segment)
        token = FirestoreProviderSttOutbox.reopen_in_transaction(tx, job, now)
        row = tx.get(TABLE, segment)
        # Represents today's deferred stock on its regular recheck after the claim.
        row.update(deferred_reason='not_due', lease_token='old-lease', lease_until=now + 1800, attempts=4)
        tx.put(TABLE, segment, row)
        return Claim(OutboxKind.PROVIDER_STT, segment, 'old-lease', token, 4, now + 1800, job['owner_id'], {}, None)

    return h.store.run(claim_legacy_row)


@pytest.mark.parametrize('second_check', [False, True])
@pytest.mark.parametrize('release_mode', ['grant', 'rollback', 'revocation'])
def test_provider_b08_replay(h, monkeypatch, second_check, release_mode):
    monkeypatch.setenv('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', 'true')
    claim = admit_provider(h)
    segment = claim.row_id
    owner = owner_key(claim.owner_id)
    artifacts, vendor = Artifacts(), Vendor()
    denial = (False, 'allowance_exhausted')
    allowed = Mock(side_effect=[True, denial] if second_check else [denial])
    assert (
        stage(h.store, artifacts, vendor, allowed=allowed, now=125).run(segment, claim=claim).reason == 'allowance_held'
    )
    held = get(h, segment)
    assert (held['state'], held['merge_pending']) == (STATE, False)
    assert held['compute_decision'] == {'outcome': 'held', 'reason': 'allowance_exhausted', 'at': 125}
    assert held['audio_uri'] == f'gs://synthetic/{segment}' and held['enqueued_at'] == 100
    assert _admission([held], 125, 300) == 'allowance_held'
    assert h.store.run(lambda tx: tx.get(TABLE, segment))['closed_reason'] == 'allowance_held'
    assert h.store.allowance_owners(125, 20) == [owner]
    assert h.store.allowance_page(owner, None, 100) == [segment]
    assert artifacts.fetches == int(second_check) and vendor.calls == 0
    assert h.store.run(lambda tx: tx.get(OWNERS, owner))['held_count'] == 1

    def gpu_state(tx):
        return tx.get('control', scheduler_control_key(owner)), tx.get('queues', f'{int(Priority.FRESH)}_{owner}')

    def wake(row, token):
        # A wake must observe the released job and its outbox after commit.
        assert get(h, row)['state'] == 'provider_pending'
        assert h.store.run(lambda tx: tx.get(TABLE, row))['task_token'] == token
        wakes.append((row, token))

    gpu_before = h.store.run(gpu_state)
    wakes = []
    controller = AllowanceHolds(h.store, lambda *_: ('granted', True), provider_wake=wake)
    if release_mode == 'rollback':
        monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    if release_mode == 'revocation':
        h.customer.block_privacy(claim.owner_id)
        assert controller.tick(150) == 0
        assert get(h, segment)['state'] == 'privacy_blocked'
        assert h.store.run(lambda tx: tx.get(TABLE, segment))['state'] == 'closed'
        assert h.store.run(lambda tx: tx.get(OWNERS, owner))['held_count'] == 0
        assert wakes == []
        return

    assert controller.tick(150) == 1
    assert controller.tick(151) == 0
    assert h.store.run(gpu_state) == gpu_before
    assert h.store.run(lambda tx: tx.get(OWNERS, owner))['held_count'] == 0
    assert get(h, segment)['compute_decision'] == {'outcome': 'unattempted'}
    assert get(h, segment)['merge_pending'] is True
    reopened = h.store.run(lambda tx: tx.get(TABLE, segment))
    token = reopened['task_token']
    assert wakes == [(segment, token)] and token != claim.wake_token
    assert reopened['state'] == 'open' and reopened['due_at'] == reopened['woken_at'] == 150
    assert reopened['lease_token'] is None and reopened['lease_until'] == 0

    worker = stage(h.store, artifacts, vendor, now=151)
    assert worker.run(segment, claim=claim).reason == 'superseded'
    assert vendor.calls == 0

    current = claim_provider_release(h, claim)
    assert worker.run(segment, claim=current).reason == 'processed'
    assert worker.run(segment, claim=current).reason == 'superseded'
    assert vendor.calls == 1
    assert len(get(h, segment)['provider_attempts']) == 1


def claim_provider_release(h, claim):
    def claim_release(tx):
        row = tx.get(TABLE, claim.row_id)
        row.update(lease_token='release-lease', lease_until=row['due_at'] + 1800)
        tx.put(TABLE, claim.row_id, row)
        return Claim(
            OutboxKind.PROVIDER_STT,
            claim.row_id,
            row['lease_token'],
            row['task_token'],
            1,
            row['lease_until'],
            claim.owner_id,
            {'segment_id': claim.row_id},
            None,
        )

    return h.store.run(claim_release)


def test_provider_parked_older_unit_rejoins_merge_after_later_byok(h, monkeypatch):
    monkeypatch.setenv('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', 'true')
    old = admit_provider(h, 'older')
    later = admit_provider(h, 'byok', now=110, route=resolve_route('ja', byok=True))
    artifacts, vendor = Artifacts(), Vendor()
    denied = Mock(return_value=(False, 'allowance_exhausted'))
    worker = stage(h.store, artifacts, vendor, allowed=denied, now=130)
    assert worker.run(old.row_id, claim=old).reason == 'allowance_held'
    assert worker.run(later.row_id, claim=later).reason == 'processed'
    assert denied.call_count == 1 and vendor.calls == 1

    merge = OrderedMerge(h.store)
    first = merge.commit_next(old.owner_id, 131)
    assert first['segment_id'] == later.row_id
    controller = AllowanceHolds(h.store, lambda *_: ('granted', True), provider_wake=Mock())
    assert controller.tick(150) == 1
    assert (
        stage(h.store, artifacts, vendor, now=151).run(old.row_id, claim=claim_provider_release(h, old)).reason
        == 'processed'
    )
    second = merge.commit_next(old.owner_id, 152)
    assert second['segment_id'] == old.row_id
    assert second['log_sequence'] == first['log_sequence'] + 1


@pytest.mark.parametrize(
    'changes,denial',
    [
        ({'provider_intent': {'settled_at': 120}}, 'allowance_exhausted'),
        ({'provider_attempts': [{'attempt': 1}]}, 'allowance_exhausted'),
        ({'result': {'result_uri': 'synthetic'}}, 'allowance_exhausted'),
        ({}, 'budget_exhausted'),
        ({}, 'allowance_unavailable'),
    ],
)
def test_provider_funding_defers_without_parking_ineligible_rows(h, monkeypatch, changes, denial):
    monkeypatch.setenv('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', 'true')
    claim = admit_provider(h)
    segment = claim.row_id
    h.store.run(lambda tx: tx.put('jobs', segment, {**tx.get('jobs', segment), **changes}))
    artifacts, vendor = Artifacts(), Vendor()
    worker = stage(h.store, artifacts, vendor, allowed=lambda *_: (False, denial), now=125)
    assert worker.run(segment, claim=claim).outcome == 'deferred'
    assert get(h, segment)['state'] == 'provider_pending'
    assert h.store.run(lambda tx: tx.get(TABLE, segment))['state'] == 'open'
    assert h.store.allowance_owners(125, 20) == []
    assert artifacts.fetches == vendor.calls == 0


def test_provider_allowance_release_can_recover_before_commit_and_after_wake_loss(h, monkeypatch):
    monkeypatch.setenv('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', 'true')
    claim = admit_provider(h)
    segment = claim.row_id
    worker = stage(h.store, Artifacts(), Vendor(), allowed=lambda *_: (False, 'allowance_exhausted'), now=125)
    assert worker.run(segment, claim=claim).reason == 'allowance_held'
    wake = Mock(side_effect=RuntimeError('injected lost wake'))
    controller = AllowanceHolds(h.store, lambda *_: ('granted', True), provider_wake=wake)
    reopen = FirestoreProviderSttOutbox.reopen_in_transaction

    def fail_before_commit(tx, job, now):
        reopen(tx, job, now)
        raise RuntimeError('injected failure before commit')

    with monkeypatch.context() as patch:
        patch.setattr(FirestoreProviderSttOutbox, 'reopen_in_transaction', staticmethod(fail_before_commit))
        assert controller.tick(150) == 0
    assert get(h, segment)['state'] == STATE
    assert h.store.run(lambda tx: tx.get(TABLE, segment))['task_token'] == claim.wake_token
    wake.assert_not_called()

    assert controller.tick(271) == 1
    row = h.store.run(lambda tx: tx.get(TABLE, segment))
    assert row['state'] == 'open' and row['task_token'] != claim.wake_token
    wake.assert_called_once_with(segment, row['task_token'])
    assert controller.tick(272) == 0
    if h.name == 'emulator':
        rewakes = []
        outbox = FirestoreProviderSttOutbox(
            h.store.client,
            privacy_blocked=lambda *_: False,
            collection=f'{h.namespace}_{TABLE}',
            create_wake=lambda *args: rewakes.append(args),
        )
        assert outbox.sweep(now=900).rewoken == 1
        assert len(rewakes) == 1 and rewakes[0][0] == segment


def test_provider_writer_defaults_off(h, monkeypatch):
    monkeypatch.delenv('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', raising=False)
    claim = admit_provider(h)
    stage_runner = stage(h.store, Artifacts(), Vendor(), allowed=lambda *_: (False, 'allowance_exhausted'), now=125)
    assert stage_runner.run(claim.row_id, claim=claim).outcome == 'deferred'
    assert get(h, claim.row_id)['state'] == 'provider_pending'
    assert h.store.allowance_owners(125, 20) == []


def test_provider_allowance_does_not_extend_staged_audio_lifetime(h, monkeypatch):
    monkeypatch.setenv('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', 'true')
    uri = f'gs://{STAGING_BUCKET}/synthetic/expired.wav'
    claim = admit_provider(h, audio_uri=uri)
    segment = claim.row_id
    worker = stage(h.store, Artifacts(), Vendor(), allowed=lambda *_: (False, 'allowance_exhausted'), now=125)
    assert worker.run(segment, claim=claim).reason == 'allowance_held'
    assert staged_enqueue(get(h, segment)) == 100

    after_expiry = 100 + LIFECYCLE_DAYS * 86400 + 1
    assert AllowanceHolds(h.store, lambda *_: ('new-period', True), provider_wake=Mock()).tick(after_expiry) == 1
    released = get(h, segment)
    assert released['audio_uri'] == uri and staged_enqueue(released) == 100
    artifacts = Artifacts()
    artifacts.fetch_audio = Mock(side_effect=NotFound('staging object expired'))
    vendor = Vendor()
    with pytest.raises(NotFound):
        stage(h.store, artifacts, vendor, now=after_expiry).run(segment, claim=claim_provider_release(h, claim))
    assert vendor.calls == 0 and 'provider_intent' not in get(h, segment)


def test_purge_debits_parked_provider_once(h, monkeypatch):
    if h.name != 'emulator':
        pytest.skip('Production purge runs against Firestore')
    from database.batch_pipeline_purge import _delete_job
    from database.batch_pipeline_store import allowance_held_count

    monkeypatch.setenv('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', 'true')
    claim = admit_provider(h)
    segment, owner = claim.row_id, owner_key(claim.owner_id)
    worker = stage(h.store, Artifacts(), Vendor(), allowed=lambda *_: (False, 'allowance_exhausted'), now=125)
    assert worker.run(segment, claim=claim).reason == 'allowance_held'
    assert allowance_held_count(h.store.client, h.namespace, provider_only=True) == 1
    snapshot = h.store.client.collection(f'{h.namespace}_jobs').document(segment).get()
    for _ in range(2):
        _delete_job(h.store.client, h.namespace, snapshot, retain_ordering=True)
        assert h.store.run(lambda tx: tx.get(OWNERS, owner))['held_count'] == 0
    assert allowance_held_count(h.store.client, h.namespace, provider_only=True) == 0
    assert not get(h, segment)
    assert h.store.run(lambda tx: tx.get(TABLE, segment))['state'] == 'closed'
    wake = Mock()
    assert AllowanceHolds(h.store, lambda *_: ('granted', True), provider_wake=wake).tick(150) == 0
    wake.assert_not_called()


def test_concurrent_provider_rollback_ticks_issue_one_wake(h, monkeypatch):
    if h.name == 'sim':
        pytest.skip('Concurrent release requires a transactional backend')
    monkeypatch.setenv('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', 'true')
    claim = admit_provider(h)
    worker = stage(h.store, Artifacts(), Vendor(), allowed=lambda *_: (False, 'allowance_exhausted'), now=125)
    assert worker.run(claim.row_id, claim=claim).reason == 'allowance_held'
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    both_selected = Barrier(2)
    page = h.store.allowance_page

    def stale_page(*args):
        candidates = page(*args)
        both_selected.wait(timeout=10)
        return candidates

    monkeypatch.setattr(h.store, 'allowance_page', stale_page)
    wake = Mock()
    controller = AllowanceHolds(h.store, Mock(), provider_wake=wake)
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(controller.tick, (150, 150))) == [0, 1]
    outbox = h.store.run(lambda tx: tx.get(TABLE, claim.row_id))
    wake.assert_called_once_with(claim.row_id, outbox['task_token'])
    assert h.store.run(lambda tx: tx.get(OWNERS, owner_key(claim.owner_id)))['held_count'] == 0
