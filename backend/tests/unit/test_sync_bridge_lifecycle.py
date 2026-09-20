"""Transactional intake plus replayable bridge effects with all service leaves fake."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_capture_continuity import capture


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from database import conversations
    from utils.conversations import lifecycle, merge_conversations
    from utils.sync import bridge


@pytest.fixture
def system(monkeypatch):
    from database import conversations as db
    from utils.conversations import lifecycle
    from utils.sync import bridge

    store = StrictFirestore()
    assign = db.assign_sync_conversation
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(
        db, 'assign_sync_conversation', lambda uid, row, **kw: assign(uid, row, firestore_client=store, **kw)
    )
    monkeypatch.setattr(
        db, 'get_conversation', lambda uid, cid: deepcopy(store.rows.get(('users', 'u', 'conversations', cid)))
    )
    retract = MagicMock()
    copy = MagicMock()
    monkeypatch.setattr(bridge, '_delete_conversation_and_related_data', retract)
    monkeypatch.setattr(bridge, '_copy_audio_chunks_for_merge', copy)

    def ingest(i):
        row = capture(i)
        row.update(status='completed', data_protection_level='enhanced', private_cloud_sync_enabled=True)
        return lifecycle.ingest_sync_conversation('u', row)

    return store, ingest, retract, copy


def test_bridge_cleanup_failure_is_retryable_after_atomic_persistence(system):
    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    retract.side_effect = RuntimeError('retraction unavailable')
    with pytest.raises(RuntimeError, match='retraction unavailable'):
        ingest(2)
    loser = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    assert loser['deleted'] and loser['sync_merged_into'] == 'chunk-000'
    copy.assert_not_called()
    retract.side_effect = None
    row, _, survivors = ingest(2)
    assert survivors == []
    assert len(row['transcript_segments']) == 3
    retract.assert_called_with('u', 'chunk-004', retain_capture=True)
    copy.assert_called_with('u', [{'id': 'chunk-004'}], 'chunk-000', strict=True)


def test_stale_snapshots_of_survivor_and_donor_cannot_commit(system, monkeypatch):
    from database import conversations as db

    store, ingest, _, _ = system
    old_left = ingest(0)[0]
    old_right = ingest(4)[0]
    ingest(2)
    monkeypatch.setattr(db, 'db', store)
    for old in (old_left, old_right):
        assert not db.persist_processing_result_with_lifecycle('u', old)


def test_cleanup_follows_bridge_that_wins_during_audio_copy(system):
    from utils.sync import bridge

    store, ingest, retract, copy = system
    ingest(4)
    ingest(8)
    ingest(6)
    fired = False

    def copy_then_bridge(*args, **kwargs):
        nonlocal fired
        if not fired:
            fired = True
            ingest(2)

    copy.side_effect = copy_then_bridge
    assert bridge.finish_sync_bridges('u', 'chunk-004') == 'chunk-002'
    assert store.rows[('users', 'u', 'conversations', 'chunk-002')]['sync_merged_from'] == ['chunk-004', 'chunk-008']


def test_shared_cleanup_retains_capture_and_propagates_task_failure(monkeypatch):
    from utils.conversations import merge_conversations as merge
    from database import action_items

    monkeypatch.setattr(merge, 'retraction_can_be_skipped', lambda *a, **kw: True)
    monkeypatch.setattr(merge, 'MemoryService', MagicMock())
    tasks = MagicMock(side_effect=RuntimeError('task store unavailable'))
    monkeypatch.setattr(action_items, 'delete_action_items_for_conversation', tasks)
    audio = MagicMock()
    delete = MagicMock()
    monkeypatch.setattr(merge, 'delete_conversation_audio_files', audio)
    monkeypatch.setattr(merge.conversations_db, 'delete_conversation', delete)
    monkeypatch.setattr(merge.conversations_db, '_delete_conversation_search_index', MagicMock())
    monkeypatch.setattr(merge, 'delete_vector', MagicMock())
    with pytest.raises(RuntimeError, match='task store unavailable'):
        merge._delete_conversation_and_related_data('u', 'donor', retain_capture=True)
    tasks.side_effect = None
    merge._delete_conversation_and_related_data('u', 'donor', retain_capture=True)
    audio.assert_not_called()
    delete.assert_not_called()
