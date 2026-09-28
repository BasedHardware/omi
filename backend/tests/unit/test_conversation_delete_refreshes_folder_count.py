import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.folders as folders_db
from utils.conversations import merge_conversations

UID = 'uid-folder-count'


def _delete(monkeypatch, row):
    deleted = []
    refreshed = []
    monkeypatch.setattr(merge_conversations.conversations_db, 'get_conversation', lambda uid, cid: dict(row))
    monkeypatch.setattr(
        merge_conversations.conversations_db, 'delete_conversation', lambda uid, cid: deleted.append(cid)
    )
    monkeypatch.setattr(
        folders_db, 'update_folder_conversation_count', lambda uid, folder_id: refreshed.append((uid, folder_id))
    )
    merge_conversations.delete_conversation_with_sync_sources(UID, 'conv-1')
    return deleted, refreshed


def test_deleting_a_filed_conversation_refreshes_the_folder_count(monkeypatch):
    deleted, refreshed = _delete(monkeypatch, {'id': 'conv-1', 'folder_id': 'folder-1'})

    assert deleted == ['conv-1']
    assert refreshed == [(UID, 'folder-1')]


def test_deleting_an_unfiled_conversation_refreshes_nothing(monkeypatch):
    deleted, refreshed = _delete(monkeypatch, {'id': 'conv-1', 'folder_id': None})

    assert deleted == ['conv-1']
    assert refreshed == []


def test_a_failed_count_refresh_does_not_fail_the_delete(monkeypatch):
    def _boom(uid, folder_id):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(merge_conversations.conversations_db, 'get_conversation', lambda uid, cid: {'folder_id': 'f1'})
    monkeypatch.setattr(merge_conversations.conversations_db, 'delete_conversation', lambda uid, cid: None)
    monkeypatch.setattr(folders_db, 'update_folder_conversation_count', _boom)

    merge_conversations.delete_conversation_with_sync_sources(UID, 'conv-1')
