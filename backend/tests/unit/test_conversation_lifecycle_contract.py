"""Characterize the current conversation lifecycle before #9516 convergence.

These tests intentionally lock both the useful compare-and-swap claim and the
legacy escape hatches around it. The follow-up lifecycle service will replace
the latter with an explicit state machine and update these characterizations
where the product contract deliberately changes.
"""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import pytest

import database.conversations as conversations_db
from models.conversation_enums import ConversationStatus
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
        if self.path not in self.firestore.documents:
            raise KeyError(self.path)
        self.firestore.documents[self.path].update(copy.deepcopy(updates))
        self.firestore.write_log.append((self.path, copy.deepcopy(updates)))

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


class _RecordedMetric:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []
        self._labels: dict[str, str] | None = None

    def labels(self, **labels: str) -> '_RecordedMetric':
        self._labels = labels
        return self

    def inc(self) -> None:
        assert self._labels is not None
        self.events.append(self._labels)


@pytest.fixture
def lifecycle_store(monkeypatch):
    store = _FakeFirestore()
    metric = _RecordedMetric()

    def transactional(func):
        def locked(transaction, *args, **kwargs):
            with transaction.firestore.transaction_lock:
                return func(transaction, *args, **kwargs)

        return locked

    monkeypatch.setattr(conversations_db, 'db', store)
    monkeypatch.setattr(conversations_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(conversations_db, 'CONVERSATION_LIFECYCLE_LEGACY_MUTATIONS', metric)
    return store, metric


@pytest.mark.parametrize(
    ('initial_status', 'target_status'),
    [
        (ConversationStatus.in_progress, ConversationStatus.processing),
        (ConversationStatus.processing, ConversationStatus.completed),
        (ConversationStatus.processing, ConversationStatus.failed),
        (ConversationStatus.completed, ConversationStatus.merging),
        (ConversationStatus.merging, ConversationStatus.completed),
    ],
)
def test_current_lifecycle_transitions_are_written(initial_status, target_status, lifecycle_store):
    """Existing callers directly persist each observed lifecycle transition."""
    store, metric = lifecycle_store
    store.put_conversation('uid', 'conversation', status=initial_status.value, discarded=False)

    conversations_db.update_conversation_status('uid', 'conversation', target_status)

    assert store.conversation('uid', 'conversation')['status'] == target_status
    assert metric.events == [{'writer': 'other', 'operation': 'status_update'}]


def test_current_generic_writer_allows_an_illegal_status_reversal(lifecycle_store):
    """Characterize the generic-write escape hatch the lifecycle service must remove."""
    store, metric = lifecycle_store
    store.put_conversation('uid', 'conversation', status=ConversationStatus.completed.value, discarded=False)

    conversations_db.update_conversation('uid', 'conversation', {'status': ConversationStatus.in_progress.value})

    assert store.conversation('uid', 'conversation')['status'] == ConversationStatus.in_progress.value
    assert metric.events == [{'writer': 'other', 'operation': 'generic_update'}]


def test_conditional_claim_admits_only_one_finalizer(lifecycle_store):
    """The existing CAS is the one current path that makes finalization idempotent."""
    store, metric = lifecycle_store
    store.put_conversation('uid', 'conversation', status=ConversationStatus.in_progress.value, discarded=False)

    first = conversations_db.claim_conversation_status(
        'uid', 'conversation', ConversationStatus.in_progress, ConversationStatus.processing
    )
    second = conversations_db.claim_conversation_status(
        'uid', 'conversation', ConversationStatus.in_progress, ConversationStatus.processing
    )

    assert (first, second) == (True, False)
    assert store.conversation('uid', 'conversation')['status'] == ConversationStatus.processing.value
    assert metric.events == [{'writer': 'other', 'operation': 'conditional_claim'}]


def test_concurrent_finalizers_have_one_successful_claim(lifecycle_store):
    """The Firestore transaction seam serializes simultaneous finalize claims."""
    store, _ = lifecycle_store
    store.put_conversation('uid', 'conversation', status=ConversationStatus.in_progress.value, discarded=False)
    start = threading.Barrier(2)

    def claim() -> bool:
        start.wait()
        return conversations_db.claim_conversation_status(
            'uid', 'conversation', ConversationStatus.in_progress, ConversationStatus.processing
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _unused: claim(), range(2)))

    assert sorted(results) == [False, True]
    assert store.conversation('uid', 'conversation')['status'] == ConversationStatus.processing.value


def test_sync_live_collision_bypasses_a_successful_claim(lifecycle_store):
    """Current sync/live-style drivers can both record processing admission work."""
    store, _ = lifecycle_store
    store.put_conversation('uid', 'conversation', status=ConversationStatus.in_progress.value, discarded=False)

    assert conversations_db.claim_conversation_status(
        'uid', 'conversation', ConversationStatus.in_progress, ConversationStatus.processing
    )
    conversations_db.update_conversation_status('uid', 'conversation', ConversationStatus.processing)

    assert [updates for _path, updates in store.write_log] == [
        {'status': ConversationStatus.processing.value},
        {'status': ConversationStatus.processing},
    ]


def test_concurrent_finalize_and_reprocess_have_order_dependent_admission(lifecycle_store):
    """Current reprocess persistence is not fenced by the finalizer's CAS claim."""
    store, metric = lifecycle_store
    store.put_conversation('uid', 'conversation', status=ConversationStatus.in_progress.value, discarded=False)
    start = threading.Barrier(2)

    def finalize() -> bool:
        start.wait()
        return conversations_db.claim_conversation_status(
            'uid', 'conversation', ConversationStatus.in_progress, ConversationStatus.processing
        )

    def reprocess() -> None:
        start.wait()
        conversations_db.upsert_conversation(
            'uid',
            {
                'id': 'conversation',
                'status': ConversationStatus.completed,
                'discarded': False,
                'data_protection_level': 'standard',
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        finalizer = executor.submit(finalize)
        reprocessor = executor.submit(reprocess)
        finalizer_claimed = finalizer.result()
        assert reprocessor.result() is None

    assert store.conversation('uid', 'conversation')['status'] == ConversationStatus.completed
    expected_operations = {'upsert'}
    if finalizer_claimed:
        expected_operations.add('conditional_claim')
    assert {event['operation'] for event in metric.events} == expected_operations


def test_import_of_an_already_completed_conversation_is_a_single_document_upsert(lifecycle_store):
    """The current import persistence path updates the existing conversation identity."""
    store, metric = lifecycle_store
    store.put_conversation('uid', 'imported', status=ConversationStatus.completed.value, discarded=False, title='old')

    conversations_db.upsert_conversation(
        'uid',
        {
            'id': 'imported',
            'status': ConversationStatus.completed,
            'discarded': False,
            'title': 'imported title',
            'data_protection_level': 'standard',
        },
    )

    assert list(store.documents) == [('users', 'uid', 'conversations', 'imported')]
    assert store.conversation('uid', 'imported')['status'] == ConversationStatus.completed
    assert store.conversation('uid', 'imported')['title'] == 'imported title'
    assert metric.events == [{'writer': 'other', 'operation': 'upsert'}]


def test_discard_is_not_currently_terminal(lifecycle_store):
    """Characterize the developer re-open path before the terminal-discard change."""
    store, metric = lifecycle_store
    store.put_conversation('uid', 'conversation', status=ConversationStatus.completed.value, discarded=False)

    conversations_db.set_conversation_as_discarded('uid', 'conversation')
    conversations_db.update_conversation('uid', 'conversation', {'discarded': False})

    assert store.conversation('uid', 'conversation')['discarded'] is False
    assert metric.events == [
        {'writer': 'other', 'operation': 'discard'},
        {'writer': 'other', 'operation': 'generic_update'},
    ]


def test_merge_rejects_processing_conversations():
    """Merge has a separate current admission rule: all sources must be completed."""
    is_valid, error_message, warning_message = validate_merge_compatibility(
        [
            {'id': 'completed', 'status': ConversationStatus.completed.value},
            {'id': 'processing', 'status': ConversationStatus.processing.value},
        ]
    )

    assert (is_valid, warning_message) == (False, None)
    assert error_message == 'Conversation processing is not ready (status: processing). Wait for it to complete.'


def test_lifecycle_metric_writer_labels_are_bounded_to_the_current_inventory():
    assert {
        conversations_db.lifecycle_writer_label(module_name)
        for module_name in (
            'routers.transcribe',
            'routers.pusher',
            'routers.conversations',
            'routers.sync',
            'routers.developer',
            'utils.sync.pipeline',
            'utils.conversations.process_conversation',
            'utils.conversations.postprocess_conversation',
            'utils.conversations.merge_conversations',
            'utils.imports.limitless',
        )
    } == {
        'transcribe',
        'pusher',
        'conversations_router',
        'sync_router',
        'developer_router',
        'sync_pipeline',
        'process_conversation',
        'postprocess_conversation',
        'merge_conversations',
        'limitless_import',
    }
    assert conversations_db.lifecycle_writer_label('unexpected.module') == 'other'


def test_lifecycle_metric_traces_the_direct_writer_module(lifecycle_store):
    """The temporary counter identifies the legacy writer without caller plumbing."""
    store, metric = lifecycle_store
    store.put_conversation('uid', 'conversation', status=ConversationStatus.in_progress.value, discarded=False)
    transcribe = ModuleType('routers.transcribe')
    transcribe.conversations_db = conversations_db
    transcribe.ConversationStatus = ConversationStatus
    exec(
        "def mark_processing():\n"
        "    conversations_db.update_conversation_status(\n"
        "        'uid', 'conversation', ConversationStatus.processing\n"
        "    )\n",
        transcribe.__dict__,
    )

    transcribe.mark_processing()

    assert metric.events == [{'writer': 'transcribe', 'operation': 'status_update'}]
