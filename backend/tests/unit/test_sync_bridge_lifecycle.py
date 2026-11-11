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
    from database import action_item_refresh

    store = StrictFirestore()
    monkeypatch.setattr(action_item_refresh, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(action_item_refresh, 'bump_action_items_list_version', lambda uid: None)
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
            import threading

            bridge.finish_sync_segment(
                'u', result[0], {'new_memories': set(), 'updated_memories': set()}, threading.Lock(), 'en'
            )
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
    copy.assert_called_with('u', [{'id': 'chunk-004'}], 'chunk-000', strict=True, skip_existing=True)


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
    copy.assert_called_once_with('u', [{'id': 'chunk-004'}], 'chunk-000', strict=True, skip_existing=True)


def test_bridge_redirect_cycle_is_bounded_as_assignment_conflict_subtype(monkeypatch):
    from utils.sync import bridge

    monkeypatch.setattr(
        bridge.conversations_db,
        'get_conversation',
        lambda uid, conversation_id: {'id': conversation_id, 'sync_merged_into': 'loop'},
    )

    with pytest.raises(bridge.SyncAssignmentConflict, match='redirect cycle') as exc_info:
        bridge.finish_sync_bridges('u', 'loop')

    assert exc_info.value.subtype == 'redirect_cycle'


def test_bridge_source_shape_conflict_has_its_own_subtype(monkeypatch):
    from utils.sync import bridge

    rows = {
        'survivor': {'id': 'survivor', 'sync_merged_from': ['donor']},
        'donor': {'id': 'donor', 'deleted': False},
    }
    monkeypatch.setattr(bridge.conversations_db, 'get_conversation', lambda uid, cid: rows.get(cid))

    with pytest.raises(bridge.SyncAssignmentConflict, match='source missing or not a tombstone') as exc_info:
        bridge.finish_sync_bridges('u', 'survivor')

    assert exc_info.value.subtype == 'bridge_source_not_tombstone'


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
    copy.assert_called_once_with('u', [{'id': 'chunk-004'}], 'chunk-000', strict=True, skip_existing=True)


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
        copy.assert_called_with('u', [{'id': 'chunk-004'}], 'chunk-000', strict=True, skip_existing=True)
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


@pytest.mark.parametrize('redirect', [False, True])
def test_refresh_target_changes_after_bridge_read_without_failing_persisted_intake(system, monkeypatch, redirect):
    from utils.sync import bridge

    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    transfer = bridge.transfer_donor
    changed = False

    def change_before_refresh(uid, donor_id, target_id):
        nonlocal changed
        if not changed:
            changed = True
            target = store.rows[('users', 'u', 'conversations', target_id)]
            if redirect:
                survivor = deepcopy(target)
                survivor['id'] = 'survivor'
                survivor['sync_merged_from'] = [target_id, donor_id]
                store.rows[('users', 'u', 'conversations', 'survivor')] = survivor
                target['sync_merged_into'] = 'survivor'
            target['deleted'] = True
        transfer(uid, donor_id, target_id)

    monkeypatch.setattr(bridge, 'transfer_donor', change_before_refresh)
    row, _, _ = ingest(2)
    donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    assert row['transcript_segments']  # assignment committed before finalize
    if redirect:
        copy.assert_called_with('u', [{'id': 'chunk-004'}], 'survivor', strict=True, skip_existing=True)
        assert donor['sync_bridge_cleaned_revision'] == donor['sync_content_revision']
    else:
        retract.assert_not_called()
        copy.assert_not_called()
        assert 'sync_bridge_cleaned_revision' not in donor


def test_failed_refresh_preserves_donor_and_pending_receipt_then_converges(system, monkeypatch):
    from utils.sync import bridge

    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    transfer = bridge.transfer_donor
    failed = MagicMock(side_effect=RuntimeError('refresh unavailable'))
    monkeypatch.setattr(bridge, 'transfer_donor', failed)
    ingest(2)
    donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    retract.assert_not_called()
    assert 'sync_bridge_cleaned_revision' not in donor
    copy.assert_called_once()
    monkeypatch.setattr(bridge, 'transfer_donor', transfer)
    bridge.finish_sync_bridges('u', 'chunk-000')
    retract.assert_called_once()
    assert donor['sync_bridge_cleaned_revision'] == donor['sync_content_revision']


def test_refresh_recovery_kill_switch_retains_strict_failure(system, monkeypatch):
    from database.action_item_refresh import RefreshConversationUnavailable
    from utils.sync import bridge

    _, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    monkeypatch.setenv('SYNC_FINALIZE_TARGET_RECOVERY_ENABLED', 'off')
    monkeypatch.setattr(bridge, 'transfer_donor', MagicMock(side_effect=RefreshConversationUnavailable()))
    with pytest.raises(RefreshConversationUnavailable):
        ingest(2)
    retract.assert_not_called()
    copy.assert_not_called()


def test_deleted_target_completes_intake_after_audio_and_clears_response(monkeypatch):
    import threading
    from utils.sync import bridge
    from utils.sync.intake_completion import complete_sync_intake

    monkeypatch.setattr(bridge.conversations_db, 'get_conversation', lambda *a: {'deleted': True})
    events = []
    response = {'new_memories': set(), 'updated_memories': set()}
    complete_sync_intake(
        uid='u',
        assigned={'id': 'gone', 'sync_relevance': 'keep', 'sync_merged_from': ['donor']},
        created=False,
        survivors=[{}],
        response=response,
        lock=threading.Lock(),
        language='en',
        audio_enabled=True,
        store_audio=lambda cid: events.append('audio'),
        mark_finalize=lambda: events.append('finalize'),
        finish=bridge.finish_sync_segment,
        acknowledge=lambda: events.append('ack'),
    )
    assert events == ['audio', 'finalize', 'ack']
    assert response == {'new_memories': set(), 'updated_memories': set(), '_merged': {}}


@pytest.mark.parametrize('value, expected', [('', True), ('true', True), ('off', False), ('typo', False)])
def test_finalize_recovery_switch_is_default_on_and_typos_disable(monkeypatch, value, expected):
    from config.sync_finalize import sync_finalize_target_recovery_enabled

    monkeypatch.setenv('SYNC_FINALIZE_TARGET_RECOVERY_ENABLED', value)
    assert sync_finalize_target_recovery_enabled() is expected


def test_refresh_guard_diagnostic_identifies_site_without_message(system):
    from database import action_item_refresh
    from utils.sync.telemetry import finalize_exception_site

    with pytest.raises(action_item_refresh.RefreshConversationUnavailable) as caught:
        action_item_refresh.reconcile('u', 'missing', [], expected_revision=None)
    assert finalize_exception_site(caught.value) == 'action_item_refresh'


@pytest.mark.parametrize('flatten', ['true', 'off'])
def test_redirect_during_refresh_retains_transitive_sync_donors(system, monkeypatch, flatten):
    from utils.sync import bridge

    monkeypatch.setenv('CONVERSATION_SMART_MERGE_FLATTEN_ENABLED', flatten)
    store, ingest, retract, copy = system
    ingest(4)
    ingest(8)
    ingest(0)
    transfer = bridge.transfer_donor
    fired = False

    def absorb_before_refresh(uid, donor_id, target_id):
        nonlocal fired
        if not fired:
            fired = True
            ingest(2)  # real atomic sync assignment absorbs the current target
        transfer(uid, donor_id, target_id)

    monkeypatch.setattr(bridge, 'transfer_donor', absorb_before_refresh)
    ingest(6)
    target = store.rows[('users', 'u', 'conversations', 'chunk-000')]
    assert set(target['sync_merged_from']) == {'chunk-004', 'chunk-008'}
    for source in ('chunk-004', 'chunk-008'):
        donor = store.rows[('users', 'u', 'conversations', source)]
        assert donor['sync_bridge_cleaned_revision'] == donor['sync_content_revision']
    assert ('u', [{'id': 'chunk-008'}], 'chunk-000') in [c.args for c in copy.call_args_list]


def test_silent_bridge_keeps_notification_capable_cleanup_debt(system, monkeypatch):
    from utils.sync import bridge

    store, ingest, retract, copy = system
    ingest(0)
    ingest(4)
    # Persist a bridge without running its ordinary post-persist callback.
    from utils.conversations import lifecycle

    incoming = capture(2)
    incoming.update(status='completed', data_protection_level='enhanced', private_cloud_sync_enabled=True)
    lifecycle.ingest_sync_conversation('u', incoming)
    transfer = MagicMock()
    monkeypatch.setattr(bridge, 'transfer_donor', transfer)
    assert bridge.finish_sync_bridges('u', 'chunk-000', silent=True) == 'chunk-000'
    transfer.assert_not_called()
    retract.assert_not_called()
    assert 'sync_bridge_cleaned_revision' not in store.rows[('users', 'u', 'conversations', 'chunk-004')]
    copy.assert_called_once()
    # Normal later work still owns the retained cleanup; silence is not global.
    bridge.finish_sync_bridges('u', 'chunk-000')
    transfer.assert_called_once()
    retract.assert_called_once()
