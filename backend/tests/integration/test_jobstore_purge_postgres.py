"""A5: batch privacy erasure reaches the Postgres copy synchronously, not through the best-effort mirror.

The primary is the simulator store; the shadow is a real ``PostgresStore`` (local Postgres, or the staging
database via OMI_TEST_POSTGRES_IAM). Each case first lets the mirror copy an owner's rows, then removes them
from the primary *without* a mirror refresh (the dropped-refresh case a full queue or the 200 ms budget can
cause), and requires ``purge_owner_now`` to leave Postgres holding exactly the primary's state.
"""

from __future__ import annotations

import uuid

import pytest

from config.batch_pipeline import scheduler_control_key
from database.batch_pipeline_privacy import privacy_owner_key
from testing.pipeline_sim.store import CustomerData, SimStore
from testing.store_fixtures import BackendUnavailable, postgres_connect, required_backends

pytestmark = pytest.mark.integration


@pytest.fixture
def stores():
    from database.jobstore.connection import Pool
    from database.jobstore.dual_store import DualStore
    from database.jobstore.postgres_store import PostgresStore

    try:
        connect = postgres_connect()
    except BackendUnavailable as exc:
        if 'postgres' in required_backends():
            pytest.fail(f'required postgres backend unavailable: {exc}')
        pytest.skip(str(exc))
    namespace = f'batch_pipeline_test_{uuid.uuid4().hex[:12]}'
    customer = CustomerData()
    primary = SimStore(customer, namespace=namespace)
    pool = Pool('', connect=connect)
    shadow = PostgresStore(namespace, pool=pool, customer_client=customer.client, harness_customer_tables=True)
    dual = DualStore(primary, shadow, inline=True)
    yield customer, primary, shadow, dual
    shadow.purge_namespace()
    pool.close()


def _owner_rows(uid: str, segment: str) -> list[tuple[str, str, dict]]:
    key = privacy_owner_key(uid)
    job = {'segment_id': segment, 'owner_id': uid, 'owner_key': key, 'priority': 1, 'state': 'committed'}
    return [
        ('jobs', segment, job),
        ('results', segment, {'segment_id': segment, 'owner_key': key, 'projection_state': 'completed'}),
        ('owners', key, {'revision': 1, 'projection_watermark': segment}),
        ('queues', f'1_{key}', {'head': '', 'tail': ''}),
        ('intakes', f'in-{segment}', {'owner_key': key, 'segment_ids': [segment]}),
        ('artifacts', f'ar-{segment}', {'owner_id': uid, 'segment_id': segment}),
    ]


def _write(dual, rows) -> None:
    def body(tx):
        for table, key, doc in rows:
            tx.put(table, key, doc)

    dual.run(body)


def _postgres(shadow, table: str, key: str) -> dict:
    with shadow.pool.connection() as conn:
        return shadow.read_doc(conn, table, key)


def test_account_purge_erases_rows_the_mirror_never_heard_about(stores):
    customer, primary, shadow, dual = stores
    gone, kept = 'synthetic-gone', 'synthetic-kept'
    for uid in (gone, kept):
        customer.add_user(uid)
    rows, others = _owner_rows(gone, 'g1') + _owner_rows(gone, 'g2'), _owner_rows(kept, 'k1')
    _write(dual, rows + others)
    assert all(_postgres(shadow, table, key) for table, key, _ in rows)

    for table, key, _ in rows:  # the primary's purge, with every mirror refresh dropped
        primary.delete(table, key)

    reconciled = dual.purge_owner_now(gone)
    assert reconciled >= len({(table, key) for table, key, _ in rows})
    assert not any(_postgres(shadow, table, key) for table, key, _ in rows)
    assert all(_postgres(shadow, table, key) == primary.get(table, key) != {} for table, key, _ in others)


def test_conversation_purge_leaves_postgres_equal_to_the_erased_primary(stores):
    customer, primary, shadow, dual = stores
    uid = 'synthetic-conversation'
    customer.add_user(uid)
    rows = _owner_rows(uid, 'c1')
    _write(dual, rows)
    erased = {'segment_id': 'c1', 'owner_key': privacy_owner_key(uid), 'projection_state': 'erased'}
    primary.apply(('results', 'c1'), erased)  # a conversation purge keeps an erased result for ordering
    primary.delete('artifacts', 'ar-c1')

    dual.purge_owner_now(uid)
    assert _postgres(shadow, 'results', 'c1') == erased
    assert _postgres(shadow, 'artifacts', 'ar-c1') == {}
    assert _postgres(shadow, 'jobs', 'c1') == primary.get('jobs', 'c1')


def test_shard_control_is_reconciled_with_the_owner(stores):
    customer, primary, shadow, dual = stores
    uid = 'synthetic-shard'
    customer.add_user(uid)
    shard = scheduler_control_key(privacy_owner_key(uid))
    _write(dual, [('control', shard, {'rings': {'1': [f'1_{privacy_owner_key(uid)}']}, 'p1_active': True})])
    primary.apply(('control', shard), {'rings': {'1': []}, 'p1_active': False})  # fairness purge, refresh dropped

    dual.purge_owner_now(uid)
    assert _postgres(shadow, 'control', shard) == {'rings': {'1': []}, 'p1_active': False}


def test_a_failed_reconcile_raises_so_the_deletion_retries(stores, monkeypatch):
    customer, primary, shadow, dual = stores
    uid = 'synthetic-failure'
    customer.add_user(uid)
    _write(dual, _owner_rows(uid, 'f1'))

    def fail(*args, **kwargs):
        raise RuntimeError('postgres unavailable')

    monkeypatch.setattr(dual, 'copy_current', fail)
    with pytest.raises(RuntimeError):
        dual.purge_owner_now(uid)
