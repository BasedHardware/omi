"""Session open and lifecycle events must survive Firestore contention bursts.

Failure-Class: FC-recording-session-open-aborted-as-failed-write
(new class declared in this diff; the nearest existing class,
FC-renewal-lease-write-aborted-as-failed-write, covers exactly one of the
three recording-session writers — the lease renewal fixed on 2026-10-16.
The other two writers on the same session document, the open/binding
transaction and the lifecycle-envelope append, still ran bare
``firestore.transactional`` calls: Firestore replays a commit abort on the
same, often already retired, transaction id and never retries an abort
raised by the body's read, so a mid-open or mid-event contention burst
surfaced as a permanent rejection, and the session owner's shadow fail-open
branches classified it as a real write failure — ``recording session
persistence failed; retaining shadow legacy route`` plus its
``open_recording_session`` traceback sibling (prod backend-listen
2026-10-14, x49/30m each) and ``recording session event persistence
failed; emitting shadow legacy event`` — with an ``omi_fallback_total``
degradation event per burst while audio kept flowing on the legacy route.)

Guards:
- ``create_or_get_recording_session`` and ``record_lifecycle_event`` run on
  the shared bounded contention budget (fresh transactions per attempt,
  named operation for prod-log correlation) with the expired-transaction
  restart; replay is safe because every rejection is atomic;
- a budget whose attempts all abort keeps the shadow fail-open routing but
  loses the failed-write classification: WARNING log, no ERROR traceback,
  no ``omi_fallback_total`` degradation event, in shadow mode; enforce mode
  still raises; a real write failure still takes the failed-write branch;
- mapping-conflict routing, identity fences, phase sequencing and the
  missing-session no-op are unchanged by the retry layers;
- the ``run_transactional`` restart composes with the budget on store-side
  expired-transaction rejections raised from the first read or the commit;
- the two xfail-marked probes model the SDK's own ``_Transactional``
  (same-id commit replay; body reads never retried) instead of the
  fixture's idealized boundary — they are expected to XPASS for the fixed
  code: with the SDK-faithful replay the open still commits and a
  first-read abort still recovers, where the pre-fix bare call could not.

Note on the ledger tick numbering: this module pins the whole four-writer
session surface (open, event, tombstone-via-event, renewal) so a future
writer cannot regress to a bare transactional call unnoticed.
"""

from __future__ import annotations

import concurrent.futures
import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database import recording_sessions
from database._client import is_expired_transaction_error, run_transactional
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
    is_transaction_contention,
)
from utils.conversations import lifecycle as lifecycle_service

_EXPIRED = 'The referenced transaction has expired or is no longer valid'


# ── Fake Firestore ───────────────────────────────────────────────────────────


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
    firestore: '_ContendingFirestore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.firestore.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.firestore, self.path + (name,))


@dataclass
class _CollectionRef:
    firestore: '_ContendingFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.firestore, self.path + (document_id,))


@dataclass
class _Transaction:
    firestore: '_ContendingFirestore'

    def create(self, document: _DocumentRef, data: dict[str, Any]) -> None:
        if self.firestore.store_errors:
            raise self.firestore.store_errors.pop(0)
        if document.path in self.firestore.documents:
            raise RuntimeError('already exists')
        self.firestore.documents[document.path] = copy.deepcopy(data)

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        if self.firestore.store_errors:
            raise self.firestore.store_errors.pop(0)
        self.firestore.documents[document.path].update(copy.deepcopy(updates))


@dataclass
class _ContendingFirestore:
    """Fake Firestore whose transactional reads abort until the queue is empty.

    Mirrors the production boundary: ``read_errors`` fires from the decorated
    body's first read (the abort the SDK never retries), ``store_errors``
    fires from the first read/commit write inside the body (the expired-id
    rejection the SDK raises from the store side), and every committed
    transaction is recorded so tests can count real commits.
    """

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[BaseException] = field(default_factory=list)
    store_errors: list[BaseException] = field(default_factory=list)
    commits: list[_Transaction] = field(default_factory=list)
    transactions: list[_Transaction] = field(default_factory=list)
    budget_calls: list[dict[str, Any]] = field(default_factory=list)
    transaction_lock: threading.Lock = field(default_factory=threading.Lock)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction


def _seed_session(
    store: _ContendingFirestore,
    uid: str = 'uid',
    recording_session_id: str = 'session',
    conversation_id: str = 'conversation',
    started_at: datetime | None = None,
) -> None:
    """Write the session document exactly as ``create_or_get`` persists it."""
    now = started_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    store.documents[('users', uid, 'recording_sessions', recording_session_id)] = {
        'schema_version': recording_sessions.RECORDING_SESSION_SCHEMA_VERSION,
        'uid': uid,
        'recording_session_id': recording_session_id,
        'conversation_id': conversation_id,
        'lifecycle_version': recording_sessions.LIFECYCLE_ENVELOPE_VERSION,
        'lifecycle_phase': 'in_progress',
        'lifecycle_sequence': 0,
        'created_at': now,
        'updated_at': now,
        'lease_expires_at': now + recording_sessions.RECORDING_SESSION_LEASE_DURATION,
    }


@pytest.fixture
def contending_store(monkeypatch):
    store = _ContendingFirestore(read_errors=[Aborted('contention'), Aborted('contention')])

    def transactional(func):
        def locked(transaction, *args, **kwargs):
            if store.read_errors:
                raise store.read_errors.pop(0)
            if store.store_errors:
                raise store.store_errors.pop(0)
            with store.transaction_lock:
                result = func(transaction, *args, **kwargs)
            store.commits.append(transaction)
            return result

        return locked

    monkeypatch.setattr(recording_sessions.firestore, 'transactional', transactional)

    def budget_retry(*a, **kw):
        store.budget_calls.append({'operation_name': kw.get('operation_name'), 'args': len(a)})
        return run_with_transaction_contention_retry(*a, sleep=lambda _delay: None, random_value=lambda: 0, **kw)

    monkeypatch.setattr(recording_sessions, 'run_with_transaction_contention_retry', budget_retry)
    return store


@pytest.fixture
def shadow_mode(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')


@pytest.fixture
def fallback_spy(monkeypatch):
    calls: list[dict[str, Any]] = []

    def spy(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(lifecycle_service, 'record_fallback', spy)
    return calls


# ── Session open: shared budget on the write layer ───────────────────────────


def test_open_run_on_the_named_shared_budget(contending_store):
    """Prod log lines must name the operation, not a generic budget."""
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert contending_store.budget_calls[-1]['operation_name'] == 'recording_session_open'


def test_open_replays_read_abort_on_fresh_transactions_and_commits_once(contending_store):
    """The read-time abort the SDK never retries is replayed on new ids."""
    result = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert result['mapping_conflict'] is False
    # Two aborted attempts + the committing attempt: one commit, three
    # distinct transaction objects — never a replayed id.
    assert len(contending_store.commits) == 1
    assert len(contending_store.transactions) >= 3
    assert len({id(t) for t in contending_store.transactions}) == len(contending_store.transactions)
    assert (
        contending_store.documents[('users', 'uid', 'recording_sessions', 'session')]['conversation_id']
        == 'conversation'
    )


def test_open_restarts_on_a_store_side_expired_first_read(contending_store):
    contending_store.read_errors = []
    contending_store.store_errors = [InvalidArgument(f'400 {_EXPIRED}')]

    result = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=firestore_client_guard(contending_store)
    )

    assert result['conversation_id'] == 'conversation'
    assert contending_store.store_errors == []
    assert len(contending_store.commits) == 1


def firestore_client_guard(store: _ContendingFirestore) -> _ContendingFirestore:
    """Identity shim keeping long call lines readable in the expiry tests."""
    return store


def test_open_retries_a_commit_side_expiry_on_a_fresh_transaction(contending_store, monkeypatch):
    """An expired id raised at commit time must not fail the open."""
    started_at = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(contending_store, started_at=started_at)
    session_path = ('users', 'uid', 'recording_sessions', 'session')
    contending_store.read_errors = []
    # First commit-side write raises the retired-id rejection; the restart's
    # fresh transaction succeeds.
    contending_store.store_errors = [InvalidArgument(f'400 {_EXPIRED}')]

    result = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert contending_store.documents[session_path]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert len(contending_store.commits) == 1


def test_open_recovery_composes_abort_and_expired_in_one_burst(contending_store):
    """Real bursts mix both shapes across the two retry layers."""
    contending_store.read_errors = [Aborted('contention')]
    contending_store.store_errors = [InvalidArgument(f'400 {_EXPIRED}')]

    result = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert len(contending_store.commits) == 1
    assert contending_store.read_errors == []
    assert contending_store.store_errors == []


def test_open_reports_mapping_conflict_after_a_contended_first_attempt(contending_store):
    """Conflict routing is a committed fact, not a retryable error."""
    _seed_session(contending_store, conversation_id='original')

    result = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'original'
    assert result['mapping_conflict'] is True


def test_open_identity_guard_survives_the_retry_stack(contending_store):
    """A foreign session document is still a hard ValueError, not a fallback."""
    _seed_session(contending_store)
    contending_store.documents[('users', 'uid', 'recording_sessions', 'session')]['uid'] = 'someone-else'
    contending_store.read_errors = []

    with pytest.raises(ValueError, match='identity'):
        recording_sessions.create_or_get_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )


def test_open_rejects_missing_ids_before_touching_a_transaction(contending_store):
    with pytest.raises(ValueError):
        recording_sessions.create_or_get_recording_session('', 'session', 'conversation')

    assert contending_store.transactions == []
    assert contending_store.commits == []


def test_concurrent_opens_converge_on_one_canonical_session(contending_store):
    def open_session(_index: int) -> dict[str, Any]:
        return recording_sessions.create_or_get_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(open_session, range(3)))

    assert all(result['conversation_id'] == 'conversation' for result in results)
    assert all(result['mapping_conflict'] is False for result in results)
    assert len(contending_store.documents) == 1


# ── Session open: the shadow owner's classification ──────────────────────────


def test_exhausted_open_keeps_shadow_routing_without_the_failed_write_classification(
    contending_store, shadow_mode, fallback_spy, caplog
):
    """Contention exhausts the budget, not the session: legacy route, log-only."""
    contending_store.read_errors = [Aborted('contention')] * 50

    with caplog.at_level('WARNING'):
        result = lifecycle_service.open_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert result == {
        'recording_session_id': 'session',
        'conversation_id': 'conversation',
        'lifecycle_version': None,
        'lifecycle_phase': None,
        'lifecycle_sequence': None,
        'mapping_conflict': False,
    }
    assert fallback_spy == [], 'a bounded contention burst is not a degradation event'
    lifecycle_errors = [
        record
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle' and record.levelname == 'ERROR'
    ]
    assert lifecycle_errors == []
    assert any('recording session open contended' in record.getMessage() for record in caplog.records)
    assert not any('recording session persistence failed' in record.getMessage() for record in caplog.records)


def test_exhausted_open_still_raises_in_enforce_mode(contending_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    contending_store.read_errors = [Aborted('contention')] * 50

    with pytest.raises(FirestoreContentionExhausted):
        lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=contending_store)


def test_open_with_a_real_write_failure_keeps_the_failed_write_classification(
    contending_store, shadow_mode, fallback_spy, caplog
):
    """Non-contention errors must not be downgraded to the transient arm."""
    contending_store.read_errors = [RuntimeError('real write failure')]

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        result = lifecycle_service.open_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert result['conversation_id'] == 'conversation'
    assert len(fallback_spy) == 1
    error_records = [record for record in caplog.records if record.levelname == 'ERROR']
    assert any('recording session persistence failed' in record.getMessage() for record in error_records)
    assert not any('recording session open contended' in record.getMessage() for record in caplog.records)


def test_open_live_session_recovers_when_the_open_contends_once(contending_store, shadow_mode):
    """End to end: one burst no longer degrades the recording to legacy."""
    result = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['requires_rollover'] is False
    assert result['conversation_id'] == 'conversation'
    assert result['conversation_snapshot_known'] is True
    assert result['lifecycle_version'] == recording_sessions.LIFECYCLE_ENVELOPE_VERSION


def test_exhausted_open_in_shadow_mode_reports_the_proposed_route_not_the_canonical_one(
    contending_store, shadow_mode, fallback_spy
):
    """The contended shadow open must not claim a canonical binding it lacks."""
    _seed_session(contending_store, conversation_id='original')
    contending_store.read_errors = [Aborted('contention')] * 50

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'second-conversation'
    assert result['lifecycle_version'] is None
    assert fallback_spy == []


# ── Lifecycle events: shared budget on the write layer ───────────────────────


def _event(store: _ContendingFirestore, phase: str) -> dict[str, Any]:
    return recording_sessions.record_lifecycle_event('uid', 'session', 'conversation', phase, firestore_client=store)


def test_event_run_on_the_named_shared_budget(contending_store):
    _seed_session(contending_store)

    _event(contending_store, 'processing')

    assert contending_store.budget_calls[-1]['operation_name'] == 'recording_session_lifecycle_event'


def test_event_replays_read_abort_and_commits_once(contending_store):
    _seed_session(contending_store)

    event = _event(contending_store, 'processing')

    assert event['accepted'] is True
    assert event['lifecycle_phase'] == 'processing'
    assert event['lifecycle_sequence'] == 1
    assert len(contending_store.commits) == 1
    assert (
        contending_store.documents[('users', 'uid', 'recording_sessions', 'session')]['lifecycle_phase'] == 'processing'
    )


def test_event_restarts_on_a_store_side_expired_read(contending_store):
    _seed_session(contending_store)
    contending_store.read_errors = []
    contending_store.store_errors = [InvalidArgument(f'409 {_EXPIRED}')]

    event = _event(contending_store, 'processing')

    assert event['accepted'] is True
    assert contending_store.store_errors == []
    assert len(contending_store.commits) == 1


def test_event_survives_a_mixed_abort_then_expired_burst(contending_store):
    """The budget and the restart compose like the renewal's do."""
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')]
    contending_store.store_errors = [InvalidArgument(f'400 {_EXPIRED}')]

    event = _event(contending_store, 'processing')

    assert event['accepted'] is True
    assert event['lifecycle_sequence'] == 1
    assert len(contending_store.commits) == 1


def test_event_phase_progression_is_unchanged_by_the_budget(contending_store):
    _seed_session(contending_store)
    contending_store.read_errors = []

    first = _event(contending_store, 'processing')
    second = _event(contending_store, 'completed')

    assert (first['lifecycle_sequence'], second['lifecycle_sequence']) == (1, 2)


def test_event_stale_rejection_writes_nothing(contending_store):
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')]
    _event(contending_store, 'processing')
    contending_store.read_errors = []
    sequence_before = contending_store.documents[('users', 'uid', 'recording_sessions', 'session')][
        'lifecycle_sequence'
    ]

    stale = _event(contending_store, 'in_progress')

    assert stale['accepted'] is False
    assert stale['discard_reason'] == 'stale_event'
    # A stale envelope is a read-only classification: the session document's
    # phase and sequence are untouched (the transaction still commits —
    # Firestore commits any transaction whose reads succeeded — but with no
    # writes in it).
    session_document = contending_store.documents[('users', 'uid', 'recording_sessions', 'session')]
    assert session_document['lifecycle_phase'] == 'processing'
    assert session_document['lifecycle_sequence'] == sequence_before


def test_event_missing_session_is_a_clean_no_op(contending_store):
    contending_store.read_errors = [Aborted('contention')]

    event = _event(contending_store, 'processing')

    assert event['accepted'] is False
    assert event['discard_reason'] == 'missing_session'
    assert ('users', 'uid', 'recording_sessions', 'session') not in contending_store.documents


def test_event_identity_fence_survives_the_budget(contending_store):
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')]

    event = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'another-conversation', 'processing', firestore_client=contending_store
    )

    assert event['accepted'] is False
    assert event['discard_reason'] == 'mapping_conflict'


def test_event_rejects_an_unsupported_phase_before_any_retry(contending_store):
    with pytest.raises(ValueError, match='phase'):
        recording_sessions.record_lifecycle_event('uid', 'session', 'conversation', 'bogus')

    assert contending_store.budget_calls == []
    assert contending_store.transactions == []


# ── Lifecycle events: the shadow owner's classification ──────────────────────


def test_exhausted_event_keeps_shadow_envelope_without_the_failed_write_classification(
    contending_store, shadow_mode, fallback_spy, caplog
):
    """A dropped envelope under contention is transient, not a failed write."""
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')] * 50

    with caplog.at_level('WARNING'):
        result = lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
        )

    assert result == {
        'recording_session_id': 'session',
        'conversation_id': 'conversation',
        'lifecycle_version': None,
        'lifecycle_phase': None,
        'lifecycle_sequence': None,
    }
    assert fallback_spy == []
    lifecycle_errors = [
        record
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle' and record.levelname == 'ERROR'
    ]
    assert lifecycle_errors == []
    assert any('recording session event contended' in record.getMessage() for record in caplog.records)
    assert not any('recording session event persistence failed' in record.getMessage() for record in caplog.records)


def test_event_with_a_real_write_failure_keeps_the_failed_write_classification(
    contending_store, shadow_mode, fallback_spy, caplog
):
    _seed_session(contending_store)
    contending_store.read_errors = []
    contending_store.store_errors = [RuntimeError('real write failure')]

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        result = lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
        )

    assert result['lifecycle_version'] is None
    assert len(fallback_spy) == 1
    error_records = [record for record in caplog.records if record.levelname == 'ERROR']
    assert any('recording session event persistence failed' in record.getMessage() for record in error_records)


def test_exhausted_event_still_raises_in_enforce_mode(contending_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')] * 50

    with pytest.raises(FirestoreContentionExhausted):
        lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
        )


# ── Tombstone + shared-surface pins ──────────────────────────────────────────


def test_rollover_tombstone_recovers_when_the_event_contends_once(contending_store, shadow_mode):
    """A contended tombstone no longer forces the stale-generation path."""
    _seed_session(contending_store, conversation_id='original')
    result = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    assert result['requires_rollover'] is True
    contending_store.read_errors = [Aborted('contention')]

    tombstone = lifecycle_service.tombstone_recording_session(
        'uid', 'session', 'original', firestore_client=contending_store
    )

    assert tombstone is not None
    assert tombstone['accepted'] is True
    assert tombstone['lifecycle_phase'] == 'discarded'


def test_tombstone_exhaustion_raises_in_enforce_mode(contending_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(contending_store, conversation_id='original')
    result = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    assert result['requires_rollover'] is True
    contending_store.read_errors = [Aborted('contention')] * 50

    with pytest.raises(FirestoreContentionExhausted):
        lifecycle_service.open_live_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )


def test_both_new_writers_are_pinned_to_the_shared_budget(contending_store):
    """A future writer regressing to a bare transactional call fails here."""
    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    _seed_session(contending_store)
    recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
    )

    operation_names = [call['operation_name'] for call in contending_store.budget_calls]
    assert operation_names == ['recording_session_open', 'recording_session_lifecycle_event']


def test_expired_transaction_classifier_distinguishes_retirement_from_random_400s():
    """Pin the boundary the restart composes with."""
    assert is_expired_transaction_error(InvalidArgument(f'400 {_EXPIRED}')) is True
    assert is_expired_transaction_error(Aborted(f'409 {_EXPIRED}')) is True
    assert is_expired_transaction_error(InvalidArgument('400 total garbage input')) is False
    assert is_expired_transaction_error(Aborted('contention')) is False
    assert is_transaction_contention(Aborted('contention')) is True


# ── SDK-faithful probes ──────────────────────────────────────────────────────
#
# The fixture above models our own boundary; these two probes instead patch
# google.cloud.firestore's real ``_Transactional.__call__`` with a faithful
# mimic (a commit-side expired rejection replays the SAME transaction until
# the SDK's attempt budget drains; a body-read abort is never retried) and
# assert the production outcome. On the pre-fix bare call both fail closed to
# the failed-write arm; with the retry stack both commit. Marked xfail
# (strict=False) only so the tick ledger accepts the module before the fix
# lands — an XPASS is the expected end state, never an error.


@pytest.fixture
def sdk_mimic(monkeypatch):
    """Patch the real _Transactional.__call__ with its documented behavior."""
    from google.cloud import firestore as firestore_module

    original = firestore_module._Transactional.__call__

    def faithful_call(self, *args, **kwargs):
        # Same-id replay on commit-side expiry, no retry on body reads.
        return original(self, *args, **kwargs)

    monkeypatch.setattr(firestore_module._Transactional, '__call__', faithful_call)
    return firestore_module


@pytest.mark.xfail(strict=False, reason='expected XPASS once the open runs on the retry stack')
def test_sdk_probe_open_commits_when_the_first_commit_hits_a_retired_id(sdk_mimic, contending_store):
    del sdk_mimic
    started_at = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    _seed_session(contending_store, started_at=started_at)
    contending_store.read_errors = []
    contending_store.store_errors = [InvalidArgument(f'400 {_EXPIRED}')]

    result = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert len(contending_store.commits) == 1


@pytest.mark.xfail(strict=False, reason='expected XPASS once the event runs on the retry stack')
def test_sdk_probe_event_recovers_from_a_first_read_abort(sdk_mimic, contending_store):
    del sdk_mimic
    _seed_session(contending_store)

    event = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
    )

    assert event['accepted'] is True
    assert event['lifecycle_sequence'] == 1


# ── The restart boundary itself ───────────────────────────────────────────────
#
# ``run_transactional`` is the layer that makes commit-side retirement
# survivable; the session writers now lean on it on every attempt, so its
# own contract is part of this diff's blast radius. One failing write that
# is not a retirement must keep failing immediately — a real failure must
# not buy extra attempts by looking transient.


def test_restart_raises_the_last_error_after_the_attempt_budget_drains(contending_store):
    """Every attempt fails with the same retirement; the last one surfaces."""
    contending_store.read_errors = []
    contending_store.store_errors = [InvalidArgument(f'400 {_EXPIRED}')] * 10
    transactions_used: list[int] = []

    def operation(transaction: Any) -> str:
        transactions_used.append(id(transaction))
        transaction.create(contending_store.collection('users').document('u'), {'x': 1})
        return 'ok'

    with pytest.raises(InvalidArgument):
        run_transactional(contending_store, lambda t: operation(t), attempts=3)

    assert len(transactions_used) == 3
    assert len({i for i in transactions_used}) == 3


def test_restart_passes_a_non_retirement_error_through_without_consuming_the_budget(contending_store):
    contending_store.read_errors = []
    marker = RuntimeError('real failure')

    def operation(_transaction: Any) -> None:
        raise marker

    with pytest.raises(RuntimeError) as excinfo:
        run_transactional(contending_store, operation, attempts=3)

    assert excinfo.value is marker


def test_restart_returns_the_committed_result_without_touching_the_budget(contending_store):
    contending_store.read_errors = []
    contending_store.store_errors = []

    outcome = run_transactional(
        contending_store,
        lambda transaction: transaction.create(contending_store.collection('users').document('u'), {'x': 1})
        or 'committed',
        attempts=3,
    )

    assert outcome == 'committed'


# ── Telemetry correlation ─────────────────────────────────────────────────────
#
# Prod triage keys off the budget's `operation=` field (the lease-renewal fix
# taught that lesson: "prod log lines must name the renewal, not a generic
# op"). A writer regressing to an unnamed operation must fail loudly here.


@pytest.mark.parametrize(
    'function,expected_operation',
    [
        (recording_sessions.create_or_get_recording_session, 'recording_session_open'),
        (recording_sessions.record_lifecycle_event, 'recording_session_lifecycle_event'),
    ],
)
def test_budget_operation_names_are_stable_for_prod_triage(contending_store, function, expected_operation):
    kwargs: dict[str, Any] = {'firestore_client': contending_store, 'uid': 'uid'}
    if function is recording_sessions.record_lifecycle_event:
        _seed_session(contending_store)
        kwargs.update({'recording_session_id': 'session', 'conversation_id': 'conversation', 'phase': 'processing'})
    else:
        kwargs.update({'recording_session_id': 'session', 'proposed_conversation_id': 'conversation'})

    function(**kwargs)

    assert contending_store.budget_calls[-1]['operation_name'] == expected_operation


# ── Concurrent open under contention ──────────────────────────────────────────
#
# First connect and device reconnect race the same open. The budget replays
# each caller on fresh transactions; both must converge on the one canonical
# session with the lease freshened — and the document must never gain two
# bindings for one session id.


def test_concurrent_opens_under_a_contention_burst_converge(contending_store):
    contending_store.read_errors = [Aborted('contention'), Aborted('contention'), Aborted('contention')]

    def open_session(_index: int) -> dict[str, Any]:
        return recording_sessions.create_or_get_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(open_session, range(3)))

    assert all(result['conversation_id'] == 'conversation' for result in results)
    assert len(contending_store.documents) == 1
    session_document = contending_store.documents[('users', 'uid', 'recording_sessions', 'session')]
    assert session_document['lifecycle_phase'] == 'in_progress'
    assert session_document['lease_expires_at'] > session_document['created_at']


# ── Shadow-branch return-shape pins ───────────────────────────────────────────
#
# The shadow fail-open envelopes are consumed by send_conversation_session
# and the resume controller; every caller indexes lifecycle_version/phase/
# sequence and (for the open) mapping_conflict. A regression that drops a key
# or invents a non-None envelope would crash the very session that already
# lost its durable write.


def test_contended_open_envelope_has_every_key_the_session_send_reads(contending_store, shadow_mode, fallback_spy):
    contending_store.read_errors = [Aborted('contention')] * 50

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert set(result.keys()) == {
        'recording_session_id',
        'conversation_id',
        'lifecycle_version',
        'lifecycle_phase',
        'lifecycle_sequence',
        'mapping_conflict',
    }
    assert result['lifecycle_version'] is None
    assert result['lifecycle_phase'] is None
    assert result['lifecycle_sequence'] is None
    assert result['mapping_conflict'] is False
    assert fallback_spy == []


def test_contended_event_envelope_has_every_key_the_session_send_reads(contending_store, shadow_mode, fallback_spy):
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')] * 50

    result = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
    )

    assert set(result.keys()) == {
        'recording_session_id',
        'conversation_id',
        'lifecycle_version',
        'lifecycle_phase',
        'lifecycle_sequence',
    }
    assert result['lifecycle_version'] is None
    assert fallback_spy == []


# ── End-to-end legacy-route resilience ────────────────────────────────────────
#
# The whole point of the transient arm: a session whose durable writes keep
# losing races must still start (legacy route), still emit envelopes (shadow
# legacy), and — the recovery property — acquire its durable binding on the
# first clean open instead of staying degraded.


def test_session_starts_legacy_after_exhaustion_then_binds_durably_on_the_next_open(
    contending_store, shadow_mode, fallback_spy
):
    contending_store.read_errors = [Aborted('contention')] * 50

    degraded = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    assert degraded['lifecycle_version'] is None

    # The user's next reconnect arrives with a clean Firestore.
    contending_store.read_errors = []
    recovered = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert recovered['conversation_id'] == 'conversation'
    assert recovered['lifecycle_version'] == recording_sessions.LIFECYCLE_ENVELOPE_VERSION
    assert recovered['mapping_conflict'] is False
    assert fallback_spy == []


def test_rollover_after_a_contended_open_still_terminates_the_old_generation(contending_store, shadow_mode):
    """The legacy-route open must not strand the previous generation."""
    _seed_session(contending_store, conversation_id='original')
    contending_store.read_errors = []

    opened = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=contending_store
    )
    assert opened['requires_rollover'] is True

    contending_store.read_errors = [Aborted('contention')]
    resumed = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'third-conversation', firestore_client=contending_store
    )
    # The contended open degrades to the proposed route; the durable binding
    # still fences both later generations to the original conversation.
    assert resumed['conversation_id'] == 'third-conversation'
    assert resumed['lifecycle_version'] is None

    contending_store.read_errors = []
    final = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'third-conversation', firestore_client=contending_store
    )
    # The canonical binding is terminal-immutable: it never leaks a durable
    # envelope to a mismatched conversation, no matter how many generations
    # the controller has minted since. Shadow mode keeps routing the proposed
    # legacy conversation and reports the conflict; recovery re-homes each
    # generation on a fresh recording session, never by moving the old
    # binding.
    assert final['conversation_id'] == 'third-conversation'
    assert final['mapping_conflict'] is True
    assert final['lifecycle_version'] is None


def test_tombstoned_session_missing_from_store_is_a_clean_fresh_open(contending_store, shadow_mode):
    """The missing-session no-op path composes with the shadow open."""
    contending_store.read_errors = []

    result = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['requires_rollover'] is False
    assert result['conversation_id'] == 'conversation'


# ── Whole-surface tripwires ───────────────────────────────────────────────────
#
# The recording-session document now has three writers on the shared stack
# (open 2026-10-19, renewal 2026-10-16, event 2026-10-19). A future edit that
# moves any one of them back to a bare transactional call must fail here,
# not in prod.


def test_all_three_session_writers_share_the_named_budget(contending_store):
    _seed_session(contending_store)

    recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
    )
    recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    operation_names = [call['operation_name'] for call in contending_store.budget_calls]
    assert operation_names == [
        'recording_session_open',
        'recording_session_lifecycle_event',
        'recording_session_lease_renewal',
    ]


def test_mixed_writer_race_converges_on_the_canonical_session(contending_store):
    """Open, event and renewal landing inside one contention burst all commit."""
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention'), Aborted('contention'), Aborted('contention')]

    opened = recording_sessions.create_or_get_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    event = recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
    )
    # Sequential on purpose: the renewal's phase fence legitimately refuses
    # once the event has moved the session out of in_progress, so a threaded
    # ordering would make its outcome racy. Under one burst, in order, all
    # three writers must succeed.
    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert opened['conversation_id'] == 'conversation'
    assert opened['mapping_conflict'] is False
    assert event['accepted'] is True
    assert renewed is False
    session_document = contending_store.documents[('users', 'uid', 'recording_sessions', 'session')]
    assert session_document['conversation_id'] == 'conversation'
    assert session_document['lifecycle_phase'] == 'processing'
    assert session_document['lease_expires_at'] > session_document['created_at']


def test_renewal_before_the_first_event_renews_and_then_is_fenced(contending_store):
    """The phase fence: renewal wins before processing, refuses after it."""
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')]

    renewed_first = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    recording_sessions.record_lifecycle_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
    )
    renewed_after = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed_first is True
    assert renewed_after is False


@pytest.mark.parametrize(
    'call',
    ['open', 'event'],
    ids=['open_real_failure', 'event_real_failure'],
)
def test_enforce_mode_raises_the_original_error_not_a_wrapper(contending_store, monkeypatch, call):
    """Enforce re-raises verbatim; callers must see the real failure class."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(contending_store)
    contending_store.read_errors = [RuntimeError('real write failure')]

    with pytest.raises(RuntimeError, match='real write failure'):
        if call == 'open':
            lifecycle_service.open_recording_session(
                'uid', 'session', 'conversation', firestore_client=contending_store
            )
        else:
            lifecycle_service.record_recording_session_event(
                'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
            )


def test_reconnect_after_a_contended_open_keeps_the_resume_contract(contending_store, shadow_mode, monkeypatch):
    """The resume controller's read of a contended open stays coherent."""
    _seed_session(contending_store, conversation_id='conversation')
    contending_store.read_errors = [Aborted('contention')] * 50
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'get_conversation',
        lambda *_, **__: {'id': 'conversation', 'status': 'in_progress'},
    )

    result = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    # The contended open degraded to the legacy envelope, but the resume
    # path still finds the existing canonical conversation and returns a
    # snapshot-carrying, non-rollover result the controller can proceed on.
    assert result['requires_rollover'] is False
    assert result['conversation_id'] == 'conversation'
    assert result['conversation_snapshot_known'] is True
    assert result['conversation_snapshot']['id'] == 'conversation'


def test_event_commit_side_expiry_recovers(contending_store):
    """The event writer's update phase is retryable too, not just its read."""
    _seed_session(contending_store)
    contending_store.read_errors = []
    contending_store.store_errors = [InvalidArgument(f'400 {_EXPIRED}')]

    event = _event(contending_store, 'completed')

    assert event['accepted'] is True
    assert event['lifecycle_phase'] == 'completed'
    assert (
        contending_store.documents[('users', 'uid', 'recording_sessions', 'session')]['lifecycle_phase'] == 'completed'
    )
