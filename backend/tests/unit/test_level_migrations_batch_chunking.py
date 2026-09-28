"""Tests for level migration Firestore batch chunking.

Verifies that migrate_memories_level_batch and migrate_chats_level_batch chunk batch writes
into max 450 operations per batch commit, staying safely below Firestore's 500-write limit.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

import database.chat as chat_db
import database.memories as memories_db


@contextmanager
def dummy_fence(uid, firestore_client=None):
    yield


def test_migrate_memories_level_batch_chunks_commits(monkeypatch):
    mock_db = MagicMock()
    mock_batch1 = MagicMock()
    mock_batch2 = MagicMock()
    mock_db.batch.side_effect = [mock_batch1, mock_batch2]

    # Create 600 mock document snapshots requiring migration
    mock_snapshots = []
    for i in range(600):
        snap = MagicMock()
        snap.exists = True
        snap.to_dict.return_value = {'data_protection_level': 'standard', 'content': f'Memory {i}'}
        snap.reference = f'ref-{i}'
        mock_snapshots.append(snap)

    mock_db.get_all.return_value = mock_snapshots

    monkeypatch.setattr(memories_db, 'external_write_fence', dummy_fence)
    monkeypatch.setattr(memories_db, '_get_db', lambda client=None: mock_db)
    monkeypatch.setattr(memories_db, '_prepare_memory_for_read', lambda data, uid: data)
    monkeypatch.setattr(memories_db, 'encryption', MagicMock(encrypt=lambda text, uid: f'encrypted-{text}'))

    memory_ids = [f'mem-{i}' for i in range(600)]
    memories_db.migrate_memories_level_batch('user-123', memory_ids, 'enhanced')

    # Verify batch.commit() was called on both batch instances
    mock_batch1.commit.assert_called_once()
    mock_batch2.commit.assert_called_once()

    # batch1 should have received 450 updates, batch2 should have received 150 updates
    assert mock_batch1.update.call_count == 450
    assert mock_batch2.update.call_count == 150


def test_migrate_chats_level_batch_chunks_commits(monkeypatch):
    mock_db = MagicMock()
    mock_batch1 = MagicMock()
    mock_batch2 = MagicMock()
    mock_db.batch.side_effect = [mock_batch1, mock_batch2]

    # Create 600 mock document snapshots requiring migration
    mock_snapshots = []
    for i in range(600):
        snap = MagicMock()
        snap.exists = True
        snap.to_dict.return_value = {'data_protection_level': 'standard', 'text': f'Message {i}'}
        snap.reference = f'ref-{i}'
        mock_snapshots.append(snap)

    mock_db.get_all.return_value = mock_snapshots

    monkeypatch.setattr(chat_db, 'db', mock_db)
    monkeypatch.setattr(chat_db, '_prepare_message_for_read', lambda data, uid: data)
    monkeypatch.setattr(chat_db, 'encryption', MagicMock(encrypt=lambda text, uid: f'encrypted-{text}'))

    msg_ids = [f'msg-{i}' for i in range(600)]
    chat_db.migrate_chats_level_batch('user-123', msg_ids, 'enhanced')

    # Verify batch.commit() was called on both batch instances
    mock_batch1.commit.assert_called_once()
    mock_batch2.commit.assert_called_once()

    # batch1 should have received 450 updates, batch2 should have received 150 updates
    assert mock_batch1.update.call_count == 450
    assert mock_batch2.update.call_count == 150
