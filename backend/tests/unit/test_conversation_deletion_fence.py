"""User deletion is terminal, while temporary ingestion cleanup stays retryable."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from database import conversations as conversations_db, proactivity
from database import conversation_deletions as deletions_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.sync.assignment import assign_in_transaction
from utils.sync.assignment_errors import SyncAssignmentSuperseded


@pytest.fixture
def store(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'db', client)
    monkeypatch.setattr(conversations_db, 'leave_capture_group', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_args: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_args: None)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *_args: None)
    monkeypatch.setattr(proactivity, 'purge_source_items', lambda **_kwargs: None)
    # Child enumeration is irrelevant to this childless purge. The shared
    # strict fixture owns parent deletion and every transaction ordering check.
    monkeypatch.setattr(StrictFirestoreDocument, 'collections', lambda _self: [], raising=False)
    monkeypatch.setattr(StrictFirestoreDocument, 'delete', lambda self: self._database.rows.pop(self.path, None))
    return client


def payload(conversation_id='old-desktop-session'):
    return {
        'id': conversation_id,
        'status': 'processing',
        'discarded': False,
        'source': 'desktop',
        'data_protection_level': 'standard',
        'started_at': datetime.fromtimestamp(1000, timezone.utc),
        'finished_at': datetime.fromtimestamp(1009, timezone.utc),
        'transcript_segments': [{'text': 'A substantive explanation of the project.', 'start': 0.0, 'end': 9.0}],
    }


def mark_user_deleted(store, conversation_id):
    return conversations_db.mark_conversation_deleted('uid', conversation_id, firestore_client=store)


@pytest.mark.parametrize('writer', ['create', 'upsert'])
def test_actual_user_delete_cannot_be_replayed_by_ingestion(store, writer):
    conversation = payload()
    conversations_db.create_conversation_if_absent_with_lifecycle('uid', deepcopy(conversation))
    mark_user_deleted(store, conversation['id'])
    conversations_db.delete_conversation('uid', conversation['id'])

    with pytest.raises(LookupError, match='deleted'):
        if writer == 'create':
            conversations_db.create_conversation_if_absent_with_lifecycle('uid', deepcopy(conversation))
        else:
            conversations_db.upsert_conversation_with_lifecycle('uid', deepcopy(conversation))

    assert ('users', 'uid', 'conversations', conversation['id']) not in store.rows


def test_temporary_cleanup_still_allows_a_legacy_ingestion_retry(store):
    conversation = payload()
    assert conversations_db.create_conversation_if_absent_with_lifecycle('uid', deepcopy(conversation)) is True
    conversations_db.delete_conversation('uid', conversation['id'])
    assert conversations_db.create_conversation_if_absent_with_lifecycle('uid', deepcopy(conversation)) is True


def test_receipt_blocks_a_late_processor_before_content_removal(store):
    conversation = payload()
    conversations_db.create_conversation_if_absent_with_lifecycle('uid', deepcopy(conversation))
    mark_user_deleted(store, conversation['id'])
    conversation['status'] = 'completed'

    assert conversations_db.persist_processing_result_with_lifecycle('uid', conversation) is False
    assert store.rows[('users', 'uid', 'conversations', conversation['id'])]['status'] == 'processing'
    assert (
        conversations_db.is_visible_conversation(
            store.rows[('users', 'uid', 'conversations', conversation['id'])], include_discarded=True
        )
        is False
    )


def test_receipts_are_per_principal_idempotent_and_content_free(store):
    assert mark_user_deleted(store, 'old-desktop-session') is True
    before = deepcopy(store.rows)
    assert mark_user_deleted(store, 'old-desktop-session') is False
    assert store.rows == before
    receipts = [value for path, value in store.rows.items() if path[2] == 'conversation_deletions']
    assert len(receipts) == 1
    assert set(receipts[0]) == {'schema_version', 'deleted_at'}
    assert conversations_db.create_conversation_if_absent_with_lifecycle('another-uid', payload()) is True


def intake(store, conversation, *, target_id=None):
    return assign_in_transaction(
        store.transaction(),
        store.collection('users').document('uid'),
        conversation,
        target_id=target_id,
        decode=deepcopy,
        encode=deepcopy,
        invalidate=lambda _payload: None,
    )


@pytest.mark.parametrize('targeted', [False, True])
def test_sync_cannot_recreate_deleted_source_or_fall_back_from_deleted_target(store, targeted):
    mark_user_deleted(store, 'old-desktop-session')
    incoming = payload('another-sync-key' if targeted else 'old-desktop-session')
    incoming['status'] = 'completed'

    with pytest.raises(SyncAssignmentSuperseded):
        intake(store, incoming, target_id='old-desktop-session' if targeted else None)

    assert not any(path[2] == 'conversations' for path in store.rows)


def test_user_delete_fences_retained_sync_sources_before_their_purge(store):
    row = payload('survivor')
    row['sync_merged_from'] = ['source']
    conversations_db.create_conversation_if_absent_with_lifecycle('uid', row)
    mark_user_deleted(store, 'survivor')
    conversations_db.delete_conversation('uid', 'survivor')

    with pytest.raises(LookupError, match='deleted'):
        conversations_db.create_conversation_if_absent_with_lifecycle('uid', payload('source'))


def test_large_sync_ancestry_is_fenced_in_bounded_batches_without_blocking_deletion(store):
    row = payload('survivor')
    row['sync_merged_from'] = [f'source-{index}' for index in range(500)]
    conversations_db.create_conversation_if_absent_with_lifecycle('uid', row)
    mark_user_deleted(store, 'survivor')
    assert len([path for path in store.rows if path[2] == 'conversation_deletions']) == 501
    assert all(len(tx.creates) + len(tx.updates) + len(tx.sets) <= 400 for tx in store.transactions)
    conversations_db.delete_conversation('uid', 'survivor')
    assert ('users', 'uid', 'conversations', 'survivor') not in store.rows
    with pytest.raises(LookupError, match='deleted'):
        conversations_db.create_conversation_if_absent_with_lifecycle('uid', payload('source-499'))


def test_partial_fanout_uses_all_ancestry_candidates_and_keeps_retry_authority(store, monkeypatch):
    row = payload('z-survivor')
    row['sync_merged_from'] = [f'source-{index}' for index in range(500)]
    conversations_db.create_conversation_if_absent_with_lifecycle('uid', row)
    store.rows[('users', 'uid', 'conversations', 'a-ordinary-donor')] = {
        'deleted': True,
        'sync_merged_from': ['source-499'],
    }
    with monkeypatch.context() as scoped:
        scoped.setattr(
            deletions_db,
            '_persist_source_receipt_batch',
            lambda *_args: (_ for _ in ()).throw(RuntimeError('synthetic batch failure')),
        )
        with pytest.raises(RuntimeError, match='synthetic batch failure'):
            mark_user_deleted(store, row['id'])
    with pytest.raises(LookupError, match='deleted'):
        conversations_db.create_conversation_if_absent_with_lifecycle('uid', payload('source-499'))
    with pytest.raises(deletions_db.ConversationDeletionFanoutPendingError):
        conversations_db.delete_conversation('uid', row['id'])
    assert conversations_db.create_conversation_if_absent_with_lifecycle('uid', payload('unrelated')) is True
    mark_user_deleted(store, row['id'])
    assert deletions_db._fanout_state_ref(store.collection('users').document('uid')).get().to_dict() == {
        'pending_fanouts': 0
    }


def test_sync_legacy_principal_without_receipts_can_ingest(store):
    incoming = payload('legacy-sync-key')
    incoming['status'] = 'completed'
    result, created, _survivors = intake(store, incoming)
    assert created is True
    assert result['id'] == incoming['id']


@pytest.mark.parametrize('state', [{}, {'pending_fanouts': True}, {'pending_fanouts': -1}])
def test_malformed_existing_shared_hint_never_opens_the_ingestion_fence(store, state):
    store.rows[('users', 'uid', 'conversation_deletion_state', 'fanout')] = state
    with pytest.raises(RuntimeError, match='deletion state is unavailable'):
        conversations_db.create_conversation_if_absent_with_lifecycle('uid', payload('unknown-source'))
    assert ('users', 'uid', 'conversations', 'unknown-source') not in store.rows


def test_malformed_pending_receipt_cannot_grant_parent_purge_authority(store):
    user_ref = store.collection('users').document('uid')
    ref = deletions_db.deletion_receipt_ref(user_ref, 'root')
    store.rows[ref.path] = {'schema_version': 1, 'deleted_at': datetime.now(timezone.utc), 'fanout_pending': 'false'}
    store.rows[('users', 'uid', 'conversations', 'root')] = payload('root')
    with pytest.raises(RuntimeError, match='deletion receipt is unavailable'):
        conversations_db.delete_conversation('uid', 'root')
    assert ('users', 'uid', 'conversations', 'root') in store.rows


@pytest.mark.parametrize('legacy_ancestry', [None, 'unrelated-source'])
def test_ancestry_query_excludes_non_array_legacy_fields(store, legacy_ancestry):
    store.rows[('users', 'uid', 'conversation_deletion_state', 'fanout')] = {'pending_fanouts': 1}
    store.rows[('users', 'uid', 'conversations', 'legacy')] = {
        'user_deleted': True,
        'sync_merged_from': legacy_ancestry,
    }
    assert conversations_db.create_conversation_if_absent_with_lifecycle('uid', payload('unrelated')) is True
