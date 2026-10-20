"""Contract tests for durable listen recording-session routing (#9351)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import copy
import threading
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument, PermissionDenied

from database import conversations as conversations_db
from database import recording_sessions
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from routers.listen.conversations import LiveConversationController
from routers.listen.receiver import ListenReceiver
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


def test_session_open_atomically_marks_the_conversation_before_a_recovery_sweep(recording_store):
    """Session creation and its recovery fence are one transaction boundary."""
    conversation_path = ('users', 'uid', 'conversations', 'conversation')
    recording_store.documents[conversation_path] = {
        'id': 'conversation',
        'status': 'in_progress',
        'external_data': {'existing_marker': 'preserved'},
    }

    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )

    assert recording_store.documents[conversation_path]['external_data'] == {
        'existing_marker': 'preserved',
        'recording_session_id': 'session',
    }
    assert ('users', 'uid', 'recording_sessions', 'session') in recording_store.documents


class _MinuteFramesWebSocket:
    def __init__(self, clock: list[datetime]) -> None:
        self.clock = clock
        self.frame = 0

    async def receive(self):
        if self.frame > 10:
            return {'type': 'websocket.disconnect', 'code': 1000}
        self.clock[0] += timedelta(minutes=1) if self.frame else timedelta()
        self.frame += 1
        await asyncio.sleep(0)
        return {'bytes': b'pcm-frame'}


async def test_ten_minute_audio_session_keeps_renewing_its_recovery_lease(recording_store, monkeypatch):
    started_at = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
    clock = [started_at]
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock[0])
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )

    renewals: list[tuple[str, str, str]] = []
    tasks: list[asyncio.Task] = []

    async def persistence_call(fn, *args, **kwargs):
        if fn.__name__ == 'renew_live_recording_session_lease':
            renewals.append(args)
            kwargs['firestore_client'] = recording_store
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(
            uid='uid',
            source='phone',
            websocket=_MinuteFramesWebSocket(clock),
            codec='pcm',
            sample_rate=16000,
        ),
        state=SimpleNamespace(
            active=True,
            close_code=1001,
            current_conversation_id='conversation',
            last_audio_received_time=None,
            last_activity_time=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
            audio_ring_buffer=None,
        ),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        recording_session_id='session',
        is_multi_channel=False,
        use_custom_stt=True,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=lambda _segments: None),
        start_live_transcription=lambda: None,
        persistence=SimpleNamespace(call=persistence_call),
    )
    host.spawn = lambda coroutine, *, name: tasks.append(asyncio.create_task(coroutine, name=name))
    host.conversations = LiveConversationController(host, clock=lambda: clock[0])

    await ListenReceiver(host, [], {}).receive_data()
    await asyncio.gather(*tasks)

    session_path = ('users', 'uid', 'recording_sessions', 'session')
    assert len(renewals) == 11
    assert recording_store.documents[session_path]['lease_expires_at'] > clock[0]


def test_audio_activity_renews_only_the_matching_in_progress_session(recording_store):
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )
    path = ('users', 'uid', 'recording_sessions', 'session')
    before = recording_store.documents[path]['lease_expires_at']
    recording_store.documents[path]['lease_expires_at'] = before - timedelta(minutes=10)

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=recording_store
    )
    mismatched = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'other-conversation', firestore_client=recording_store
    )

    assert renewed is True
    assert mismatched is False
    assert recording_store.documents[path]['lease_expires_at'] > before - timedelta(minutes=10)


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
    monkeypatch.setattr(lifecycle_service.conversations_db, 'get_conversation', lambda *_, **__: None)
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
    monkeypatch.setattr(lifecycle_service.conversations_db, 'get_conversation', lambda *_, **__: None)
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


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_empty_cleanup_atomically_tombstones_its_session(recording_store, level):
    conversation_path = ('users', 'uid', 'conversations', 'conversation')
    recording_store.documents[conversation_path] = _stored_conversation([], level=level)
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


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_empty_cleanup_refuses_late_content_without_tombstoning(recording_store, level):
    conversation_path = ('users', 'uid', 'conversations', 'conversation')
    recording_store.documents[conversation_path] = _stored_conversation(
        [{'id': 'late-segment', 'text': 'persisted'}], level=level
    )
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


def test_empty_cleanup_keeps_a_conversation_whose_segments_cannot_be_decoded(recording_store):
    conversation_path = ('users', 'uid', 'conversations', 'conversation')
    recording_store.documents[conversation_path] = {
        'id': 'conversation',
        'status': 'in_progress',
        'transcript_segments': b'not-a-zlib-stream',
        'transcript_segments_compressed': True,
    }
    recording_sessions.create_or_get_recording_session(
        'uid', 'recording', 'conversation', firestore_client=recording_store
    )

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=recording_store
    )

    assert deleted is False
    assert conversation_path in recording_store.documents


def test_conflicting_retry_returns_the_original_conversation(recording_store):
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'first-conversation', firestore_client=recording_store
    )

    result = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=recording_store
    )

    assert result['conversation_id'] == 'first-conversation'
    assert result['mapping_conflict'] is True


# ── The empty-delete transaction survives a contention burst ────────────────
#
# Prod (backend-listen 2026-10-14): the rollover stage's finalize path calls
# this transaction while a late segment write or the lease renewal holds the
# same session document. The bare ``firestore.transactional`` call replayed a
# commit abort on the same — often already retired — transaction id and never
# retried an abort raised by the body's read, so the burst surfaced as
# ``Listen pending finalization failed stage=lifecycle_rollover`` (x135/30m)
# and its ``delete_empty_recording_conversation`` traceback sibling instead of
# a replay on a fresh transaction.

_EXPIRED_TRANSACTION_MESSAGE = 'The referenced transaction has expired or is no longer valid'


@dataclass
class _DeleteStoreCollection:
    store: '_ContendingDeleteStore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> '_DeleteStoreDoc':
        return _DeleteStoreDoc(self.store, self.path + (document_id,))


@dataclass
class _DeleteStoreDoc:
    store: '_ContendingDeleteStore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> Any:
        del transaction
        data = self.store.documents.get(self.path)
        return SimpleNamespace(exists=data is not None, to_dict=lambda: copy.deepcopy(data))

    def collection(self, name: str) -> '_DeleteStoreCollection':
        return _DeleteStoreCollection(self.store, self.path + tuple(name.split('/')))


@dataclass
class _ContendingDeleteStore:
    """Fake Firestore whose transactional boundary fails until the queue drains.

    ``boundary_errors`` fires from the decorated call — a read-time ``Aborted``
    (the SDK never retries it) or an expired-id rejection raised from the store
    side. Committed transactions are recorded so tests can count real commits.
    """

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    boundary_errors: list[BaseException] = field(default_factory=list)
    commits: list[Any] = field(default_factory=list)
    fresh_transactions: list[Any] = field(default_factory=list)
    budget_calls: list[dict[str, Any]] = field(default_factory=list)

    def collection(self, name: str) -> _DeleteStoreCollection:
        return _DeleteStoreCollection(self, tuple(name.split('/')))

    def transaction(self) -> '_DeleteStoreTransaction':
        transaction = _DeleteStoreTransaction(self)
        self.fresh_transactions.append(transaction)
        return transaction


@dataclass
class _DeleteStoreTransaction:
    store: '_ContendingDeleteStore'

    def update(self, document: _DeleteStoreDoc, updates: dict[str, Any]) -> None:
        self.store.documents[document.path].update(copy.deepcopy(updates))

    def delete(self, document: _DeleteStoreDoc) -> None:
        self.store.documents.pop(document.path, None)


@pytest.fixture
def contending_delete_store(monkeypatch):
    store = _ContendingDeleteStore(boundary_errors=[Aborted('contention'), Aborted('contention')])

    def transactional(func):
        def locked(transaction, *args, **kwargs):
            if store.boundary_errors:
                raise store.boundary_errors.pop(0)
            result = func(transaction, *args, **kwargs)
            store.commits.append(transaction)
            return result

        return locked

    monkeypatch.setattr(recording_sessions.firestore, 'transactional', transactional)

    def budget_retry(*a, **kw):
        store.budget_calls.append({'operation_name': kw.get('operation_name'), 'args': len(a)})
        kw.setdefault('sleep', lambda _delay: None)
        kw.setdefault('random_value', lambda: 0)
        return run_with_transaction_contention_retry(*a, **kw)

    monkeypatch.setattr(recording_sessions, 'run_with_transaction_contention_retry', budget_retry)
    return store


def _seed_empty_conversation(store: _ContendingDeleteStore, uid: str = 'uid', conversation_id: str = 'conversation'):
    store.documents[('users', uid, 'conversations', conversation_id)] = _stored_conversation([])


def test_empty_delete_replays_read_abort_on_fresh_transactions_and_commits_once(contending_delete_store):
    """A read-time abort — which the SDK never retries — still deletes the row."""
    _seed_empty_conversation(contending_delete_store)
    path = ('users', 'uid', 'conversations', 'conversation')

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert deleted is True
    assert path not in contending_delete_store.documents
    # One real commit: two aborted attempts, then the successful one.
    assert len(contending_delete_store.commits) == 1
    # Every attempt got a brand-new transaction from the budget's factory.
    assert len(contending_delete_store.fresh_transactions) == 3


def test_empty_delete_restarts_a_store_side_expired_id(contending_delete_store):
    """The expired-id 400 raised at the boundary is restarted, not surfaced."""
    _seed_empty_conversation(contending_delete_store)
    contending_delete_store.boundary_errors = [InvalidArgument(_EXPIRED_TRANSACTION_MESSAGE)]
    path = ('users', 'uid', 'conversations', 'conversation')

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert deleted is True
    assert path not in contending_delete_store.documents
    assert len(contending_delete_store.commits) == 1


def test_empty_delete_survives_a_mixed_abort_then_expired_burst(contending_delete_store):
    _seed_empty_conversation(contending_delete_store)
    contending_delete_store.boundary_errors = [
        Aborted('contention'),
        InvalidArgument(_EXPIRED_TRANSACTION_MESSAGE),
    ]
    path = ('users', 'uid', 'conversations', 'conversation')

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert deleted is True
    assert path not in contending_delete_store.documents


def test_exhausted_empty_delete_still_refuses_a_real_write_failure(contending_delete_store):
    """Non-contention rejections are not replayed; the caller keeps its signal."""
    _seed_empty_conversation(contending_delete_store)
    contending_delete_store.boundary_errors = [PermissionDenied('the caller cannot write this row')]

    with pytest.raises(PermissionDenied):
        recording_sessions.tombstone_and_delete_empty_conversation(
            'uid', 'conversation', 'recording', firestore_client=contending_delete_store
        )
    # Nothing was deleted and no attempt committed.
    assert ('users', 'uid', 'conversations', 'conversation') in contending_delete_store.documents
    assert contending_delete_store.commits == []


def test_empty_delete_late_content_refusal_is_not_replayed_as_a_delete(contending_delete_store):
    """Content that arrived before the delete keeps the row across every attempt."""
    path = ('users', 'uid', 'conversations', 'conversation')
    contending_delete_store.documents[path] = _stored_conversation([{'id': 'late-segment', 'text': 'persisted'}])
    sessions_path = ('users', 'uid', 'recording_sessions', 'recording')
    now = datetime.now(timezone.utc)
    contending_delete_store.documents[sessions_path] = {
        'schema_version': recording_sessions.RECORDING_SESSION_SCHEMA_VERSION,
        'uid': 'uid',
        'recording_session_id': 'recording',
        'conversation_id': 'conversation',
        'lifecycle_version': recording_sessions.LIFECYCLE_ENVELOPE_VERSION,
        'lifecycle_phase': 'in_progress',
        'lifecycle_sequence': 0,
        'created_at': now,
        'updated_at': now,
    }

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert deleted is False
    assert path in contending_delete_store.documents
    # The refusal is a read-only transaction (no update, no delete), so the
    # committing attempt leaves the bound session exactly as it was.
    session = contending_delete_store.documents[('users', 'uid', 'recording_sessions', 'recording')]
    assert session['lifecycle_phase'] == 'in_progress'
    assert session['lifecycle_sequence'] == 0


def test_empty_delete_tombstone_still_lands_after_a_contended_first_attempt(contending_delete_store):
    """The session tombstone written by the committing attempt is the durable one."""
    _seed_empty_conversation(contending_delete_store)
    sessions_path = ('users', 'uid', 'recording_sessions', 'recording')
    now = datetime.now(timezone.utc)
    contending_delete_store.documents[sessions_path] = {
        'schema_version': recording_sessions.RECORDING_SESSION_SCHEMA_VERSION,
        'uid': 'uid',
        'recording_session_id': 'recording',
        'conversation_id': 'conversation',
        'lifecycle_version': recording_sessions.LIFECYCLE_ENVELOPE_VERSION,
        'lifecycle_phase': 'in_progress',
        'lifecycle_sequence': 0,
        'created_at': now,
        'updated_at': now,
    }

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert deleted is True
    session = contending_delete_store.documents[sessions_path]
    assert session['lifecycle_phase'] == 'discarded'
    assert session['lifecycle_sequence'] == 1


def test_empty_delete_runs_on_the_named_shared_budget(contending_delete_store):
    """The delete uses the same named budget as the session's other writers."""
    _seed_empty_conversation(contending_delete_store)
    contending_delete_store.boundary_errors = []

    recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert contending_delete_store.budget_calls == [{'operation_name': 'recording_session_empty_delete', 'args': 2}]


def test_exhausted_empty_delete_budget_raises_contention_exhausted(contending_delete_store, caplog):
    """A fully contended burst surfaces the exhaustion, not a bare SDK error."""
    _seed_empty_conversation(contending_delete_store)
    contending_delete_store.boundary_errors = [Aborted('contention')] * 50

    with caplog.at_level('ERROR', logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            recording_sessions.tombstone_and_delete_empty_conversation(
                'uid', 'conversation', 'recording', firestore_client=contending_delete_store
            )

    exhausted = [r for r in caplog.records if r.getMessage().endswith('outcome=exhausted')]
    assert exhausted, 'the exhausted burst must be correlated by operation name'
    assert 'operation=recording_session_empty_delete' in exhausted[0].getMessage()
    # The row survives; the caller (sweep or create) retries it later.
    assert ('users', 'uid', 'conversations', 'conversation') in contending_delete_store.documents


def test_deleted_conversation_snapshot_refilled_by_the_committing_attempt(contending_delete_store):
    """A contended first attempt must not leave a stale snapshot in the out-param."""
    _seed_empty_conversation(contending_delete_store)
    published: dict[str, Any] = {'stale': 'value'}

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid',
        'conversation',
        'recording',
        firestore_client=contending_delete_store,
        deleted_conversation=published,
    )

    assert deleted is True
    # The pre-fix contract: the snapshot belongs to the attempt that commits.
    assert published.get('id') == 'conversation'
    assert 'stale' not in published


def test_empty_delete_without_a_session_binding_still_deletes(contending_delete_store):
    """The legacy route deletes without touching any session document."""
    _seed_empty_conversation(contending_delete_store)
    contending_delete_store.boundary_errors = [Aborted('contention')]
    path = ('users', 'uid', 'conversations', 'conversation')

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', None, firestore_client=contending_delete_store
    )

    assert deleted is True
    assert path not in contending_delete_store.documents


@pytest.mark.parametrize(
    ('fence_field', 'fence_value'),
    [
        ('status', 'processing'),
        ('discarded', True),
        ('deleted', True),
        ('is_locked', True),
        ('sync_content_revision', 7),
    ],
    ids=['status', 'discarded', 'deleted', 'locked', 'sync-revision'],
)
def test_empty_delete_fence_survives_a_contended_first_attempt(contending_delete_store, fence_field, fence_value):
    """Every refusal fence holds on the attempt that finally commits."""
    path = ('users', 'uid', 'conversations', 'conversation')
    row = _stored_conversation([])
    if fence_field == 'status':
        row['status'] = fence_value
    else:
        row[fence_field] = fence_value
    contending_delete_store.documents[path] = row

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert deleted is False
    assert path in contending_delete_store.documents
    # The refusal short-circuits before the session tombstone is touched, so a
    # session document seeded by the caller stays exactly as it was.


def test_empty_delete_missing_row_is_replayed_and_reports_false(contending_delete_store):
    """A row already gone is a clean no-op that still survives the burst."""
    contending_delete_store.boundary_errors = [Aborted('contention')]

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert deleted is False
    # The read-only refusal still commits (Firestore commits empty
    # transactions), but nothing was written anywhere.
    assert len(contending_delete_store.commits) == 1


def test_empty_delete_budget_writes_nothing_when_attempts_expire_the_row_read(contending_delete_store):
    """A store-side expired rejection on every attempt leaves the row intact."""
    _seed_empty_conversation(contending_delete_store)
    contending_delete_store.boundary_errors = [InvalidArgument(_EXPIRED_TRANSACTION_MESSAGE)] * 5

    with pytest.raises(InvalidArgument):
        recording_sessions.tombstone_and_delete_empty_conversation(
            'uid', 'conversation', 'recording', firestore_client=contending_delete_store
        )

    assert ('users', 'uid', 'conversations', 'conversation') in contending_delete_store.documents
    assert contending_delete_store.commits == []


def test_empty_delete_content_guard_holds_across_the_replayed_attempts(contending_delete_store):
    """A row whose stored segments decode to real content is refused every time."""
    path = ('users', 'uid', 'conversations', 'conversation')
    contending_delete_store.documents[path] = _stored_conversation([{'id': 'real', 'text': 'words'}])
    contending_delete_store.boundary_errors = [Aborted('contention')]

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_delete_store
    )

    assert deleted is False
    assert path in contending_delete_store.documents


def test_empty_delete_published_snapshot_is_untouched_by_a_refusal(contending_delete_store):
    """A refused delete publishes nothing into the out-param."""
    path = ('users', 'uid', 'conversations', 'conversation')
    contending_delete_store.documents[path] = _stored_conversation([{'id': 'real', 'text': 'words'}])
    contending_delete_store.boundary_errors = []
    published: dict[str, Any] = {}

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid',
        'conversation',
        'recording',
        firestore_client=contending_delete_store,
        deleted_conversation=published,
    )

    assert deleted is False
    assert published == {}


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


# ── Reuse the lifecycle-owner's conversation read instead of re-reading it ──
#
# Session opening already reads the bound conversation inside its marker-write
# transaction. create_new_in_progress_conversation must reuse that snapshot
# instead of issuing another get by id on every resumed live session.


class _ResumeSessionHost:
    """Wires create_new_in_progress_conversation's persistence.call to the real
    lifecycle_service.open_live_recording_session against a fake firestore, so
    the get_conversation call count reflects what actually happens end to end
    rather than what a mock says happens."""

    def __init__(self, *, firestore_client: Any) -> None:
        self.request = SimpleNamespace(uid='uid', source='omi', call_id=None, conversation_role=None)
        self.client_device_context = SimpleNamespace(client_device_id='dev-1', platform='desktop')
        self.language = 'en'
        self.conversation_creation_timeout = 120
        self.use_custom_stt = False
        self.private_cloud_sync_enabled = False
        self.client_conversation_id = None
        self.recording_session_id = 'recording-1'
        self.is_multi_channel = False
        self.state = SimpleNamespace(current_conversation_id=None)
        self.recording_session_ids_by_conversation = {}
        self.persistence = SimpleNamespace(call=self._call)
        self.speakers = SimpleNamespace(refresh_for_conversation=self._refresh_speakers)
        self._firestore_client = firestore_client

    async def _refresh_speakers(self, _conversation_id: str) -> None:
        return None

    async def _call(self, fn, *args, **kwargs):
        if fn.__name__ == 'open_live_recording_session':
            return fn(*args, firestore_client=self._firestore_client, **kwargs)
        if fn.__name__ in ('set_in_progress_conversation_id', 'update_conversation'):
            return None
        return fn(*args, **kwargs)


class _ResumeSessionController(LiveConversationController):
    def send_conversation_session(self, *args, **kwargs) -> None:
        pass


async def test_resume_reuses_the_lifecycle_snapshot_instead_of_reading_twice(recording_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')

    get_conversation_calls: list[str] = []
    conversation = {
        'id': 'conversation-old',
        'status': 'in_progress',
        'discarded': False,
        'source': 'omi',
        'client_device_id': 'dev-1',
        'finished_at': datetime.now(timezone.utc),
    }

    def counting_get_conversation(_uid, conversation_id, **_kwargs):
        get_conversation_calls.append(conversation_id)
        return conversation if conversation_id == 'conversation-old' else None

    monkeypatch.setattr(lifecycle_service.conversations_db, 'get_conversation', counting_get_conversation)

    # A prior message on this recording session already created and bound
    # 'conversation-old'; this call is the reconnect that resumes it.
    recording_store.documents[('users', 'uid', 'conversations', 'conversation-old')] = copy.deepcopy(conversation)
    lifecycle_service.open_recording_session('uid', 'recording-1', 'conversation-old', firestore_client=recording_store)

    host = _ResumeSessionHost(firestore_client=recording_store)
    controller = _ResumeSessionController(host)

    await controller.create_new_in_progress_conversation()

    assert (
        get_conversation_calls == []
    ), f'transactional snapshot should avoid a second read, got {get_conversation_calls}'
    assert host.state.current_conversation_id == 'conversation-old'


def _stored_conversation_with_audio(audio_files: list[dict[str, Any]]) -> dict[str, Any]:
    """An empty generation that nonetheless registered private-cloud audio.

    This is the shape STT failure leaves behind: the pusher landed real chunks
    and registered them, but no segment ever arrived, so the emptiness guard
    still authorizes the delete.
    """
    return conversations_db.encode_conversation_for_write(
        'uid',
        {
            'id': 'conversation',
            'status': 'in_progress',
            'transcript_segments': [],
            'audio_files': audio_files,
        },
        'standard',
    )


def test_empty_cleanup_publishes_the_snapshot_it_deleted(recording_store):
    conversation_path = ('users', 'uid', 'conversations', 'conversation')
    audio_files = [{'path': 'chunks/uid/conversation/0.wav'}]
    recording_store.documents[conversation_path] = _stored_conversation_with_audio(audio_files)
    recording_sessions.create_or_get_recording_session(
        'uid', 'recording', 'conversation', firestore_client=recording_store
    )

    captured: dict[str, Any] = {}
    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid',
        'conversation',
        'recording',
        firestore_client=recording_store,
        deleted_conversation=captured,
    )

    assert deleted is True
    assert conversation_path not in recording_store.documents
    # Physical cleanup can only see the row through this snapshot; the document
    # itself is gone by the time the caller gets to decide anything.
    assert captured['audio_files'] == audio_files


def test_empty_cleanup_publishes_nothing_when_it_refuses_to_delete(recording_store):
    conversation_path = ('users', 'uid', 'conversations', 'conversation')
    recording_store.documents[conversation_path] = _stored_conversation([{'id': 'late', 'text': 'persisted'}])
    recording_sessions.create_or_get_recording_session(
        'uid', 'recording', 'conversation', firestore_client=recording_store
    )

    captured: dict[str, Any] = {}
    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid',
        'conversation',
        'recording',
        firestore_client=recording_store,
        deleted_conversation=captured,
    )

    assert deleted is False
    assert conversation_path in recording_store.documents
    assert captured == {}


@pytest.mark.parametrize('field,value', [('is_locked', True), ('deleted', True), ('sync_content_revision', 1)])
def test_empty_cleanup_preserves_protected_or_sync_owned_rows(recording_store, field, value):
    path = ('users', 'uid', 'conversations', 'conversation')
    row = _stored_conversation([], level='standard')
    row[field] = value
    recording_store.documents[path] = row
    recording_sessions.create_or_get_recording_session(
        'uid', 'recording', 'conversation', firestore_client=recording_store
    )
    assert not recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=recording_store
    )
    assert recording_store.documents[path] == row
