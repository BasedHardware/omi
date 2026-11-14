"""Dark typed workload and committed-prefix checks on real local PostgreSQL."""

from uuid import uuid4
import pytest

from database.jobstore.authority import (
    AuthorityRefused,
    transition,
    committed_prefix,
    journal,
    stop_copier,
    replay_page,
)
from database.jobstore.units import Units
from database.privacy_fence import Fence, owner_key
from database.jobstore.connection import Pool
from testing.store_fixtures import postgres_connect

pytestmark = pytest.mark.integration


@pytest.fixture
def source():
    pool = Pool('', size=2, connect=postgres_connect())
    ns = 'batch_pipeline_test_' + uuid4().hex
    fence = Fence(pool)
    owner = owner_key(ns)
    before = fence.snapshot(owner)
    with pool.connection() as conn, conn.transaction():
        admission = fence.admit(conn, owner, before, 'synthetic')
        conn.execute('INSERT INTO queue_authority(namespace) VALUES (%s)', (ns,))
        transition(conn, ns, 'FS_OPEN', 0, 'FS_CLOSING')
        transition(conn, ns, 'FS_CLOSING', 1, 'BOTH_CLOSED')
        ticket = transition(conn, ns, 'BOTH_CLOSED', 2, 'PG_OPEN')
    yield Units(pool, fence, ticket), owner, admission
    pool.close()


def seed(store, owner, admission, identity, *, total=2, fresh=True):
    with store.pool.connection() as conn, conn.transaction():
        return store.admit(
            conn,
            identity,
            owner,
            'recording',
            admission,
            capture_at=100,
            units_total=total,
            custody_deadline=10000,
            fresh=fresh,
            owner_turn=1,
            now=100,
        )


def test_corrected_schema_class_and_terminal_counter(source):
    store, owner, admission = source
    assert seed(store, owner, admission, 'fresh')
    assert not seed(store, owner, admission, 'fresh')
    assert seed(store, owner, admission, 'backlog', fresh=False)
    claimed = store.claim(2, now=100, lease_seconds=20, backlog_share=1)
    assert [row['class'] for row in claimed] == [0, 1]
    for row in claimed:
        state = 'quarantined' if row['class'] else 'result_ready'
        assert store.settle(row['unit_id'], row['attempt_token'], state, None, now=101, partial_wait=60)
        assert not store.settle(row['unit_id'], row['attempt_token'], state, None, now=101, partial_wait=60)
    with store.pool.connection() as conn:
        assert conn.execute(
            'SELECT units_final,units_total FROM recordings WHERE namespace=%s', (store.namespace,)
        ).fetchone() == (2, 2)
        assert conn.execute('SELECT count(*) FROM outbox WHERE namespace=%s', (store.namespace,)).fetchone()[0] == 1


def test_unresolved_paid_outcome_is_held_not_sent_twice(source):
    store, owner, admission = source
    seed(store, owner, admission, 'one')
    (first,) = store.claim(1, now=100, lease_seconds=20, backlog_share=0)
    assert not store.heartbeat('one', 'wrong', now=101, lease_seconds=20)
    assert store.heartbeat('one', first['lease_token'], now=101, lease_seconds=20)
    assert store.claim(1, now=122, lease_seconds=20, backlog_share=0) == []
    with store.pool.connection() as conn:
        assert (
            conn.execute('SELECT hold_reason FROM units WHERE namespace=%s', (store.namespace,)).fetchone()[0]
            == 'vendor'
        )


def test_rolled_back_journal_allocation_leaves_no_committed_gap(source):
    store, owner, _ = source
    with store.pool.connection() as conn:
        with pytest.raises(RuntimeError):
            with conn.transaction():
                assert journal(conn, store.ticket, 'test', {'key': 'one'}, owner, {}) == 1
                raise RuntimeError('kill before COMMIT')
        with conn.transaction():
            assert committed_prefix(conn, store.namespace) == 0
            assert journal(conn, store.ticket, 'test', {'key': 'two'}, owner, {}) == 1
        assert conn.execute('SELECT seq FROM queue_journal WHERE namespace=%s', (store.namespace,)).fetchall() == [(1,)]


def test_stale_epoch_and_uncertified_reverse_open_refused(source):
    store, owner, admission = source
    with store.pool.connection() as conn, conn.transaction():
        transition(conn, store.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
    with pytest.raises(AuthorityRefused):
        seed(store, owner, admission, 'stale')
    with store.pool.connection() as conn, conn.transaction(), pytest.raises(AuthorityRefused):
        transition(conn, store.namespace, 'BOTH_CLOSED', 5, 'FS_OPEN')


def test_stop_preserves_checkpoint(source):
    store, _, _ = source
    with store.pool.connection() as conn, conn.transaction():
        assert stop_copier(conn, store.namespace) == (0, 0)


def test_copier_stop_during_sink_io_never_advances_checkpoint(source):
    store, owner, admission = source
    seed(store, owner, admission, 'one')
    with store.pool.connection() as conn, conn.transaction():
        conn.execute('UPDATE queue_authority SET copier_stopped=false WHERE namespace=%s', (store.namespace,))

    def sink(row, *, timeout):
        assert 0 < timeout <= 1.5
        with store.pool.connection() as conn, conn.transaction():
            stop_copier(conn, store.namespace)

    assert replay_page(store.pool, store.namespace, sink) > 0
    with store.pool.connection() as conn:
        assert (
            conn.execute('SELECT applied_seq FROM queue_authority WHERE namespace=%s', (store.namespace,)).fetchone()[0]
            == 0
        )


def test_lost_reverse_ack_preserves_durable_checkpoint(source):
    store, owner, admission = source
    seed(store, owner, admission, 'one')
    with store.pool.connection() as conn, conn.transaction():
        conn.execute('UPDATE queue_authority SET copier_stopped=false WHERE namespace=%s', (store.namespace,))

    def sink(row, *, timeout):
        raise RuntimeError('lost sink COMMIT response')

    with pytest.raises(RuntimeError):
        replay_page(store.pool, store.namespace, sink)
    with store.pool.connection() as conn:
        assert (
            conn.execute('SELECT applied_seq FROM queue_authority WHERE namespace=%s', (store.namespace,)).fetchone()[0]
            == 0
        )


def test_old_sql_image_without_epoch_cannot_mutate_registered_queue(source):
    store, owner, admission = source
    seed(store, owner, admission, 'one')
    with store.pool.connection() as conn, pytest.raises(Exception, match='epoch refused'):
        with conn.transaction():
            conn.execute("UPDATE units SET hold_reason='vendor' WHERE namespace=%s", (store.namespace,))


def test_closed_and_expired_admissions_do_not_poison_other_owners_claims(source):
    from datetime import timedelta
    from database.jobstore.authority import acquire
    from database.jobstore.postgres_store import jsonb

    store, closed_owner, closed_admission = source
    seed(store, closed_owner, closed_admission, 'closed', total=1)
    store.fence.close(closed_owner, local=True)
    for identity in ('expired', 'healthy'):
        owner = owner_key(store.namespace + identity)
        before = store.fence.snapshot(owner)
        with store.pool.connection() as conn, conn.transaction():
            admission = store.fence.admit(conn, owner, before, 'synthetic')
            store.admit(
                conn,
                identity,
                owner,
                identity,
                admission,
                capture_at=100,
                units_total=1,
                custody_deadline=10000,
                fresh=True,
                owner_turn=1,
                now=100,
            )
            if identity == 'expired':
                admission['admitted_at'] -= timedelta(minutes=20)
                acquire(conn, store.ticket)
                conn.execute(
                    'UPDATE units SET admission=%s WHERE namespace=%s AND unit_id=%s',
                    (jsonb(admission), store.namespace, identity),
                )
    assert [job['unit_id'] for job in store.claim(3, now=100, lease_seconds=20, backlog_share=0)] == ['healthy']
    assert store.claim(3, now=101, lease_seconds=20, backlog_share=0) == []
    with store.pool.connection() as conn:
        assert conn.execute(
            'SELECT unit_id,hold_reason,state FROM units WHERE namespace=%s ORDER BY unit_id', (store.namespace,)
        ).fetchall() == [
            ('closed', 'privacy_deferred', 'pending'),
            ('expired', 'privacy_deferred', 'pending'),
            ('healthy', None, 'pending'),
        ]


def test_restore_admission_and_claim_do_not_invert_owner_namespace_locks(source):
    import threading
    import time

    store, owner, old = source
    seed(store, owner, old, 'old', total=1)
    store.fence.close(owner, local=True)
    before = store.fence.snapshot(owner)
    held, release = threading.Event(), threading.Event()
    errors = []

    def restore():
        try:
            with store.pool.connection() as conn, conn.transaction():
                admission = store.fence.admit(conn, owner, before, 'restored')
                held.set()
                assert release.wait(5)
                store.admit(
                    conn,
                    'new',
                    owner,
                    'new-recording',
                    admission,
                    capture_at=101,
                    units_total=1,
                    custody_deadline=10000,
                    fresh=True,
                    owner_turn=2,
                    now=101,
                )
        except Exception as error:
            errors.append(error)

    def claim():
        try:
            store.claim(1, now=102, lease_seconds=20, backlog_share=0)
        except Exception as error:
            errors.append(error)

    producer = threading.Thread(target=restore)
    consumer = threading.Thread(target=claim)
    producer.start()
    assert held.wait(5)
    consumer.start()
    # A separate synthetic connection observes the blocked privacy lock. This
    # establishes the interleaving without sleeping while holding a pool slot.
    observer = postgres_connect()()
    try:
        deadline = time.monotonic() + 1.5
        waiting = False
        while time.monotonic() < deadline:
            waiting = bool(
                observer.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted").fetchone()[
                    0
                ]
            )
            if waiting:
                break
            time.sleep(0.01)
    finally:
        release.set()
        observer.close()
        producer.join(6)
        consumer.join(6)
    assert waiting and not producer.is_alive() and not consumer.is_alive()
    assert not errors
    assert [job['unit_id'] for job in store.claim(1, now=103, lease_seconds=20, backlog_share=0)] == ['new']
