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
    from database import sync_bridges

    store = StrictFirestore()
    mark = sync_bridges.mark_sync_bridge_cleaned
    monkeypatch.setattr(bridge, 'mark_sync_bridge_cleaned', lambda *a: mark(*a, firestore_client=store))
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
    from utils.conversations import merge_conversations

    # Exercise the public seams; replace only their external-effect leaves.
    monkeypatch.setattr(merge_conversations, '_delete_conversation_and_related_data', retract)
    monkeypatch.setattr(merge_conversations, '_copy_audio_chunks_for_merge', copy)

    def ingest(i):
        row = capture(i)
        row.update(status='completed', data_protection_level='enhanced', private_cloud_sync_enabled=True)
        result = lifecycle.ingest_sync_conversation('u', row)
        if result[0].get('sync_merged_from'):
            bridge.finish_sync_bridges('u', result[0]['id'])
        return result

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
    ingest(0)
    fired = False

    def copy_then_bridge(*args, **kwargs):
        nonlocal fired
        if not fired:
            fired = True
            ingest(2)

    copy.side_effect = copy_then_bridge
    assert bridge.finish_sync_bridges('u', 'chunk-004', audio_source_id='chunk-008') == 'chunk-000'
    assert store.rows[('users', 'u', 'conversations', 'chunk-000')]['sync_merged_from'] == ['chunk-004', 'chunk-008']


def test_shared_cleanup_retains_capture_and_propagates_task_failure(monkeypatch):
    from utils.conversations import merge_conversations as merge
    from database import action_items

    monkeypatch.setattr(merge, 'retraction_can_be_skipped', lambda *a, **kw: True)
    monkeypatch.setattr(merge, 'MemoryService', MagicMock())
    tasks = MagicMock(side_effect=RuntimeError('task store unavailable'))
    # The current merge cleanup reads source tasks before deleting them so it
    # can cancel client reminders. Keep this test hermetic across both the
    # legacy delete-only path and the reminder-aware path.
    monkeypatch.setattr(action_items, 'get_action_items_by_conversation', lambda *a, **kw: [])
    monkeypatch.setattr(action_items, 'delete_action_items_for_conversation', tasks)
    audio = MagicMock()
    delete = MagicMock()
    monkeypatch.setattr(merge, 'delete_conversation_audio_files', audio)
    monkeypatch.setattr(merge.conversations_db, 'delete_conversation', delete)
    monkeypatch.setattr(merge.conversations_db, '_delete_conversation_search_index', MagicMock())
    monkeypatch.setattr(merge, 'delete_vector', MagicMock())
    with pytest.raises(RuntimeError, match='task store unavailable'):
        merge.retract_sync_bridge_source('u', 'donor')
    tasks.side_effect = None
    merge.retract_sync_bridge_source('u', 'donor')
    audio.assert_not_called()
    delete.assert_not_called()


def test_cleanup_receipt_skips_later_appends_and_retries_failed_cleanup(system):
    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    retract.side_effect = RuntimeError('cleanup failed')
    with pytest.raises(RuntimeError, match='cleanup failed'):
        ingest(2)
    donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    assert 'sync_bridge_cleaned_revision' not in donor
    retract.side_effect = None
    ingest(3)  # a different append recovers the interrupted cleanup
    assert donor['sync_bridge_cleaned_revision'] == donor['sync_content_revision']
    retract.reset_mock()
    copy.reset_mock()
    ingest(5)
    retract.assert_not_called()
    copy.assert_not_called()
    donor['sync_content_revision'] += 1
    ingest(6)
    retract.assert_called_once_with('u', 'chunk-004', retain_capture=True)


def test_late_audio_copies_without_retracting_completed_ancestor(system):
    from utils.sync import bridge

    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    ingest(2)
    retract.reset_mock()
    copy.reset_mock()
    assert bridge.finish_sync_bridges('u', 'chunk-004', audio_source_id='chunk-004') == 'chunk-000'
    retract.assert_not_called()
    copy.assert_called_once_with('u', [{'id': 'chunk-004'}], 'chunk-000', strict=True)


def test_receipt_does_not_mark_a_newer_tombstone_revision(system):
    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)

    def advance_revision(*a, **kw):
        store.rows[('users', 'u', 'conversations', 'chunk-004')]['sync_content_revision'] += 1

    retract.side_effect = advance_revision
    with pytest.raises(RuntimeError, match='completion revision changed'):
        ingest(2)
    assert 'sync_bridge_cleaned_revision' not in store.rows[('users', 'u', 'conversations', 'chunk-004')]


def test_transactional_ingest_does_not_run_external_cleanup(system):
    from utils.conversations import lifecycle

    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    row = capture(2)
    row['status'] = 'completed'
    result = lifecycle.ingest_sync_conversation('u', row)
    assert result[0]['sync_merged_from'] == ['chunk-004']
    retract.assert_not_called()
    copy.assert_not_called()


def test_failed_late_audio_copy_is_pending_without_transient_source_hint(system):
    from utils.sync import bridge

    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    ingest(2)
    retract.reset_mock()
    copy.side_effect = RuntimeError('copy unavailable')
    with pytest.raises(RuntimeError, match='copy unavailable'):
        bridge.finish_sync_bridges('u', 'chunk-004', audio_source_id='chunk-004')
    donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    assert donor['sync_bridge_audio_target'] is None
    assert donor['sync_bridge_cleaned_revision'] == donor['sync_content_revision']
    copy.side_effect = None
    copy.reset_mock()
    ingest(3)
    retract.assert_not_called()
    copy.assert_called_once_with('u', [{'id': 'chunk-004'}], 'chunk-000', strict=True)


def test_intake_accepts_chunk_when_destructive_gate_is_held_and_retraction_converges_later(system, caplog):
    """Held account gate must not fail accepted sync intake; retraction defers then converges.

    POST /v2/sync-local-files answers 202 only after the chunk is admitted. Donor
    retraction that collides with the exclusive destructive-operation gate used
    to raise DestructiveOperationInProgress and turn that admission into a 503.
    """
    from database.legal_holds import DestructiveOperationInProgress

    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    retract.side_effect = DestructiveOperationInProgress('another destructive operation owns the account gate')
    with caplog.at_level('INFO'):
        row, _, _ = ingest(2)
        assert len(row['transcript_segments']) == 3
        donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
        assert donor['deleted'] and donor['sync_merged_into'] == 'chunk-000'
        assert 'sync_bridge_cleaned_revision' not in donor
        copy.assert_called_with('u', [{'id': 'chunk-004'}], 'chunk-000', strict=True)
        assert any('event=sync_bridge outcome=deferred' in record.message for record in caplog.records)
        retract.side_effect = None
        retract.reset_mock()
        copy.reset_mock()
        ingest(3)
        assert donor['sync_bridge_cleaned_revision'] == donor['sync_content_revision']
        retract.assert_called_with('u', 'chunk-004', retain_capture=True)
        assert any('event=sync_bridge outcome=converged' in record.message for record in caplog.records)


def test_sync_bridge_retraction_does_not_claim_the_account_destructive_gate(monkeypatch):
    from utils.conversations import merge_conversations as merge
    from database import action_items

    seen: dict[str, object] = {}

    class FakeMemoryService:
        def __init__(self, db_client=None):
            del db_client

        def retract_conversation_memories(self, uid, conversation_id, **kwargs):
            del uid, conversation_id
            seen.update(kwargs)

    monkeypatch.setattr(merge, 'retraction_can_be_skipped', lambda *a, **kw: False)
    monkeypatch.setattr(merge, 'MemoryService', FakeMemoryService)
    # Source-task lookup is part of merge cleanup on current main; avoid
    # constructing a real Firestore client in this seam-focused test.
    monkeypatch.setattr(action_items, 'get_action_items_by_conversation', lambda *a, **kw: [])
    monkeypatch.setattr(action_items, 'delete_action_items_for_conversation', MagicMock(return_value=0))
    monkeypatch.setattr(merge, 'delete_conversation_audio_files', MagicMock())
    monkeypatch.setattr(merge.conversations_db, 'delete_conversation', MagicMock())
    monkeypatch.setattr(merge.conversations_db, '_delete_conversation_search_index', MagicMock())
    monkeypatch.setattr(merge, 'delete_vector', MagicMock())
    merge.retract_sync_bridge_source('u', 'donor')
    assert seen.get('claim_destructive_gate') is False


def test_shared_cleanup_reminder_failure_does_not_fail_bridge_retraction(monkeypatch):
    """FCM cancel is best-effort after the task rows are already gone.

    Sync-bridge cleanup retries the whole donor retraction. If reminder delivery
    shared the task-store try, an FCM/ADC fault would raise after delete and
    consume that retry budget; a later retry would see no rows and never send
    the cancel. Keep delivery isolated, like process_conversation replacement.
    """
    from utils.conversations import merge_conversations as merge
    from database import action_items

    monkeypatch.setattr(merge, 'retraction_can_be_skipped', lambda *a, **kw: True)
    monkeypatch.setattr(merge, 'MemoryService', MagicMock())
    monkeypatch.setattr(
        action_items,
        'get_action_items_by_conversation',
        lambda *a, **kw: [{'id': 'task-open', 'due_at': '2026-09-21T09:00:00+00:00', 'completed': False}],
    )
    monkeypatch.setattr(action_items, 'delete_action_items_for_conversation', MagicMock(return_value=1))
    monkeypatch.setattr(merge, '_sync_source_task_reminder', MagicMock(side_effect=RuntimeError('fcm unavailable')))
    audio = MagicMock()
    delete = MagicMock()
    monkeypatch.setattr(merge, 'delete_conversation_audio_files', audio)
    monkeypatch.setattr(merge.conversations_db, 'delete_conversation', delete)
    monkeypatch.setattr(merge.conversations_db, '_delete_conversation_search_index', MagicMock())
    monkeypatch.setattr(merge, 'delete_vector', MagicMock())
    merge.retract_sync_bridge_source('u', 'donor')
    audio.assert_not_called()
    delete.assert_not_called()
    merge._sync_source_task_reminder.assert_called_once()


def test_bridge_failure_log_includes_bounded_reason(system, caplog):
    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    retract.side_effect = RuntimeError('canonical retraction conflicted repeatedly')
    with caplog.at_level('ERROR'):
        with pytest.raises(RuntimeError, match='canonical retraction conflicted repeatedly'):
            ingest(2)
    assert any(
        'event=sync_bridge outcome=failed' in record.message
        and 'exception_type=RuntimeError' in record.message
        and 'reason=canonical retraction conflicted repeatedly' in record.message
        for record in caplog.records
    )
    donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    assert 'sync_bridge_cleaned_revision' not in donor
    copy.assert_not_called()


def test_bare_assertion_failure_logs_empty_reason_and_does_not_receipt(system, caplog):
    """A stripped AssertionError must be diagnosable as reason=empty, not silent."""
    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    retract.side_effect = AssertionError()
    with caplog.at_level('ERROR'):
        with pytest.raises(AssertionError):
            ingest(2)
    assert any(
        'event=sync_bridge outcome=failed' in record.message
        and 'exception_type=AssertionError' in record.message
        and 'reason=empty' in record.message
        for record in caplog.records
    )
    donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    assert 'sync_bridge_cleaned_revision' not in donor
    copy.assert_not_called()
