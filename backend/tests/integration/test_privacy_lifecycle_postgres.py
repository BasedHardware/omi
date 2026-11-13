"""G2 durable drain / A9 restore against loopback Firestore and real PostgreSQL."""

import os
import subprocess
import sys
from uuid import uuid4

import pytest

from database.jobstore.authority import transition
from database.jobstore.connection import Pool
from database.jobstore.units import Units
from database.privacy_fence import Fence, Lifecycle, owner_key, conversation_key
from testing.jobstore_cutover import local_only
from testing.store_fixtures import postgres_connect, _emulator_client, ClientCustomerData

pytestmark = pytest.mark.integration


@pytest.fixture
def source():
    local_only()
    pool = Pool('', size=2, connect=postgres_connect())
    client = _emulator_client()
    uid = 'lifecycle-' + uuid4().hex
    customer = ClientCustomerData(client)
    customer.add_user(uid)
    customer.add_conversation(uid, 'c')
    customer.add_conversation(uid, 'other')
    fence = Fence(pool)
    owner = owner_key(uid)
    admission = fence.admit_from_authority(client, uid, ['c'], lambda *_: None)
    ns = 'batch_pipeline_test_' + uuid4().hex
    with pool.connection() as conn, conn.transaction():
        conn.execute('INSERT INTO queue_authority(namespace) VALUES (%s)', (ns,))
        transition(conn, ns, 'FS_OPEN', 0, 'FS_CLOSING')
        transition(conn, ns, 'FS_CLOSING', 1, 'BOTH_CLOSED')
        ticket = transition(conn, ns, 'BOTH_CLOSED', 2, 'PG_OPEN')
    store = Units(pool, fence, ticket)
    yield store, client, uid, owner, admission
    pool.close()
    client.close()


def register(source, *, kind='provider', started=False, admission=None, sink=None):
    store, _, _, owner, original = source
    with store.pool.connection() as conn, conn.transaction():
        identity = store.fence.register(
            conn, owner, uuid4().hex, admission or original, kind, lease_seconds=120, sink=sink
        )
        if started:
            store.fence.start(conn, owner, identity, admission or original)
    return identity


def expire_effect(source, effect):
    with source[0].pool.connection() as conn, conn.transaction():
        conn.execute(
            "UPDATE privacy_effect_inflight SET lease_until=now()-interval '1 second' WHERE effect_id=%s",
            (effect,),
        )


def unit(source, identity='unit'):
    store, _, _, owner, admission = source
    with store.pool.connection() as conn, conn.transaction():
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


def test_close_and_drain_task_survive_process_exit_before_wake(source):
    store, _, _, owner, _ = source
    effect = register(source)
    with store.pool.connection() as conn:
        dsn = conn.info.dsn
    # The fixture DSN is private/local. The child exits without returning a
    # close acknowledgement or emitting a wake; the parent is the restarted runner.
    command = """
import os
import testing.pipeline_sim._env
from database.jobstore.connection import Pool
from database.privacy_fence import Fence
pool = Pool(os.environ['OMI_LIFECYCLE_CHILD_DSN'], size=1)
Fence(pool).close(os.environ['OMI_LIFECYCLE_CHILD_OWNER'], local=True)
os._exit(86)
"""
    result = subprocess.run(
        [sys.executable, '-c', command],
        env={**os.environ, 'OMI_LIFECYCLE_CHILD_DSN': dsn, 'OMI_LIFECYCLE_CHILD_OWNER': owner},
        timeout=15,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 86, result.stderr
    assert Lifecycle(store.fence).close_pass(owner=owner) == 1
    with store.pool.connection() as conn:
        assert conn.execute('SELECT count(*) FROM privacy_close_drain WHERE owner_key=%s', (owner,)).fetchone()[0] == 0
        assert not conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (effect,)).fetchone()


@pytest.mark.parametrize('gap', ['before_close_commit', 'after_claim', 'after_retire', 'after_ack'])
def test_restart_at_real_drain_commit_gaps(source, gap):
    store, _, _, owner, admission = source
    effect = register(source)
    with store.pool.connection() as conn:
        dsn = conn.info.dsn
    if gap != 'before_close_commit':
        store.fence.close(owner, local=True)
    command = """
import os
import testing.pipeline_sim._env
from database.jobstore.connection import Pool
from database.privacy_fence import Fence
from database.privacy_fence.lifecycle import Lifecycle
pool = Pool(os.environ['OMI_LIFECYCLE_CHILD_DSN'], size=1)
owner = os.environ['OMI_LIFECYCLE_CHILD_OWNER']
gap = os.environ['OMI_LIFECYCLE_CHILD_GAP']
fence = Fence(pool)
if gap == 'before_close_commit':
    # Exit after the real close's final SQL statement, before its context
    # manager can COMMIT. The server rolls back both close and task.
    original = pool._connect
    class ExitAtTask:
        def __init__(self, conn):
            self.conn = conn
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def execute(self, query, *args, **kwargs):
            result = self.conn.execute(query, *args, **kwargs)
            if 'INSERT INTO privacy_close_drain' in query:
                os._exit(86)
            return result
    pool._connect = lambda: ExitAtTask(original())
    fence.close(owner, local=True)
    raise AssertionError('did not reach real close commit gap')
runner = Lifecycle(fence)
task = runner.claim(owner=owner)
assert task
if gap == 'after_claim':
    os._exit(86)
remaining = fence.drain_pass(owner, before_seq=task['seq'])
assert remaining == 0
if gap == 'after_retire':
    os._exit(86)
assert runner.finish(task, remaining=remaining)
os._exit(86)
"""
    result = subprocess.run(
        [sys.executable, '-c', command],
        env={
            **os.environ,
            'OMI_LIFECYCLE_CHILD_DSN': dsn,
            'OMI_LIFECYCLE_CHILD_OWNER': owner,
            'OMI_LIFECYCLE_CHILD_GAP': gap,
        },
        timeout=15,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 86, result.stderr
    if gap == 'before_close_commit':
        with store.pool.connection() as conn, conn.transaction():
            store.fence.check_work_write(conn, owner, admission)
            assert conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (effect,)).fetchone()
            assert not conn.execute('SELECT 1 FROM privacy_close_drain WHERE owner_key=%s', (owner,)).fetchone()
    else:
        # Takeover after lease expiry, using an entirely new runner instance.
        with store.pool.connection() as conn, conn.transaction():
            conn.execute(
                "UPDATE privacy_close_drain SET lease_until=now()-interval '1 second' WHERE owner_key=%s", (owner,)
            )
        assert Lifecycle(store.fence).close_pass(owner=owner) == int(gap != 'after_ack')
        with store.pool.connection() as conn:
            assert not conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (effect,)).fetchone()
            assert not conn.execute('SELECT 1 FROM privacy_close_drain WHERE owner_key=%s', (owner,)).fetchone()


def test_task_takeover_fences_stale_ack_and_replays_lost_ack(source):
    store, _, _, owner, _ = source
    register(source)
    store.fence.close(owner, local=True)
    first_runner = Lifecycle(store.fence)
    first = first_runner.claim(owner=owner)
    assert first is not None
    # Crash while leased. A new runner takes over only after lease expiry.
    with store.pool.connection() as conn, conn.transaction():
        conn.execute(
            "UPDATE privacy_close_drain SET lease_until=now()-interval '1 second' WHERE owner_key=%s", (owner,)
        )
    second_runner = Lifecycle(store.fence)
    second = second_runner.claim(owner=owner)
    assert second and second['lease_token'] != first['lease_token']
    remaining = store.fence.drain_pass(owner, before_seq=second['seq'])
    assert remaining == 0
    assert not first_runner.finish(first, remaining=0)
    # Lost acknowledgement after successful DELETE: re-reading/replaying the
    # terminal task does not recreate it or a registry capability.
    assert second_runner.finish(second, remaining=0)
    assert not second_runner.finish(second, remaining=0)
    assert second_runner.claim(owner=owner) is None


def test_old_close_task_never_retires_post_restore_effects(source):
    store, client, uid, owner, _ = source
    old = register(source)
    store.fence.close(owner, local=True)
    fresh = store.fence.admit_from_authority(client, uid, ['c'], lambda *_: None)
    new = register(source, admission=fresh)
    assert Lifecycle(store.fence).close_pass(owner=owner) == 1
    with store.pool.connection() as conn, conn.transaction():
        assert not conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (old,)).fetchone()
        store.fence.start(conn, owner, new, fresh)
        assert store.fence.complete(conn, owner, new, fresh, lambda _: None)


def test_conversation_task_does_not_retire_another_conversations_effect(source):
    store, client, uid, owner, _ = source
    other_admission = store.fence.admit_from_authority(client, uid, ['other'], lambda *_: None)
    affected = register(source)
    unrelated = register(source, admission=other_admission, started=True)
    store.fence.close(owner, local=True, conversation=conversation_key(owner, 'c'), state='deleted')
    assert Lifecycle(store.fence).close_pass(owner=owner) == 1
    with store.pool.connection() as conn, conn.transaction():
        assert not conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (affected,)).fetchone()
        assert store.fence.complete(conn, owner, unrelated, other_admission, lambda _: None)


def test_registered_rows_cannot_hide_behind_a_page_of_unexpired_started_rows(source):
    store, _, _, owner, _ = source
    for _ in range(100):
        register(source, started=True)
    waiting = register(source)
    store.fence.close(owner, local=True)
    assert store.fence.drain_pass(owner) == 100
    with store.pool.connection() as conn:
        assert not conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (waiting,)).fetchone()


def test_open_owner_janitor_retains_gcs_until_terminal_proof(source):
    store, _, _, owner, _ = source
    effect = register(source, kind='gcs_put', started=True, sink={'session': 'synthetic-only'})
    expire_effect(source, effect)
    assert Lifecycle(store.fence).janitor_pass() >= 1
    with store.pool.connection() as conn:
        assert conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (effect,)).fetchone()
        assert conn.execute(
            'SELECT maintenance_after>now() FROM privacy_effect_inflight WHERE effect_id=%s', (effect,)
        ).fetchone()[0]
        conn.execute('UPDATE privacy_effect_inflight SET maintenance_after=now() WHERE effect_id=%s', (effect,))
    # This adapter is a synthetic proof source, not a real C4 sink claim.
    assert Lifecycle(store.fence, fence_gcs=lambda _: True).janitor_pass() >= 1
    with store.pool.connection() as conn:
        assert not conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (effect,)).fetchone()


@pytest.mark.parametrize(
    'kind,started',
    [('provider', False), ('provider', True), ('vector', False), ('vector', True), ('push', True), ('outbox', True)],
)
def test_open_owner_janitor_terminal_lifecycle_deletes_registry_and_only_retains_vector_residue(source, kind, started):
    store, _, _, owner, admission = source
    effect = register(source, kind=kind, started=started)
    expire_effect(source, effect)
    assert Lifecycle(store.fence).janitor_pass() >= 1
    with store.pool.connection() as conn, conn.transaction():
        store.fence.check_work_write(conn, owner, admission)
        assert not conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (effect,)).fetchone()
        assert conn.execute('SELECT count(*) FROM privacy_residue_target WHERE owner_key=%s', (owner,)).fetchone()[
            0
        ] == int(kind == 'vector' and started)


def test_stuck_gcs_owner_cannot_monopolize_bounded_janitor_pages(source):
    store, client, uid, _, _ = source
    blocked = register(source, kind='gcs_put', started=True, sink={'session': 'synthetic-only'})
    other_uid = uid + '-other'
    customer = ClientCustomerData(client)
    customer.add_user(other_uid)
    other_owner = owner_key(other_uid)
    other = store.fence.admit_from_authority(client, other_uid, [], lambda *_: None)
    with store.pool.connection() as conn, conn.transaction():
        healthy = store.fence.register(conn, other_owner, 'job', other, 'provider', lease_seconds=120)
        conn.execute(
            "UPDATE privacy_effect_inflight SET lease_until=now()-interval '2 seconds' WHERE effect_id=%s", (blocked,)
        )
        conn.execute(
            "UPDATE privacy_effect_inflight SET lease_until=now()-interval '1 second' WHERE effect_id=%s", (healthy,)
        )
    runner = Lifecycle(store.fence)
    assert runner.janitor_pass(limit=1) == 1
    assert runner.janitor_pass(limit=1) == 1
    with store.pool.connection() as conn:
        assert conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (blocked,)).fetchone()
        assert not conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (healthy,)).fetchone()


@pytest.mark.parametrize('paid', [False, True])
def test_restore_mints_new_admission_and_never_adopts_old_paid_result(source, paid):
    store, client, uid, owner, old = source
    unit(source)
    claim = store.claim(1, now=100, lease_seconds=20, backlog_share=0)[0] if paid else None
    store.fence.close(owner, local=True)
    # An expired paid attempt is still selected for refusal status before it can
    # be considered for dispatch; its attempt token remains durable.
    assert store.claim(1, now=121, lease_seconds=20, backlog_share=0) == []
    assert store.readmit(client, uid, ['c'], 'unit')
    with store.pool.connection() as conn:
        current = store._unit(conn, 'unit')
        assert current['admission']['admission_id'] != old['admission_id']
        assert current['hold_reason'] == ('vendor' if paid else None)
        assert current['attempt_token'] == (claim['attempt_token'] if paid else None)
        assert (str(current['attempt_admission_id']) if paid else None) == (old['admission_id'] if paid else None)
        assert (
            str(
                conn.execute(
                    'SELECT admission_id FROM queue_custody WHERE namespace=%s AND identity=%s',
                    (store.namespace, 'unit'),
                ).fetchone()[0]
            )
            == current['admission']['admission_id']
        )
    if paid:
        assert not store.settle(
            'unit', claim['attempt_token'], 'result_ready', {'late': True}, now=122, partial_wait=60
        )
        assert not store.heartbeat('unit', claim['lease_token'], now=122, lease_seconds=20)
        assert store.claim(1, now=122, lease_seconds=20, backlog_share=0) == []
        with store.pool.connection() as conn:
            assert conn.execute(
                'SELECT units_final FROM recordings WHERE namespace=%s', (store.namespace,)
            ).fetchone() == (0,)
            assert conn.execute('SELECT count(*) FROM outbox WHERE namespace=%s', (store.namespace,)).fetchone() == (0,)
    else:
        new_claim = store.claim(1, now=122, lease_seconds=20, backlog_share=0)[0]
        assert store.settle('unit', new_claim['attempt_token'], 'result_ready', None, now=123, partial_wait=60)
    assert not store.readmit(client, uid, ['c'], 'unit')


def test_unclaimed_unit_cannot_settle_using_a_missing_attempt_token(source):
    store, _, _, _, _ = source
    unit(source)
    assert not store.settle('unit', None, 'result_ready', None, now=101, partial_wait=60)


def test_restore_rechecks_real_deletion_authority_and_original_targets(source):
    store, client, uid, owner, _ = source
    unit(source)
    store.fence.close(owner, local=True)
    store.claim(1, now=121, lease_seconds=20, backlog_share=0)
    # Dropping the original conversation must fail even if the remaining walk
    # allows. The attempted A2 reopen rolls back with its queue mutation.
    from database.jobstore.authority import AuthorityRefused

    with pytest.raises(AuthorityRefused, match='original privacy target'):
        store.readmit(client, uid, [], 'unit')
    ClientCustomerData(client).delete_conversation(uid, 'c')
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    with pytest.raises(BatchPrivacyBlocked):
        store.readmit(client, uid, ['c'], 'unit')
    with store.pool.connection() as conn:
        assert store._unit(conn, 'unit')['hold_reason'] == 'privacy_deferred'


def test_close_drain_does_not_hold_pool_or_exclusive_lock_during_gcs_io(source):
    store, _, _, owner, admission = source
    effect = register(source, kind='gcs_put', started=True, sink={'session': 'synthetic-only'})
    store.fence.close(owner, local=True)
    pool_was_free = []

    def terminal(_):
        # Borrow both slots and the exclusive owner guard during the sink call.
        # A held slot or L_x would block this call rather than silently pass.
        from database.privacy_fence.protocol import lock

        with store.pool.connection(timeout=2) as first, store.pool.connection(timeout=2) as second:
            with first.transaction():
                lock(first, owner, exclusive=True)
                assert second.execute('SELECT 1').fetchone() == (1,)
                pool_was_free.append(True)
        return True

    assert Lifecycle(store.fence, fence_gcs=terminal).close_pass(owner=owner) == 1
    assert pool_was_free == [True]
    with store.pool.connection() as conn, conn.transaction():
        assert not store.fence.complete(conn, owner, effect, admission, lambda _: pytest.fail('late GCS result'))
