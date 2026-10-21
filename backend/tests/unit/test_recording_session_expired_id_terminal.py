"""A drained expired-transaction retirement must not read as a failed write.

Failure-Class: FC-retired-transaction-treated-as-fatal — boundary arm: the
write layer's ``run_transactional`` restart and the shared contention budget
already replay a retired transaction id on fresh transactions, but a burst
that outlives both budgets still reaches the lifecycle owner as a bare
``InvalidArgument 400 The referenced transaction has expired or is no longer
valid``. The owner's failed-write arm claimed it (``logger.exception`` + an
``omi_fallback_total`` degradation event) even though nothing was written and
the next renewal/open/event retries the durable write for free. Prod
backend-listen 2026-10-21: this terminal shape was the window's top signature
(``renew_live_recording_session_lease`` traceback ×70/30m, the
``open_recording_session`` sibling ×33/30m, every listen pod). This suite
pins the boundary half of the remediation: the transient classification all
three recording-session boundaries share, not just the replay inside the
write layer.

Guards:
- a drained expired-id commit keeps every boundary on the log-only transient
  arm — no failed-write ERROR, no degradation event — in the prod-default
  dual_write mode and in shadow;
- the drain writes nothing: no partial lease, no session document, no
  sequence advance — and the next clean call re-attempts the durable write;
- recovery inside the budgets stays silent; repeated drains stay bounded;
- enforce mode still raises every shape it raised before;
- a random ``InvalidArgument`` (no retirement marker) and a plain
  ``RuntimeError`` keep the failed-write classification, so the classifier is
  not over-broad;
- all three boundaries consult the one shared predicate, so the boundary and
  the write layer's restart budget can never drift apart.
"""

from __future__ import annotations

import copy
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database import recording_sessions
from database._client import is_expired_transaction_error
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from utils.conversations import lifecycle as lifecycle_service

_EXPIRED = 'The referenced transaction has expired or is no longer valid'
_SESSION_PATH = ('users', 'uid', 'recording_sessions', 'session')


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

    def document(self, document_id: str) -> '_DocumentRef':
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
    """Fake Firestore whose transactional body raises the queued store error.

    ``store_errors`` fires from the body's first read/write — where the real
    commit-side retirement surfaces — so every replay attempt of both retry
    layers consumes one until the queue drains and the error escapes. This is
    the exact shape the SDK cannot recover inside ``firestore.transactional``:
    the wrapped callable re-raises, the SDK's ``except`` only matches
    ``Aborted``, and the ``InvalidArgument`` retirement walks straight out.
    """

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[BaseException] = field(default_factory=list)
    store_errors: list[BaseException] = field(default_factory=list)
    commits: list[_Transaction] = field(default_factory=list)
    transactions: list[_Transaction] = field(default_factory=list)
    transaction_lock: threading.Lock = field(default_factory=threading.Lock)

    def collection(self, name: str) -> '_CollectionRef':
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


def _queue(store: _ContendingFirestore, errors: list[BaseException]) -> None:
    store.read_errors = []
    store.store_errors = list(errors)


def _drained_commit_side_expiry(store: _ContendingFirestore) -> None:
    """Queue enough retirement 400s to outlive both retry budgets."""
    _queue(store, [InvalidArgument(f'400 {_EXPIRED}')] * 50)


def _drained_read_side_expiry(store: _ContendingFirestore) -> None:
    """The same retirement on the streaming-read path: ``Aborted`` 409."""
    _queue(store, [Aborted(f'409 {_EXPIRED}')] * 50)


def _drained_sdk_replay_wrapper(store: _ContendingFirestore) -> None:
    """The SDK's own exhaustion envelope: ``ValueError`` chaining the abort."""
    replay = ValueError('Aborted after 5 attempts. Original exception: contention.')
    replay.__cause__ = Aborted('contention')
    _queue(store, [replay] * 50)


def _failed_write_logs(caplog, fragment: str) -> list:
    return [
        record
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle'
        and record.levelno >= logging.ERROR
        and fragment in record.getMessage()
    ]


def _transient_warnings(caplog, fragment: str) -> list:
    return [
        record
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle'
        and record.levelname == 'WARNING'
        and fragment in record.getMessage()
    ]


# ── A. Boundary transient arm: commit-side 400 retirement (the prod shape) ───


def test_renewal_boundary_absorbs_a_drained_expired_id_commit(contending_store, fallback_spy, caplog):
    """The prod ×70/30m family: retirement drain must stay a log-only transient."""
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert renewed is False
    assert fallback_spy == []
    assert _failed_write_logs(caplog, 'recording session lease renewal failed') == []
    assert _transient_warnings(caplog, 'lease renewal contended')


def test_open_boundary_absorbs_a_drained_expired_id_commit(contending_store, shadow_mode, caplog):
    """A drained open keeps the shadow legacy route without the failed-write log."""
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    with caplog.at_level('WARNING'):
        result = lifecycle_service.open_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert result['conversation_id'] == 'conversation'
    assert result['lifecycle_version'] is None
    assert _failed_write_logs(caplog, 'recording session persistence failed') == []
    assert _transient_warnings(caplog, 'recording session open contended')


def test_open_boundary_absorbs_drained_expiry_in_dual_write(contending_store, fallback_spy):
    """dual_write is the prod default; its open needs no shadow fixture to survive."""
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert result['lifecycle_phase'] is None
    assert fallback_spy == []


def test_event_boundary_absorbs_a_drained_expired_id_commit(contending_store, shadow_mode, caplog):
    """A drained event append keeps the shadow envelope without the failed-write log."""
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    with caplog.at_level('WARNING'):
        result = lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
        )

    assert result['conversation_id'] == 'conversation'
    assert result['lifecycle_phase'] is None
    assert _failed_write_logs(caplog, 'recording session event persistence failed') == []
    assert _transient_warnings(caplog, 'recording session event contended')


# ── B. Read-side 409 retirement drains keep the same transient arm ───────────


def test_renewal_boundary_absorbs_a_drained_read_side_retirement(contending_store, fallback_spy, caplog):
    _seed_session(contending_store)
    _drained_read_side_expiry(contending_store)

    renewed = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is False
    assert fallback_spy == []
    assert _failed_write_logs(caplog, 'recording session lease renewal failed') == []


def test_open_boundary_absorbs_a_drained_read_side_retirement(contending_store, shadow_mode, fallback_spy):
    _seed_session(contending_store)
    _drained_read_side_expiry(contending_store)

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert fallback_spy == []


def test_event_boundary_absorbs_a_drained_read_side_retirement(contending_store, shadow_mode, fallback_spy):
    _seed_session(contending_store)
    _drained_read_side_expiry(contending_store)

    result = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert fallback_spy == []


# ── C. The drain writes nothing and reports no canonical state it lacks ──────


def test_drained_renewal_writes_no_partial_lease(contending_store):
    started_at = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    _seed_session(contending_store, started_at=started_at)
    _drained_commit_side_expiry(contending_store)

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert contending_store.commits == []
    assert contending_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_drained_open_creates_no_session_document(contending_store, shadow_mode):
    _drained_commit_side_expiry(contending_store)

    lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=contending_store)

    assert _SESSION_PATH not in contending_store.documents


def test_drained_event_advances_no_sequence(contending_store, shadow_mode):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    result = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert contending_store.documents[_SESSION_PATH]['lifecycle_sequence'] == 0
    assert result['lifecycle_sequence'] is None


def test_drained_open_in_shadow_reports_the_proposed_route_not_the_canonical_one(contending_store, shadow_mode):
    _seed_session(contending_store, conversation_id='original')
    _drained_commit_side_expiry(contending_store)

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'second-conversation'
    assert result['lifecycle_version'] is None


def test_drained_event_envelope_carries_every_key_the_client_send_reads(contending_store, shadow_mode):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    result = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert set(result) >= {
        'recording_session_id',
        'conversation_id',
        'lifecycle_version',
        'lifecycle_phase',
        'lifecycle_sequence',
    }


# ── D. Transient warnings carry the session identity prod triage needs ───────


def test_renewal_warning_carries_session_identity(contending_store, caplog):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    with caplog.at_level('WARNING'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    warnings = _transient_warnings(caplog, 'lease renewal contended')
    assert warnings
    message = warnings[0].getMessage()
    assert 'uid=uid' in message and 'session=session' in message and 'conversation=conversation' in message


def test_open_warning_carries_session_identity(contending_store, shadow_mode, caplog):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    with caplog.at_level('WARNING'):
        lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=contending_store)

    warnings = _transient_warnings(caplog, 'recording session open contended')
    assert warnings
    message = warnings[0].getMessage()
    assert 'uid=uid' in message and 'session=session' in message


def test_event_warning_carries_the_phase(contending_store, shadow_mode, caplog):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    with caplog.at_level('WARNING'):
        lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
        )

    warnings = _transient_warnings(caplog, 'recording session event contended')
    assert warnings
    assert 'phase=completed' in warnings[0].getMessage()


# ── E. No degradation telemetry on the transient arm ─────────────────────────


def test_open_drain_records_no_fallback_event(contending_store, shadow_mode, fallback_spy):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=contending_store)

    assert fallback_spy == []


def test_event_drain_records_no_fallback_event(contending_store, shadow_mode, fallback_spy):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert fallback_spy == []


# ── F. Repeated drains stay bounded: degraded results, never exceptions ──────


def test_renewal_survives_back_to_back_drained_minutes(contending_store):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    for _ in range(3):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )
        assert renewed is False


def test_open_survives_back_to_back_drained_opens(contending_store, shadow_mode):
    _drained_commit_side_expiry(contending_store)

    for _ in range(3):
        result = lifecycle_service.open_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )
        assert result['conversation_id'] == 'conversation'
        assert result['lifecycle_version'] is None


def test_event_survives_back_to_back_drained_events(contending_store, shadow_mode):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    for _ in range(3):
        result = lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
        )
        assert result['lifecycle_sequence'] is None


def test_renewal_drain_returns_false_not_none(contending_store):
    """``False`` keeps the controller's renewal timestamp accounting honest."""
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    renewed = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is False


def test_renewal_drain_in_shadow_mode_returns_false(contending_store, shadow_mode):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    renewed = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is False


# ── G. Recovery: the next clean call re-attempts the durable write ───────────


def test_next_clean_renewal_after_a_drained_minute_commits_the_lease(contending_store):
    started_at = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    _seed_session(contending_store, started_at=started_at)
    _drained_commit_side_expiry(contending_store)

    first = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    _queue(contending_store, [])
    second = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert first is False
    assert second is True
    assert contending_store.documents[_SESSION_PATH]['lease_expires_at'] > (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_next_clean_open_after_a_drained_open_binds_durably(contending_store, shadow_mode):
    _drained_commit_side_expiry(contending_store)

    first = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    _queue(contending_store, [])
    second = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert first['lifecycle_version'] is None
    assert second['lifecycle_version'] == recording_sessions.LIFECYCLE_ENVELOPE_VERSION
    assert second['conversation_id'] == 'conversation'
    assert len(contending_store.commits) == 1


def test_next_clean_event_after_a_drained_event_appends_the_envelope(contending_store, shadow_mode):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    first = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )
    _queue(contending_store, [])
    second = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert first['lifecycle_sequence'] is None
    assert second['accepted'] is True
    assert second['lifecycle_sequence'] == 1


# ── H. Recovery inside the budgets stays silent at the boundary ──────────────


def test_renewal_commit_expiry_inside_the_budget_recovers_silently(contending_store, caplog):
    _seed_session(contending_store)
    _queue(contending_store, [InvalidArgument(f'400 {_EXPIRED}')])

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert renewed is True
    assert _transient_warnings(caplog, 'lease renewal contended') == []


def test_open_commit_expiry_inside_the_budget_recovers_silently(contending_store, shadow_mode, caplog):
    _queue(contending_store, [InvalidArgument(f'400 {_EXPIRED}')])

    with caplog.at_level('WARNING'):
        result = lifecycle_service.open_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert result['lifecycle_version'] == recording_sessions.LIFECYCLE_ENVELOPE_VERSION
    assert _transient_warnings(caplog, 'recording session open contended') == []


def test_event_commit_expiry_inside_the_budget_recovers_silently(contending_store, shadow_mode, caplog):
    _seed_session(contending_store)
    _queue(contending_store, [InvalidArgument(f'400 {_EXPIRED}')])

    with caplog.at_level('WARNING'):
        result = lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
        )

    assert result['accepted'] is True
    assert _transient_warnings(caplog, 'recording session event contended') == []


# ── I. Enforce mode fails closed for every shape ─────────────────────────────


def test_drained_expired_id_still_raises_in_enforce_mode(contending_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    with pytest.raises(InvalidArgument):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )


def test_drained_open_raises_in_enforce_mode(contending_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _drained_commit_side_expiry(contending_store)

    with pytest.raises(InvalidArgument):
        lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=contending_store)


def test_drained_event_raises_in_enforce_mode(contending_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    with pytest.raises(InvalidArgument):
        lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
        )


def test_contention_exhaustion_still_raises_in_enforce_mode(contending_store, monkeypatch):
    """The pre-existing enforce contract for contention must not regress."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(contending_store)
    _queue(contending_store, [Aborted('contention')] * 50)

    with pytest.raises(FirestoreContentionExhausted):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )


def test_enforce_random_400_still_raises(contending_store, monkeypatch):
    """Enforce has no fail-open arm: real failures reach the caller."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(contending_store)
    _queue(contending_store, [InvalidArgument('400 random bad request')] * 50)

    with pytest.raises(InvalidArgument):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )


# ── J. Real failures keep the failed-write classification ────────────────────


def test_random_400s_keep_the_failed_write_classification(contending_store, caplog):
    """Over-broadening the transient arm would hide real write failures."""
    _seed_session(contending_store)
    _queue(contending_store, [InvalidArgument('400 random bad request')] * 50)

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert renewed is False
    assert _failed_write_logs(caplog, 'recording session lease renewal failed')
    assert _transient_warnings(caplog, 'lease renewal contended') == []


def test_open_random_400_keeps_the_failed_write_classification(contending_store, shadow_mode, fallback_spy, caplog):
    _seed_session(contending_store)
    _queue(contending_store, [InvalidArgument('400 random bad request')] * 50)

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert len(fallback_spy) == 1
    assert _failed_write_logs(caplog, 'recording session persistence failed')
    assert _transient_warnings(caplog, 'recording session open contended') == []


def test_event_random_400_keeps_the_failed_write_classification(contending_store, shadow_mode, fallback_spy, caplog):
    _seed_session(contending_store)
    _queue(contending_store, [InvalidArgument('400 random bad request')] * 50)

    result = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert result['lifecycle_sequence'] is None
    assert len(fallback_spy) == 1
    assert _failed_write_logs(caplog, 'recording session event persistence failed')
    assert _transient_warnings(caplog, 'recording session event contended') == []


def test_open_real_runtime_error_keeps_the_failed_write_classification(contending_store, shadow_mode, fallback_spy):
    _seed_session(contending_store)
    _queue(contending_store, [RuntimeError('real write failure')] * 50)

    lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=contending_store)

    assert len(fallback_spy) == 1


def test_event_real_runtime_error_keeps_the_failed_write_classification(contending_store, shadow_mode, fallback_spy):
    _seed_session(contending_store)
    _queue(contending_store, [RuntimeError('real write failure')] * 50)

    lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert len(fallback_spy) == 1


def test_renewal_real_runtime_error_keeps_the_failed_write_classification(contending_store, caplog):
    _seed_session(contending_store)
    _queue(contending_store, [RuntimeError('real write failure')] * 50)

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert renewed is False
    assert _failed_write_logs(caplog, 'recording session lease renewal failed')


# ── K. The classifier itself: exactly the bounded transients ─────────────────


def test_transient_classifier_pins_the_retirement_boundary():
    """Exactly contention exhaustion, chained aborts, and the retirement 400."""

    class _SdkAbortWrapper(Aborted):
        def __init__(self) -> None:
            super().__init__('503 wrapped retry abort')

    wrapped = _SdkAbortWrapper()
    wrapped.__cause__ = Aborted('contention')

    assert lifecycle_service._is_recording_session_transient(
        FirestoreContentionExhausted('recording_session_lease_renewal')
    )
    assert lifecycle_service._is_recording_session_transient(Aborted('contention'))
    assert lifecycle_service._is_recording_session_transient(wrapped)
    assert lifecycle_service._is_recording_session_transient(InvalidArgument(f'400 {_EXPIRED}'))

    # A random 400 and every non-Firestore failure stay real failures.
    assert not lifecycle_service._is_recording_session_transient(InvalidArgument('400 bad request'))
    assert not lifecycle_service._is_recording_session_transient(RuntimeError('real write failure'))
    assert not lifecycle_service._is_recording_session_transient(ValueError('identity'))


def test_expired_classifier_is_the_write_layer_classifier():
    """The boundary and the restart budget must never drift apart."""

    assert is_expired_transaction_error(InvalidArgument(f'400 {_EXPIRED}'))
    assert is_expired_transaction_error(InvalidArgument('400 bad request')) is False


def test_classifier_treats_chained_sdk_aborts_as_transient():
    replay = ValueError('Aborted after 5 attempts. Original exception: contention.')
    replay.__cause__ = Aborted('contention')

    assert lifecycle_service._is_recording_session_transient(replay) is True


def test_classifier_treats_contention_exhaustion_as_transient():
    assert (
        lifecycle_service._is_recording_session_transient(
            FirestoreContentionExhausted('Firestore transaction contention exhausted for x')
        )
        is True
    )


def test_classifier_rejects_unrelated_400s():
    assert lifecycle_service._is_recording_session_transient(InvalidArgument('400 total garbage input')) is False


def test_classifier_rejects_plain_runtime_errors():
    assert lifecycle_service._is_recording_session_transient(RuntimeError('boom')) is False


def test_classifier_reads_the_409_read_side_variant():
    """The streaming-read retirement reports the same message as ``Aborted`` 409."""

    assert lifecycle_service._is_recording_session_transient(Aborted(f'409 {_EXPIRED}')) is True


def test_retirement_marker_matches_the_prod_error_text():
    """The write layer's marker is the exact substring prod's terminal 400 carries."""
    from database._client import _EXPIRED_TRANSACTION_MARKER

    assert _EXPIRED_TRANSACTION_MARKER == 'transaction has expired'
    assert _EXPIRED_TRANSACTION_MARKER in f'400 {_EXPIRED}'.lower()


def test_dual_write_is_the_default_mode(monkeypatch):
    """The prod rollout runs without RECORDING_SESSION_MODE; drains hit dual_write."""
    monkeypatch.delenv('RECORDING_SESSION_MODE', raising=False)

    assert lifecycle_service.recording_session_mode() == 'dual_write'


# ── L. All three boundaries consult the one shared predicate (anti-drift) ────


def test_renewal_uses_the_shared_transient_classifier(contending_store, monkeypatch, caplog):
    """Flipping the shared predicate must flip the renewal's classification."""
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)
    monkeypatch.setattr(lifecycle_service, '_is_recording_session_transient', lambda error: False)

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert renewed is False
    assert _failed_write_logs(caplog, 'recording session lease renewal failed')


def test_open_uses_the_shared_transient_classifier(contending_store, shadow_mode, monkeypatch, fallback_spy):
    _drained_commit_side_expiry(contending_store)
    monkeypatch.setattr(lifecycle_service, '_is_recording_session_transient', lambda error: False)

    lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=contending_store)

    assert len(fallback_spy) == 1


def test_event_uses_the_shared_transient_classifier(contending_store, shadow_mode, monkeypatch, fallback_spy):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)
    monkeypatch.setattr(lifecycle_service, '_is_recording_session_transient', lambda error: False)

    lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert len(fallback_spy) == 1


# ── M. The SDK's own exhaustion envelope is transient at every boundary ──────


def test_sdk_valueerror_replay_wrapper_is_transient_at_the_renewal_boundary(contending_store, fallback_spy):
    _seed_session(contending_store)
    _drained_sdk_replay_wrapper(contending_store)

    renewed = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert renewed is False
    assert fallback_spy == []


def test_sdk_valueerror_replay_wrapper_is_transient_at_the_open_boundary(contending_store, shadow_mode, fallback_spy):
    _drained_sdk_replay_wrapper(contending_store)

    result = lifecycle_service.open_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert fallback_spy == []


def test_sdk_valueerror_replay_wrapper_is_transient_at_the_event_boundary(contending_store, shadow_mode, fallback_spy):
    _seed_session(contending_store)
    _drained_sdk_replay_wrapper(contending_store)

    result = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )

    assert result['conversation_id'] == 'conversation'
    assert fallback_spy == []


# ── N. The chain boundary inherits the transient arm end to end ──────────────


def test_open_live_chain_survives_a_drained_expired_id_commit(contending_store, fallback_spy, caplog, monkeypatch):
    """``open_live_recording_session`` wraps the open: the drain must not leak.

    Its callers build the live rollover decision on the returned envelope, so a
    raised retirement would tear down the whole session setup instead of
    degrading one open.
    """
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'get_conversation',
        lambda *_, **__: {'id': 'conversation', 'status': 'in_progress'},
    )

    with caplog.at_level('WARNING'):
        result = lifecycle_service.open_live_recording_session(
            'uid', 'session', 'conversation', firestore_client=contending_store
        )

    assert result['conversation_id'] == 'conversation'
    assert fallback_spy == []
    assert _failed_write_logs(caplog, 'recording session persistence failed') == []


def test_open_live_chain_binds_durably_after_a_drained_open(contending_store, shadow_mode, monkeypatch):
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'get_conversation',
        lambda *_, **__: {'id': 'conversation', 'status': 'in_progress'},
    )

    first = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    _queue(contending_store, [])
    second = lifecycle_service.open_live_recording_session(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert first['lifecycle_version'] is None
    assert second['lifecycle_version'] == recording_sessions.LIFECYCLE_ENVELOPE_VERSION


# ── O. The drain must not corrupt real-write invariants ──────────────────────


def test_drained_renewal_keeps_the_lease_fence_intact_for_recovery(contending_store):
    """A terminal-phase session still refuses the next clean renewal."""
    started_at = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    _seed_session(contending_store, started_at=started_at)
    contending_store.documents[_SESSION_PATH]['lifecycle_phase'] = 'completed'
    _drained_commit_side_expiry(contending_store)

    drained = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )
    _queue(contending_store, [])
    clean = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=contending_store
    )

    assert drained is False
    assert clean is False
    assert contending_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_drained_open_still_honors_the_canonical_binding_on_the_next_clean_open(contending_store):
    """The drain must not let a clean open claim the proposed id over the canonical one."""
    _seed_session(contending_store, conversation_id='original')
    _drained_commit_side_expiry(contending_store)

    drained = lifecycle_service.open_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=contending_store
    )
    _queue(contending_store, [])
    clean = lifecycle_service.open_recording_session(
        'uid', 'session', 'second-conversation', firestore_client=contending_store
    )

    # dual_write's conflict routing intentionally keeps the client on its
    # proposed id until enforce cutover, but a clean open must still flag the
    # conflict and refuse to borrow the canonical ordered envelope — the drain
    # must not have made the session look cleanly bound.
    assert drained['conversation_id'] == 'second-conversation'
    assert clean['mapping_conflict'] is True
    assert clean['lifecycle_version'] is None
    assert clean['lifecycle_phase'] is None


def test_drained_event_still_keeps_the_sequence_monotonic_on_the_next_clean_event(contending_store, shadow_mode):
    """The drain must not reset the counter the next real append reads."""
    _seed_session(contending_store)
    _drained_commit_side_expiry(contending_store)

    drained = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'completed', firestore_client=contending_store
    )
    _queue(contending_store, [])
    processing = lifecycle_service.record_recording_session_event(
        'uid', 'session', 'conversation', 'processing', firestore_client=contending_store
    )

    assert drained['lifecycle_sequence'] is None
    assert processing['accepted'] is True
    assert processing['lifecycle_phase'] == 'processing'
    # The clean append advances the DURABLE sequence by exactly one from the
    # pre-drain value: the drain wrote nothing between them.
    assert processing['lifecycle_sequence'] == 1
    assert contending_store.documents[_SESSION_PATH]['lifecycle_sequence'] == 1
