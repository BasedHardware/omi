"""A live recording's recovery fence must survive Firestore contention bursts.

Failure-Class: FC-renewal-lease-write-aborted-as-failed-write
(new class declared in this diff; the nearest existing classes cover the
neighbouring shapes — FC-sync-assignment-read-abort-escapes-retry is scoped to
sync intake's assignment transaction, and FC-retired-transaction-treated-as-fatal
covers the expired-id commit via ``run_transactional`` — not the live fence,
whose renewal used to run bare and classify a retried contention burst as the
failed write its fail-open branch exists for.)

Guards:
- ``renew_recording_session_lease`` replays a read-time ``Aborted`` on a fresh
  transaction and commits once;
- an expired-transaction rejection restarts instead of surfacing;
- after the bounded budget exhausts, the lifecycle owner reports False with a
  log-only contended outcome — no ``recording session lease renewal failed``
  exception log, no ``omi_fallback_total`` degradation event — while a real
  failure still takes the fail-open branch;
- enforce mode still raises, and non-contention errors keep the failed-write
  classification;
- concurrent renewals converge on one durable lease.
"""

from __future__ import annotations

import concurrent.futures
import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database import recording_sessions
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    _INITIAL_MAX_DELAY_SECONDS,
    _MAX_DELAY_SECONDS,
    is_transaction_contention,
    run_with_transaction_contention_retry,
)
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
        if document.path in self.firestore.documents:
            raise RuntimeError('already exists')
        self.firestore.documents[document.path] = copy.deepcopy(data)

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.firestore.documents[document.path].update(copy.deepcopy(updates))


@dataclass
class _ContendingFirestore:
    """Fake Firestore whose transactional reads abort until the queue is empty.

    Mirrors the production boundary the SDK cannot model in a unit fake: the
    abort fires from the decorated body's read, before any write — exactly the
    retry hole ``run_with_transaction_contention_retry`` exists to fill.
    """

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[BaseException] = field(default_factory=list)
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


def test_renewal_runs_on_the_named_shared_budget(contending_store):
    """Correlation key: prod log lines must name the renewal, not a generic op."""
    _seed_session(contending_store)

    recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert contending_store.budget_calls[0]['operation_name'] == 'recording_session_lease_renewal'


def test_renewal_replays_read_abort_on_fresh_transactions_and_commits_once(contending_store):
    _seed_session(contending_store)
    session_path = ('users', 'uid', 'recording_sessions', 'session')
    before = contending_store.documents[session_path]['lease_expires_at']

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is True
    # Two read aborts replayed on two fresh transactions; the third attempt
    # read clean and committed exactly once.
    assert len(contending_store.commits) == 1
    assert contending_store.documents[session_path]['lease_expires_at'] > before


def test_renewal_restarts_on_expired_transaction_id(contending_store):
    _seed_session(contending_store)
    contending_store.read_errors = [InvalidArgument('The referenced transaction has expired or is no longer valid')]
    session_path = ('users', 'uid', 'recording_sessions', 'session')
    before = contending_store.documents[session_path]['lease_expires_at']

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is True
    assert contending_store.documents[session_path]['lease_expires_at'] > before


def test_exhausted_contention_reports_contended_not_failed_write(contending_store, monkeypatch):
    _seed_session(contending_store)
    # Every attempt of the bounded budget aborts; the exhaustion raises
    # FirestoreContentionExhausted, which the owner must classify as transient.
    contending_store.read_errors = [Aborted('contention')] * 50

    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    renewed = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is False
    assert fallbacks == []


def test_exhausted_contention_is_log_only_without_failed_write_log(contending_store, caplog):
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')] * 50

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert renewed is False
    # The retry budget's own exhaustion ERROR is expected telemetry; what must
    # be gone is the lifecycle owner's failed-write exception log.
    failed_write_logs = [
        record
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle'
        and record.levelname == 'ERROR'
        and 'recording session lease renewal failed' in record.getMessage()
    ]
    assert failed_write_logs == []
    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert any('lease renewal contended' in record.getMessage() for record in warnings)


def test_exhausted_contention_raises_in_enforce_mode(contending_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(contending_store)
    contending_store.read_errors = [Aborted('contention')] * 50

    with pytest.raises(FirestoreContentionExhausted):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )


def test_non_contention_failure_keeps_the_failed_write_classification(contending_store, caplog):
    _seed_session(contending_store)
    contending_store.read_errors = [RuntimeError('real write failure')] * 50

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert renewed is False
    error_records = [record for record in caplog.records if record.levelname == 'ERROR']
    assert any('recording session lease renewal failed' in record.getMessage() for record in error_records)
    assert not any(
        'lease renewal contended' in record.getMessage() for record in caplog.records if record.levelname == 'WARNING'
    )


def test_concurrent_renewals_converge_on_one_durable_lease(contending_store):
    _seed_session(contending_store)
    session_path = ('users', 'uid', 'recording_sessions', 'session')
    before = contending_store.documents[session_path]['lease_expires_at']

    def renew(_index: int) -> bool:
        return recording_sessions.renew_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(renew, range(3)))

    assert outcomes == [True, True, True]
    assert contending_store.documents[session_path]['lease_expires_at'] > before


def test_lease_advances_by_the_full_duration_after_contention(contending_store, monkeypatch):
    started_at = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(contending_store, started_at=started_at)
    contending_store.read_errors = [Aborted('contention')]
    session_path = ('users', 'uid', 'recording_sessions', 'session')

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is True
    renewed_until = contending_store.documents[session_path]['lease_expires_at']
    assert renewed_until == started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION


def test_identity_mismatch_still_refuses_the_renewal(contending_store):
    _seed_session(contending_store)

    mismatched = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'other-conversation', firestore_client=contending_store
    )

    assert mismatched is False


def test_budget_delays_are_jittered_and_bounded(monkeypatch):
    delays: list[float] = []

    def aborting_operation(_transaction: Any) -> None:
        aborting_operation.calls += 1
        if aborting_operation.calls < 5:
            raise Aborted('contention')

    aborting_operation.calls = 0

    run_with_transaction_contention_retry(
        lambda: object(),
        aborting_operation,
        operation_name='probe',
        random_value=lambda: 0.5,
        sleep=delays.append,
    )

    assert len(delays) == 4
    assert delays[0] == pytest.approx(_INITIAL_MAX_DELAY_SECONDS * 0.75)
    assert all(0 < delay <= _MAX_DELAY_SECONDS for delay in delays)


def test_contention_classification_matches_the_budget():
    assert is_transaction_contention(Aborted('contention')) is True
    wrapped = FirestoreContentionExhausted('exhausted')
    wrapped.__cause__ = Aborted('contention')
    assert is_transaction_contention(wrapped) is True
    assert is_transaction_contention(RuntimeError('unrelated')) is False
    assert is_transaction_contention(InvalidArgument('bad request')) is False


# ── Renewal cadence under contention ─────────────────────────────────────────
#
# note_audio_activity re-arms the renewal only once per minute of audio
# activity. Every contended minute that failed to move lease_expires_at used
# to be a minute of fence decay with no retry until the next minute boundary;
# the bounded budget turns a burst into at most one lost minute, and a burst
# that exhausts in the interval's last moments must still leave the failure
# classified as transient, not as a dead write.


def test_exhaustion_inside_the_renew_interval_keeps_transient_classification(contending_store, monkeypatch, caplog):
    """A burst during the throttle window cannot misclassify as failed write."""
    started_at = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(contending_store, started_at=started_at)
    contending_store.read_errors = [Aborted('contention')] * 50

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert renewed is False
    failed = [
        record
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle' and record.levelname == 'ERROR'
    ]
    assert failed == []


def test_contended_minute_is_recoverable_by_the_next_clean_renewal(contending_store, monkeypatch):
    """One fully contended minute costs at most that minute, not the fence."""
    started_at = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(contending_store, started_at=started_at)
    session_path = ('users', 'uid', 'recording_sessions', 'session')
    contending_store.read_errors = [Aborted('contention')] * 50

    contended = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    # The next minute arrives with a clean Firestore.
    next_minute = started_at + timedelta(minutes=1)
    monkeypatch.setattr(recording_sessions, '_now', lambda: next_minute)
    contending_store.read_errors = []
    recovered = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert contended is False
    assert recovered is True
    assert (
        contending_store.documents[session_path]['lease_expires_at']
        == next_minute + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_success_still_reports_true_for_controller_accounting(contending_store):
    """The controller gates nothing on the bool, but False must mean 'not renewed'."""
    started_at = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    _seed_session(contending_store, started_at=started_at)

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is True


def test_missing_session_reports_not_renewed_without_writing(contending_store):
    """A session another flow already tombstoned is a clean no-op, not an error."""
    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'ghost', 'conversation', firestore_client=contending_store
    )

    assert renewed is False
    # Nothing may resurrect the session: the transaction read a missing row and
    # wrote nothing (an empty commit at most).
    assert ('users', 'uid', 'recording_sessions', 'ghost') not in contending_store.documents


# ── Shared-budget regression guards ──────────────────────────────────────────
#
# The renewal now shares the same bounded budget and classification helper the
# rest of database/ uses. These pins stop the two layers from drifting: the
# budget must keep replaying *fresh* transactions (a replayed id is already
# retired), never sleep on the first attempt's path, and keep its exhaustion
# wrapped so callers can classify without SDK-type matching.


def test_budget_builds_a_fresh_transaction_per_attempt(monkeypatch):
    transactions: list[int] = []

    def factory() -> object:
        transactions.append(len(transactions))
        return object()

    calls = {'n': 0}

    def aborting_operation(_transaction: object) -> None:
        calls['n'] += 1
        if calls['n'] < 3:
            raise Aborted('contention')

    run_with_transaction_contention_retry(
        factory,
        aborting_operation,
        operation_name='probe',
        sleep=lambda _delay: None,
        random_value=lambda: 0,
    )

    # Two aborted attempts + one committing attempt, each on its own
    # transaction object — never a replayed id.
    assert len(transactions) == 3


def test_budget_never_sleeps_after_the_final_aborted_attempt(monkeypatch):
    delays: list[float] = []

    calls = {'n': 0}

    def aborting_operation(_transaction: object) -> None:
        calls['n'] += 1
        raise Aborted('contention')

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            aborting_operation,
            operation_name='probe',
            max_attempts=3,
            sleep=delays.append,
            random_value=lambda: 0,
        )

    assert len(delays) == 2


def test_budget_rejects_a_non_positive_attempt_budget():
    with pytest.raises(ValueError):
        run_with_transaction_contention_retry(
            lambda: object(),
            lambda _transaction: None,
            operation_name='probe',
            max_attempts=0,
            sleep=lambda _delay: None,
            random_value=lambda: 0,
        )


def test_exhaustion_is_wrapped_for_caller_classification():
    """The budget's exhausted error chains the last Aborted as __cause__."""
    calls = {'n': 0}

    def aborting_operation(_transaction: object) -> None:
        calls['n'] += 1
        raise Aborted('contention')

    with pytest.raises(FirestoreContentionExhausted) as excinfo:
        run_with_transaction_contention_retry(
            lambda: object(),
            aborting_operation,
            operation_name='probe',
            max_attempts=2,
            sleep=lambda _delay: None,
            random_value=lambda: 0,
        )

    assert isinstance(excinfo.value.__cause__, Aborted)
    assert is_transaction_contention(excinfo.value) is True


# ── Fence isolation contracts ────────────────────────────────────────────────
#
# The lease is a per-(uid, session, conversation) fence. Contention handling
# must not widen what a renewal touches: another user's identically-named
# session, a terminal phase, and SDK retirement wrapped by provider errors are
# all distinct contracts the renewal has to keep separate.


def test_same_session_id_across_users_renews_only_its_own_row(contending_store):
    _seed_session(contending_store, uid='user-one')
    _seed_session(contending_store, uid='user-two')

    renewed = recording_sessions.renew_recording_session_lease(
        'user-one', 'session', 'conversation', firestore_client=contending_store
    )

    one_path = ('users', 'user-one', 'recording_sessions', 'session')
    two_path = ('users', 'user-two', 'recording_sessions', 'session')
    assert renewed is True
    assert (
        contending_store.documents[one_path]['lease_expires_at']
        > contending_store.documents[two_path]['lease_expires_at']
    )


def test_terminal_phase_refuses_the_renewal_without_writing(contending_store, monkeypatch):
    """A finished session is a durable refusal, not a retryable contention."""
    started_at = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(contending_store, started_at=started_at)
    session_path = ('users', 'uid', 'recording_sessions', 'session')
    contending_store.documents[session_path]['lifecycle_phase'] = 'completed'
    contending_store.read_errors = []

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is False
    # The read itself is the fence: the phase moved on and the lease must not.
    assert contending_store.documents[session_path]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_expiry_retry_composes_with_contention_retry(contending_store, monkeypatch):
    """Real bursts mix both: an expired id inside the contention budget."""
    started_at = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(contending_store, started_at=started_at)
    contending_store.read_errors = [
        Aborted('contention'),
        InvalidArgument('The referenced transaction has expired or is no longer valid'),
    ]
    session_path = ('users', 'uid', 'recording_sessions', 'session')

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is True
    assert (
        contending_store.documents[session_path]['lease_expires_at']
        == started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_sdk_abort_wrapping_a_provider_error_is_still_contention():
    """SDK wrappers chain the original error; the classifier must follow __cause__."""

    class _SdkAbortWrapper(Aborted):
        def __init__(self) -> None:
            super().__init__('503 wrapped retry abort')

    wrapped = _SdkAbortWrapper()
    wrapped.__cause__ = Aborted('contention')
    assert is_transaction_contention(wrapped) is True
    assert is_transaction_contention(ValueError('unrelated chain')) is False
