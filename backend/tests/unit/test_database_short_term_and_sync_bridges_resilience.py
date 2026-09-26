"""Tests for database.short_term_memories and database.sync_bridges resilience, input guards, and NotFound safety."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from google.api_core.exceptions import NotFound

import database.short_term_memories as stm
import database.sync_bridges as sync_bridges


# ============================================================================
# database.short_term_memories tests
# ============================================================================

def test_mark_consolidated_valid(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_short_coll = MagicMock()
    fake_doc_ref = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_short_coll
    fake_short_coll.document.return_value = fake_doc_ref
    fake_doc_ref.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    monkeypatch.setattr(stm, 'db', fake_db)

    stm.mark_consolidated('user-1', 'st-1', 'commit-123')

    fake_doc_ref.update.assert_called_once()
    payload = fake_doc_ref.update.call_args[0][0]
    assert payload['status'] == 'consolidated'
    assert payload['consolidated_commit_id'] == 'commit-123'
    assert isinstance(payload['consolidated_at'], datetime)


def test_mark_consolidated_doc_not_found_noop(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_short_coll = MagicMock()
    fake_doc_ref = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_short_coll
    fake_short_coll.document.return_value = fake_doc_ref
    fake_doc_ref.get.return_value = fake_snapshot
    fake_snapshot.exists = False
    monkeypatch.setattr(stm, 'db', fake_db)

    stm.mark_consolidated('user-1', 'st-1', 'commit-123')
    fake_doc_ref.update.assert_not_called()


def test_mark_consolidated_concurrent_not_found_exception(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_short_coll = MagicMock()
    fake_doc_ref = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_short_coll
    fake_short_coll.document.return_value = fake_doc_ref
    fake_doc_ref.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    fake_doc_ref.update.side_effect = NotFound("404 No document to update")
    monkeypatch.setattr(stm, 'db', fake_db)

    # Must no-op without raising
    stm.mark_consolidated('user-1', 'st-1', 'commit-123')


def test_mark_consolidated_invalid_inputs(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(stm, 'db', fake_db)

    stm.mark_consolidated('', 'st-1', 'commit-123')
    stm.mark_consolidated('   ', 'st-1', 'commit-123')
    stm.mark_consolidated('user-1', '', 'commit-123')
    stm.mark_consolidated('user-1', '   ', 'commit-123')
    stm.mark_consolidated(None, 'st-1', 'commit-123')
    stm.mark_consolidated('user-1', None, 'commit-123')

    fake_db.collection.assert_not_called()


def test_tombstone_source_valid(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_short_coll = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_short_coll

    doc1 = MagicMock()
    doc1.id = 'doc-1'
    doc1.to_dict.return_value = {
        'evidence': [
            {'source_id': 'source-target', 'redaction_status': 'active'},
            {'source_id': 'source-other', 'redaction_status': 'active'},
        ]
    }

    doc2 = MagicMock()
    doc2.id = 'doc-2'
    doc2.to_dict.return_value = {
        'evidence': [{'source_id': 'source-target', 'redaction_status': 'active'}]
    }

    fake_short_coll.stream.return_value = [doc1, doc2]
    monkeypatch.setattr(stm, 'db', fake_db)

    tombstoned = stm.tombstone_source('user-1', 'source-target')
    assert tombstoned == ['doc-1', 'doc-2']

    doc1.reference.update.assert_called_once()
    payload1 = doc1.reference.update.call_args[0][0]
    # doc1 still has active evidence from source-other
    assert 'status' not in payload1

    doc2.reference.update.assert_called_once()
    payload2 = doc2.reference.update.call_args[0][0]
    # doc2 has no remaining active evidence -> source_tombstoned
    assert payload2['status'] == 'source_tombstoned'
    assert payload2['redaction_status'] == 'payload_tombstoned'


def test_tombstone_source_handles_concurrent_not_found(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_short_coll = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_short_coll

    doc1 = MagicMock()
    doc1.id = 'doc-1'
    doc1.to_dict.return_value = {
        'evidence': [{'source_id': 'source-target', 'redaction_status': 'active'}]
    }
    doc1.reference.update.side_effect = NotFound("Document deleted concurrently")

    doc2 = MagicMock()
    doc2.id = 'doc-2'
    doc2.to_dict.return_value = {
        'evidence': [{'source_id': 'source-target', 'redaction_status': 'active'}]
    }

    fake_short_coll.stream.return_value = [doc1, doc2]
    monkeypatch.setattr(stm, 'db', fake_db)

    # doc1 fails with NotFound, doc2 succeeds; function continues without crash
    tombstoned = stm.tombstone_source('user-1', 'source-target')
    assert tombstoned == ['doc-2']


def test_tombstone_source_invalid_inputs(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(stm, 'db', fake_db)

    assert stm.tombstone_source('', 'source-1') == []
    assert stm.tombstone_source('user-1', '') == []
    assert stm.tombstone_source('   ', 'source-1') == []
    assert stm.tombstone_source(None, 'source-1') == []

    fake_db.collection.assert_not_called()


# ============================================================================
# database.sync_bridges tests
# ============================================================================

def test_mark_sync_bridge_cleaned_invalid_inputs():
    assert sync_bridges.mark_sync_bridge_cleaned('', 'src-1', 'rev-1', 'target') is False
    assert sync_bridges.mark_sync_bridge_cleaned('user-1', '', 'rev-1', 'target') is False
    assert sync_bridges.mark_sync_bridge_cleaned('   ', 'src-1', 'rev-1', 'target') is False
    assert sync_bridges.mark_sync_bridge_cleaned('user-1', '   ', 'rev-1', 'target') is False
    assert sync_bridges.mark_sync_bridge_cleaned(None, 'src-1', 'rev-1', 'target') is False


def test_mark_sync_bridge_cleaned_valid(monkeypatch):
    fake_client = MagicMock()
    fake_conv_coll = MagicMock()
    fake_doc_ref = MagicMock()
    fake_snapshot = MagicMock()
    fake_transaction = MagicMock()

    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref
    fake_doc_ref.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    fake_snapshot.to_dict.return_value = {
        'deleted': True,
        'sync_merged_into': 'merged-conv-1',
        'sync_content_revision': 'rev-1',
    }

    def fake_run_transactional(client, fn):
        return fn(fake_transaction)

    monkeypatch.setattr(sync_bridges, 'run_transactional', fake_run_transactional)

    success = sync_bridges.mark_sync_bridge_cleaned(
        'user-1', 'src-1', 'rev-1', 'audio-1', firestore_client=fake_client
    )
    assert success is True
    fake_transaction.update.assert_called_once_with(
        fake_doc_ref,
        {'sync_bridge_cleaned_revision': 'rev-1', 'sync_bridge_audio_target': 'audio-1'}
    )


def test_mark_sync_bridge_cleaned_not_deleted_or_unmerged(monkeypatch):
    fake_client = MagicMock()
    fake_doc_ref = MagicMock()
    fake_snapshot = MagicMock()
    fake_transaction = MagicMock()

    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref
    fake_doc_ref.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    fake_snapshot.to_dict.return_value = {
        'deleted': False,
        'sync_merged_into': None,
    }

    def fake_run_transactional(client, fn):
        return fn(fake_transaction)

    monkeypatch.setattr(sync_bridges, 'run_transactional', fake_run_transactional)

    success = sync_bridges.mark_sync_bridge_cleaned(
        'user-1', 'src-1', 'rev-1', 'audio-1', firestore_client=fake_client
    )
    assert success is False
    fake_transaction.update.assert_not_called()


def test_mark_sync_bridge_cleaned_revision_mismatch(monkeypatch):
    fake_client = MagicMock()
    fake_doc_ref = MagicMock()
    fake_snapshot = MagicMock()
    fake_transaction = MagicMock()

    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = fake_doc_ref
    fake_doc_ref.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    fake_snapshot.to_dict.return_value = {
        'deleted': True,
        'sync_merged_into': 'merged-conv-1',
        'sync_content_revision': 'old-rev',
    }

    def fake_run_transactional(client, fn):
        return fn(fake_transaction)

    monkeypatch.setattr(sync_bridges, 'run_transactional', fake_run_transactional)

    success = sync_bridges.mark_sync_bridge_cleaned(
        'user-1', 'src-1', 'new-rev', 'audio-1', firestore_client=fake_client
    )
    assert success is False
    fake_transaction.update.assert_not_called()


def test_mark_sync_bridge_cleaned_handles_not_found(monkeypatch):
    fake_client = MagicMock()

    def fake_run_transactional(client, fn):
        raise NotFound("Conversation document purged")

    monkeypatch.setattr(sync_bridges, 'run_transactional', fake_run_transactional)

    success = sync_bridges.mark_sync_bridge_cleaned(
        'user-1', 'src-1', 'rev-1', 'audio-1', firestore_client=fake_client
    )
    assert success is False
