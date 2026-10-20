"""Synthetic deletion races against real loopback Firestore, never cloud data."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_privacy import (
    BatchPrivacyBlocked,
    assert_batch_write_allowed,
    privacy_owner_key,
    erased_predecessors,
)
from database.batch_pipeline_purge import purge_batch_owner
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.contracts import WorkItem, WorkResult, Priority
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.retention import (
    register_batch_artifact,
    expire_completed_segment,
    cleanup_completed_artifacts,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def state():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    client = firestore.Client(project='demo-batch-pipeline-d', credentials=AnonymousCredentials())
    store = FirestoreStore(f'batch_pipeline_test_{uuid.uuid4().hex}', firestore_client=client)
    uid = f'synthetic-{uuid.uuid4().hex}'
    user = client.collection('users').document(uid)
    user.set({'data_protection_level': 'enhanced'})
    user.collection('conversations').document('source').set({'id': 'source'})
    erased = []

    def purge(conversation_id=None, reason='deleted', delete_uri=None):
        return purge_batch_owner(
            uid,
            firestore_client=client,
            namespaces=[store.namespace],
            conversation_id=conversation_id,
            reason=reason,
            delete_uri=delete_uri or (lambda owner, uri: erased.append(uri)),
        )

    yield store, uid, user, purge, erased
    for table in ('jobs', 'queues', 'owners', 'control', 'results', 'gpus', 'artifacts', 'projections', 'intakes'):
        for doc in client.collection(f'{store.namespace}_{table}').stream():
            doc.reference.delete()
    for sub in user.collections():
        for doc in sub.stream():
            doc.reference.delete()
    user.delete()
    client.collection('account_deletions').document(uid).delete()
    client.collection('batch_pipeline_privacy').document(privacy_owner_key(uid)).delete()
    client.close()


def work(uid, segment='a', conversation='source'):
    return WorkItem(
        segment,
        uid,
        1,
        f'gs://synthetic/{segment}',
        30,
        Priority.DEEP,
        conversation_id=conversation,
        privacy_generation=0,
    )


def delete_source(user):
    user.collection('deleted_conversations').document('source').set({'conversation_id': 'source'})
    user.collection('conversations').document('source').delete()


def project(store, uid, segment='a'):
    @firestore.transactional
    def commit(transaction):
        result = store.client.collection(f'{store.namespace}_results').document(segment).get(transaction=transaction)
        assert_batch_write_allowed(store.client, transaction, uid, conversation_ids=['source'], expected_generation=0)
        if not result.exists:
            return False
        transaction.set(
            store.client.collection('users').document(uid).collection('conversations').document('source'),
            {'id': 'source', 'synthetic_projected': True},
        )
        return True

    return commit(store.client.transaction())


@pytest.mark.parametrize('phase', ['before_run', 'during_run', 'committed'])
@pytest.mark.parametrize('scope', ['conversation', 'account'])
def test_deletion_at_each_durable_boundary_never_resurrects(state, phase, scope):
    store, uid, user, purge, erased = state
    queue, merge = Scheduler(store), OrderedMerge(store)
    queue.enqueue(work(uid), 0)
    lease = None
    if phase != 'before_run':
        lease = queue.pull(0)[0]
    if phase == 'committed':
        assert queue.complete(WorkResult('a', 'gs://synthetic/result'), lease.token, 1)
        assert merge.commit_next(uid, 2)
    if scope == 'conversation':
        delete_source(user)
        purge('source')
    else:
        store.client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
        purge()
        for sub in user.collections():
            for doc in sub.stream():
                doc.reference.delete()
        user.delete()
    assert queue.pull(3) == []
    if lease:
        assert not queue.complete(WorkResult('a', 'gs://synthetic/late'), lease.token, 3)
    assert merge.commit_next(uid, 3) is None
    with pytest.raises(BatchPrivacyBlocked):
        project(store, uid)
    assert not user.collection('conversations').document('source').get().exists
    assert not list(store.client.collection(f'{store.namespace}_jobs').stream())
    results = [row.to_dict() for row in store.client.collection(f'{store.namespace}_results').stream()]
    assert (
        not results
        if scope == 'account'
        else all(row['projection_state'] == 'erased' and 'result' not in row for row in results)
    )
    assert 'gs://synthetic/a' in erased


def test_conversation_purge_unlinks_middle_and_preserves_other_work(state):
    store, uid, user, purge, _ = state
    queue = Scheduler(store)
    queue.enqueue(work(uid, 'a', 'keep'), 0)
    queue.enqueue(work(uid, 'b'), 0)
    queue.enqueue(work(uid, 'c', 'keep'), 0)
    delete_source(user)
    purge('source')
    leases = queue.pull(0, 3)
    assert [v.item.segment_id for v in leases] == ['a', 'c']


def test_pending_lease_old_next_pointer_does_not_corrupt_unlink(state):
    store, uid, user, purge, _ = state
    queue = Scheduler(store)
    queue.enqueue(work(uid, 'a', 'keep'), 0)
    queue.enqueue(work(uid, 'b'), 0)
    queue.enqueue(work(uid, 'c', 'keep'), 0)
    assert queue.pull(0)[0].item.segment_id == 'a'
    delete_source(user)
    purge('source')
    assert queue.pull(0)[0].item.segment_id == 'c'


def test_delete_during_projection_serializes_with_tombstone(state):
    store, uid, user, purge, _ = state
    queue = Scheduler(store)
    queue.enqueue(work(uid), 0)
    lease = queue.pull(0)[0]
    queue.complete(WorkResult('a', 'gs://synthetic/result'), lease.token, 1)
    OrderedMerge(store).commit_next(uid, 2)

    def projection():
        try:
            return project(store, uid)
        except BatchPrivacyBlocked:
            return False

    def deletion():
        # Intent first. If projection commits first, this physical delete wins;
        # if intent commits first, projection must retry and reject.
        delete_source(user)
        purge('source')

    with ThreadPoolExecutor(max_workers=2) as pool:
        projected, deleted = pool.submit(projection), pool.submit(deletion)
        projected.result()
        deleted.result()
    assert not user.collection('conversations').document('source').get().exists
    with pytest.raises(BatchPrivacyBlocked):
        project(store, uid)


def test_protection_change_and_return_to_enhanced_cannot_accept_old_generation(state):
    store, uid, user, purge, _ = state
    queue = Scheduler(store)
    queue.enqueue(work(uid), 0)
    user.update({'data_protection_level': 'e2ee'})
    purge(reason='data_protection')
    user.update({'data_protection_level': 'enhanced'})
    with pytest.raises(BatchPrivacyBlocked):
        queue.enqueue(work(uid, 'stale'), 1)
    assert queue.enqueue(replace(work(uid, 'new'), privacy_generation=1), 1)


def test_object_failure_preserves_retryable_reference_and_blocks_admission(state):
    store, uid, user, purge, _ = state
    queue = Scheduler(store)
    queue.enqueue(work(uid), 0)

    def reject(*args):
        raise RuntimeError('synthetic storage unavailable')

    with pytest.raises(RuntimeError, match='storage unavailable'):
        purge(delete_uri=reject)
    assert store.client.collection(f'{store.namespace}_jobs').document('a').get().exists
    with pytest.raises(BatchPrivacyBlocked):
        queue.enqueue(work(uid, 'new'), 1)
    assert purge() > 0
    assert not store.client.collection(f'{store.namespace}_jobs').document('a').get().exists


def test_completion_retention_waits_for_projection_and_object_erasure(state):
    store, uid, _, _, _ = state
    queue = Scheduler(store)
    queue.enqueue(work(uid), 0)
    lease = queue.pull(0)[0]
    artifact = register_batch_artifact(store, uid, 'a', 'gs://synthetic/result', 'result', 0)
    queue.complete(WorkResult('a', 'gs://synthetic/result'), lease.token, 1)
    OrderedMerge(store).commit_next(uid, 2)
    assert not expire_completed_segment(store, uid, 'a', 3)
    reference = store.client.collection(f'{store.namespace}_results').document('a')
    assert 'expires_at' not in reference.get().to_dict()
    reference.update({'projection_state': 'ready'})
    assert expire_completed_segment(store, uid, 'a', 3)
    artifact_ref = store.client.collection(f'{store.namespace}_artifacts').document(artifact)
    data = artifact_ref.get().to_dict()
    assert 'expires_at' not in data
    due = datetime.fromtimestamp(3, timezone.utc) + timedelta(hours=24)
    erased = []
    assert cleanup_completed_artifacts(store, due - timedelta(seconds=1), delete_uri=lambda *v: erased.append(v)) == 0
    assert cleanup_completed_artifacts(store, due, delete_uri=lambda *v: erased.append(v)) == 1
    assert erased == [(uid, 'gs://synthetic/result')]
    final = artifact_ref.get().to_dict()
    assert 'uri' not in final and 'expires_at' in final


def test_inflight_object_reference_survives_until_final_erasure(state):
    store, uid, user, purge, _ = state
    queue = Scheduler(store)
    queue.enqueue(work(uid), 0)
    queue.pull(0)
    artifact = register_batch_artifact(store, uid, 'a', 'gs://synthetic/result', 'result', 0)
    artifact_ref = store.client.collection(f'{store.namespace}_artifacts').document(artifact)
    delete_source(user)
    purge('source')
    pending = artifact_ref.get().to_dict()
    assert pending['erasure_requested'] and 'expires_at' not in pending
    erased = []
    assert cleanup_completed_artifacts(store, pending['cleanup_after'], delete_uri=lambda *v: erased.append(v)) == 1
    assert not artifact_ref.get().exists
    assert erased == [(uid, 'gs://synthetic/result')]


def test_erased_ordering_edge_never_skips_an_unfinished_earlier_projection(state):
    store, uid, user, purge, _ = state
    queue, merge = Scheduler(store), OrderedMerge(store)
    for segment, conversation in [('a', 'keep'), ('b', 'source'), ('c', 'keep')]:
        queue.enqueue(work(uid, segment, conversation), 0)
    for lease in queue.pull(0, 3):
        queue.complete(
            WorkResult(lease.item.segment_id, f'gs://synthetic/{lease.item.segment_id}-result'), lease.token, 1
        )
    for _ in range(3):
        assert merge.commit_next(uid, 2)
    delete_source(user)
    purge('source')
    receipt = store.client.collection(f'{store.namespace}_results').document('b').get().to_dict()
    assert receipt['projection_state'] == 'erased' and 'result' not in receipt and 'expires_at' not in receipt

    @firestore.transactional
    def read(transaction, cursor):
        return erased_predecessors(store.client, transaction, store.namespace, privacy_owner_key(uid), 'b', cursor)

    assert read(store.client.transaction(), None) is None
    refs = read(store.client.transaction(), 'a')
    assert [ref.id for ref in refs] == ['b']


def test_assigned_target_deletion_erases_jobs_artifacts_and_intake_mapping(state):
    store, uid, user, purge, erased = state
    queue, merge = Scheduler(store), OrderedMerge(store)
    queue.enqueue(work(uid, conversation='original'), 0)
    lease = queue.pull(0)[0]
    artifact = register_batch_artifact(store, uid, 'a', 'gs://synthetic/result', 'result', 0)
    queue.complete(WorkResult('a', 'gs://synthetic/result'), lease.token, 1)
    merge.commit_next(uid, 2)
    result = store.client.collection(f'{store.namespace}_results').document('a')
    result.update({'projection': {'conversation_id': 'source', 'state': 'persisted'}})
    intake = store.client.collection(f'{store.namespace}_intakes').document('bp_synthetic')
    intake.set({'owner_key': privacy_owner_key(uid), 'segment_ids': ['a']})
    delete_source(user)
    purge('source')
    assert not store.client.collection(f'{store.namespace}_jobs').document('a').get().exists
    assert not intake.get().exists
    assert 'gs://synthetic/result' in erased
    assert (
        store.client.collection(f'{store.namespace}_artifacts').document(artifact).get().to_dict()['erasure_requested']
    )


def test_owner_purge_pages_past_one_hundred_references(state):
    store, uid, _, purge, erased = state
    batch = store.client.batch()
    for index in range(105):
        batch.set(
            store.client.collection(f'{store.namespace}_artifacts').document(f'{index:04}'),
            {'owner_key': privacy_owner_key(uid), 'uri': f'gs://synthetic/{index}'},
        )
    batch.commit()
    assert purge() == 105
    assert len(erased) == 105
    assert not list(store.client.collection(f'{store.namespace}_artifacts').stream())


def test_server_merge_redirect_is_allowed_but_user_intent_and_cycles_deny(state):
    store, uid, user, _, _ = state
    user.collection('conversations').document('source').set({'deleted': True, 'sync_merged_into': 'canonical'})
    target = user.collection('conversations').document('canonical')
    target.set({'id': 'canonical'})

    @firestore.transactional
    def guard(transaction):
        return assert_batch_write_allowed(store.client, transaction, uid, conversation_ids=['source', 'canonical'])

    assert guard(store.client.transaction()) == 0
    target.update({'deleted': True, 'sync_merged_into': 'source'})
    with pytest.raises(BatchPrivacyBlocked, match='redirect_cycle'):
        guard(store.client.transaction())
    target.set({'id': 'canonical'})
    user.collection('deleted_conversations').document('canonical').set({'conversation_id': 'canonical'})
    with pytest.raises(BatchPrivacyBlocked, match='conversation_deleted'):
        guard(store.client.transaction())
