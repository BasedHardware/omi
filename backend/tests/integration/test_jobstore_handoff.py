"""Dark custody fault boundaries on real local FS and PostgreSQL.

This is the protocol seam, not the full scheduler/projection qualification.
"""

from uuid import uuid4

import pytest
from google.cloud import firestore
from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1.types import CommitRequest, Document, DocumentMask, Write

from database.jobstore.authority import AuthorityRefused, Epoch, acquire, fingerprint, transition
from database.jobstore.connection import Pool
from database.jobstore.fs_fence import FirestoreAuthority, handoff_ref
from database.jobstore.handoff import Handoff
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.privacy_fence import Fence, FenceRefused, owner_key
from testing.store_fixtures import ClientCustomerData, _emulator_client, postgres_connect

pytestmark = pytest.mark.integration


@pytest.fixture
def context():
    client = _emulator_client()
    pool = Pool('', size=2, connect=postgres_connect())
    uid = 'custody-' + uuid4().hex
    ns = 'batch_pipeline_test_' + uuid4().hex
    customer = ClientCustomerData(client)
    customer.add_user(uid)
    customer.add_conversation(uid, 'c')
    with pool.connection() as conn, conn.transaction():
        conn.execute('INSERT INTO queue_authority(namespace) VALUES (%s)', (ns,))
        transition(conn, ns, 'FS_OPEN', 0, 'FS_CLOSING')
        transition(conn, ns, 'FS_CLOSING', 1, 'BOTH_CLOSED')
        ticket = transition(conn, ns, 'BOTH_CLOSED', 2, 'PG_OPEN')
    handoff = Handoff(pool, Fence(pool), client, ticket)
    handoff.authority.ref.set({'namespace': ns, 'epoch': 3, 'state': 'PG_OPEN', 'protocol': 1})
    yield handoff, uid
    pool.close()
    client.close()


def stage(handoff, uid, payload=None):
    @firestore.transactional
    def commit(transaction):
        return handoff.stage(transaction, 'recording', uid, ['c'], payload or {'segment_id': 'one'})

    return commit(handoff.client.transaction())


def deliver(handoff):
    def mutate(conn, payload, admission):
        # Real SQL mutation shares admission/intent COMMIT, not a Python fake.
        conn.execute(
            "INSERT INTO docs(namespace,tbl,key,doc) SELECT namespace,'intakes','one',"
            "jsonb_build_object('owner_key',owner_key,'accepted',true) FROM queue_handoffs "
            'WHERE namespace=%s AND identity=%s',
            (handoff.ticket.namespace, 'recording'),
        )

    return handoff.deliver('recording', mutate)


def seal(handoff, envelope=None):
    with handoff.pool.connection() as conn, conn.transaction():
        return handoff.complete(conn, 'recording', envelope or {'result_uri': 'encrypted://local/ref'})


def test_intent_and_pg_admission_replay_are_idempotent(context):
    handoff, uid = context
    digest = stage(handoff, uid, {'a': 1, 'b': 2})
    assert stage(handoff, uid, {'b': 2, 'a': 1}) == digest
    first = deliver(handoff)
    assert deliver(handoff)['admission_id'] == first['admission_id']
    with handoff.pool.connection() as conn:
        assert conn.execute('SELECT count(*) FROM docs WHERE namespace=%s', (handoff.ticket.namespace,)).fetchone() == (
            1,
        )
    with pytest.raises(AuthorityRefused, match='different intent'):
        stage(handoff, uid, {'a': 3})


def test_admission_rollback_preserves_intent_and_no_queue_mutation(context):
    handoff, uid = context
    stage(handoff, uid)

    def killed(conn, payload, admission):
        raise RuntimeError('kill before PG COMMIT')

    with pytest.raises(RuntimeError):
        handoff.deliver('recording', killed)
    with handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT count(*) FROM queue_handoffs WHERE namespace=%s', (handoff.ticket.namespace,)
        ).fetchone() == (0,)
    assert handoff.ref('intent', 'recording').get().exists
    deliver(handoff)


def test_completion_is_atomic_and_immutable_even_for_direct_sql(context):
    handoff, uid = context
    stage(handoff, uid)
    deliver(handoff)
    with handoff.pool.connection() as conn, pytest.raises(RuntimeError):
        with conn.transaction():
            handoff.complete(conn, 'recording', {'result_uri': 'encrypted://lost'})
            raise RuntimeError('kill before result COMMIT')
    with pytest.raises(AuthorityRefused, match='not committed'):
        handoff.export('recording')
    digest = seal(handoff)
    assert seal(handoff) == digest
    with pytest.raises(AuthorityRefused, match='immutable'):
        seal(handoff, {'result_uri': 'encrypted://different'})
    with handoff.pool.connection() as conn, pytest.raises(Exception, match='immutable handoff'):
        with conn.transaction():
            # Protocol and epoch alone cannot change a sealed envelope.
            conn.execute("SET LOCAL omi.privacy_fence_protocol='2'")
            acquire(conn, handoff.ticket)
            conn.execute("UPDATE queue_handoffs SET completion='{}' WHERE namespace=%s", (handoff.ticket.namespace,))


def test_projection_receipt_and_customer_effect_commit_once_then_ack(context):
    handoff, uid = context
    stage(handoff, uid)
    deliver(handoff)
    seal(handoff)
    handoff.export('recording')
    assert fingerprint(handoff.export('recording')) == fingerprint(
        handoff.ref('completion', 'recording').get().to_dict()
    )
    customer_ref = handoff.client.collection('users').document(uid).collection('usage').document('test')
    calls = []

    def project(transaction, envelope):
        current = customer_ref.get(transaction=transaction).to_dict() or {}
        calls.append(envelope['result_uri'])
        transaction.set(customer_ref, {'seconds': current.get('seconds', 0) + 10})
        return {'conversation_id': 'c'}

    assert handoff.project('recording', project) == {'conversation_id': 'c'}
    # Simulate lost FS Commit reply by replaying, without a post-commit observer.
    assert handoff.project('recording', project) == {'conversation_id': 'c'}
    assert calls == ['encrypted://local/ref']
    assert customer_ref.get().to_dict() == {'seconds': 10}
    assert handoff.ack('recording')
    assert not handoff.ack('recording')


def test_failed_projection_rolls_back_customer_effect_and_receipt(context):
    handoff, uid = context
    stage(handoff, uid)
    deliver(handoff)
    seal(handoff)
    handoff.export('recording')
    customer_ref = handoff.client.collection('users').document(uid).collection('usage').document('test')

    def killed(transaction, envelope):
        transaction.set(customer_ref, {'seconds': 10})
        raise RuntimeError('kill before FS projection COMMIT')

    with pytest.raises(RuntimeError):
        handoff.project('recording', killed)
    assert not customer_ref.get().exists
    assert not handoff.ref('receipt', 'recording').get().exists
    with pytest.raises(AuthorityRefused, match='receipt required'):
        handoff.ack('recording')


def test_forged_receipt_cannot_ack_and_privacy_close_stops_export(context):
    handoff, uid = context
    stage(handoff, uid)
    deliver(handoff)
    seal(handoff)
    handoff.ref('receipt', 'recording').set({'completion_hash': 'forged'})
    with pytest.raises(AuthorityRefused, match='binding mismatch'):
        handoff.ack('recording')
    handoff.fence.close(owner_key(uid), local=True)
    with pytest.raises(FenceRefused):
        handoff.export('recording')


def test_fs_and_pg_close_independently_refuse_stale_handoffs(context):
    handoff, uid = context
    stage(handoff, uid)
    deliver(handoff)
    seal(handoff)
    handoff.authority.transition('PG_OPEN', 'PG_CLOSING', 'test-close')
    with pytest.raises(AuthorityRefused):
        handoff.export('recording')
    with handoff.pool.connection() as conn, conn.transaction():
        transition(conn, handoff.ticket.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
    with pytest.raises(AuthorityRefused):
        seal(handoff)


def test_fs_writer_commit_guard_refuses_paused_direct_and_bulk_writers(context):
    handoff, _ = context
    authority = FirestoreAuthority(handoff.client, Epoch(handoff.ticket.namespace, 0))
    authority.ref.set({'namespace': handoff.ticket.namespace, 'epoch': 0, 'state': 'FS_OPEN', 'protocol': 1})
    ref = handoff.client.collection(handoff.ticket.namespace + '_jobs').document('one')
    request = CommitRequest(
        database=handoff.client._database_string, writes=[Write(update=Document(name=ref._document_path))]
    )
    assert authority.prepare(request)
    authority.transition('FS_OPEN', 'FS_CLOSING', 'close')
    with pytest.raises(FailedPrecondition):
        handoff.client._firestore_api.commit(request=request)
    with authority.writers(), pytest.raises(AuthorityRefused):
        ref.set({'state': 'ready'})
    with authority.writers(), pytest.raises(AuthorityRefused):
        writer = handoff.client.bulk_writer()
        writer.set(ref, {'state': 'ready'})
        writer.flush()
    assert not ref.get().exists


def test_fs_unknown_writer_fails_closed_and_unbound_default_is_dark(context):
    handoff, _ = context
    authority = FirestoreAuthority(handoff.client, Epoch(handoff.ticket.namespace, 0))
    ref = handoff.client.collection(handoff.ticket.namespace + '_future_queue').document('one')
    request = CommitRequest(writes=[Write(update=Document(name=ref._document_path), update_mask=DocumentMask())])
    with pytest.raises(AuthorityRefused, match='inventory incomplete'):
        authority.prepare(request)
    # No context means imports do not activate any new runtime check.
    ref.set({'dark': True})
    assert ref.get().to_dict() == {'dark': True}


def test_selected_store_transaction_checks_authority_and_namespace(context):
    from database.batch_pipeline_store import FirestoreStore

    handoff, uid = context
    authority = FirestoreAuthority(handoff.client, Epoch(handoff.ticket.namespace, 0))
    authority.ref.set({'namespace': handoff.ticket.namespace, 'epoch': 0, 'state': 'FS_OPEN', 'protocol': 1})
    store = FirestoreStore(handoff.ticket.namespace, firestore_client=handoff.client, queue_authority=authority)
    store.run(
        lambda tx: tx.put(
            'jobs', 'one', {'owner_id': uid, 'conversation_id': 'c', 'privacy_generation': 0, 'state': 'ready'}
        )
    )
    ref = handoff.client.collection(store.namespace + '_jobs').document('one')
    assert ref.get().to_dict()['state'] == 'ready'
    authority.transition('FS_OPEN', 'FS_CLOSING', 'close-store')
    with pytest.raises(AuthorityRefused):
        store.run(lambda tx: tx.put('jobs', 'one', {'state': 'leased'}))
    assert ref.get().to_dict()['state'] == 'ready'
    with pytest.raises(ValueError, match='match the store namespace'):
        FirestoreStore(store.namespace + 'x', firestore_client=handoff.client, queue_authority=authority)


def test_deferred_bulk_flush_keeps_binding_after_scope_and_rejects_switch(context):
    handoff, _ = context
    authority = FirestoreAuthority(handoff.client, Epoch(handoff.ticket.namespace, 0))
    authority.ref.set({'namespace': handoff.ticket.namespace, 'epoch': 0, 'state': 'FS_OPEN', 'protocol': 1})
    ref = handoff.client.collection(handoff.ticket.namespace + '_jobs').document('one')
    writer = handoff.client.bulk_writer()  # constructed before authority scope
    with authority.writers():
        writer.set(ref, {'state': 'ready'})
    authority.transition('FS_OPEN', 'FS_CLOSING', 'close-before-flush')
    with pytest.raises(AuthorityRefused):
        writer.flush()  # thread RPC after scope has exited still refuses
    assert not ref.get().exists
    other = FirestoreAuthority(handoff.client, Epoch(handoff.ticket.namespace, 1))
    with other.writers(), pytest.raises(ValueError, match='cannot change authority'):
        writer.set(ref, {'state': 'ready'})


def test_live_customer_privacy_change_refuses_projection_without_pg_ack(context):
    handoff, uid = context
    stage(handoff, uid)
    deliver(handoff)
    seal(handoff)
    handoff.export('recording')
    ClientCustomerData(handoff.client).delete_conversation(uid, 'c')
    with pytest.raises(BatchPrivacyBlocked):
        handoff.project('recording', lambda *_: pytest.fail('deleted source projected'))
    assert not handoff.ref('receipt', 'recording').get().exists


def test_bulk_privacy_coordinator_survives_sdk_thread_and_scope(context):
    from database.batch_privacy_write_fence import g2_coordinator
    from database.privacy_fence.interceptor import Coordinator

    handoff, uid = context
    stage(handoff, uid)
    deliver(handoff)
    token = g2_coordinator.set(Coordinator(handoff.client, handoff.fence))
    try:
        writer = handoff.client.bulk_writer()
        writer.set(handoff.client.collection('account_deletions').document(uid), {'wipe_status': 'pending'})
    finally:
        g2_coordinator.reset(token)
    writer.flush()
    guard = handoff.client.collection('batch_pipeline_privacy_fence').document(owner_key(uid)).get().to_dict()
    assert guard['landed'] == [1]
    with handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT generation,pending_changes FROM privacy_owner_fence WHERE owner_key=%s', (owner_key(uid),)
        ).fetchone() == (2, 0)


def test_existing_admission_joins_customer_ledger_and_intent_without_fs_queue(context, monkeypatch):
    from database.batch_pipeline_intake import admit
    from database.batch_pipeline_store import FirestoreStore
    from database.sync_ledger import sync_content_ledger_ref
    from config.policy import BatchUnitPolicy
    from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, Priority

    handoff, uid = context
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    source = FirestoreStore(handoff.ticket.namespace, firestore_client=handoff.client)
    binding = ProjectionBinding(uid, 'recording', 'content', ('one',), target_conversation_id='c')
    item = WorkItem(
        'one', uid, 100, 'encrypted://audio#1', 10, Priority.RECENT, conversation_id='c', privacy_generation=0
    )
    policy = BatchUnitPolicy(batch_enabled=True, batch_percent=100)
    kwargs = dict(
        namespace=source.namespace,
        policy=policy,
        handoff=handoff,
        intake={'owner_id': uid, 'segment_ids': ['one'], 'repair_lineage': 'synthetic-customer-context'},
    )
    assert admit(source, [item], binding, 101, **kwargs)['outcome'] == 'batch'
    assert admit(source, [item], binding, 102, **kwargs)['outcome'] == 'batch'
    intent = handoff.ref('intent', 'recording').get().to_dict()['intent']
    assert intent['payload']['jobs']['one']['projection_binding']['job_id'] == 'recording'
    assert intent['payload']['jobs']['one']['enqueued_at'] == 101
    assert 'repair_lineage' not in intent['payload']['intakes']['recording']
    assert (
        handoff.client.collection(source.namespace + '_intakes').document('recording').get().to_dict()['repair_lineage']
        == 'synthetic-customer-context'
    )
    assert not handoff.client.collection(source.namespace + '_jobs').document('one').get().exists
    assert not handoff.client.collection(source.namespace + '_control').limit(1).get()
    assert sync_content_ledger_ref(handoff.client, uid, 'content').get().to_dict()['job_id'] == 'recording'
