"""Loopback-only Firestore proof that deletion and replay writes serialize safely."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import conversations as conversations_db, proactivity, users as users_db
from database.conversation_deletions import ConversationDeletedError, deletion_receipt_ref
from database import conversation_deletions as deletions_db
from utils.sync.assignment import assign_in_transaction
from utils.sync.assignment_errors import SyncAssignmentSuperseded

pytestmark = pytest.mark.skipif(not os.getenv('FIRESTORE_EMULATOR_HOST'), reason='requires loopback Firestore emulator')


@pytest.fixture
def store(monkeypatch):
    host = os.environ['FIRESTORE_EMULATOR_HOST']
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('Conversation deletion proof requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-conversation-deletion', credentials=AnonymousCredentials())
    monkeypatch.setattr(conversations_db, 'db', client)
    monkeypatch.setattr(conversations_db, 'leave_capture_group', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_args: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_args: None)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *_args: None)
    monkeypatch.setattr(proactivity, 'purge_source_items', lambda **_kwargs: None)
    yield client, 'deletion-proof-' + uuid4().hex
    client.close()


def payload(conversation_id):
    return {
        'id': conversation_id,
        'status': 'completed',
        'discarded': False,
        'source': 'desktop',
        'data_protection_level': 'standard',
        'started_at': datetime.fromtimestamp(1000, timezone.utc),
        'finished_at': datetime.fromtimestamp(1009, timezone.utc),
        'transcript_segments': [{'text': 'A substantive explanation of the project.', 'start': 0.0, 'end': 9.0}],
    }


@pytest.mark.parametrize('writer', ['create', 'upsert', 'sync'])
def test_user_delete_racing_ingestion_leaves_no_recreated_conversation(store, writer):
    client, uid = store
    user_ref = client.collection('users').document(uid)
    for iteration in range(3):
        conversation_id = f'replayed-session-{iteration}'
        incoming = payload(conversation_id)
        barrier = threading.Barrier(2)

        def replay():
            barrier.wait(timeout=5)
            try:
                if writer == 'create':
                    conversations_db.create_conversation_if_absent_with_lifecycle(uid, deepcopy(incoming))
                elif writer == 'upsert':
                    conversations_db.upsert_conversation_with_lifecycle(uid, deepcopy(incoming))
                else:

                    @firestore.transactional
                    def assign(transaction):
                        return assign_in_transaction(
                            transaction,
                            user_ref,
                            incoming,
                            decode=deepcopy,
                            encode=deepcopy,
                            invalidate=lambda _payload: None,
                        )

                    assign(client.transaction())
            except (ConversationDeletedError, SyncAssignmentSuperseded):
                return 'deleted'
            return 'stored_before_deletion'

        def delete():
            barrier.wait(timeout=5)
            conversations_db.mark_conversation_deleted(uid, conversation_id, firestore_client=client)
            conversations_db.delete_conversation(uid, conversation_id)

        with ThreadPoolExecutor(max_workers=2) as workers:
            deletion = workers.submit(delete)
            replayed = workers.submit(replay)
            deletion.result(timeout=30)
            assert replayed.result(timeout=30) in {'deleted', 'stored_before_deletion'}

        assert not user_ref.collection('conversations').document(conversation_id).get().exists
        assert deletion_receipt_ref(user_ref, conversation_id).get().exists
        with pytest.raises(ConversationDeletedError):
            conversations_db.create_conversation_if_absent_with_lifecycle(uid, deepcopy(incoming))


def test_recursive_account_wipe_removes_deletion_receipts_even_without_a_user_parent(store, monkeypatch):
    client, uid = store
    user_ref = client.collection('users').document(uid)
    conversations_db.mark_conversation_deleted(uid, 'deleted-session', firestore_client=client)
    assert not user_ref.get().exists
    assert deletion_receipt_ref(user_ref, 'deleted-session').get().exists
    monkeypatch.setattr(users_db, 'db', client)

    assert users_db.delete_user_data(uid)['status'] == 'ok'

    assert not deletion_receipt_ref(user_ref, 'deleted-session').get().exists


def large_row(root_id, prefix):
    row = payload(root_id)
    row['sync_merged_from'] = [f'{prefix}-{index:04}' for index in range(600)]
    return row


def test_partial_large_fanout_fences_missing_aliases_and_resumes_before_purge(store, monkeypatch):
    client, uid = store
    user_ref = client.collection('users').document(uid)
    root = large_row('z-root', 'source')
    root_ref = user_ref.collection('conversations').document(root['id'])
    root_ref.set(root)
    # An ordinary redirect can precede the explicitly deleted parent in the
    # ancestry query. Only the latter is user-deletion authority.
    user_ref.collection('conversations').document('a-ordinary').set(
        {'deleted': True, 'sync_merged_from': ['source-0500']}
    )
    user_ref.collection('conversations').document('other-live').set(payload('other-live'))
    stamp = deletions_db._persist_source_receipt_batch
    attempts = 0

    def fail_second_batch(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError('synthetic receipt batch failure')
        stamp(*args)

    with monkeypatch.context() as scoped:
        scoped.setattr(deletions_db, '_persist_source_receipt_batch', fail_second_batch)
        with pytest.raises(RuntimeError, match='synthetic receipt batch failure'):
            conversations_db.mark_conversation_deleted(uid, root['id'], firestore_client=client)

    assert root_ref.get().to_dict()['user_deleted'] is True
    assert not deletion_receipt_ref(user_ref, 'source-0500').get().exists
    assert deletions_db._fanout_state_ref(user_ref).get().to_dict()['pending_fanouts'] == 1
    with pytest.raises(ConversationDeletedError):
        conversations_db.create_conversation_if_absent_with_lifecycle(uid, payload('source-0500'))

    @firestore.transactional
    def replay_into_other(transaction):
        incoming = payload('source-0500')
        incoming['transcript_segments'][0]['text'] = 'Deleted private source speech'
        return assign_in_transaction(
            transaction,
            user_ref,
            incoming,
            target_id='other-live',
            decode=deepcopy,
            encode=deepcopy,
            invalidate=lambda _payload: None,
        )

    with pytest.raises(SyncAssignmentSuperseded):
        replay_into_other(client.transaction())
    assert user_ref.collection('conversations').document('other-live').get().to_dict() == payload('other-live')
    assert conversations_db.create_conversation_if_absent_with_lifecycle(uid, payload('unrelated-capture')) is True
    with pytest.raises(deletions_db.ConversationDeletionFanoutPendingError):
        conversations_db.delete_conversation(uid, root['id'])
    assert root_ref.get().to_dict()['sync_merged_from'] == root['sync_merged_from']

    conversations_db.mark_conversation_deleted(uid, root['id'], firestore_client=client)
    assert all(deletion_receipt_ref(user_ref, source).get().exists for source in root['sync_merged_from'])
    assert deletions_db._fanout_state_ref(user_ref).get().to_dict()['pending_fanouts'] == 0
    conversations_db.delete_conversation(uid, root['id'])
    assert not root_ref.get().exists
    with pytest.raises(ConversationDeletedError):
        conversations_db.create_conversation_if_absent_with_lifecycle(uid, payload('source-0500'))


def test_two_pending_roots_clear_only_the_completed_roots_shared_hint(store, monkeypatch):
    client, uid = store
    user_ref = client.collection('users').document(uid)
    roots = [large_row('root-a', 'a-source'), large_row('root-b', 'b-source')]
    with monkeypatch.context() as scoped:
        scoped.setattr(
            deletions_db,
            '_persist_source_receipt_batch',
            lambda *_args: (_ for _ in ()).throw(RuntimeError('synthetic receipt batch failure')),
        )
        for row in roots:
            user_ref.collection('conversations').document(row['id']).set(row)
            with pytest.raises(RuntimeError):
                conversations_db.mark_conversation_deleted(uid, row['id'], firestore_client=client)

    assert deletions_db._fanout_state_ref(user_ref).get().to_dict()['pending_fanouts'] == 2
    conversations_db.mark_conversation_deleted(uid, 'root-a', firestore_client=client)
    assert deletions_db._fanout_state_ref(user_ref).get().to_dict()['pending_fanouts'] == 1
    with pytest.raises(ConversationDeletedError):
        conversations_db.create_conversation_if_absent_with_lifecycle(uid, payload('b-source-0500'))
    conversations_db.mark_conversation_deleted(uid, 'root-b', firestore_client=client)
    assert deletions_db._fanout_state_ref(user_ref).get().to_dict()['pending_fanouts'] == 0


def test_zero_hint_writer_and_large_root_fence_serialize_without_a_visible_recreated_source(store, monkeypatch):
    client, uid = store
    user_ref = client.collection('users').document(uid)
    root = large_row('root', 'source')
    user_ref.collection('conversations').document(root['id']).set(root)
    deletions_db._fanout_state_ref(user_ref).set({'pending_fanouts': 0})
    writer_read_zero = threading.Event()
    root_ready_to_fence = threading.Event()
    count_pending = deletions_db._pending_fanouts
    first_writer_read = True

    def observed_pending(state):
        nonlocal first_writer_read
        value = count_pending(state)
        if threading.current_thread().name.startswith('source-replay') and first_writer_read:
            first_writer_read = False
            assert value == 0
            writer_read_zero.set()
            assert root_ready_to_fence.wait(timeout=5)
        elif threading.current_thread().name.startswith('root-deletion'):
            root_ready_to_fence.set()
        return value

    monkeypatch.setattr(deletions_db, '_pending_fanouts', observed_pending)

    def replay():
        try:
            conversations_db.create_conversation_if_absent_with_lifecycle(uid, payload('source-0500'))
        except ConversationDeletedError:
            return 'deleted'
        return 'stored_before_root_fence'

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='source-replay') as writers:
        replayed = writers.submit(replay)
        assert writer_read_zero.wait(timeout=5)
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='root-deletion') as deleters:
            deletion = deleters.submit(
                conversations_db.mark_conversation_deleted, uid, root['id'], firestore_client=client
            )
            deletion.result(timeout=30)
        assert replayed.result(timeout=30) in {'deleted', 'stored_before_root_fence'}

    source = user_ref.collection('conversations').document('source-0500').get().to_dict()
    assert source is None or source['deleted'] is True
    with pytest.raises(ConversationDeletedError):
        conversations_db.create_conversation_if_absent_with_lifecycle(uid, payload('source-0500'))
