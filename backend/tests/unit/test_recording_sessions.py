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
    assert stale['discard_reason'] == 'stale_event'
    assert stale['lifecycle_sequence'] == 2


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
