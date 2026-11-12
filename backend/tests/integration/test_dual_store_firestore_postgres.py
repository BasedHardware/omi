"""A2 on the real primary: ``DualStore(FirestoreStore on the emulator, PostgresStore)``.

Proves the mirror reads ``FirestoreTransaction``'s committed writes, and that Firestore's own value types
(``DatetimeWithNanoseconds``) compare equal to the Postgres copy. Needs the loopback Firestore emulator and
a Postgres; ``OMI_REQUIRE_STORE_BACKENDS=emulator,postgres`` makes a missing one a failure.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from testing.store_fixtures import BackendUnavailable, postgres_connect, required_backends

pytestmark = pytest.mark.integration


def _need(name: str, exc: Exception):
    if name in required_backends():
        pytest.fail(f'required {name} backend unavailable: {exc}')
    pytest.skip(str(exc))


@pytest.fixture
def dual(monkeypatch):
    from database.batch_pipeline_store import FirestoreStore
    from database.jobstore.connection import Pool
    from database.jobstore.dual_store import DualStore
    from database.jobstore.postgres_store import PostgresStore
    from testing.store_fixtures import _emulator_client, _new_ids  # type: ignore[attr-defined]

    monkeypatch.delenv('JOBSTORE_SHADOW_WRITES', raising=False)
    try:
        client = _emulator_client()
    except BackendUnavailable as exc:
        _need('emulator', exc)
    try:
        connect = postgres_connect()
    except BackendUnavailable as exc:
        _need('postgres', exc)
    namespace, _ = _new_ids()
    pool = Pool('', connect=connect)
    shadow = PostgresStore(namespace, pool=pool, customer_client=None)
    store = DualStore(FirestoreStore(namespace, firestore_client=client), shadow, budget_s=5.0)
    yield store, shadow, pool
    store.drain(30)
    from database.jobstore.dual_store import MIRRORED_TABLES

    for table in MIRRORED_TABLES:
        for doc in client.collection(f'{namespace}_{table}').stream():
            doc.reference.delete()
    shadow.purge_namespace()
    pool.close()
    client.close()


def _count(table: str, op: str, outcome: str) -> float:
    from database.jobstore.dual_store import SHADOW_PARITY_TOTAL

    return SHADOW_PARITY_TOTAL.labels(table=table, op=op, outcome=outcome)._value.get()


def test_firestore_commits_mirror_and_read_back_at_parity(dual):
    store, shadow, pool = dual
    at = datetime(2026, 10, 19, 12, 30, 1, 123456, tzinfo=timezone.utc)
    docs = {
        ('queues', '0_owner'): {'head': 's1', 'tail': 's2', 'updated_at': at, 'n': 2},
        ('owners', 'owner'): {'privacy_generation': 3, 'blob': b'\x00\x01', 'nested': {'a': [1, 2.5, None]}},
        ('control', 'c0'): {'p0_active': True, 'p0_service': 1.5, 'p0_batch_available_at': 10.0},
    }
    mirrored = {t: _count(t, 'write', 'mirrored') for t, _ in docs}
    matched = {t: _count(t, 'read', 'match') for t, _ in docs}

    store.run(lambda tx: [tx.put(t, k, v) for (t, k), v in docs.items()])
    assert store.drain(30)
    with pool.connection() as conn:
        for (table, key), value in docs.items():
            assert shadow.read_doc(conn, table, key) == value

    read = store.run(lambda tx: {(t, k): tx.get(t, k) for (t, k) in docs})
    assert store.drain(30)
    assert type(read[('queues', '0_owner')]['updated_at']).__name__ == 'DatetimeWithNanoseconds'
    for table, _ in docs:
        assert _count(table, 'write', 'mirrored') == mirrored[table] + 1
        assert _count(table, 'read', 'match') == matched[table] + 1


# Package C exercises the serving implementation, not a second hand-written SQL query.
READ_CASES = [
    ('due', ('retry', 10, 2), {}),
    ('oldest', (1,), {}),
    ('oldest', (1,), {'ready_only': True}),
    ('oldest_retry', (1,), {}),
    ('oldest_admissible_ready', (1, 10), {}),
    ('ready_for_capacity', (1, 10), {}),
    ('control_candidate', (1, 'batch', 10), {'worker_id': 'synthetic', 'exclude': ('b',)}),
    ('control_candidates', (1, 'batch', 10), {'worker_id': 'synthetic', 'fanout': 2}),
    ('fresh_pending', ('owner', 2), {}),
    ('longest_ready_pending', ('owner',), {}),
    ('held_merge_owners', (2,), {}),
    ('held_merge_owners', (2,), {'after': 'owner'}),
    ('projection_pending', (2,), {}),
    ('projection_page', (2,), {}),
    ('projection_page', (2,), {'after': (1.0, 'a')}),
    ('projection_page', (2,), {'due_before': 10}),
    ('projection_successor', ('owner', None), {}),
    ('projection_successor', ('owner', 'a'), {}),
    ('projection_successor', ('owner', 'absent'), {}),
]
TX_READ_CASES = [
    ('get', ('queues', 'q'), {}),
    ('get', ('jobs', 'absent'), {}),
    ('first_pending', ('owner',), {}),
    ('first_ready_pending', ('owner',), {}),
    ('ready_predecessor', ('owner', 1, 'target'), {}),
    ('service_frontier', (1,), {}),
]


def _seed_queries(store):
    rows = {}
    for key, state in [('a', 'ready'), ('b', 'retry'), ('r', 'result_ready')]:
        rows['jobs', key] = {
            'segment_id': key,
            'owner_key': 'owner',
            'owner_id': 'synthetic',
            'state': state,
            'priority': 1,
            'capture_at': 1.0,
            'enqueued_at': 1.0,
            'available_at': 1.0,
            'retry_started_at': 1.0,
            'merge_pending': True,
            'fresh_capture': True,
            'next': 'target',
            'ready_at': 2.0,
            'compute_decision': {'outcome': 'unattempted'},
        }
        rows['results', key] = {
            'segment_id': key,
            'owner_key': 'owner',
            'projection_state': 'pending',
            'previous_segment_id': None if key == 'a' else 'a',
            'committed_at': 1.0,
            'projection_finish_due_at': 5.0,
        }
    rows['queues', 'q'] = {'head': 'a', 'tail': 'r', 'nullable': None}
    rows['merge_holds', 'owner'] = {'held': True}
    for key in ['a', 'b']:
        rows['control', key] = {'p1_active': True, 'p1_service': 1.0, 'p1_batch_available_at': 1.0}
    for (table, key), value in rows.items():
        store.primary.client.collection(f'{store.namespace}_{table}').document(key).set(value)
    store.refresh(list(rows))
    assert store.drain(30)


@pytest.mark.parametrize('query,args,kwargs', READ_CASES + TX_READ_CASES)
@pytest.mark.parametrize('populated', [False, True])
def test_frozen_actual_serving_methods_equal_firestore(dual, query, args, kwargs, populated):
    from database.jobstore.serving_parity import TRANSACTION_QUERIES, compare_serving_query

    store, shadow, _ = dual
    if populated:
        _seed_queries(store)
    assert (
        compare_serving_query(
            store.primary,
            shadow,
            query,
            *args,
            transaction=query in TRANSACTION_QUERIES,
            budget_s=5,
            **kwargs,
        )
        == 'match'
    )


def test_actual_query_drift_is_a_failure_and_mutations_are_refused(dual):
    from database.jobstore.serving_parity import compare_serving_query

    store, shadow, pool = dual
    _seed_queries(store)
    with pool.connection() as conn:
        shadow.delete_doc(conn, 'jobs', 'b')
    assert compare_serving_query(store.primary, shadow, 'due', 'retry', 10, 100, budget_s=5) == 'mismatch'
    with pytest.raises(ValueError, match='serving reads'):
        compare_serving_query(store.primary, shadow, 'acquire_pull_claim', 'a', 'token', 10, 30)


def test_complete_census_includes_claims_and_holds_without_claiming_on_pg(dual, monkeypatch):
    from database.jobstore.backfill import backfill
    from database.jobstore.dual_store import MIRRORED_TABLES

    store, shadow, _ = dual
    monkeypatch.setattr(shadow, 'acquire_pull_claim', lambda *a: pytest.fail('shadow must never claim'))
    assert store.acquire_pull_claim('scheduler_00', 'synthetic-token', 10, 30)
    store.run(lambda tx: tx.put('merge_holds', 'owner', {'held': True}))
    assert store.drain(30)
    report = backfill(store, store.primary.client, sorted(MIRRORED_TABLES), apply=False)
    assert report['pull_claims']['match'] == report['merge_holds']['match'] == 1
    assert not any(row['missing'] or row['mismatch'] or row['postgres_only'] for row in report.values())


@pytest.mark.parametrize('missing', [True, False], ids=['missing', 'null'])
@pytest.mark.parametrize(
    'query,args,kwargs',
    [
        ('fresh_pending', ('owner', 2), {}),
        ('longest_ready_pending', ('owner',), {}),
        ('projection_successor', ('owner', None), {}),
        ('projection_page', (1,), {'after': (1.0, '')}),
        ('held_merge_owners', (1,), {'after': 'owner'}),
    ],
)
def test_null_missing_and_inclusive_cursor_cases(dual, missing, query, args, kwargs):
    from database.jobstore.serving_parity import compare_serving_query

    store, shadow, _ = dual
    _seed_queries(store)
    client = store.primary.client
    ref = client.collection(f'{store.namespace}_jobs').document('r')
    doc = ref.get().to_dict()
    if missing:
        doc.pop('ready_at')
    else:
        doc['ready_at'] = None
    ref.set(doc)
    ref = client.collection(f'{store.namespace}_results').document('a')
    doc = ref.get().to_dict()
    if missing:
        doc.pop('previous_segment_id')
    else:
        doc['previous_segment_id'] = None
    ref.set(doc)
    store.refresh([('jobs', 'r'), ('results', 'a')])
    assert store.drain(30)
    assert compare_serving_query(store.primary, shadow, query, *args, budget_s=5, **kwargs) == 'match'


def test_opt_in_observation_runs_actual_queries_and_preserves_primary_result(dual, monkeypatch):
    from database.jobstore.serving_parity import SERVING_PARITY_TOTAL

    store, _, _ = dual
    _seed_queries(store)
    metric = SERVING_PARITY_TOTAL.labels(query='due', outcome='match')
    before = metric._value.get()
    monkeypatch.setenv('JOBSTORE_SHADOW_QUERY_PARITY', 'on')
    assert store.due('retry', 10, 100) == ['b']
    assert store.drain(30)
    assert metric._value.get() == before + 1
