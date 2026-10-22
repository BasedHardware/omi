"""Behavioral contract for the exclusive conversation lifecycle owner (#9516)."""

import copy
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx
import pytest
from fastapi import HTTPException
from google.api_core.exceptions import AlreadyExists

import database.conversations as conversations_db
from database import conversation_finalization_jobs as jobs_db
from models.conversation_enums import ConversationStatus
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.merge_conversations import validate_merge_compatibility
from utils.llm.gateway_error_contract import conversation_processing_http_exception


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


def test_ingest_sync_conversation_records_created_versus_merged(monkeypatch):
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_sync_intake_outcome', lambda **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(
        conversations_db,
        'assign_sync_conversation',
        lambda *_args, **_kwargs: ({'id': 'created-row'}, True, []),
    )

    created_result = lifecycle_service.ingest_sync_conversation('uid', {'status': ConversationStatus.completed.value})
    assert created_result == ({'id': 'created-row'}, True, [])
    assert recorded == [{'created': True}]

    recorded.clear()
    monkeypatch.setattr(
        conversations_db,
        'assign_sync_conversation',
        lambda *_args, **_kwargs: ({'id': 'merged-row'}, False, []),
    )
    merged_result = lifecycle_service.ingest_sync_conversation(
        'uid', {'status': ConversationStatus.completed.value}, candidate_id='hint'
    )
    assert merged_result == ({'id': 'merged-row'}, False, [])
    assert recorded == [{'created': False}]


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


def test_update_conversation_reports_a_deleted_owner(lifecycle_store):
    """Callers that keep producing work for a conversation must be able to see it is gone (#11742)."""
    lifecycle_store.put_conversation('uid', 'conversation', status=ConversationStatus.completed.value, discarded=False)

    assert conversations_db.update_conversation('uid', 'conversation', {'language': 'en'}) is True
    assert conversations_db.update_conversation('uid', 'missing', {'language': 'en'}) is False


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
    created = lifecycle_service.persist_imported_conversation(
        'uid',
        {
            'id': 'imported',
            'status': ConversationStatus.completed,
            'discarded': False,
            'title': 'imported title',
            'data_protection_level': 'standard',
        },
    )

    assert created is True
    assert list(lifecycle_store.documents) == [('users', 'uid', 'conversations', 'imported')]
    stored = lifecycle_store.conversation('uid', 'imported')
    assert stored['status'] == ConversationStatus.completed
    assert stored['imported'] is True
    assert (
        lifecycle_service.persist_imported_conversation(
            'uid',
            {
                'id': 'imported',
                'status': ConversationStatus.completed,
                'discarded': False,
                'title': 'later export title',
                'data_protection_level': 'standard',
            },
        )
        is False
    )
    assert lifecycle_store.conversation('uid', 'imported')['title'] == 'imported title'
    assert lifecycle_store.conversation('uid', 'imported')['imported'] is True


def test_persist_imported_conversation_forces_imported_true(lifecycle_store):
    created = lifecycle_service.persist_imported_conversation(
        'uid',
        {
            'id': 'forced-imported',
            'status': ConversationStatus.completed,
            'discarded': False,
            'imported': False,
            'title': 'should be stamped',
            'data_protection_level': 'standard',
        },
    )

    assert created is True
    assert lifecycle_store.conversation('uid', 'forced-imported')['imported'] is True


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


_ANTHROPIC_CREDIT_EXHAUSTED_BODY = {
    'type': 'error',
    'error': {
        'type': 'invalid_request_error',
        'message': 'Your credit balance is too low to access the Anthropic API. '
        'Please go to Plans & Billing to upgrade or purchase credits.',
    },
}


def _raise_byok_credit_exhaustion_halt() -> None:
    """Raise the exact chain ``_get_structured`` produces for a spent BYOK Anthropic account."""
    request = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')
    response = httpx.Response(
        400, request=request, headers={'request-id': 'req_unit'}, json=_ANTHROPIC_CREDIT_EXHAUSTED_BODY
    )
    try:
        raise anthropic.BadRequestError(
            f'Error code: 400 - {_ANTHROPIC_CREDIT_EXHAUSTED_BODY}',
            response=response,
            body=_ANTHROPIC_CREDIT_EXHAUSTED_BODY,
        )
    except anthropic.BadRequestError as error:
        raise conversation_processing_http_exception(error) from error


def _quiet_heartbeat(monkeypatch) -> None:
    monkeypatch.setattr(jobs_db, 'renew_processing_lease', lambda *_args: True)
    monkeypatch.setattr(lifecycle_service, '_processing_lease_renewal_interval', lambda: 60.0)


def _guard_failure_records(caplog) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == lifecycle_service.logger.name
        and 'synchronous conversation processing failed' in record.getMessage()
    ]


def test_processing_admission_guard_logs_a_byok_account_state_halt_by_bounded_class(monkeypatch, caplog):
    """A spent BYOK provider account is account state only the user can fix. The
    composition boundary already answered it as a typed 429 and logged it by
    bounded class; the guard must not re-emit the chained provider traceback
    (which carries the provider's error body) as an ERROR for the same halt.
    """
    _quiet_heartbeat(monkeypatch)
    caplog.set_level(logging.WARNING)

    with pytest.raises(HTTPException) as raised:
        with lifecycle_service.processing_admission_guard('uid', 'conversation', rollback_on_failure=False):
            _raise_byok_credit_exhaustion_halt()

    # The typed response reaches the caller unchanged.
    assert raised.value.status_code == 429
    assert raised.value.detail['code'] == 'byok_quota'
    assert isinstance(raised.value.__cause__, anthropic.BadRequestError)

    (record,) = _guard_failure_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert 'no rollback: producer owns recovery' in record.getMessage()
    assert 'credit balance' not in caplog.text
    assert 'Traceback' not in caplog.text
    assert 'BadRequestError' not in caplog.text


def test_processing_admission_guard_still_rolls_back_a_byok_account_state_halt(monkeypatch, caplog):
    _quiet_heartbeat(monkeypatch)
    caplog.set_level(logging.WARNING)
    rolled_back: list[tuple[str, str]] = []

    def fake_rollback(uid, conversation_id):
        rolled_back.append((uid, conversation_id))
        return True

    monkeypatch.setattr(lifecycle_service, 'rollback_processing_admission', fake_rollback)

    with pytest.raises(HTTPException):
        with lifecycle_service.processing_admission_guard('uid', 'conversation'):
            _raise_byok_credit_exhaustion_halt()

    assert rolled_back == [('uid', 'conversation')]
    (record,) = _guard_failure_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert 'rolled_back=True' in record.getMessage()
    assert 'credit balance' not in caplog.text


def test_processing_admission_guard_bounds_the_rollback_failure_log_during_a_byok_halt(monkeypatch, caplog):
    """When the typed BYOK halt coincides with a rollback failure (e.g. a
    Firestore outage), the nested rollback log must also stay bounded: an
    exception traceback there formats the rollback error's implicit
    ``__context__`` chain back to the original HTTPException and its provider
    error body — the exact body this guard exists to keep out of logs.
    """
    _quiet_heartbeat(monkeypatch)
    caplog.set_level(logging.WARNING)

    def failing_rollback(uid, conversation_id):
        raise RuntimeError('rollback store is down')

    monkeypatch.setattr(lifecycle_service, 'rollback_processing_admission', failing_rollback)

    with pytest.raises(HTTPException):
        with lifecycle_service.processing_admission_guard('uid', 'conversation'):
            _raise_byok_credit_exhaustion_halt()

    rollback_records = [
        record
        for record in caplog.records
        if record.name == lifecycle_service.logger.name
        and 'processing admission rollback failed' in record.getMessage()
    ]
    (rollback_record,) = rollback_records
    assert rollback_record.levelno == logging.WARNING
    assert rollback_record.exc_info is None
    assert 'rollback store is down' in rollback_record.getMessage()

    records = _guard_failure_records(caplog)
    assert all(record.levelno == logging.WARNING for record in records)
    assert all(record.exc_info is None for record in records)
    assert 'rolled_back=False' in caplog.text
    assert 'credit balance' not in caplog.text
    assert 'Traceback' not in caplog.text
    assert 'BadRequestError' not in caplog.text


def test_processing_admission_guard_keeps_the_traceback_for_unexpected_failures(monkeypatch, caplog):
    """Every other failure is still a processor fault and keeps its full traceback."""
    _quiet_heartbeat(monkeypatch)
    caplog.set_level(logging.WARNING)

    with pytest.raises(RuntimeError):
        with lifecycle_service.processing_admission_guard('uid', 'conversation', rollback_on_failure=False):
            raise RuntimeError('processor crashed')

    (record,) = _guard_failure_records(caplog)
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
    assert 'processor crashed' in caplog.text


def test_processing_admission_guard_keeps_the_traceback_for_a_generic_processing_500(monkeypatch, caplog):
    """The boundary's generic 500 is not account state; its traceback stays visible."""
    _quiet_heartbeat(monkeypatch)
    caplog.set_level(logging.WARNING)

    with pytest.raises(HTTPException) as raised:
        with lifecycle_service.processing_admission_guard('uid', 'conversation', rollback_on_failure=False):
            try:
                raise ValueError('notes parse failed')
            except ValueError as error:
                raise conversation_processing_http_exception(error) from error

    assert raised.value.status_code == 500
    (record,) = _guard_failure_records(caplog)
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None


def test_first_completed_writes_observe_shape_once(monkeypatch, lifecycle_store):
    observed: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        lifecycle_service,
        'observe_completed_conversation_shape',
        lambda uid, payload: observed.append((uid, payload.get('id') if isinstance(payload, dict) else None)),
    )

    created = lifecycle_service.create_completed_conversation(
        'uid',
        {
            'id': 'new-conversation',
            'status': ConversationStatus.completed,
            'source': 'omi',
            'data_protection_level': 'standard',
        },
        idempotent=True,
    )
    assert created is True
    replay = lifecycle_service.create_completed_conversation(
        'uid',
        {
            'id': 'new-conversation',
            'status': ConversationStatus.completed,
            'source': 'omi',
            'data_protection_level': 'standard',
        },
        idempotent=True,
    )
    assert replay is False
    assert observed == [('uid', 'new-conversation')]


def test_persist_processed_observes_only_on_first_completion(monkeypatch, lifecycle_store):
    observed: list[str] = []
    monkeypatch.setattr(
        lifecycle_service,
        'observe_completed_conversation_shape',
        lambda uid, payload: observed.append(payload['id']),
    )
    lifecycle_store.put_conversation(
        'uid',
        'conversation',
        status=ConversationStatus.processing.value,
        discarded=False,
    )
    payload = {
        'id': 'conversation',
        'status': ConversationStatus.completed,
        'source': 'omi',
        'data_protection_level': 'standard',
    }
    assert lifecycle_service.persist_processed_conversation('uid', payload) is True
    assert observed == ['conversation']
    assert lifecycle_service.persist_processed_conversation('uid', payload) is True
    assert observed == ['conversation']


def test_persist_processed_survives_shape_observer_errors(monkeypatch, lifecycle_store):
    monkeypatch.setattr(
        lifecycle_service,
        'observe_completed_conversation_shape',
        lambda uid, payload: (_ for _ in ()).throw(RuntimeError('observer failed')),
    )
    lifecycle_store.put_conversation(
        'uid',
        'conversation',
        status=ConversationStatus.processing.value,
        discarded=False,
    )
    assert (
        lifecycle_service.persist_processed_conversation(
            'uid',
            {
                'id': 'conversation',
                'status': ConversationStatus.completed,
                'data_protection_level': 'standard',
            },
        )
        is True
    )
    assert lifecycle_store.conversation('uid', 'conversation')['status'] == ConversationStatus.completed


def test_ingest_sync_observes_created_not_merged(monkeypatch):
    observed: list[object] = []
    monkeypatch.setattr(
        lifecycle_service,
        'observe_completed_conversation_shape',
        lambda uid, payload: observed.append(payload),
    )
    monkeypatch.setattr(lifecycle_service, 'record_sync_intake_outcome', lambda **_kwargs: None)
    monkeypatch.setattr(
        conversations_db,
        'assign_sync_conversation',
        lambda *_args, **_kwargs: (
            {'id': 'created-row', 'sync_content_revision': 1, 'source': 'omi'},
            True,
            [],
        ),
    )
    lifecycle_service.ingest_sync_conversation('uid', {'status': ConversationStatus.completed.value})
    assert len(observed) == 1
    assert observed[0]['id'] == 'created-row'
    assert observed[0]['sync_content_revision'] == 1

    monkeypatch.setattr(
        conversations_db,
        'assign_sync_conversation',
        lambda *_args, **_kwargs: ({'id': 'merged-row', 'sync_content_revision': 2}, False, []),
    )
    lifecycle_service.ingest_sync_conversation(
        'uid', {'status': ConversationStatus.completed.value}, candidate_id='hint'
    )
    assert len(observed) == 1


def test_import_observes_once_on_first_create(monkeypatch, lifecycle_store):
    observed: list[str] = []
    monkeypatch.setattr(
        lifecycle_service,
        'observe_completed_conversation_shape',
        lambda uid, payload: observed.append(payload['id']),
    )
    payload = {
        'id': 'imported',
        'status': ConversationStatus.completed,
        'discarded': False,
        'title': 'imported title',
        'data_protection_level': 'standard',
    }
    assert lifecycle_service.persist_imported_conversation('uid', payload) is True
    assert observed == ['imported']
    assert lifecycle_service.persist_imported_conversation('uid', payload) is False
    assert observed == ['imported']
