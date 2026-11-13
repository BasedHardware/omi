"""G2 primitives against primary PostgreSQL and the real customer-data emulator.

These tests intentionally do not use make_postgres's simulated CustomerData.
They are a source checkpoint, not the complete §5.2 enforcement qualification.
"""

import threading
from uuid import uuid4
from datetime import timedelta

import pytest
from google.api_core.exceptions import AlreadyExists, FailedPrecondition

from database.batch_privacy_write_fence import g2_coordinator
from database.jobstore.connection import Pool
from database.privacy_fence import Fence, FenceRefused, AdmissionChanged, owner_key, conversation_key
from database.privacy_fence.interceptor import Coordinator
from database.privacy_fence.protocol import lock
from testing.store_fixtures import postgres_connect, _emulator_client, ClientCustomerData

pytestmark = pytest.mark.integration


@pytest.fixture
def context():
    client = _emulator_client()
    pool = Pool('', size=2, connect=postgres_connect())
    uid = 'g2-' + uuid4().hex
    customer = ClientCustomerData(client)
    customer.add_user(uid)
    customer.add_conversation(uid, 'c')
    fence = Fence(pool)
    yield fence, client, uid, owner_key(uid)
    pool.close()
    client.close()


def admit(context, keys=()):
    fence, client, uid, owner = context
    # Production walk and token minting are exercised separately; this helper
    # isolates the PG A1/A2 protocol with an explicit synthetic allowing token.
    before = fence.snapshot(owner, keys)
    with fence.pool.connection() as conn, conn.transaction():
        return fence.admit(conn, owner, before, 'synthetic-token', keys)


def test_admission_close_restore_changes_fingerprint(context):
    fence, _, _, owner = context
    old = admit(context)
    seq = fence.close(owner)
    with pytest.raises(FenceRefused):
        fence.snapshot(owner)
    fence.settle(owner, seq, 'landed')
    fresh = admit(context)
    assert old['admission_id'] != fresh['admission_id']
    assert fresh['privacy_generation'] > old['privacy_generation']
    with fence.pool.connection() as conn, conn.transaction(), pytest.raises(AdmissionChanged):
        fence.check_work_write(conn, owner, old)


def test_close_between_a1_a2_cannot_reopen(context):
    fence, _, _, owner = context
    admit(context)
    before = fence.snapshot(owner)
    fence.close(owner, local=True)
    with fence.pool.connection() as conn, conn.transaction(), pytest.raises(AdmissionChanged):
        fence.admit(conn, owner, before, 't')


@pytest.mark.parametrize('started,kind', [(False, 'provider'), (True, 'provider'), (True, 'vector'), (True, 'push')])
def test_close_drain_registry_lifecycle_and_accepted_late_send(context, started, kind):
    fence, _, _, owner = context
    job = admit(context)
    with fence.pool.connection() as conn, conn.transaction():
        effect = fence.register(conn, owner, 'job', job, kind, lease_seconds=120)
        if started:
            fence.start(conn, owner, effect, job)
    fence.close(owner, local=True)
    if started:
        assert fence.drain_pass(owner) == 1
        with fence.pool.connection() as conn, conn.transaction():
            conn.execute(
                "UPDATE privacy_effect_inflight SET lease_until=now()-interval '1 second' WHERE effect_id=%s", (effect,)
            )
    assert fence.drain_pass(owner) == 0
    with fence.pool.connection() as conn, conn.transaction():
        assert not fence.complete(conn, owner, effect, job, lambda _: pytest.fail('late result persisted'))
        count = conn.execute('SELECT count(*) FROM privacy_residue_target WHERE owner_key=%s', (owner,)).fetchone()[0]
        assert count == int(started and kind == 'vector')
    # A sink call after committed START can still happen here. G2 A3 accepts
    # that unbounded transmission; only result persistence is forbidden.


def test_unrelated_conversation_close_blocks_start_but_not_complete(context):
    fence, _, _, owner = context
    key = conversation_key(owner, 'c')
    job = admit(context, [key])
    with fence.pool.connection() as conn, conn.transaction():
        started = fence.register(conn, owner, 'j1', job, 'provider', lease_seconds=120)
        waiting = fence.register(conn, owner, 'j2', job, 'provider', lease_seconds=120)
        fence.start(conn, owner, started, job)
    fence.close(owner, conversation=conversation_key(owner, 'other'), state='deleted', local=True)
    with fence.pool.connection() as conn, conn.transaction(), pytest.raises(FenceRefused):
        fence.start(conn, owner, waiting, job)
    with fence.pool.connection() as conn, conn.transaction():
        assert fence.complete(conn, owner, started, job, lambda _: None)


def test_clock_backward_and_expired_admission_refused(context):
    fence, _, _, owner = context
    job = admit(context)
    for delta in (timedelta(days=1), -timedelta(minutes=16)):
        stale = {**job, 'admitted_at': job['admitted_at'] + delta}
        with fence.pool.connection() as conn, conn.transaction(), pytest.raises(AdmissionChanged):
            fence.check_work_write(conn, owner, stale)


def test_gcs_custody_retained_until_terminal_and_absent(context):
    fence, _, _, owner = context
    job = admit(context)
    with fence.pool.connection() as conn, conn.transaction():
        effect = fence.register(conn, owner, 'j', job, 'gcs_put', lease_seconds=120, sink={'session': 'synthetic'})
        fence.start(conn, owner, effect, job)
    assert fence.drain_pass(owner, janitor=True, fence_gcs=lambda sink: pytest.fail('unexpired session cancelled')) == 1
    fence.close(owner, local=True)
    assert fence.drain_pass(owner, fence_gcs=lambda sink: False) == 1
    assert fence.drain_pass(owner, fence_gcs=lambda sink: True) == 0


def test_protocol_barrier_and_explicit_exclusive_lock(context):
    fence, _, _, owner = context
    admit(context)
    with fence.pool.connection() as conn:
        with pytest.raises(Exception, match='exclusive privacy lock'):
            with conn.transaction():
                conn.execute("UPDATE privacy_owner_fence SET generation=generation+1 WHERE owner_key=%s", (owner,))
        with conn.transaction():
            conn.execute('UPDATE privacy_fence_config SET enforce_protocol=2')
            with pytest.raises(Exception, match='privacy protocol 2'):
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO docs(namespace,tbl,key,doc) VALUES ('batch_pipeline_test_barrier','x','x','{}')"
                    )
            conn.execute('UPDATE privacy_fence_config SET enforce_protocol=1')


def test_close_waits_for_work_commit_and_reads_after_lock(context):
    fence, _, _, owner = context
    job = admit(context)
    entered, release = threading.Event(), threading.Event()
    errors = []

    def writer():
        try:
            with fence.pool.connection() as conn, conn.transaction():
                fence.check_work_write(conn, owner, job)
                entered.set()
                assert release.wait(1)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=writer)
    thread.start()
    assert entered.wait(2)
    release.set()
    fence.close(owner, local=True)
    thread.join(2)
    assert not thread.is_alive() and not errors
    with fence.pool.connection() as conn, conn.transaction(), pytest.raises(FenceRefused):
        fence.check_work_write(conn, owner, job)


def test_real_guard_update_time_and_exact_sequence_kill(context):
    fence, client, uid, owner = context
    admit(context)
    coordinator = Coordinator(client, fence)
    token = g2_coordinator.set(coordinator)
    try:
        client.collection('account_deletions').document(uid).set({'wipe_status': 'pending'})
    finally:
        g2_coordinator.reset(token)
    guard = client.collection('batch_pipeline_privacy_fence').document(owner)
    observed = guard.get()
    assert observed.to_dict()['landed'] == [1]
    assert coordinator.reconcile(owner, 1) == 'landed'
    seq = fence.close(owner, guard_version=observed.update_time)
    assert coordinator.reconcile(owner, seq) == 'abandoned'
    from google.cloud.firestore_v1.types import Document, DocumentMask, Precondition, Write

    with pytest.raises(FailedPrecondition):
        client._firestore_api.commit(
            metadata=client._rpc_metadata,
            request={
                'database': client._database_string,
                'writes': [
                    Write(
                        update=Document(name=guard._document_path),
                        update_mask=DocumentMask(field_paths=[]),
                        current_document=Precondition(update_time=observed.update_time),
                    ),
                ],
            },
        )
    # This establishes emulator behavior only, not equivalence to production.


def test_g2_15a_15b_concurrent_guard_versions_never_settle_by_high_water(context):
    from google.cloud.firestore_v1.types import CommitRequest, Document, Value, Write

    fence, client, uid, owner = context
    admit(context)
    coordinator = Coordinator(client, fence)

    def request():
        return CommitRequest(
            database=client._database_string,
            writes=[
                Write(
                    update=Document(
                        name=client.collection('account_deletions').document(uid)._document_path,
                        fields={'wipe_status': Value(string_value='pending')},
                    )
                )
            ],
        )

    first, second = request(), request()
    assert coordinator.prepare(first) == [(owner, 1)]
    assert coordinator.prepare(second) == [(owner, 2)]
    client._firestore_api.commit(request=second, metadata=client._rpc_metadata)
    # Emulator v1.22 reports exists=false as AlreadyExists, while a stale
    # update_time produces FailedPrecondition. Both refuse the entire Commit.
    with pytest.raises((FailedPrecondition, AlreadyExists)):
        client._firestore_api.commit(request=first, metadata=client._rpc_metadata)
    assert coordinator.reconcile(owner, 2) == 'landed'
    with fence.pool.connection() as conn:
        assert (
            conn.execute('SELECT state FROM privacy_fence_change WHERE owner_key=%s AND seq=1', (owner,)).fetchone()[0]
            == 'pending'
        )
    assert coordinator.reconcile(owner, 1) == 'abandoned'


def test_g2_16b_restore_cannot_adopt_pre_restore_effect(context):
    fence, _, _, owner = context
    old = admit(context)
    with fence.pool.connection() as conn, conn.transaction():
        effect = fence.register(conn, owner, 'j', old, 'provider', lease_seconds=120)
        fence.start(conn, owner, effect, old)
    fence.close(owner, local=True)
    restored = admit(context)
    with fence.pool.connection() as conn, conn.transaction():
        assert not fence.complete(conn, owner, effect, restored, lambda _: pytest.fail('old effect adopted'))


def test_g2_17_seed_race_does_not_upgrade_shared_lock(context):
    fence, _, _, owner = context
    before = fence.snapshot(owner)
    admit(context)
    with fence.pool.connection() as conn, conn.transaction(), pytest.raises(AdmissionChanged):
        fence.admit(conn, owner, before, 't')


def test_full_production_admission_walk_and_detector(context):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    fence, client, uid, owner = context
    persisted = []
    admission = fence.admit_from_authority(client, uid, ['c'], lambda conn, a: persisted.append(a))
    assert persisted == [admission] and admission['admission_version'] == 2
    assert admission['privacy_targets'] == [{'conversation_key': conversation_key(owner, 'c'), 'generation': 0}]
    ClientCustomerData(client).delete_conversation(uid, 'c')
    with pytest.raises(BatchPrivacyBlocked):
        fence.admit_from_authority(client, uid, ['c'], lambda *_: pytest.fail('deleted conversation admitted'))
    with fence.pool.connection() as conn:
        assert (
            conn.execute('SELECT state FROM privacy_conversation_fence WHERE owner_key=%s', (owner,)).fetchone()[0]
            == 'deleted'
        )


@pytest.mark.parametrize('value', [{'status': 'in_progress', 'target_level': 'enhanced'}, {}, False, 0, None])
def test_migration_status_only_explicit_null_is_non_narrowing(context, value):
    fence, client, uid, owner = context
    job = admit(context)
    token = g2_coordinator.set(Coordinator(client, fence))
    try:
        client.collection('users').document(uid).update({'migration_status': value})
    finally:
        g2_coordinator.reset(token)
    with fence.pool.connection() as conn, conn.transaction():
        if value is None:
            fence.check_work_write(conn, owner, job)
        else:
            with pytest.raises(FenceRefused):
                fence.check_work_write(conn, owner, job)


def test_generation_purge_writer_closes_actual_hashed_owner_before_commit(context):
    from database.batch_pipeline_privacy import advance_privacy_generation

    fence, client, uid, owner = context
    job = admit(context)
    token = g2_coordinator.set(Coordinator(client, fence))
    try:
        assert advance_privacy_generation(client, uid, blocked=True) == 1
    finally:
        g2_coordinator.reset(token)
    assert client.collection('batch_pipeline_privacy_fence').document(owner).get().to_dict()['landed'] == [1]
    with fence.pool.connection() as conn, conn.transaction(), pytest.raises(FenceRefused):
        fence.check_work_write(conn, owner, job)


def test_legal_hold_token_rotation_does_not_close_pg_owner(context):
    fence, client, uid, owner = context
    job = admit(context)
    token = g2_coordinator.set(Coordinator(client, fence))
    try:
        client.collection('legal_holds').document(uid).set({'active': True})
    finally:
        g2_coordinator.reset(token)
    with fence.pool.connection() as conn, conn.transaction():
        fence.check_work_write(conn, owner, job)
    assert not client.collection('batch_pipeline_privacy_fence').document(owner).get().exists


def test_redirect_target_is_snapshotted_before_retrying_allowing_walk(context):
    fence, client, uid, owner = context
    customer = ClientCustomerData(client)
    customer.merge_conversation(uid, 'c', 'target')
    admit(context)
    key = conversation_key(owner, 'target')
    fence.close(owner, local=True, conversation=key, state='closed')
    persisted = []
    admission = fence.admit_from_authority(client, uid, ['c'], lambda conn, value: persisted.append(value))
    assert persisted == [admission]
    assert key in {target['conversation_key'] for target in admission['privacy_targets']}
    with fence.pool.connection() as conn, conn.transaction():
        fence.check_work_write(conn, owner, admission)


def test_r14_legacy_marker_denies_admission_and_never_discovers_a_wipe(context):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    fence, client, uid, owner = context
    marker = client.collection('account_deletions').document(uid)
    marker.set({'legacy': True})
    with pytest.raises(BatchPrivacyBlocked):
        fence.admit_from_authority(client, uid, ['c'], lambda *_: pytest.fail('legacy marker admitted'))
    assert marker.get().to_dict() == {'legacy': True}
    with fence.pool.connection() as conn:
        assert (
            conn.execute('SELECT state FROM privacy_owner_fence WHERE owner_key=%s', (owner,)).fetchone()[0] == 'closed'
        )


def test_erased_owner_never_reopens(context):
    fence, _, _, owner = context
    admit(context)
    with fence.pool.connection() as conn, conn.transaction():
        lock(conn, owner, exclusive=True)
        conn.execute(
            "UPDATE privacy_owner_fence SET state='erased',close_reason='deleted',generation=generation+1 "
            'WHERE owner_key=%s',
            (owner,),
        )
    with pytest.raises(FenceRefused):
        fence.snapshot(owner)
    with fence.pool.connection() as conn, pytest.raises(Exception, match='terminal'):
        with conn.transaction():
            lock(conn, owner, exclusive=True)
            conn.execute(
                "UPDATE privacy_owner_fence SET state='open',close_reason=NULL,generation=generation+1 "
                'WHERE owner_key=%s',
                (owner,),
            )
