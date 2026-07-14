"""Contract tests for durable listen recording-session routing (#9351)."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from typing import Any

import pytest

from database import recording_sessions
from utils.conversations import lifecycle as lifecycle_service


@dataclass
class _Snapshot:
    data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self.data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return copy.deepcopy(self.data)


@dataclass
class _DocumentRef:
    firestore: '_FakeFirestore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.firestore.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.firestore, self.path + (name,))


@dataclass
class _CollectionRef:
    firestore: '_FakeFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.firestore, self.path + (document_id,))


@dataclass
class _Transaction:
    firestore: '_FakeFirestore'

    def create(self, document: _DocumentRef, data: dict[str, Any]) -> None:
        if document.path in self.firestore.documents:
            raise RuntimeError('already exists')
        self.firestore.documents[document.path] = copy.deepcopy(data)

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.firestore.documents[document.path].update(copy.deepcopy(updates))

    def delete(self, document: _DocumentRef) -> None:
        self.firestore.documents.pop(document.path, None)


@dataclass
class _FakeFirestore:
    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    transaction_lock: threading.Lock = field(default_factory=threading.Lock)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        return _Transaction(self)


@pytest.fixture
def recording_store(monkeypatch):
    store = _FakeFirestore()

    def transactional(func):
        def locked(transaction, *args, **kwargs):
            with transaction.firestore.transaction_lock:
                return func(transaction, *args, **kwargs)

        return locked

    monkeypatch.setattr(recording_sessions.firestore, 'transactional', transactional)
    return store


def test_retry_keeps_one_canonical_recording_session_binding(recording_store):
    first = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )
    retry = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )

    assert first == retry
    assert first['mapping_conflict'] is False
    assert len(recording_store.documents) == 1


def test_completed_retry_returns_its_canonical_terminal_envelope(recording_store):
    recording_sessions.create_or_get_recording_session(
        'uid', 'recording-one', 'conversation-one', firestore_client=recording_store
    )
    recording_sessions.record_lifecycle_event(
        'uid', 'recording-one', 'conversation-one', 'processing', firestore_client=recording_store
    )
    completed = recording_sessions.record_lifecycle_event(
        'uid', 'recording-one', 'conversation-one', 'completed', firestore_client=recording_store
    )

    retry = recording_sessions.create_or_get_recording_session(
        'uid', 'recording-one', 'new-proposed-conversation', firestore_client=recording_store
    )
    replay = recording_sessions.record_lifecycle_event(
        'uid', 'recording-one', retry['conversation_id'], 'completed', firestore_client=recording_store
    )
    rollover = recording_sessions.create_or_get_recording_session(
        'uid', 'recording-two', 'conversation-two', firestore_client=recording_store
    )

    assert retry['conversation_id'] == 'conversation-one'
    assert retry['mapping_conflict'] is True
    assert replay['accepted'] is True
    assert replay['lifecycle_phase'] == 'completed'
    assert replay['lifecycle_sequence'] == completed['lifecycle_sequence']
    assert rollover['conversation_id'] == 'conversation-two'
    assert len(recording_store.documents) == 2


def test_empty_recording_tombstone_forces_a_fresh_live_generation(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    monkeypatch.setattr(lifecycle_service.conversations_db, 'get_conversation', lambda *_: None)
    lifecycle_service.open_recording_session(
        'uid', 'recording-old', 'conversation-old', firestore_client=recording_store
    )

    tombstone = lifecycle_service.tombstone_recording_session(
        'uid', 'recording-old', 'conversation-old', firestore_client=recording_store
    )
    reconnect = lifecycle_service.open_live_recording_session(
        'uid', 'recording-old', 'conversation-old', firestore_client=recording_store
    )
    fresh = lifecycle_service.open_live_recording_session(
        'uid', 'recording-new', 'conversation-new', firestore_client=recording_store
    )
    original = recording_sessions.get_recording_session('uid', 'recording-old', firestore_client=recording_store)

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
    lifecycle_service.open_recording_session(
        'uid', 'recording-old', 'conversation-old', firestore_client=recording_store
    )

    reconnect = lifecycle_service.open_live_recording_session(
        'uid', 'recording-old', 'conversation-old', firestore_client=recording_store
    )
    original = recording_sessions.get_recording_session('uid', 'recording-old', firestore_client=recording_store)

    assert reconnect['requires_rollover'] is True
    assert original is not None
    assert original['lifecycle_phase'] == 'discarded'


def test_empty_cleanup_atomically_tombstones_its_session(recording_store):
    conversation_path = ('users', 'uid', 'conversations', 'conversation')
    recording_store.documents[conversation_path] = {
        'id': 'conversation',
        'status': 'in_progress',
        'transcript_segments': [],
        'has_content': False,
    }
    recording_sessions.create_or_get_recording_session(
        'uid', 'recording', 'conversation', firestore_client=recording_store
    )

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=recording_store
    )
    binding = recording_sessions.get_recording_session('uid', 'recording', firestore_client=recording_store)

    assert deleted is True
    assert conversation_path not in recording_store.documents
    assert binding is not None
    assert binding['lifecycle_phase'] == 'discarded'


def test_empty_cleanup_refuses_late_content_without_tombstoning(recording_store):
    conversation_path = ('users', 'uid', 'conversations', 'conversation')
    recording_store.documents[conversation_path] = {
        'id': 'conversation',
        'status': 'in_progress',
        'transcript_segments': [{'id': 'late-segment', 'text': 'persisted'}],
        'has_content': True,
    }
    recording_sessions.create_or_get_recording_session(
        'uid', 'recording', 'conversation', firestore_client=recording_store
    )

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=recording_store
    )
    binding = recording_sessions.get_recording_session('uid', 'recording', firestore_client=recording_store)

    assert deleted is False
    assert conversation_path in recording_store.documents
    assert binding is not None
    assert binding['lifecycle_phase'] == 'in_progress'


def test_conflicting_retry_returns_the_original_conversation(recording_store):
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'first-conversation', firestore_client=recording_store
    )

    result = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=recording_store
    )

    assert result['conversation_id'] == 'first-conversation'
    assert result['mapping_conflict'] is True


def test_same_recording_id_is_scoped_to_each_user(recording_store):
    one = recording_sessions.create_or_get_recording_session(
        'first-user', 'session', 'first-conversation', firestore_client=recording_store
    )
    two = recording_sessions.create_or_get_recording_session(
        'second-user', 'session', 'second-conversation', firestore_client=recording_store
    )

    assert (one['conversation_id'], two['conversation_id']) == ('first-conversation', 'second-conversation')
    assert len(recording_store.documents) == 2


def test_events_are_monotonic_and_stale_callbacks_are_discarded(recording_store):
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )

    processing = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=recording_store
    )
    completed = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=recording_store
    )
    stale = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=recording_store
    )

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
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )
    if terminal_phase != 'completed':
        recording_sessions.record_lifecycle_event(
            'uid', 'session', 'conversation', 'processing', firestore_client=recording_store
        )
    terminal = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', terminal_phase, firestore_client=recording_store
    )
    replacement = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', replacement_phase, firestore_client=recording_store
    )

    assert replacement['accepted'] is False
    assert replacement['discard_reason'] == 'terminal_immutable'
    assert replacement['lifecycle_sequence'] == terminal['lifecycle_sequence']


def test_event_for_a_different_conversation_is_discarded(recording_store):
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )

    result = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'other-conversation', 'processing', firestore_client=recording_store
    )

    assert result['accepted'] is False
    assert result['discard_reason'] == 'mapping_conflict'
    assert result['conversation_id'] == 'conversation'


def test_lifecycle_owner_enforces_a_conflicting_durable_binding(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    lifecycle_service.open_recording_session('uid', 'session', 'first-conversation', firestore_client=recording_store)

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=recording_store
    )

    assert result['conversation_id'] == 'first-conversation'
    assert result['mapping_conflict'] is True


def test_shadow_mode_keeps_legacy_route_but_reports_the_mismatch(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')
    lifecycle_service.open_recording_session('uid', 'session', 'first-conversation', firestore_client=recording_store)

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=recording_store
    )

    assert result['conversation_id'] == 'second-conversation'
    assert result['mapping_conflict'] is True
    assert result['lifecycle_version'] is None
    assert result['lifecycle_phase'] is None
    assert result['lifecycle_sequence'] is None


def test_dual_write_mode_keeps_legacy_route_while_reporting_the_mismatch(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    lifecycle_service.open_recording_session('uid', 'session', 'first-conversation', firestore_client=recording_store)

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=recording_store
    )

    assert result['conversation_id'] == 'second-conversation'
    assert result['mapping_conflict'] is True
    assert result['lifecycle_version'] is None
    assert result['lifecycle_phase'] is None
    assert result['lifecycle_sequence'] is None


def test_dual_write_mismatch_keeps_legacy_processing_and_completion_events(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    lifecycle_service.open_recording_session('uid', 'session', 'first-conversation', firestore_client=recording_store)
    binding = lifecycle_service.open_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=recording_store
    )

    processing = lifecycle_service.record_recording_session_event(
        'uid', 'session', binding['conversation_id'], 'processing', firestore_client=recording_store
    )
    completed = lifecycle_service.record_recording_session_event(
        'uid', 'session', binding['conversation_id'], 'completed', firestore_client=recording_store
    )
    canonical = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'first-conversation', firestore_client=recording_store
    )

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
