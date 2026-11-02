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
    for table in ('queues', 'owners', 'control'):
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
