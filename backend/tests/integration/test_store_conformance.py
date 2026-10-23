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

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from testing.store_fixtures import store_backend  # noqa: F401  (the parametrized fixture)

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
    with pytest.raises(ValueError):
        h.store.control_candidate(3, 'batch', 1.0)
    with pytest.raises(ValueError):
        h.store.control_candidate(1, 'gpu', 1.0)


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
