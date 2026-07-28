"""Behavioral contract for the exclusive conversation lifecycle owner (#9516)."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import database.conversations as conversations_db
from database import conversation_finalization_jobs as jobs_db
from models.conversation_enums import ConversationStatus
from tests.store_fakes import FakeDocumentStore
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.merge_conversations import validate_merge_compatibility


class _LifecycleStore(FakeDocumentStore):
    """FakeDocumentStore (WP2 port) plus the conveniences the old raw-Firestore fake exposed.

    Transactions are serialized under a lock so the concurrency contract (exactly one admission
    wins) holds — mirroring the atomicity the real backend transaction provides, which the direct
    ``run_transaction`` of the base fake does not. Writes are logged and documents are addressable
    by tuple path for the assertions below.
    """

    def __init__(self):
        super().__init__()
        self._txn_lock = threading.Lock()
        self.write_log = []

    @staticmethod
    def _path(uid, conversation_id):
        return f'users/{uid}/conversations/{conversation_id}'

    def run_transaction(self, fn, *, attempts=3):
        with self._txn_lock:
            return super().run_transaction(fn)

    def set(self, path, data, *, merge=False):
        super().set(path, data, merge=merge)
        self.write_log.append((tuple(path.split('/')), copy.deepcopy(data)))

    def update(self, path, data):
        super().update(path, data)
        self.write_log.append((tuple(path.split('/')), copy.deepcopy(data)))

    def create(self, path, data):
        super().create(path, data)
        self.write_log.append((tuple(path.split('/')), copy.deepcopy(data)))

    # --- test conveniences (mirror the old fake's helpers) ---------------------------------
    def put_conversation(self, uid, conversation_id, **data):
        # Seed directly (no write_log entry) so write_log reflects only the code under test.
        path = self._path(uid, conversation_id)
        self._docs[path] = copy.deepcopy(data)
        self._stamp(path)

    def conversation(self, uid, conversation_id):
        return self.get(self._path(uid, conversation_id)).to_dict()

    @property
    def documents(self):
        return {tuple(p.split('/')): self.get(p).to_dict() for p in self._docs}


@pytest.fixture
def lifecycle_store(monkeypatch):
    store = _LifecycleStore()
    monkeypatch.setattr(conversations_db, '_store', lambda: store)
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


def test_processing_admission_guard_renews_the_lease_while_the_processor_is_alive(monkeypatch):
    """A live synchronous processor must keep its admission lease fresh so the
    crash-orphan sweep can never mistake it for a stranded row (#10461 ownership
    fence). The guard renews the lease on a heartbeat while the guarded block runs.
    """
    renewed = threading.Event()
    renew_calls: list[tuple[str, str]] = []

    def fake_renew(uid, conversation_id):
        renew_calls.append((uid, conversation_id))
        renewed.set()
        return True

    monkeypatch.setattr(jobs_db, 'renew_processing_lease', fake_renew)
    monkeypatch.setattr(lifecycle_service, '_processing_lease_renewal_interval', lambda: 0.001)

    with lifecycle_service.processing_admission_guard('uid', 'conversation'):
        # Block inside the guarded block until the heartbeat has renewed at least once.
        assert renewed.wait(timeout=5.0)

    assert renew_calls


def test_processing_admission_guard_stops_the_heartbeat_when_the_processor_finishes(monkeypatch):
    """On exit the guard must stop the heartbeat so a finished processor releases its lease."""
    renew_calls: list[tuple[str, str]] = []
    stop_seen = threading.Event()

    def fake_renew(uid, conversation_id):
        renew_calls.append((uid, conversation_id))
        return True

    monkeypatch.setattr(jobs_db, 'renew_processing_lease', fake_renew)
    monkeypatch.setattr(lifecycle_service, '_processing_lease_renewal_interval', lambda: 0.001)

    with lifecycle_service.processing_admission_guard('uid', 'conversation'):
        pass  # the guarded block finishes immediately; the heartbeat should not hot-loop
    # After exit, allow a brief window for any in-flight renewal to settle, then snapshot.
    snapshot_after_exit = len(renew_calls)
    stop_seen.wait(timeout=0.05)
    assert len(renew_calls) == snapshot_after_exit
