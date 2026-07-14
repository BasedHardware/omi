"""Behavioral contract for the exclusive conversation lifecycle owner (#9516)."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import pytest

import database.conversations as conversations_db
from models.conversation_enums import ConversationStatus
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.merge_conversations import validate_merge_compatibility


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

    def update(self, updates: dict[str, Any]) -> None:
        self.firestore.documents[self.path].update(copy.deepcopy(updates))
        self.firestore.write_log.append((self.path, copy.deepcopy(updates)))

    def create(self, data: dict[str, Any]) -> None:
        if self.path in self.firestore.documents:
            raise RuntimeError('already exists')
        self.firestore.documents[self.path] = copy.deepcopy(data)
        self.firestore.write_log.append((self.path, copy.deepcopy(data)))

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

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        document.update(updates)

    def set(self, document: _DocumentRef, data: dict[str, Any], merge: bool = False) -> None:
        if merge and document.path in self.firestore.documents:
            self.firestore.documents[document.path].update(copy.deepcopy(data))
        else:
            self.firestore.documents[document.path] = copy.deepcopy(data)
        self.firestore.write_log.append((document.path, copy.deepcopy(data)))


@dataclass
class _FakeFirestore:
    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    write_log: list[tuple[tuple[str, ...], dict[str, Any]]] = field(default_factory=list)
    transaction_lock: threading.Lock = field(default_factory=threading.Lock)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def put_conversation(self, uid: str, conversation_id: str, **data: Any) -> None:
        self.documents[('users', uid, 'conversations', conversation_id)] = copy.deepcopy(data)

    def conversation(self, uid: str, conversation_id: str) -> dict[str, Any]:
        return self.documents[('users', uid, 'conversations', conversation_id)]


@pytest.fixture
def lifecycle_store(monkeypatch):
    store = _FakeFirestore()

    def transactional(func):
        def locked(transaction, *args, **kwargs):
            with transaction.firestore.transaction_lock:
                return func(transaction, *args, **kwargs)

        return locked

    monkeypatch.setattr(conversations_db, 'db', store)
    monkeypatch.setattr(conversations_db.firestore, 'transactional', transactional)
    return store


def test_lifecycle_service_allows_only_declared_transitions(lifecycle_store):
    lifecycle_store.put_conversation(
        'uid', 'conversation', status=ConversationStatus.in_progress.value, discarded=False
    )

    assert lifecycle_service.admit_processing('uid', 'conversation') is True
    assert lifecycle_service.complete('uid', 'conversation') is True
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.completed
    with pytest.raises(lifecycle_service.LifecycleTransitionError, match='invalid lifecycle transition'):
        lifecycle_service.begin_merge('uid', 'conversation')


def test_generic_lifecycle_field_write_fails_closed(lifecycle_store):
    lifecycle_store.put_conversation('uid', 'conversation', status=ConversationStatus.completed.value, discarded=False)

    with pytest.raises(ValueError, match='lifecycle fields'):
        conversations_db.update_conversation('uid', 'conversation', {'status': ConversationStatus.in_progress.value})
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.completed.value


def test_concurrent_finalizers_have_one_service_admission(lifecycle_store):
    lifecycle_store.put_conversation(
        'uid', 'conversation', status=ConversationStatus.in_progress.value, discarded=False
    )
    start = threading.Barrier(2)

    def admit() -> bool:
        start.wait()
        return lifecycle_service.admit_processing('uid', 'conversation')

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _unused: admit(), range(2)))

    assert sorted(results) == [False, True]
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.processing.value


def test_discarded_conversation_cannot_be_readmitted(lifecycle_store):
    lifecycle_store.put_conversation(
        'uid', 'conversation', status=ConversationStatus.in_progress.value, discarded=False
    )

    lifecycle_service.discard('uid', 'conversation')
    assert lifecycle_store.conversation('uid', 'conversation')['discarded'] is True
    assert lifecycle_service.admit_processing('uid', 'conversation') is False
    lifecycle_service.restore_discarded('uid', 'conversation')
    assert lifecycle_store.conversation('uid', 'conversation')['discarded'] is False


def test_discard_fences_a_stale_processing_result_and_completion(lifecycle_store):
    lifecycle_store.put_conversation(
        'uid',
        'conversation',
        status=ConversationStatus.processing.value,
        discarded=True,
        title='user-kept terminal state',
    )

    lifecycle_service.persist_processed_conversation(
        'uid',
        {
            'id': 'conversation',
            'status': ConversationStatus.completed,
            'discarded': False,
            'title': 'stale processor output',
            'data_protection_level': 'standard',
        },
    )

    assert lifecycle_service.complete('uid', 'conversation') is False
    assert lifecycle_store.conversation('uid', 'conversation') == {
        'status': ConversationStatus.processing.value,
        'discarded': True,
        'title': 'user-kept terminal state',
    }


def test_import_persists_through_the_lifecycle_owner(lifecycle_store):
    lifecycle_service.persist_imported_conversation(
        'uid',
        {
            'id': 'imported',
            'status': ConversationStatus.completed,
            'discarded': False,
            'title': 'imported title',
            'data_protection_level': 'standard',
        },
    )

    assert list(lifecycle_store.documents) == [('users', 'uid', 'conversations', 'imported')]
    assert lifecycle_store.conversation('uid', 'imported')['status'] == ConversationStatus.completed


def test_merge_rejects_processing_conversations():
    is_valid, error_message, warning_message = validate_merge_compatibility(
        [
            {'id': 'completed', 'status': ConversationStatus.completed.value},
            {'id': 'processing', 'status': ConversationStatus.processing.value},
        ]
    )

    assert (is_valid, warning_message) == (False, None)
    assert error_message == 'Conversation processing is not ready (status: processing). Wait for it to complete.'
