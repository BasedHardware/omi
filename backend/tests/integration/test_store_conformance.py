"""Batch ``Store`` / ``Transaction`` conformance across sim, Firestore emulator and Postgres.

Every behaviour here is one that scheduler / merge / admission / recovery code relies on and that
all three implementations must share (plan A0). The suite only speaks the protocol
(``database/batch_pipeline_store.py``) plus the read helpers the real code calls on the concrete
store; it never reaches into a backend's internals, so a fourth implementation is checked by adding
a factory in ``testing/store_fixtures.py``.

Run all three (a missing backend SKIPS locally; ``OMI_REQUIRE_STORE_BACKENDS=all`` makes it fail)::

    cd backend && firebase emulators:exec --only firestore --project demo-omi-isolated-tests \\
        'OMI_REQUIRE_STORE_BACKENDS=all python -m pytest -m integration tests/integration/test_store_conformance.py'
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from config.batch_pipeline import scheduler_control_key
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from testing.store_fixtures import store_backend  # noqa: F401  (the parametrized fixture)
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.scheduler import Scheduler, owner_key as scheduler_owner_key

pytestmark = pytest.mark.integration


def owner_key(owner: str) -> str:
    return f'ok-{owner}'


def job(harness, segment, owner='o', **fields):
    uid = harness.uid(owner)
    base = {
        'segment_id': segment,
        'owner_id': uid,
        'owner_key': owner_key(uid),
        'conversation_id': None,
        'priority': 1,
        'state': 'ready',
        'capture_at': 1.0,
        'enqueued_at': 1.0,
        'merge_pending': False,
    }
    base.update(fields)
    if base['conversation_id'] is None:
        del base['conversation_id']
    return base


def put_all(harness, rows):
    def body(tx):
        for table, key, doc in rows:
            tx.put(table, key, doc)

    harness.store.run(body)


@pytest.fixture
def h(store_backend):
    store_backend.seed_user('o')
    store_backend.seed_user('p')
    return store_backend


def need(harness, *names):
    """Skip a test that does not apply to a backend by design."""
    if harness.name in names:
        pytest.skip(f'not applicable to the {harness.name} backend')


def test_shared_ready_cursor_rejects_stale_progress_and_reaches_fresh_owner(h, monkeypatch):
    from utils.batch_pipeline.ready_discovery import ReadyDiscovery

    monkeypatch.setenv('BATCH_PIPELINE_READY_DISCOVERY_CURSOR_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_READY_DISCOVERY_OWNERS_PER_TICK', '2')
    monkeypatch.setenv('BATCH_PIPELINE_READY_DISCOVERY_TICK_SECONDS', '60')
    put_all(
        h,
        [
            (
                'jobs',
                key,
                job(
                    h,
                    key,
                    owner_key=key,
                    state='result_ready',
                    merge_pending=True,
                    fresh_capture=key == 'z',
                    stt_route={'stt_route': 'provider'},
                ),
            )
            for key in ('b', 'd', 'f', 'h', 'z')
        ],
    )
    serving, pump = ReadyDiscovery(h.store, 'serving'), ReadyDiscovery(h.store, 'pump')
    stale = serving.page()
    for expected in (['b', 'd'], ['f', 'h']):
        page = pump.page()
        assert [key for key, _ in pump.owners(page)] == expected
        assert pump.finish(page)
    progress = h.store.run(lambda tx: tx.get('merge_discovery', 'cursor'))
    assert progress['after_owner_key'] == 'h' and progress['revision'] == 2
    assert [key for key, _ in serving.owners(stale)] == ['b', 'd']
    assert serving.finish(stale)
    assert h.store.run(lambda tx: tx.get('merge_discovery', 'cursor')) == progress
    page = pump.page()
    assert [key for key, _ in pump.owners(page)] == ['z']
    assert pump.finish(page)
    assert h.store.run(lambda tx: tx.get('merge_discovery', 'cursor'))['revision'] == 3


# -- document semantics ------------------------------------------------------------------------------
def test_missing_document_reads_as_empty_dict(h):
    assert h.store.run(lambda tx: tx.get('jobs', 'nope')) == {}


def test_put_get_round_trip_preserves_types_and_nesting(h):
    doc = job(
        h,
        's1',
        capture_at=1700000000.123456,
        enqueued_at=3,  # int must stay int, float must stay float
        lease_until=0.0,
        nested={'a': [1, 2.5, 'x', None, True], 'b': {'c': 'ünï'}},
        projection_binding={'target': 'c1', 'flags': [False, True]},
    )
    put_all(h, [('jobs', 's1', doc)])
    got = h.store.run(lambda tx: tx.get('jobs', 's1'))
    assert got == {**doc, 'privacy_generation': got['privacy_generation']}
    assert type(got['enqueued_at']) is int and type(got['lease_until']) is float
    assert got['nested'] == doc['nested']


def test_firestore_native_values_round_trip(h):
    from datetime import datetime, timezone

    stamp = datetime(2026, 10, 19, 12, 30, 15, 123456, tzinfo=timezone.utc)
    put_all(h, [('jobs', 's1', job(h, 's1', expires_at=stamp, blob=b'\x00\xffbytes'))])
    got = h.store.run(lambda tx: tx.get('jobs', 's1'))
    assert got['expires_at'] == stamp and got['blob'] == b'\x00\xffbytes'


def test_reads_inside_a_transaction_see_its_own_writes_but_returns_copies(h):
    put_all(h, [('jobs', 's1', job(h, 's1'))])

    def body(tx):
        before = tx.get('jobs', 's1')
        tx.put('jobs', 's1', {**before, 'state': 'leased', 'lease_until': 9.0})
        seen = tx.get('jobs', 's1')
        seen['state'] = 'mutated-locally'  # must not leak back into the transaction or the store
        return tx.get('jobs', 's1')['state']

    assert h.store.run(body) == 'leased'
    assert h.store.run(lambda tx: tx.get('jobs', 's1'))['state'] == 'leased'


def test_exception_in_body_discards_every_buffered_write(h):
    put_all(h, [('jobs', 'keep', job(h, 'keep'))])

    def body(tx):
        tx.put('jobs', 'keep', {**job(h, 'keep'), 'state': 'changed'})
        tx.put('jobs', 'new', job(h, 'new'))
        raise KeyError('boom')

    with pytest.raises(KeyError):
        h.store.run(body)
    assert h.store.run(lambda tx: tx.get('jobs', 'keep'))['state'] == 'ready'
    assert h.store.run(lambda tx: tx.get('jobs', 'new')) == {}


def test_writes_to_one_table_do_not_leak_to_another(h):
    put_all(h, [('owners', 'x', {'revision': 1}), ('gpus', 'x', {'token': 't'}), ('queues', 'x', {'head': 'a'})])
    assert h.store.run(lambda tx: (tx.get('owners', 'x'), tx.get('gpus', 'x'), tx.get('queues', 'x'))) == (
        {'revision': 1},
        {'token': 't'},
        {'head': 'a'},
    )
    assert h.store.run(lambda tx: tx.get('intakes', 'x')) == {}


def test_namespaces_are_isolated(h, store_backend):
    from testing.store_fixtures import build_backend

    second = build_backend(h.name)
    try:
        second.seed_user('o')
        put_all(h, [('owners', 'shared-key', {'v': 'first'})])
        assert second.store.run(lambda tx: tx.get('owners', 'shared-key')) == {}
    finally:
        second.close()


def test_write_budget_is_450(h):
    def rows(n):
        def body(tx):
            for i in range(n):
                tx.put('gpus', f'g{i}', {'i': i})

        return body

    h.store.run(rows(450))
    with pytest.raises(RuntimeError, match='write budget'):
        h.store.run(rows(451))
    assert h.store.run(lambda tx: tx.get('gpus', 'g450')) == {}


def test_conversation_documents_cannot_be_set_and_only_route_owner_patches(h):
    with pytest.raises(ValueError):
        h.store.run(lambda tx: tx.put('conversations', f"{h.uid('o')}/c1", {'x': 1}))
    with pytest.raises(ValueError):
        h.store.run(lambda tx: tx.patch('conversations', f"{h.uid('o')}/c1", {'other': 1}))


# -- ordered-head and recovery queries ----------------------------------------------------------------
def test_first_pending_orders_by_capture_then_segment_and_scopes_to_owner(h):
    rows = [
        ('jobs', 'b', job(h, 'b', capture_at=2.0, merge_pending=True)),
        ('jobs', 'a2', job(h, 'a2', capture_at=1.0, merge_pending=True)),
        ('jobs', 'a1', job(h, 'a1', capture_at=1.0, merge_pending=True)),  # tie on capture_at: segment id decides
        ('jobs', 'done', job(h, 'done', capture_at=0.5, merge_pending=False)),
        ('jobs', 'other', job(h, 'other', owner='p', capture_at=0.1, merge_pending=True)),
    ]
    put_all(h, rows)
    mine = owner_key(h.uid('o'))
    assert h.store.run(lambda tx: tx.first_pending(mine))['segment_id'] == 'a1'
    assert h.store.run(lambda tx: tx.first_pending(owner_key(h.uid('p'))))['segment_id'] == 'other'
    assert h.store.run(lambda tx: tx.first_pending('ok-nobody')) is None


def test_ready_predecessor_requires_exactly_one_ready_link(h):
    ok = owner_key(h.uid('o'))
    put_all(
        h,
        [
            ('jobs', 'p1', job(h, 'p1', next='target')),
            ('jobs', 'stale', job(h, 'stale', state='leased', next='target')),  # not ready: ignored
            ('jobs', 'wrongprio', job(h, 'wrongprio', priority=2, next='target')),
        ],
    )
    assert h.store.run(lambda tx: tx.ready_predecessor(ok, 1, 'target'))['segment_id'] == 'p1'
    put_all(h, [('jobs', 'p2', job(h, 'p2', next='target'))])
    assert h.store.run(lambda tx: tx.ready_predecessor(ok, 1, 'target')) is None  # two matches fail closed
    assert h.store.run(lambda tx: tx.ready_predecessor(ok, 1, 'absent')) is None


@pytest.mark.parametrize(
    'state,field',
    [
        ('leased', 'lease_until'),
        ('retry', 'available_at'),
        ('result_ready', 'enqueued_at'),
        ('record_pending', 'available_at'),
    ],
)
def test_due_returns_only_due_rows_oldest_first_with_clamped_limit(h, state, field):
    rows = [(f'd{i}', {field: float(10 - i)}) for i in range(5)]  # d4 oldest
    rows.append(('future', {field: 100.0}))
    put_all(h, [('jobs', key, job(h, key, state=state, **extra)) for key, extra in rows])
    put_all(h, [('jobs', 'wrong-state', job(h, 'wrong-state', state='ready', **{field: 1.0}))])
    assert h.store.due(state, 50.0, 100) == ['d4', 'd3', 'd2', 'd1', 'd0']
    assert h.store.due(state, 50.0, 2) == ['d4', 'd3']
    assert h.store.due(state, 50.0, 0) == ['d4']  # limit is clamped to at least one


def test_due_boundary_is_inclusive_and_default_limit_applies(h):
    put_all(h, [('jobs', f'r{i}', job(h, f'r{i}', state='retry', available_at=float(i))) for i in range(3)])
    assert h.store.due('retry', 1.0) == ['r0', 'r1']
    assert h.store.due('retry', 0.999) == ['r0']
    assert h.store.due('retry', -1.0) == []


def test_due_rejects_non_recoverable_states(h):
    with pytest.raises(ValueError):
        h.store.due('ready', 1.0)


def test_oldest_ready_and_pending_gauges(h):
    put_all(
        h,
        [
            ('jobs', 'r1', job(h, 'r1', state='ready', enqueued_at=5.0)),
            ('jobs', 'r2', job(h, 'r2', state='ready', enqueued_at=3.0)),
            ('jobs', 'm1', job(h, 'm1', state='result_ready', enqueued_at=1.0, merge_pending=True)),
            ('jobs', 'hi', job(h, 'hi', priority=2, state='ready', enqueued_at=0.5)),
        ],
    )
    assert h.store.oldest(1, ready_only=True) == 3.0
    assert h.store.oldest(1, ready_only=False) == 1.0
    assert h.store.oldest(2, ready_only=True) == 0.5
    assert h.store.oldest(0, ready_only=True) is None


def test_oldest_retry_ignores_rows_that_never_retried(h):
    put_all(
        h,
        [
            ('jobs', 'a', job(h, 'a', state='retry', retry_started_at=40.0)),
            ('jobs', 'b', job(h, 'b', state='retry', retry_started_at=20.0)),
            ('jobs', 'c', job(h, 'c', state='ready')),
        ],
    )
    assert h.store.oldest_retry(1) == 20.0
    assert h.store.oldest_retry(0) is None


def test_control_candidate_picks_lowest_service_then_availability(h):

    def control(**kw):
        base = {'p1_active': True, 'p1_service': 5.0, 'p1_batch_available_at': 0.0, 'p1_live_available_at': 0.0}
        base.update(kw)
        return base

    put_all(
        h,
        [
            ('control', 'low', control(p1_service=1.0)),
            ('control', 'high', control(p1_service=9.0)),
            ('control', 'idle', control(p1_service=0.0, p1_active=False)),
            ('control', 'later', control(p1_service=1.0, p1_batch_available_at=50.0)),
            ('control', 'neg', control(p1_service=-1.0)),
        ],
    )
    assert h.store.control_candidate(1, 'batch', 10.0) == 'low'
    assert h.store.control_candidate(1, 'batch', 60.0) == 'low'  # 'later' ties on service; availability breaks it
    assert h.store.control_candidate(0, 'batch', 10.0) is None
    assert h.store.control_candidate(1, 'live', 10.0) == 'later'  # live availability and service tie: key breaks it
    assert h.store.control_candidates(1, 'batch', 10.0, worker_id='worker') == ['low', 'high']
    assert h.store.control_candidates(1, 'batch', 10.0, worker_id='worker', fanout=1) == ['low']
    assert h.store.control_candidates(1, 'batch', 10.0, worker_id='worker', fanout=64) == ['low', 'high']

    choices = h.store.control_candidates(1, 'batch', 60.0, worker_id='worker')
    assert set(choices[:2]) == {'low', 'later'} and choices[-1] == 'high'
    assert h.store.control_candidate(1, 'batch', 60.0, worker_id='worker', exclude=choices[:2]) == 'high'
    with pytest.raises(ValueError):
        h.store.control_candidate(3, 'batch', 1.0)
    with pytest.raises(ValueError):
        h.store.control_candidate(1, 'gpu', 1.0)


@pytest.mark.parametrize('fanout', [1, 16, 64])
def test_control_candidates_limit_query_order_before_worker_affinity(h, fanout):
    import hashlib

    rows = [
        (
            'control',
            f'shard-{n:02}',
            {'p1_active': True, 'p1_service': n // 10, 'p1_batch_available_at': float(29 - n)},
        )
        for n in range(30)
    ]
    put_all(h, rows)
    # Firestore/SQL first limit by service, availability, then document key.
    # Affinity only reorders equal-service rows inside that query prefix.
    prefix = sorted(rows, key=lambda row: (row[2]['p1_service'], row[2]['p1_batch_available_at'], row[1]))[:fanout]
    expected = sorted(
        prefix, key=lambda row: (row[2]['p1_service'], hashlib.sha256(f'worker:{row[1]}'.encode()).digest())
    )
    assert h.store.control_candidates(1, 'batch', 30, worker_id='worker', fanout=fanout) == [row[1] for row in expected]


def test_scheduler_refills_saturated_candidates_without_stranding_the_seventeenth_shard(h, monkeypatch):
    from config.batch_pipeline import scheduler_control_key
    from utils.batch_pipeline.contracts import Priority, WorkItem
    from utils.batch_pipeline.scheduler import Scheduler, owner_key

    monkeypatch.setenv('BATCH_CONTROL_CANDIDATE_FANOUT', '16')
    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', 'true')
    owners = {}
    for n in range(10000):
        uid = h.uid(f'refill-{n}')
        owners.setdefault(scheduler_control_key(owner_key(uid)), uid)
        if len(owners) == 17:
            break
    assert len(owners) == 17
    queue = Scheduler(h.store, worker_id='worker')
    for shard, uid in owners.items():
        h.customer.add_user(uid)
        assert queue.enqueue(WorkItem(shard, uid, 1, 'sim://audio', 30, Priority.FRESH), 1)
    prefix = h.store.control_candidates(0, 'batch', 2, worker_id='worker')
    assert len(prefix) == 16
    for shard in prefix:
        assert h.store.acquire_pull_claim(shard, 'busy', 2, 30)

    leases = queue.pull(2)

    assert [lease.item.segment_id for lease in leases] == list(set(owners) - set(prefix))
    assert all(h.store.run(lambda tx, shard=shard: tx.get('jobs', shard))['state'] == 'ready' for shard in prefix)


def test_purging_adjacent_jobs_rereads_repaired_links_before_next_admission(h):
    from utils.batch_pipeline.contracts import Priority, WorkItem
    from utils.batch_pipeline.scheduler import Scheduler

    # Postgres mirrors the authoritative Firestore privacy purge; it has no
    # standalone conversation-purge operation in this protocol.
    need(h, 'postgres')
    uid = h.uid('o')
    h.customer.add_conversation(uid, 'gone')
    queue = Scheduler(h.store)
    # Purge walks IDs lexically: tail first, then the predecessor whose next
    # pointer it repaired. A stale row snapshot would restore the deleted tail.
    for segment in ('z-head', 'a-tail'):
        assert queue.enqueue(WorkItem(segment, uid, 1, 'sim://audio', 30, Priority.FRESH, conversation_id='gone'), 1)
    h.customer.delete_conversation(uid, 'gone')
    if h.name == 'sim':
        h.store.purge(uid, 'gone')
    else:
        from database.batch_pipeline_purge import purge_batch_owner

        purge_batch_owner(
            uid,
            firestore_client=h.store.client,
            namespaces=(h.namespace,),
            conversation_id='gone',
            delete_uri=lambda owner, uri: None,
        )

    assert queue.enqueue(WorkItem('survivor', uid, 2, 'sim://audio', 30, Priority.FRESH), 2)
    assert [lease.item.segment_id for lease in queue.pull(3)] == ['survivor']


def test_service_frontier_is_the_maximum_virtual_time_or_zero(h):
    assert h.store.run(lambda tx: tx.service_frontier(1)) == 0.0
    put_all(
        h,
        [
            ('control', 'a', {'p1_service': 2.5}),
            ('control', 'b', {'p1_service': 7.5}),
            ('control', 'c', {'p2_service': 99.0}),
        ],
    )
    assert h.store.run(lambda tx: tx.service_frontier(1)) == 7.5
    assert h.store.run(lambda tx: tx.service_frontier(2)) == 99.0
    with pytest.raises(ValueError):
        h.store.run(lambda tx: tx.service_frontier(3))


# -- privacy fence ---------------------------------------------------------------------------------------
def test_first_job_write_records_the_privacy_generation_and_a_stale_one_is_refused(h):
    put_all(h, [('jobs', 's1', job(h, 's1'))])
    stored = h.store.run(lambda tx: tx.get('jobs', 's1'))
    assert stored['privacy_generation'] == 0  # no generation document yet
    h.customer.block_privacy(h.uid('o'))  # generation 1, blocked
    with pytest.raises(BatchPrivacyBlocked):
        put_all(h, [('jobs', 's1', {**stored, 'state': 'leased'})])
    assert h.store.run(lambda tx: tx.get('jobs', 's1'))['state'] == 'ready'


def test_blocked_account_missing_account_and_deletion_are_refused_atomically(h):
    h.customer.delete_account(h.uid('p'))
    with pytest.raises(BatchPrivacyBlocked):
        put_all(h, [('jobs', 'ok-first', job(h, 'ok-first')), ('jobs', 'bad', job(h, 'bad', owner='p'))])
    assert h.store.run(lambda tx: tx.get('jobs', 'ok-first')) == {}  # the allowed write rolled back too
    ghost = job(h, 'ghost', owner='never-seeded')
    with pytest.raises(BatchPrivacyBlocked):
        put_all(h, [('jobs', 'ghost', ghost)])


def test_deleted_conversation_is_refused_and_merged_redirects_are_followed(h):
    uid = h.uid('o')
    h.customer.add_conversation(uid, 'live')
    put_all(h, [('jobs', 'ok', job(h, 'ok', conversation_id='live'))])
    h.customer.delete_conversation(uid, 'gone')
    with pytest.raises(BatchPrivacyBlocked):
        put_all(h, [('jobs', 'dead', job(h, 'dead', conversation_id='gone'))])
    h.customer.merge_conversation(uid, 'src', 'dst')
    put_all(h, [('jobs', 'merged', job(h, 'merged', conversation_id='src'))])  # follows src -> dst
    h.customer.delete_conversation(uid, 'dst')
    with pytest.raises(BatchPrivacyBlocked):
        put_all(h, [('jobs', 'merged2', job(h, 'merged2', conversation_id='src'))])  # user intent dominates


def test_results_writes_are_fenced_through_their_job(h):
    put_all(h, [('jobs', 's1', job(h, 's1'))])
    h.customer.block_privacy(h.uid('o'))
    with pytest.raises(BatchPrivacyBlocked):
        put_all(h, [('results', 's1', {'segment_id': 's1', 'projection_state': 'pending', 'committed_at': 1.0})])
    assert h.store.run(lambda tx: tx.get('results', 's1')) == {}


def test_check_privacy_returns_the_current_generation(h):
    uid = h.uid('o')
    assert h.store.run(lambda tx: tx.check_privacy(uid)) == 0
    h.customer.block_privacy(uid)
    with pytest.raises(BatchPrivacyBlocked):
        h.store.run(lambda tx: tx.check_privacy(uid))
    with pytest.raises(BatchPrivacyBlocked):
        h.store.run(lambda tx: tx.check_privacy(uid, expected_generation=0))


def test_quarantine_fenced_revokes_only_fenced_leases_and_retries(h):
    put_all(
        h,
        [
            ('jobs', 'leased', job(h, 'leased', state='leased', token='t1', lease_until=99.0)),
            ('jobs', 'retry', job(h, 'retry', state='retry', token='t2', available_at=5.0)),
            ('jobs', 'ready', job(h, 'ready', state='ready')),
            ('jobs', 'other', job(h, 'other', owner='p', state='leased', token='t3', lease_until=99.0)),
        ],
    )
    assert h.store.quarantine_fenced('leased', 10.0) is False  # not fenced yet
    h.customer.block_privacy(h.uid('o'))
    assert h.store.quarantine_fenced('leased', 10.0) is True
    revoked = h.store.run(lambda tx: tx.get('jobs', 'leased'))
    assert revoked['state'] == 'privacy_blocked' and revoked['token'] == '' and revoked['lease_until'] == 0.0
    assert revoked['privacy_blocked_at'] == 10.0 and revoked['owner_id'] == h.uid('o')  # identity untouched
    assert h.store.quarantine_fenced('retry', 11.0) is True
    assert h.store.quarantine_fenced('ready', 11.0) is False  # not a detached lease/retry
    assert h.store.quarantine_fenced('other', 11.0) is False  # other owner unfenced
    assert h.store.quarantine_fenced('leased', 12.0) is False  # already revoked
    assert h.store.quarantine_fenced('missing', 12.0) is False


def test_privacy_defer_moves_only_due_blocked_record_pending_available_at(h):
    put_all(
        h,
        [
            ('jobs', 'rp', job(h, 'rp', state='record_pending', available_at=5.0)),
            ('jobs', 'later', job(h, 'later', state='record_pending', available_at=50.0)),
            ('jobs', 'ready', job(h, 'ready', state='ready', available_at=5.0)),
            ('jobs', 'other', job(h, 'other', owner='p', state='record_pending', available_at=5.0)),
        ],
    )
    before = h.store.run(lambda tx: tx.get('jobs', 'rp'))
    assert h.store.defer_privacy_blocked_record('rp', 910.0, 10.0) is False  # not blocked: the claim owns it
    h.customer.block_privacy(h.uid('o'))
    assert h.store.defer_privacy_blocked_record('rp', 910.0, 10.0) is True
    after = h.store.run(lambda tx: tx.get('jobs', 'rp'))
    assert after == {**before, 'available_at': 910.0}  # nothing but available_at changed
    assert h.store.defer_privacy_blocked_record('rp', 1810.0, 20.0) is False  # no longer due
    assert h.store.defer_privacy_blocked_record('later', 910.0, 10.0) is False  # not due yet
    assert h.store.defer_privacy_blocked_record('ready', 910.0, 10.0) is False  # not record_pending
    assert h.store.defer_privacy_blocked_record('other', 910.0, 10.0) is False  # other owner unblocked
    assert h.store.defer_privacy_blocked_record('missing', 910.0, 10.0) is False  # purged: never created
    assert h.store.run(lambda tx: tx.get('jobs', 'missing')) == {}


# -- projection keyset scan -----------------------------------------------------------------------------
def _projection_rows(h):
    states = ['pending', 'persisted', 'ready', 'completed', 'pending']
    rows = []
    for i, state in enumerate(states):
        sid = f'r{i}'
        rows.append(('jobs', sid, job(h, sid)))
        rows.append(
            ('results', sid, {'segment_id': sid, 'projection_state': state, 'committed_at': float(10 - i // 2)})
        )
    return rows


def test_projection_page_is_a_stable_keyset_scan(h):
    put_all(h, _projection_rows(h))
    ids, cursor = h.store.projection_page(2)
    assert ids == ['r4', 'r2'] and cursor is not None  # committed_at ascending, key breaks ties
    ids2, cursor2 = h.store.projection_page(2, after=cursor)
    assert ids2 == ['r0', 'r1'] and cursor2 is not None
    ids3, cursor3 = h.store.projection_page(2, after=cursor2)
    assert ids3 == [] and cursor3 is None
    assert h.store.projection_pending(100) == ['r4', 'r2', 'r0', 'r1']


def test_projection_cursor_survives_removal_of_its_source_row(h):
    put_all(h, _projection_rows(h))
    ids, cursor = h.store.projection_page(2)
    put_all(h, [('results', ids[-1], {'segment_id': ids[-1], 'projection_state': 'completed', 'committed_at': 1.0})])
    assert h.store.projection_page(10, after=cursor)[0] == ['r0', 'r1']


def test_projection_due_page_filters_orders_and_survives_cursor_removal(h):
    rows = []
    for key, state, committed, due in [
        ('a', 'ready', 3.0, 10.0),
        ('b', 'persisted', 3.0, 10.0),
        ('c', 'ready', 1.0, 11.0),
        ('future', 'ready', 0.0, 12.0),
        ('pending', 'pending', 0.0, 10.0),
        ('missing', 'ready', 0.0, None),
    ]:
        rows.append(('jobs', key, job(h, key)))
        doc = {'segment_id': key, 'projection_state': state, 'committed_at': committed}
        if due is not None:
            doc['projection_finish_due_at'] = due
        rows.append(('results', key, doc))
    put_all(h, rows)
    args = {'states': ('persisted', 'ready'), 'due_before': 11.0}
    assert h.store.projection_page(10, **args) == (['a', 'b', 'c'], None)
    ids, cursor = h.store.projection_page(2, **args)
    assert (ids, cursor) == (['a', 'b'], (10.0, 3.0, 'b'))
    put_all(h, [('results', 'b', {'segment_id': 'b', 'projection_state': 'completed', 'committed_at': 3.0})])
    assert h.store.projection_page(2, after=cursor, **args) == (['c'], None)
    assert h.store.projection_page(10, after=(10.0,), **args) == (['a', 'c'], None)
    assert h.store.projection_page(10, after=(11.0,), **args) == (['c'], None)
    assert h.store.projection_page(10, after=(12.0,), **args) == ([], None)
    assert h.store.projection_page(10, states=('pending',)) == (['pending'], None)
    assert h.store.projection_page(10, states=('ready',), after=(1.0, '')) == (['c', 'a'], None)


@pytest.mark.parametrize('limit, expected', [(0, 1), (1, 1), (150, 150), (200, 200), (500, 200)])
@pytest.mark.parametrize('due_before', [None, 10.0])
def test_projection_page_uses_firestore_page_bounds(h, limit, expected, due_before):
    rows = []
    for i in range(201):
        key = f'bound-{i:03}'
        rows.append(('jobs', key, job(h, key)))
        rows.append(
            (
                'results',
                key,
                {
                    'segment_id': key,
                    'projection_state': 'ready',
                    'committed_at': 1.0,
                    'projection_finish_due_at': 10.0,
                },
            )
        )
    put_all(h, rows)
    ids, cursor = h.store.projection_page(limit, due_before=due_before)
    assert ids == [f'bound-{i:03}' for i in range(expected)]
    assert cursor == ((1.0, ids[-1]) if due_before is None else (10.0, 1.0, ids[-1]))


# -- merge, capacity and projection hints (Store protocol parity, plan A3 step 1) ----------------------------
def _pending(h, segment, owner='o', **fields):
    return ('jobs', segment, job(h, segment, owner=owner, merge_pending=True, **fields))


def test_first_ready_pending_is_the_earliest_pending_row_with_a_result(h):
    put_all(
        h,
        [
            _pending(h, 'a', capture_at=1.0, state='leased'),
            _pending(h, 'c', capture_at=3.0, state='result_ready'),
            _pending(h, 'b', capture_at=2.0, state='result_ready'),
            _pending(h, 'd', owner='p', capture_at=0.5, state='result_ready'),
            ('jobs', 'e', job(h, 'e', capture_at=0.1, state='result_ready', merge_pending=False)),
        ],
    )
    key = owner_key(h.uid('o'))
    assert h.store.run(lambda tx: tx.first_ready_pending(key))['segment_id'] == 'b'
    assert h.store.run(lambda tx: tx.first_ready_pending(owner_key(h.uid('nobody')))) is None


def test_longest_ready_pending_orders_by_ready_at_and_ignores_rows_without_it(h):
    put_all(
        h,
        [
            _pending(h, 'a', state='result_ready', ready_at=5.0),
            _pending(h, 'b', state='result_ready', ready_at=2.0),
            _pending(h, 'c', state='result_ready'),
            _pending(h, 'd', state='ready', ready_at=1.0),
            ('jobs', 'e', job(h, 'e', state='result_ready', ready_at=0.5, merge_pending=False)),
        ],
    )
    assert h.store.longest_ready_pending(owner_key(h.uid('o')))['segment_id'] == 'b'
    assert h.store.longest_ready_pending(owner_key(h.uid('p'))) is None


def test_fresh_pending_returns_the_earliest_fresh_rows_in_any_state(h):
    put_all(
        h,
        [
            _pending(h, 'a', capture_at=3.0, fresh_capture=True),
            _pending(h, 'b', capture_at=1.0, fresh_capture=True),
            _pending(h, 'c', capture_at=0.0, fresh_capture=False),
            _pending(h, 'e', capture_at=2.0, fresh_capture=True, state='leased'),
            ('jobs', 'f', job(h, 'f', capture_at=0.5, fresh_capture=True, merge_pending=False)),
            _pending(h, 'g', owner='p', capture_at=0.1, fresh_capture=True),
        ],
    )
    key = owner_key(h.uid('o'))
    assert [row['segment_id'] for row in h.store.fresh_pending(key, 2)] == ['b', 'e']
    assert [row['segment_id'] for row in h.store.fresh_pending(key, 10)] == ['b', 'e', 'a']


@pytest.mark.parametrize('enabled', [False, True])
def test_terminal_poll_filter_preserves_nonterminal_heads_and_fresh_wait(h, monkeypatch, enabled):
    from config.batch_pipeline import MERGE_POLL_TERMINAL_STATES
    from utils.batch_pipeline.merge import _fresh_pick

    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', str(enabled).lower())
    terminals = MERGE_POLL_TERMINAL_STATES
    nonterminal = (
        'ready',
        'leased',
        'retry',
        'result_ready',
        'record_pending',
        'held',
        'provider_pending',
        'provider_running',
        'vendor_held',
        'future_state',
    )
    for state in (*terminals, *nonterminal):
        put_all(h, [_pending(h, state, capture_at=0.0 if state in terminals else 1.0, fresh_capture=True, state=state)])
    key = owner_key(h.uid('o'))
    rows = h.store.fresh_pending(key, 32)
    expected = set(nonterminal) | (set() if enabled else set(terminals))
    assert {r['state'] for r in rows} == expected
    assert h.store.run(lambda tx: tx.first_pending(key))['state'] == rows[0]['state']

    # Isolate a decisionless allowance retry ahead of a completed fresh result.
    for state in (*terminals, *nonterminal):

        def remove(tx):
            current = tx.get('jobs', state)
            tx.put('jobs', state, {**current, 'merge_pending': False})

        h.store.run(remove)
    put_all(
        h,
        [
            _pending(
                h,
                'waiting',
                capture_at=1.0,
                state='retry',
                fresh_capture=True,
                available_at=10.0,
                last_policy_hold={'reason': 'allowance_exhausted'},
            ),
            _pending(h, 'done', capture_at=2.0, state='result_ready', fresh_capture=True, ready_at=10.0),
        ],
    )
    rows = h.store.fresh_pending(key, 32)
    assert [r['segment_id'] for r in rows] == ['waiting', 'done']
    assert h.store.run(lambda tx: tx.first_pending(key))['segment_id'] == 'waiting'
    assert _fresh_pick(rows, 100, 300) == (None, None)
    assert _fresh_pick(rows, 311, 300)[1]['segment_ids'] == ['waiting']


@pytest.mark.parametrize('enabled', [False, True])
def test_poll_filter_never_skips_recovery_or_durable_terminal_transitions(h, monkeypatch, enabled):
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')  # Legacy retry behavior under rollback.
    from utils.batch_pipeline.contracts import WorkResult
    from utils.batch_pipeline.merge import OrderedMerge
    from utils.batch_pipeline.retry_policy import quarantine_job

    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', str(enabled).lower())
    queue = Scheduler(h.store)
    uid = h.uid('o')
    assert queue.enqueue(WorkItem('recover-me', uid, 1, 'gs://synthetic/input', 30, Priority.FRESH), 100)
    lease = queue.pull(101)[0]
    assert queue.defer('recover-me', lease.token, 102, 30, held_reason='allowance_exhausted')
    assert h.store.due('retry', 133, 10) == ['recover-me']
    assert queue.recover(133) == 1
    lease = queue.pull(134)[0]
    assert queue.complete(WorkResult('recover-me', 'gs://synthetic/result'), lease.token, 135)
    assert OrderedMerge(h.store).commit_next(uid, 136) is not None
    assert h.store.run(lambda tx: tx.get('jobs', 'recover-me'))['state'] == 'committed'

    assert queue.enqueue(WorkItem('fail-me', uid, 2, 'gs://synthetic/input2', 30, Priority.FRESH), 140)

    def quarantine(tx):
        current = tx.get('jobs', 'fail-me')
        quarantine_job(tx, current, 141, 'worker_failed')
        tx.put('jobs', 'fail-me', current)

    h.store.run(quarantine)
    assert h.store.run(lambda tx: tx.get('jobs', 'fail-me'))['state'] == 'quarantined'

    # Retained terminal rows remain directly addressable for fenced redrive.
    def expire(tx):
        current = tx.get('jobs', 'fail-me')
        tx.put(
            'jobs',
            'fail-me',
            {**current, 'state': 'dead', 'merge_pending': True, 'dead_letter_reason': 'synthetic_failure'},
        )

    h.store.run(expire)
    assert h.store.run(lambda tx: tx.get('jobs', 'fail-me'))['state'] == 'dead'
    assert h.store.run(lambda tx: queue.redrive_in_transaction(tx, tx.get('jobs', 'fail-me'), 142, operator=True))
    assert h.store.run(lambda tx: tx.get('jobs', 'fail-me'))['state'] == 'ready'

    assert queue.enqueue(WorkItem('fenced', h.uid('p'), 3, 'gs://synthetic/private', 30, Priority.FRESH), 150)
    assert 'fenced' in {lease.item.segment_id for lease in queue.pull(151, 2)}
    h.customer.block_privacy(h.uid('p'))
    assert h.store.quarantine_fenced('fenced', 152)
    fenced = h.store.run(lambda tx: tx.get('jobs', 'fenced'))
    assert fenced['state'] == 'privacy_blocked' and fenced['merge_pending'] is True
    pending = h.store.run(lambda tx: tx.first_pending(fenced['owner_key']))
    assert (pending is None) if enabled else pending['segment_id'] == 'fenced'


@pytest.mark.parametrize('enabled', [False, True])
def test_held_merge_owners_rotates_markers_and_resolves_the_owner_from_pending_work(h, monkeypatch, enabled):
    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', str(enabled).lower())
    held = owner_key(h.uid('o'))
    put_all(
        h,
        [
            _pending(h, 'a', state='dead'),
            ('merge_holds', held, {'held': True}),
            ('merge_holds', 'ok-stale', {'held': True}),
            ('merge_holds', owner_key(h.uid('p')), {'held': False}),
        ],
    )
    expected = sorted([(held, h.uid('o')), ('ok-stale', None)])  # document-name (byte) order
    assert h.store.held_merge_owners(10) == expected
    assert h.store.held_merge_owners(1) == expected[:1]
    assert h.store.held_merge_owners(10, after=expected[0][0]) == expected[1:]


def test_projection_successor_follows_one_link_and_fails_closed_on_a_fork(h):
    key = 'ok-log'
    links = {'r1': None, 'r2': 'r1', 'r3': 'r2', 'r3b': 'r2'}
    rows = []
    for segment, previous in links.items():
        rows.append(('jobs', segment, job(h, segment)))
        rows.append(('results', segment, {'segment_id': segment, 'owner_key': key, 'previous_segment_id': previous}))
    rows.append(('jobs', 'r9', job(h, 'r9')))
    rows.append(('results', 'r9', {'segment_id': 'r9', 'owner_key': key}))  # no link field never equals None
    rows.append(('jobs', 'x1', job(h, 'x1')))
    rows.append(('results', 'x1', {'segment_id': 'x1', 'owner_key': 'ok-other', 'previous_segment_id': 'r1'}))
    put_all(h, rows)
    assert h.store.projection_successor(key, None) == 'r1'
    assert h.store.projection_successor(key, 'r1') == 'r2'
    assert h.store.projection_successor(key, 'r2') is None  # two successors: fail closed
    assert h.store.projection_successor(key, 'missing') is None


def test_ready_for_capacity_counts_only_due_admissible_ready_work(h):
    def row(segment, priority=1, state='ready', available_at=10.0, outcome='unattempted'):
        decision = {} if outcome is None else {'compute_decision': {'outcome': outcome}}
        return _pending(h, segment, priority=priority, state=state, available_at=available_at, **decision)

    put_all(
        h,
        [
            row('a'),
            row('b', outcome='allowed'),
            row('c', outcome='held'),
            row('d', outcome=None),
            row('e', available_at=500.0),
            row('f', state='leased'),
            row('g', priority=2),
            ('jobs', 'h', job(h, 'h', available_at=10.0, compute_decision={'outcome': 'unattempted'})),
        ],
    )
    assert h.store.ready_for_capacity(1, 100.0) == 2
    assert h.store.ready_for_capacity(2, 100.0) == 1
    empty = h.store.ready_for_capacity(0, 100.0)
    assert empty == 0 and type(empty) is int


def test_oldest_uncommitted_age_skips_allowance_holds(h):
    hold = {'compute_decision': {'outcome': 'held', 'reason': 'allowance_exhausted'}}
    parked = {'last_policy_hold': {'reason': 'allowance_exhausted'}}
    put_all(h, [_pending(h, 'a', enqueued_at=1.0, **hold), _pending(h, 'b', enqueued_at=2.0, **parked)])
    assert h.store.oldest(1) is None  # only holds, and the scan was not truncated
    put_all(h, [_pending(h, 'c', enqueued_at=3.0)])
    assert h.store.oldest(1) == 3.0
    assert h.store.oldest(1, ready_only=True) == 1.0


def test_key_tie_breaks_use_firestore_byte_order_not_the_database_collation(h):
    """Firestore orders names bytewise; a locale collation would put 'a' before 'B' and 'ä' before 'z'."""
    keys = ['ä', 'a', 'z', 'B']  # byte order: B < a < z < ä
    rows = []
    for key in keys:
        rows.append(_pending(h, key, capture_at=1.0, state='retry', available_at=1.0))
        rows.append(('results', key, {'segment_id': key, 'projection_state': 'pending', 'committed_at': 1.0}))
    put_all(h, rows)
    assert h.store.run(lambda tx: tx.first_pending(owner_key(h.uid('o'))))['segment_id'] == 'B'
    assert h.store.due('retry', 5.0, 100) == ['B', 'a', 'z', 'ä']
    first, cursor = h.store.projection_page(2)
    assert first == ['B', 'a'] and h.store.projection_page(2, after=cursor)[0] == ['z', 'ä']


def test_projection_page_narrows_to_requested_drain_states(h):
    rows = []
    for i, state in enumerate(('pending', 'quarantine_held', 'completed', 'ready')):
        rows.append(('jobs', f'q{i}', job(h, f'q{i}')))
        rows.append(('results', f'q{i}', {'segment_id': f'q{i}', 'projection_state': state, 'committed_at': 1.0 + i}))
    put_all(h, rows)
    assert h.store.projection_page(10)[0] == ['q0', 'q3']
    assert h.store.projection_page(10, states=('quarantine_held',))[0] == ['q1']
    with pytest.raises(ValueError):
        h.store.projection_page(10, states=('completed',))


# -- contention ---------------------------------------------------------------------------------------------
def test_concurrent_read_modify_write_never_loses_an_update(h):
    need(h, 'sim')  # the simulator is single-threaded by design
    put_all(h, [('owners', 'ctr', {'n': 0})])

    def bump(_):
        def body(tx):
            row = tx.get('owners', 'ctr')
            tx.put('owners', 'ctr', {'n': row['n'] + 1})

        h.store.run(body)

    with ThreadPoolExecutor(max_workers=2) as pool:  # Firestore aborts after 5 attempts under heavier contention
        list(pool.map(bump, range(6)))
    assert h.store.run(lambda tx: tx.get('owners', 'ctr'))['n'] == 6


# -- daily parity: fenced scheduler pulls (PL-141/142/143, source PR #23927) ---------------------------
@pytest.fixture
def pull_case(h, monkeypatch):
    from utils.batch_pipeline import scheduler as scheduler_module

    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', 'true')
    # All timestamps, including time spent between claim and commit, are explicit.
    clock = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: clock[0])
    queue = Scheduler(h.store)
    for segment in ('a', 'b'):
        assert queue.enqueue(WorkItem(segment, h.uid('o'), 1, f'gs://synthetic/{segment}', 30, Priority.FRESH), 1000)
    key = scheduler_owner_key(h.uid('o'))
    shard = scheduler_control_key(key)
    keys = [('jobs', 'a'), ('jobs', 'b'), ('queues', f'0_{key}'), ('owners', key), ('control', shard)]

    def snapshot():
        return h.store.run(lambda tx: [tx.get(table, name) for table, name in keys])

    return queue, shard, clock, snapshot


def test_pl141_busy_pull_claim_leaves_queue_and_control_untouched(h, pull_case, monkeypatch):
    queue, shard, _, snapshot = pull_case
    assert h.store.acquire_pull_claim(shard, 'holder', 1000, 30)
    before = snapshot()
    run = h.store.run
    reads, writes = [], []

    class ObservedTransaction:
        def __init__(self, tx):
            self.tx = tx

        def __getattr__(self, name):
            return getattr(self.tx, name)

        def get(self, table, key):
            reads.append(table)
            return self.tx.get(table, key)

        def put(self, table, key, value):
            writes.append(table)
            return self.tx.put(table, key, value)

        def delete(self, table, key):
            writes.append(table)
            return self.tx.delete(table, key)

    def observed_run(body):
        return run(lambda tx: body(ObservedTransaction(tx)))

    monkeypatch.setattr(h.store, 'run', observed_run)
    assert queue.pull(1001) == []
    # Postgres acquires through a transaction; Firestore uses conditional CAS.
    # Neither may enter the queue/control read set or write anything when busy.
    assert set(reads) <= {'pull_claims'} and writes == []
    monkeypatch.setattr(h.store, 'run', run)
    assert snapshot() == before
    assert run(lambda tx: tx.get('pull_claims', shard)) == {'token': 'holder', 'expires_at': 1030}
    assert not h.store.acquire_pull_claim(shard, 'follower', 1029.999, 30)
    assert run(lambda tx: tx.get('pull_claims', shard)) == {'token': 'holder', 'expires_at': 1030}


@pytest.mark.parametrize('takeover', [False, True], ids=['expired', 'replaced'])
def test_pl142_paused_holder_cannot_mutate_or_release_a_new_claim(h, pull_case, monkeypatch, takeover):
    queue, shard, clock, snapshot = pull_case
    before = snapshot()
    acquire = h.store.acquire_pull_claim
    issued = []

    def pause_after_acquisition(key, token, now, ttl):
        won = acquire(key, token, now, ttl)
        assert won and key == shard
        issued.append(token)
        clock[0] += ttl  # expires exactly at the transaction's current time
        if takeover:
            assert acquire(key, 'replacement', now + ttl, ttl)
        return won

    monkeypatch.setattr(h.store, 'acquire_pull_claim', pause_after_acquisition)
    assert queue.pull(1000) == []
    assert len(issued) == 1
    assert snapshot() == before
    claim = h.store.run(lambda tx: tx.get('pull_claims', shard))
    assert claim == {
        'token': 'replacement' if takeover else issued[0],
        'expires_at': 1060 if takeover else 1030,
    }
    monkeypatch.setattr(h.store, 'acquire_pull_claim', acquire)
    # A reconstructed scheduler cannot renew/clear a live replacement either.
    if takeover:
        assert Scheduler(h.store).pull(1059) == []
        assert h.store.run(lambda tx: tx.get('pull_claims', shard)) == claim
    (lease,) = Scheduler(h.store).pull(1060 if takeover else 1030)
    assert lease.item.segment_id == 'a' and lease.attempt == 1


def test_pl143_failed_pull_rolls_back_release_and_restart_recovers_after_expiry(h, pull_case, monkeypatch):
    queue, shard, _, snapshot = pull_case
    before = snapshot()
    run = h.store.run

    class BeforeCommitFailure(RuntimeError):
        pass

    def abort_after_body(body):
        def abort(tx):
            result = body(tx)
            if isinstance(result, bool):  # Postgres's separate claim-acquisition transaction
                return result
            assert result[0] is not None  # the real pull buffered a job lease and claim release
            raise BeforeCommitFailure('synthetic abort after pull body, before commit')

        return run(abort)

    monkeypatch.setattr(h.store, 'run', abort_after_body)
    with pytest.raises(BeforeCommitFailure, match='before commit'):
        queue.pull(1000)
    monkeypatch.setattr(h.store, 'run', run)
    assert snapshot() == before
    claim = run(lambda tx: tx.get('pull_claims', shard))
    assert claim['token'] and claim['expires_at'] == 1030
    restarted = Scheduler(h.store)
    assert restarted.pull(1029.999) == []
    assert snapshot() == before
    first, second = restarted.pull(1030, 2)
    assert [first.item.segment_id, second.item.segment_id] == ['a', 'b']
    assert first.token != second.token and first.attempt == second.attempt == 1
    assert run(lambda tx: tx.get('pull_claims', shard)) == {'token': '', 'expires_at': 0.0}
    assert Scheduler(h.store).pull(1031) == []  # issued job leases remain exclusive
    for lease in (first, second):
        row = run(lambda tx: tx.get('jobs', lease.item.segment_id))
        assert row['state'] == 'leased' and row['token'] == lease.token


def test_reading_a_missing_document_fences_a_concurrent_create(h):
    need(h, 'sim')  # the simulator is single-threaded by design

    def create(i):
        def body(tx):
            if tx.get('gpus', 'slot'):
                return False
            tx.put('gpus', 'slot', {'token': f't{i}'})
            return True

        return h.store.run(body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(pool.map(create, range(4)))
    assert created.count(True) == 1
    assert h.store.run(lambda tx: tx.get('gpus', 'slot'))['token'] in {f't{i}' for i in range(4)}


def test_concurrent_schedulers_lease_every_job_exactly_once(h):
    """Four pullers over one store (A3 contention gate): no job is lost, none is leased twice."""
    need(h, 'sim')  # the simulator is single-threaded by design
    import threading
    import time

    from utils.batch_pipeline.contracts import Priority, WorkItem
    from utils.batch_pipeline.scheduler import Scheduler

    owners = [h.seed_user(f'c{i}') for i in range(4)]
    expected = set()
    seed = Scheduler(h.store)
    for i, uid in enumerate(owners):
        for j in range(3):
            segment = f'c{i}-{j}'
            expected.add(segment)
            seed.enqueue(WorkItem(segment, uid, 1000.0 + j, f'gs://synthetic/{segment}', 30.0, Priority.DEEP), 1.0)
    leased: list[str] = []
    lock = threading.Lock()

    def drain(worker):
        scheduler = Scheduler(h.store, worker_id=f'w{worker}')
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            with lock:
                if len(leased) >= len(expected):
                    return
            got = scheduler.pull(time.time(), 1)
            with lock:
                leased.extend(lease.item.segment_id for lease in got)
            if not got:
                time.sleep(0.05)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(drain, range(4)))
    assert sorted(leased) == sorted(expected)


@pytest.mark.parametrize('enabled', [False, True])
def test_ordered_merge_retained_terminal_head_and_later_result(h, monkeypatch, enabled):
    from utils.batch_pipeline.contracts import WorkResult
    from utils.batch_pipeline.merge import OrderedMerge

    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', str(enabled).lower())
    uid = h.uid('o')
    queue = Scheduler(h.store)
    for segment, capture in [('terminal', 1), ('later', 2)]:
        assert queue.enqueue(WorkItem(segment, uid, capture, 'gs://synthetic/input', 30, Priority.FRESH), 100)
    leases = {lease.item.segment_id: lease for lease in queue.pull(101, 2)}
    assert queue.complete(WorkResult('later', 'gs://synthetic/result'), leases['later'].token, 102)

    def retain(tx):
        old = tx.get('jobs', 'terminal')
        old.update(state='dead', merge_pending=True, token='', lease_until=0, dead_letter_reason='synthetic_failure')
        tx.put('jobs', 'terminal', old)
        return old

    terminal = h.store.run(retain)
    merge = OrderedMerge(h.store, head_wait_seconds=0, catch_up_depth=0)
    entry = merge.commit_next(uid, 103)
    assert h.store.run(lambda tx: tx.get('jobs', 'terminal')) == terminal
    if not enabled:
        assert entry is None
        assert h.store.run(lambda tx: tx.get('results', 'later')) == {}
        return
    assert entry['segment_id'] == 'later' and entry['previous_segment_id'] is None and entry['log_sequence'] == 1
    assert h.store.run(lambda tx: queue.redrive_in_transaction(tx, tx.get('jobs', 'terminal'), 104, operator=True))
    lease = queue.pull(105)[0]
    assert lease.item.segment_id == 'terminal'
    assert queue.complete(WorkResult('terminal', 'gs://synthetic/recovered'), lease.token, 106)
    recovered = merge.commit_next(uid, 107)
    assert recovered['segment_id'] == 'terminal' and recovered['late_capture'] is True
    assert recovered['previous_segment_id'] == 'later' and recovered['log_sequence'] == 2


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('head_state', ['dead', 'future_state'])
def test_head_priority_never_promotes_past_a_terminal_or_unknown_predecessor(h, monkeypatch, enabled, head_state):
    from utils.batch_pipeline.scheduler import _prefer_merge_head

    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', str(enabled).lower())
    put_all(
        h,
        [
            _pending(h, 'head', capture_at=1, state=head_state, next='middle', duration_seconds=30),
            _pending(h, 'middle', capture_at=2, next='selected', duration_seconds=30, available_at=1),
            _pending(h, 'selected', capture_at=3, next=None, duration_seconds=30, available_at=1),
        ],
    )
    observations = []

    def pick(tx):
        return _prefer_merge_head(
            tx,
            {'tail': 'selected'},
            tx.get('jobs', 'selected'),
            [1],
            observations,
            now=10,
            max_seconds=60,
            shared_gpu=False,
        )

    assert h.store.run(pick)['segment_id'] == 'selected'
    assert h.store.run(lambda tx: tx.get('jobs', 'head'))['state'] == head_state
    assert observations == ([('ready_age', 9), ('head_not_found', None)] if enabled and head_state == 'dead' else [])


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('state', ['missing', None])
def test_missing_and_null_pending_state_match_firestore_negative_filter(h, monkeypatch, enabled, state):
    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', str(enabled).lower())
    legacy = job(h, 'legacy', state=state, merge_pending=True, fresh_capture=True, privacy_generation=0)
    if state == 'missing':
        del legacy['state']
    put_all(h, [('jobs', 'legacy', legacy)])
    key = owner_key(h.uid('o'))
    assert h.store.fresh_pending(key, 32) == ([] if enabled else [legacy])
    assert h.store.run(lambda tx: tx.first_pending(key)) == (None if enabled else legacy)
    assert h.store.run(lambda tx: tx.get('jobs', 'legacy')) == legacy


def test_state_census_counts_only_pending_missing_null_or_unknown_rows(h, monkeypatch):
    if h.name != 'emulator':
        pytest.skip('Firestore aggregate API only')
    from scripts.batch_pipeline_poll_state_census import KNOWN_STATES, census

    rows = [('jobs', state, job(h, state, state=state, merge_pending=True)) for state in KNOWN_STATES]
    put_all(h, rows)
    client = h.store.client
    collection = f'{h.store.namespace}_jobs'

    def forbid_document_reads(*args, **kwargs):
        pytest.fail('census must use aggregation COUNT, never document reads')

    commit = client._firestore_api.commit

    def aggregate_only_commit(request, **kwargs):
        assert not request['writes']
        return commit(request, **kwargs)

    with monkeypatch.context() as census_only:
        census_only.setattr(client._firestore_api, 'commit', aggregate_only_commit)
        census_only.setattr(client._firestore_api, 'run_query', forbid_document_reads)
        census_only.setattr(client._firestore_api, 'batch_get_documents', forbid_document_reads)
        assert census(client.transaction(read_only=True), client, collection) == 0
    missing = job(h, 'missing', merge_pending=True)
    del missing['state']
    put_all(
        h,
        [
            ('jobs', 'missing', missing),
            ('jobs', 'null', job(h, 'null', state=None, merge_pending=True)),
            ('jobs', 'unknown', job(h, 'unknown', state='future_state', merge_pending=True)),
            ('jobs', 'not_pending', job(h, 'not_pending', state=None, merge_pending=False)),
        ],
    )
    with monkeypatch.context() as census_only:
        census_only.setattr(client._firestore_api, 'commit', aggregate_only_commit)
        census_only.setattr(client._firestore_api, 'run_query', forbid_document_reads)
        census_only.setattr(client._firestore_api, 'batch_get_documents', forbid_document_reads)
        assert census(client.transaction(read_only=True), client, collection) == 3


def test_transactional_fresh_first_sees_ready_past_40_unready_rows_and_terminal_states(h):
    rows = [
        job(
            h,
            f'f{i:02}',
            capture_at=float(i),
            merge_pending=True,
            fresh_capture=True,
            state='result_ready' if i == 40 else 'leased',
        )
        for i in range(41)
    ]
    put_all(h, [('jobs', row['segment_id'], row) for row in rows])
    for state in ('leased', 'dead', 'quarantined', 'committed'):
        row = {**rows[0], 'state': state}
        put_all(h, [('jobs', row['segment_id'], row)])
        first, ready = h.store.run(
            lambda tx: (tx.fresh_first_pending(row['owner_key']), tx.fresh_first_ready_pending(row['owner_key']))
        )
        assert first['segment_id'] == 'f00' and ready['segment_id'] == 'f40'


@pytest.mark.parametrize('head_class', [True, None])
@pytest.mark.parametrize('wait', [0, 60])
@pytest.mark.parametrize('privacy_blocked', [False, True])
def test_unready_fresh_or_legacy_head_does_not_hide_fresh_behind_held_provider(
    h, monkeypatch, head_class, wait, privacy_blocked
):
    from utils.batch_pipeline.merge import OrderedMerge

    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', 'true')
    uid = h.uid('o')
    key = scheduler_owner_key(uid)
    rows = [
        job(
            h,
            name,
            owner_key=key,
            capture_at=float(i),
            merge_pending=True,
            fresh_capture=True,
            state='result_ready' if name in ('held', 'fresh') else 'retry',
            protocol_version=1,
            result={'text': ''},
            ready_at=1.0,
        )
        for i, name in enumerate(('head', *(f'blocked-{n}' for n in range(40)), 'held', 'fresh'))
    ]
    if head_class is None:
        rows[0].pop('fresh_capture')
    rows[-2].update(fresh_capture=False, stt_route={'stt_route': 'provider'})
    put_all(h, [('jobs', row['segment_id'], row) for row in rows])
    if privacy_blocked:
        h.customer.block_privacy(uid)
    entry = OrderedMerge(h.store, head_wait_seconds=wait, catch_up_depth=1).commit_next(uid, 100.0)
    assert (entry['segment_id'] if entry else None) == ('fresh' if wait and not privacy_blocked else None)
    assert h.store.run(lambda tx: tx.get('jobs', 'held'))['state'] == 'result_ready'


@pytest.mark.parametrize('initial_state', ['leased', 'dead'])
def test_fresh_settle_or_redrive_before_commit_beats_stale_probe(h, monkeypatch, initial_state):
    from unittest.mock import Mock

    from utils.batch_pipeline.merge import OrderedMerge

    uid = h.uid('o')
    key = scheduler_owner_key(uid)
    rows = [
        job(
            h,
            name,
            owner_key=key,
            capture_at=float(i),
            merge_pending=True,
            fresh_capture=i > 0,
            state=initial_state if i == 1 else 'leased',
            protocol_version=1,
            result={'text': ''},
            ready_at=1.0,
        )
        for i, name in enumerate(('backlog', 'early', 'later'))
    ]
    rows[2]['state'] = 'result_ready'
    put_all(h, [('jobs', row['segment_id'], row) for row in rows])
    stale = [rows[2].copy()]
    probe = Mock(return_value=stale)
    monkeypatch.setattr(h.store, 'fresh_pending', probe)
    tx_type = h.store.run(type)
    first_query, query, put = tx_type.fresh_first_pending, tx_type.fresh_first_ready_pending, tx_type.put
    firsts, reads, writes = [], [], []

    def first(tx, key):
        firsts.append(tx)
        return first_query(tx, key)

    def read(tx, key):
        reads.append(tx)
        return query(tx, key)

    def write(tx, table, key, value):
        if table == 'results':
            writes.append(tx)
        return put(tx, table, key, value)

    monkeypatch.setattr(tx_type, 'fresh_first_pending', first)
    monkeypatch.setattr(tx_type, 'fresh_first_ready_pending', read)
    monkeypatch.setattr(tx_type, 'put', write)
    run, calls = h.store.run, []

    def interleave(body):
        calls.append(body)
        result = run(body)
        if len(calls) == 1:
            assert result is None
            run(lambda tx: tx.put('jobs', 'early', {**rows[1], 'state': 'result_ready'}))
        return result

    monkeypatch.setattr(h.store, 'run', interleave)
    entry = OrderedMerge(h.store, head_wait_seconds=60, catch_up_depth=4).commit_next(uid, 100.0)
    assert entry['segment_id'] == 'early' and entry['fresh_first'] is True
    assert firsts and reads and writes and firsts[-1] is reads[-1] is writes[-1]
    probe.assert_not_called()


def test_ready_owners_skips_an_owner_block_and_ignores_nonpending_or_unready(h):
    rows = [('jobs', f's{i}', job(h, f's{i}', state='result_ready', merge_pending=True)) for i in range(5)]
    rows += [
        ('jobs', 'p', job(h, 'p', owner='p', state='result_ready', merge_pending=True)),
        ('jobs', 'unready', job(h, 'unready', owner_key='z1', merge_pending=True)),
        ('jobs', 'done', job(h, 'done', owner_key='z2', state='result_ready')),
    ]
    put_all(h, rows)
    expected = [(owner_key(h.uid(o)), h.uid(o)) for o in ('o', 'p')]
    assert h.store.ready_owners(None, 1) == expected[:1]
    assert h.store.ready_owners(expected[0][0], 1) == expected[1:]
    assert h.store.ready_owners(expected[1][0], 1) == []

    assert h.store.ready_owners(None, 1, descending=True) == expected[-1:]
    assert h.store.ready_owners(None, 2, ceiling_owner_key=expected[0][0]) == expected[:1]
