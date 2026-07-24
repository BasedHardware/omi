"""Behavioral contract for the exclusive conversation lifecycle owner (#9516)."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import pytest
from google.api_core.exceptions import AlreadyExists

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
            raise AlreadyExists('already exists')
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
    # processing -> merging stays undeclared: merge only ever admits completed conversations.
    with pytest.raises(lifecycle_service.LifecycleTransitionError, match='invalid lifecycle transition'):
        lifecycle_service.begin_merge('uid', 'conversation')
    assert lifecycle_service.complete('uid', 'conversation') is True
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.completed


def test_merge_admission_and_lifecycle_agree_on_completed(lifecycle_store):
    """The two gates in POST /v1/conversations/merge must agree on the admitted status.

    validate_merge_compatibility rejects every status except completed, so completed is the only
    status that can reach begin_merge. If the transition table omits completed -> merging, every
    accepted merge raises LifecycleTransitionError, which is an unhandled 500 and makes the merge
    feature unusable. merge_conversations' failure rollback documents the same edge in reverse.
    """
    conversations = [
        {'id': 'conversation', 'status': ConversationStatus.completed.value},
        {'id': 'other', 'status': ConversationStatus.completed.value},
    ]
    is_valid, error_message, _ = validate_merge_compatibility(conversations)
    assert (is_valid, error_message) == (True, None)

    lifecycle_store.put_conversation('uid', 'conversation', status=ConversationStatus.completed.value, discarded=False)

    assert lifecycle_service.begin_merge('uid', 'conversation') is True
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.merging


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


def test_terminal_failed_finalization_closes_only_the_current_processing_generation(lifecycle_store):
    lifecycle_store.put_conversation('uid', 'conversation', status=ConversationStatus.processing.value, discarded=False)

    assert lifecycle_service.fail_and_discard_processing('uid', 'conversation') is True
    assert lifecycle_store.conversation('uid', 'conversation') == {
        'status': ConversationStatus.failed,
        'discarded': True,
    }
    assert lifecycle_service.fail_and_discard_processing('uid', 'conversation') is False


def test_rollback_processing_admission_returns_a_failed_synchronous_finalization(lifecycle_store):
    lifecycle_store.put_conversation('uid', 'conversation', status=ConversationStatus.processing.value, discarded=False)

    assert lifecycle_service.rollback_processing_admission('uid', 'conversation') is True
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.in_progress.value
    # The generation stays finalizable — a retry can admit processing again.
    assert lifecycle_service.admit_processing('uid', 'conversation') is True


def test_rollback_processing_admission_never_reopens_a_terminal_generation(lifecycle_store):
    lifecycle_store.put_conversation('uid', 'conversation', status=ConversationStatus.completed.value, discarded=False)

    assert lifecycle_service.rollback_processing_admission('uid', 'conversation') is False
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.completed.value


def test_rollback_processing_admission_respects_discard(lifecycle_store):
    lifecycle_store.put_conversation('uid', 'conversation', status=ConversationStatus.processing.value, discarded=True)

    assert lifecycle_service.rollback_processing_admission('uid', 'conversation') is False
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.processing.value


def test_a_discard_does_not_fence_a_processing_result_or_completion(lifecycle_store):
    # A discard records that a conversation held nothing when it was judged, and
    # a later sync can arrive carrying the speech it was missing. Treating it as
    # terminal stranded those: transcribed, untitled, and invisible to their
    # owner, with the reprocess meant to recover them hitting the same fence.
    lifecycle_store.put_conversation(
        'uid',
        'conversation',
        status=ConversationStatus.processing.value,
        discarded=True,
        title='judged empty when it was judged',
    )

    persisted = lifecycle_service.persist_processed_conversation(
        'uid',
        {
            'id': 'conversation',
            'status': ConversationStatus.completed,
            'discarded': False,
            'title': 'what the sync filled it with',
            'data_protection_level': 'standard',
        },
    )

    assert persisted is True
    stored = lifecycle_store.conversation('uid', 'conversation')
    assert stored['discarded'] is False
    assert stored['title'] == 'what the sync filled it with'


def test_missing_conversation_fences_processing_result_without_resurrection(lifecycle_store):
    persisted = lifecycle_service.persist_processed_conversation(
        'uid',
        {
            'id': 'deleted-conversation',
            'status': ConversationStatus.completed,
            'title': 'stale processor output',
            'data_protection_level': 'standard',
        },
    )

    assert persisted is False
    assert ('users', 'uid', 'conversations', 'deleted-conversation') not in lifecycle_store.documents
    assert lifecycle_store.write_log == []


def test_completed_conversation_creation_is_explicit_and_idempotent(lifecycle_store):
    created = lifecycle_service.create_completed_conversation(
        'uid',
        {
            'id': 'new-conversation',
            'status': ConversationStatus.completed,
            'title': 'created by an initial request',
            'data_protection_level': 'standard',
        },
        idempotent=True,
    )

    assert created is True
    assert lifecycle_store.conversation('uid', 'new-conversation')['status'] == ConversationStatus.completed
    assert (
        lifecycle_service.create_completed_conversation(
            'uid',
            {
                'id': 'new-conversation',
                'status': ConversationStatus.completed,
                'title': 'stale duplicate request',
                'data_protection_level': 'standard',
            },
            idempotent=True,
        )
        is False
    )
    assert lifecycle_store.conversation('uid', 'new-conversation')['title'] == 'created by an initial request'


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
