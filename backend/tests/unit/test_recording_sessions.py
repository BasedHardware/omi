"""Contract tests for durable listen recording-session routing (#9351)."""

from __future__ import annotations

from typing import Any

import pytest

from database import conversations as conversations_db
from database import recording_sessions
from tests.store_fakes import FakeDocumentStore
from utils.conversations import lifecycle as lifecycle_service


def _stored_conversation(segments: list[dict[str, Any]], *, level: str = 'standard') -> dict[str, Any]:
    """Encode a conversation exactly as the production write path stores it.

    Seeding a raw ``transcript_segments`` list is what let the empty-cleanup
    guard ship reading a compressed blob as if it were a plain list.
    """
    return conversations_db.encode_conversation_for_write(
        'uid',
        {'id': 'conversation', 'status': 'in_progress', 'transcript_segments': segments},
        level,
    )


@pytest.fixture
def recording_store(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(recording_sessions, '_store', lambda: store)
    return store


def test_retry_keeps_one_canonical_recording_session_binding(recording_store):
    first = recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation')
    retry = recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation')

    assert first == retry
    assert first['mapping_conflict'] is False
    assert len(recording_store._docs) == 1


def test_completed_retry_returns_its_canonical_terminal_envelope(recording_store):
    recording_sessions.create_or_get_recording_session('uid', 'recording-one', 'conversation-one')
    recording_sessions.record_lifecycle_event('uid', 'recording-one', 'conversation-one', 'processing')
    completed = recording_sessions.record_lifecycle_event('uid', 'recording-one', 'conversation-one', 'completed')

    retry = recording_sessions.create_or_get_recording_session(
        'uid', 'recording-one', 'new-proposed-conversation'
    )
    replay = recording_sessions.record_lifecycle_event(
        'uid', 'recording-one', retry['conversation_id'], 'completed'
    )
    rollover = recording_sessions.create_or_get_recording_session('uid', 'recording-two', 'conversation-two')

    assert retry['conversation_id'] == 'conversation-one'
    assert retry['mapping_conflict'] is True
    assert replay['accepted'] is True
    assert replay['lifecycle_phase'] == 'completed'
    assert replay['lifecycle_sequence'] == completed['lifecycle_sequence']
    assert rollover['conversation_id'] == 'conversation-two'
    assert len(recording_store._docs) == 2


def test_empty_recording_tombstone_forces_a_fresh_live_generation(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    monkeypatch.setattr(lifecycle_service.conversations_db, 'get_conversation', lambda *_: None)
    lifecycle_service.open_recording_session('uid', 'recording-old', 'conversation-old')

    tombstone = lifecycle_service.tombstone_recording_session('uid', 'recording-old', 'conversation-old')
    reconnect = lifecycle_service.open_live_recording_session('uid', 'recording-old', 'conversation-old')
    fresh = lifecycle_service.open_live_recording_session('uid', 'recording-new', 'conversation-new')
    original = recording_sessions.get_recording_session('uid', 'recording-old')

    assert tombstone is not None
    assert tombstone['lifecycle_phase'] == 'discarded'
    assert reconnect['requires_rollover'] is True
    assert fresh['requires_rollover'] is False
    assert fresh['conversation_id'] == 'conversation-new'
    assert fresh['conversation_id'] != reconnect['conversation_id']
    assert original is not None
    assert original['lifecycle_phase'] == 'discarded'


def test_missing_active_binding_is_tombstoned_before_rollover(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    monkeypatch.setattr(lifecycle_service.conversations_db, 'get_conversation', lambda *_: None)
    lifecycle_service.open_recording_session('uid', 'recording-old', 'conversation-old')

    reconnect = lifecycle_service.open_live_recording_session('uid', 'recording-old', 'conversation-old')
    original = recording_sessions.get_recording_session('uid', 'recording-old')

    assert reconnect['requires_rollover'] is True
    assert original is not None
    assert original['lifecycle_phase'] == 'discarded'


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_empty_cleanup_atomically_tombstones_its_session(recording_store, level):
    conversation_path = 'users/uid/conversations/conversation'
    recording_store.set(conversation_path, _stored_conversation([], level=level))
    recording_sessions.create_or_get_recording_session('uid', 'recording', 'conversation')

    deleted = recording_sessions.tombstone_and_delete_empty_conversation('uid', 'conversation', 'recording')
    binding = recording_sessions.get_recording_session('uid', 'recording')

    assert deleted is True
    assert conversation_path not in recording_store._docs
    assert binding is not None
    assert binding['lifecycle_phase'] == 'discarded'


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_empty_cleanup_refuses_late_content_without_tombstoning(recording_store, level):
    conversation_path = 'users/uid/conversations/conversation'
    recording_store.set(conversation_path, _stored_conversation([{'id': 'late-segment', 'text': 'persisted'}], level=level))
    recording_sessions.create_or_get_recording_session('uid', 'recording', 'conversation')

    deleted = recording_sessions.tombstone_and_delete_empty_conversation('uid', 'conversation', 'recording')
    binding = recording_sessions.get_recording_session('uid', 'recording')

    assert deleted is False
    assert conversation_path in recording_store._docs
    assert binding is not None
    assert binding['lifecycle_phase'] == 'in_progress'


def test_empty_cleanup_keeps_a_conversation_whose_segments_cannot_be_decoded(recording_store):
    conversation_path = 'users/uid/conversations/conversation'
    recording_store.set(
        conversation_path,
        {
            'id': 'conversation',
            'status': 'in_progress',
            'transcript_segments': b'not-a-zlib-stream',
            'transcript_segments_compressed': True,
        },
    )
    recording_sessions.create_or_get_recording_session('uid', 'recording', 'conversation')

    deleted = recording_sessions.tombstone_and_delete_empty_conversation('uid', 'conversation', 'recording')

    assert deleted is False
    assert conversation_path in recording_store._docs


def test_conflicting_retry_returns_the_original_conversation(recording_store):
    recording_sessions.create_or_get_recording_session('uid', 'session', 'first-conversation')

    result = recording_sessions.create_or_get_recording_session('uid', 'session', 'second-conversation')

    assert result['conversation_id'] == 'first-conversation'
    assert result['mapping_conflict'] is True


def test_same_recording_id_is_scoped_to_each_user(recording_store):
    one = recording_sessions.create_or_get_recording_session('first-user', 'session', 'first-conversation')
    two = recording_sessions.create_or_get_recording_session('second-user', 'session', 'second-conversation')

    assert (one['conversation_id'], two['conversation_id']) == ('first-conversation', 'second-conversation')
    assert len(recording_store._docs) == 2


def test_events_are_monotonic_and_stale_callbacks_are_discarded(recording_store):
    recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation')

    processing = recording_sessions.record_lifecycle_event('uid', 'session', 'conversation', 'processing')
    completed = recording_sessions.record_lifecycle_event('uid', 'session', 'conversation', 'completed')
    stale = recording_sessions.record_lifecycle_event('uid', 'session', 'conversation', 'processing')

    assert (processing['accepted'], processing['lifecycle_sequence']) == (True, 1)
    assert (completed['accepted'], completed['lifecycle_sequence']) == (True, 2)
    assert stale['accepted'] is False
    assert stale['discard_reason'] == 'terminal_immutable'
    assert stale['lifecycle_sequence'] == 2


@pytest.mark.parametrize('terminal_phase', ('completed', 'failed', 'discarded'))
@pytest.mark.parametrize('replacement_phase', ('completed', 'failed', 'discarded'))
def test_terminal_session_phase_is_immutable(recording_store, terminal_phase, replacement_phase):
    if terminal_phase == replacement_phase:
        return
    recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation')
    if terminal_phase != 'completed':
        recording_sessions.record_lifecycle_event('uid', 'session', 'conversation', 'processing')
    terminal = recording_sessions.record_lifecycle_event('uid', 'session', 'conversation', terminal_phase)
    replacement = recording_sessions.record_lifecycle_event('uid', 'session', 'conversation', replacement_phase)

    assert replacement['accepted'] is False
    assert replacement['discard_reason'] == 'terminal_immutable'
    assert replacement['lifecycle_sequence'] == terminal['lifecycle_sequence']


def test_event_for_a_different_conversation_is_discarded(recording_store):
    recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation')

    result = recording_sessions.record_lifecycle_event('uid', 'session', 'other-conversation', 'processing')

    assert result['accepted'] is False
    assert result['discard_reason'] == 'mapping_conflict'
    assert result['conversation_id'] == 'conversation'


def test_lifecycle_owner_enforces_a_conflicting_durable_binding(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    lifecycle_service.open_recording_session('uid', 'session', 'first-conversation')

    result = lifecycle_service.open_recording_session('uid', 'session', 'second-conversation')

    assert result['conversation_id'] == 'first-conversation'
    assert result['mapping_conflict'] is True


def test_shadow_mode_keeps_legacy_route_but_reports_the_mismatch(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')
    lifecycle_service.open_recording_session('uid', 'session', 'first-conversation')

    result = lifecycle_service.open_recording_session('uid', 'session', 'second-conversation')

    assert result['conversation_id'] == 'second-conversation'
    assert result['mapping_conflict'] is True
    assert result['lifecycle_version'] is None
    assert result['lifecycle_phase'] is None
    assert result['lifecycle_sequence'] is None


def test_dual_write_mode_keeps_legacy_route_while_reporting_the_mismatch(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    lifecycle_service.open_recording_session('uid', 'session', 'first-conversation')

    result = lifecycle_service.open_recording_session('uid', 'session', 'second-conversation')

    assert result['conversation_id'] == 'second-conversation'
    assert result['mapping_conflict'] is True
    assert result['lifecycle_version'] is None
    assert result['lifecycle_phase'] is None
    assert result['lifecycle_sequence'] is None


def test_dual_write_mismatch_keeps_legacy_processing_and_completion_events(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    lifecycle_service.open_recording_session('uid', 'session', 'first-conversation')
    binding = lifecycle_service.open_recording_session('uid', 'session', 'second-conversation')

    processing = lifecycle_service.record_recording_session_event(
        'uid', 'session', binding['conversation_id'], 'processing'
    )
    completed = lifecycle_service.record_recording_session_event(
        'uid', 'session', binding['conversation_id'], 'completed'
    )
    canonical = recording_sessions.create_or_get_recording_session('uid', 'session', 'first-conversation')

    expected_legacy_envelope = {
        'recording_session_id': 'session',
        'conversation_id': 'second-conversation',
        'lifecycle_version': None,
        'lifecycle_phase': None,
        'lifecycle_sequence': None,
    }
    assert processing == expected_legacy_envelope
    assert completed == expected_legacy_envelope
    assert canonical['conversation_id'] == 'first-conversation'
    assert canonical['lifecycle_phase'] == 'in_progress'
    assert canonical['lifecycle_sequence'] == 0


def test_shadow_mode_emits_legacy_envelope_when_durable_event_write_fails(monkeypatch):
    fallbacks: list[dict[str, Any]] = []

    def fail(*args, **kwargs):
        del args, kwargs
        raise RuntimeError('unavailable')

    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')
    monkeypatch.setattr(lifecycle_service.recording_sessions_db, 'record_lifecycle_event', fail)
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    event = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    assert event == {
        'recording_session_id': 'session',
        'conversation_id': 'conversation',
        'lifecycle_version': None,
        'lifecycle_phase': None,
        'lifecycle_sequence': None,
    }
    assert fallbacks[0]['to_mode'] == 'legacy_pointer'
