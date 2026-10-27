"""A data-plane availability blip on the recording-session surface is the bounded transient, not a failed write.

Failure-Class: FC-availability-blip-logged-as-failed-recording-session-write —
the recording-session lifecycle boundaries classified only contention and
retired-transaction-id shapes as bounded transients. The Firestore write layer's
budgets deliberately pass an unrelated provider failure through untouched, so a
momentary 503 ``ServiceUnavailable`` / 504 ``DeadlineExceeded`` / 500
``InternalServerError`` on the lease renewal — the write a live recording issues
every single minute, on the same session document every lifecycle event and the
recovery sweep also touch — surfaced as a full ``recording session lease
renewal failed`` traceback plus an ``omi_fallback_total`` degradation event
(prod backend-listen 2026-10-22: the renewal boundary ×32/30m, after the
contention and retired-id drains; the open, event and cleanup boundaries share
the classifier). Nothing is written by a blipped attempt and the session's own
cadence re-attempts the write — the next minute's renewal, the next reconnect's
open, the next lifecycle callback — so the availability set
``conversation_scan`` and ``mcp_auth_read`` already retry is the bounded
transient here too: a WARNING without a stack trace, no degradation event.
The live-open boundary additionally probes the session document with a plain
read outside every budget; a blip on that probe defers to the transactional
open instead of escaping the boundary uncaught.

Guards:
- every availability class on every writer keeps the log-only transient arm:
  WARNING naming the session, no failed-write ERROR, no stack trace, no
  ``omi_fallback_total`` degradation event, nothing committed;
- the fence does not wedge: the next renewal after each blip commits and
  advances the lease by the full duration; back-to-back blips stay bounded;
- a blip after a drained contention burst is still the transient arm, and the
  contention/expired-id shapes still shed through the same classifier (the
  extension must not shadow the shapes it joined);
- commit-side blips are absorbed exactly like read-side ones;
- ``PermissionDenied``, the 1 MiB document-size ``InvalidArgument``,
  ``FailedPrecondition``, unknown failures and bare ``TimeoutError`` keep the
  failed-write classification (traceback + degradation event), and task
  cancellation is never absorbed;
- enforce mode still raises through every blip;
- the open boundary's probe read degrades to "no existing binding" on a blip
  and the transactional open stays the authority on existence;
- the cleanup boundary's arm stays mode-independent, matching its contract.
"""

from __future__ import annotations

import asyncio
import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    FailedPrecondition,
    InternalServerError,
    InvalidArgument,
    PermissionDenied,
    ServiceUnavailable,
)

from database import recording_sessions
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from utils.conversations import lifecycle as lifecycle_service

_SESSION_PATH = ('users', 'uid', 'recording_sessions', 'session')
_BLIPS = (
    ServiceUnavailable('503: backend unavailable'),
    DeadlineExceeded('504: deadline exceeded'),
    InternalServerError('500: internal error'),
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
    firestore: '_BlipFirestore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        if self.firestore.read_errors:
            raise self.firestore.read_errors.pop(0)
        return _Snapshot(self.firestore.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.firestore, self.path + (name,))


@dataclass
class _CollectionRef:
    firestore: '_BlipFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.firestore, self.path + (document_id,))


@dataclass
class _Transaction:
    firestore: '_BlipFirestore'

    def create(self, document: _DocumentRef, data: dict[str, Any]) -> None:
        if document.path in self.firestore.documents:
            raise RuntimeError('already exists')
        self.firestore.documents[document.path] = copy.deepcopy(data)

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        if self.firestore.write_errors:
            raise self.firestore.write_errors.pop(0)
        self.firestore.documents[document.path].update(copy.deepcopy(updates))


@dataclass
class _BlipFirestore:
    """Fake Firestore whose first reads/writes raise the injected blips.

    The error fires from inside the transactional body — after the write
    layer's budgets have nothing to replay it with (they only replay
    ``Aborted``), which is exactly how a real 503/504/500 reaches the
    lifecycle owner.
    """

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[BaseException] = field(default_factory=list)
    write_errors: list[BaseException] = field(default_factory=list)
    commits: list[_Transaction] = field(default_factory=list)
    transaction_lock: threading.Lock = field(default_factory=threading.Lock)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        return _Transaction(self)


def _seed_session(
    store: _BlipFirestore,
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
def blipping_store(monkeypatch):
    store = _BlipFirestore()

    def transactional(func):
        def locked(transaction, *args, **kwargs):
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


# ---------------------------------------------------------------------------
# Renewal: the write a live recording issues every minute.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_availability_blip_is_log_only(blipping_store, caplog, blip):
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert any('lease renewal contended' in record.getMessage() for record in warnings)
    assert not any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_availability_blip_carries_no_stack_trace(blipping_store, caplog, blip):
    """A blip is telemetry-shaped, not a traceback: exc_info must stay unset."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    with caplog.at_level('WARNING'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert warnings and all(record.exc_info is None for record in warnings)


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_availability_blip_records_no_degradation_event(blipping_store, monkeypatch, blip):
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )

    assert fallbacks == []


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_availability_blip_commits_nothing(blipping_store, blip):
    """A blipped attempt must leave the stored lease unchanged."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]
    before = blipping_store.documents[_SESSION_PATH]['lease_expires_at']

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )

    assert blipping_store.commits == []
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] == before


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_succeeds_on_the_next_minute_after_a_blip(blipping_store, blip):
    """The blip must not wedge the fence: the next renewal commits."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    first = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )
    assert first is False
    # Deplete the fence to a minute of runway so the clean renewal after the
    # blip has a real stamp to land (the runway skip leaves a still-healthy
    # fence untouched by design).
    blipping_store.documents[_SESSION_PATH]['lease_expires_at'] = blipping_store.documents[_SESSION_PATH][
        'lease_expires_at'
    ] - timedelta(minutes=4)
    before = blipping_store.documents[_SESSION_PATH]['lease_expires_at']

    second = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )
    assert second is True
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] > before


def test_renewal_after_blip_advances_the_lease_by_the_full_duration(blipping_store, monkeypatch):
    started_at = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(blipping_store, started_at=started_at)
    blipping_store.read_errors = [ServiceUnavailable('503: backend unavailable')]

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )
    renewed = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )

    assert renewed is True
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_renewal_absorbs_back_to_back_blips_bounded(blipping_store, caplog):
    """Two blipped windows in a row stay two warnings — not two tracebacks."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [
        ServiceUnavailable('503: backend unavailable'),
        DeadlineExceeded('504: deadline exceeded'),
    ]

    with caplog.at_level('WARNING'):
        first = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )
        second = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert first is False and second is False
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_blip_after_a_drained_contention_burst_is_still_transient(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [Aborted('contention')] * 50 + [ServiceUnavailable('503: backend unavailable')]

    with caplog.at_level('WARNING'):
        contention = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )
        blip = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert contention is False and blip is False
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_commit_side_blip_is_also_absorbed(blipping_store, caplog):
    """The 503 usually hits the commit, not the read — same transient arm."""
    _seed_session(blipping_store)
    blipping_store.write_errors = [ServiceUnavailable('503: backend unavailable')]
    # A fence at the floor keeps this a real write attempt (the runway skip
    # leaves a still-healthy fence untouched by design).
    blipping_store.documents[_SESSION_PATH]['lease_expires_at'] = blipping_store.documents[_SESSION_PATH][
        'lease_expires_at'
    ] - timedelta(minutes=4)

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert blipping_store.commits == []
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_blip_warning_names_the_session(blipping_store, caplog):
    """The contended WARNING keeps uid/session/conversation attribution."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [ServiceUnavailable('503: backend unavailable')]

    with caplog.at_level('WARNING'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    warning = next(record for record in caplog.records if record.levelname == 'WARNING')
    message = warning.getMessage()
    assert 'uid=uid' in message and 'session=session' in message and 'conversation=conversation' in message


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_availability_blip_still_raises_in_enforce_mode(blipping_store, monkeypatch, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    with pytest.raises(type(blip)):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )


# ---------------------------------------------------------------------------
# Renewal: the arm must stay narrow — permanent and unknown failures keep
# the failed-write classification.
# ---------------------------------------------------------------------------


def test_renewal_permission_denied_keeps_failed_write(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [PermissionDenied('permission denied on row')] * 50

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


def test_renewal_document_size_invalid_argument_keeps_failed_write(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [InvalidArgument('exceeds the maximum allowed size')] * 50

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


def test_renewal_failed_precondition_keeps_failed_write(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [FailedPrecondition('the request must be modified')] * 50

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


def test_renewal_bare_timeout_error_keeps_failed_write(blipping_store, caplog):
    """A host-side ``TimeoutError`` is not the data plane's 504 — keep it loud."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [TimeoutError('client-side deadline')] * 50

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


def test_renewal_task_cancellation_is_never_absorbed(blipping_store):
    """``except Exception`` must not swallow ``CancelledError``."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [asyncio.CancelledError()]

    with pytest.raises(asyncio.CancelledError):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )


def test_renewal_expired_id_still_sheds_through_the_shared_classifier(blipping_store, caplog):
    """Regression: the availability extension must not shadow the retired-id arm."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [InvalidArgument('The referenced transaction has expired or is no longer valid')] * 50

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert any(
        'lease renewal contended' in record.getMessage() for record in caplog.records if record.levelname == 'WARNING'
    )
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_contention_exhaustion_still_sheds_through_the_shared_classifier(blipping_store, caplog):
    """Regression: the availability extension must not shadow the contention arm."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [Aborted('contention')] * 50

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert any(
        'lease renewal contended' in record.getMessage() for record in caplog.records if record.levelname == 'WARNING'
    )


# ---------------------------------------------------------------------------
# Open boundary: the transactional open's blip sheds to the shadow legacy
# envelope; the plain probe read defers to the transactional open.
# ---------------------------------------------------------------------------


def _patch_open_probe(monkeypatch, probe_error: BaseException | None = None, probe_result: Any = None) -> None:
    def get_recording_session(uid, recording_session_id, *, firestore_client=None):
        del uid, recording_session_id, firestore_client
        if probe_error is not None:
            raise probe_error
        return probe_result

    monkeypatch.setattr(recording_sessions, 'get_recording_session', get_recording_session)


def _patch_transactional_open(
    monkeypatch, error: BaseException | None = None, result: dict[str, Any] | None = None
) -> None:
    """Patch the store seam under lifecycle.open_recording_session's transient arm."""

    def create_or_get_recording_session(
        uid, recording_session_id, proposed_conversation_id, *, firestore_client=None, **kwargs
    ):
        del uid, recording_session_id, proposed_conversation_id, firestore_client, kwargs
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(recording_sessions, 'create_or_get_recording_session', create_or_get_recording_session)


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_open_transactional_blip_sheds_to_shadow_legacy_envelope(monkeypatch, caplog, blip):
    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_transactional_open(monkeypatch, error=type(blip)(str(blip)))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['recording_session_id'] == 'session'
    assert binding['lifecycle_version'] is None
    assert binding['lifecycle_phase'] is None
    assert binding['lifecycle_sequence'] is None
    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert any('open contended' in record.getMessage() for record in warnings)


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_open_transactional_blip_records_no_degradation_event(monkeypatch, blip):
    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_transactional_open(monkeypatch, error=type(blip)(str(blip)))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert fallbacks == []


def test_open_permission_denied_keeps_failed_write(monkeypatch, caplog):
    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_transactional_open(monkeypatch, error=PermissionDenied('permission denied on row'))

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert any(
        record.levelname == 'ERROR' and 'recording session persistence failed' in record.getMessage()
        for record in caplog.records
    )


def test_open_expired_id_still_sheds_through_the_shared_classifier(monkeypatch, caplog):
    """Regression: the retired-id arm the availability extension joined still works."""
    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_transactional_open(
        monkeypatch, error=InvalidArgument('The referenced transaction has expired or is no longer valid')
    )

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['lifecycle_version'] is None
    assert any('open contended' in record.getMessage() for record in caplog.records if record.levelname == 'WARNING')


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_open_probe_blip_defers_to_the_transactional_open(monkeypatch, caplog, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=type(blip)(str(blip)))
    _patch_transactional_open(
        monkeypatch,
        result={
            'recording_session_id': 'session',
            'conversation_id': 'conversation',
            'lifecycle_version': 1,
            'mapping_conflict': False,
        },
    )

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    # The transactional open (the authority on existence) decided the result.
    assert binding['requires_rollover'] is False
    assert binding['recording_session_id'] == 'session'
    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert any('open probe contended' in record.getMessage() for record in warnings)


def test_open_probe_blip_warning_names_the_proposed_id(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=ServiceUnavailable('503: backend unavailable'))
    _patch_transactional_open(
        monkeypatch,
        result={
            'recording_session_id': 'session',
            'conversation_id': 'conversation',
            'lifecycle_version': 1,
            'mapping_conflict': False,
        },
    )

    with caplog.at_level('WARNING'):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    warning = next(record for record in caplog.records if 'open probe contended' in record.getMessage())
    assert 'proposed=conversation' in warning.getMessage()


def test_open_probe_permanent_failure_still_raises(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=PermissionDenied('permission denied on row'))

    with pytest.raises(PermissionDenied):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')


def test_open_probe_unknown_failure_still_raises(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=RuntimeError('client bug'))

    with pytest.raises(RuntimeError):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')


def test_open_probe_blip_still_raises_in_enforce_mode(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_open_probe(monkeypatch, probe_error=ServiceUnavailable('503: backend unavailable'))

    with pytest.raises(ServiceUnavailable):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')


def test_open_probe_blip_then_next_open_fully_succeeds(monkeypatch):
    """The degraded probe must not poison the next (clean) open."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    calls = {'probe': 0}

    def get_recording_session(uid, recording_session_id, *, firestore_client=None):
        calls['probe'] += 1
        if calls['probe'] == 1:
            raise ServiceUnavailable('503: backend unavailable')
        return None

    monkeypatch.setattr(recording_sessions, 'get_recording_session', get_recording_session)
    _patch_transactional_open(
        monkeypatch,
        result={
            'recording_session_id': 'session',
            'conversation_id': 'conversation',
            'lifecycle_version': 1,
            'mapping_conflict': False,
        },
    )

    first = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')
    second = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert first['requires_rollover'] is False
    assert second['requires_rollover'] is False
    assert calls['probe'] == 2


# ---------------------------------------------------------------------------
# Event boundary: every lifecycle callback re-attempts the durable append.
# ---------------------------------------------------------------------------


def _patch_event_writer(monkeypatch, error: BaseException | None = None, result: dict[str, Any] | None = None) -> None:
    def record_lifecycle_event(*args, **kwargs):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(recording_sessions, 'record_lifecycle_event', record_lifecycle_event)


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_event_blip_sheds_to_legacy_envelope(monkeypatch, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=type(blip)(str(blip)))

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    assert envelope['recording_session_id'] == 'session'
    assert envelope['lifecycle_version'] is None
    assert envelope['lifecycle_sequence'] is None


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_event_blip_records_no_degradation_event(monkeypatch, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=type(blip)(str(blip)))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    assert fallbacks == []


def test_event_permission_denied_keeps_failed_write(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=PermissionDenied('permission denied on row'))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    assert any(f.get('to_mode') == 'legacy_pointer' for f in fallbacks)
    assert any(
        record.levelname == 'ERROR' and 'recording session event persistence failed' in record.getMessage()
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle'
    )


def test_event_blip_still_raises_in_enforce(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_event_writer(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    with pytest.raises(ServiceUnavailable):
        lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')


def test_event_accepted_event_still_returns_the_durable_envelope(monkeypatch):
    """No blip: the durable envelope rides through unchanged."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(
        monkeypatch,
        result={'accepted': True, 'recording_session_id': 'session', 'conversation_id': 'conversation'},
    )

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    assert envelope['accepted'] is True


def test_event_rejected_event_still_keeps_its_own_degradation_path(monkeypatch):
    """The availability arm must not absorb the store's deliberate rejection."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(
        monkeypatch,
        result={'accepted': False, 'discard_reason': 'stale_sequence', 'recording_session_id': 'session'},
    )
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    assert envelope['lifecycle_version'] is None
    assert any(f.get('to_mode') == 'event_discarded' for f in fallbacks)


# ---------------------------------------------------------------------------
# Cleanup boundary: mode-independent by contract (a delayed delete is free).
# ---------------------------------------------------------------------------


def _patch_cleaner(monkeypatch, error: BaseException | None = None, result: bool = False) -> None:
    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )


@pytest.fixture
def cleanup_seams(monkeypatch) -> list[str]:
    """Hold the physical-cleanup boundaries a successful delete fans out to."""
    from utils.conversations import typesense_index

    touched: list[str] = []
    monkeypatch.setattr(typesense_index, 'delete_conversation_index_doc', lambda *a, **k: touched.append('index'))
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'delete_conversation_photos',
        lambda *a, **k: touched.append('photos'),
    )
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: touched.append('audio'),
        raising=False,
    )
    return touched


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_delete_blip_keeps_the_empty_generation_log_only(monkeypatch, caplog, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=type(blip)(str(blip)))

    with caplog.at_level('WARNING'):
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False
    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert any('cleanup contended' in record.getMessage() for record in warnings)
    assert not any(record.levelname == 'ERROR' and 'cleanup failed' in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_delete_blip_records_no_degradation_event(monkeypatch, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=type(blip)(str(blip)))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert fallbacks == []


def test_delete_permission_denied_keeps_failed_write(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=PermissionDenied('permission denied on row'))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False
    assert any(f.get('to_mode') == 'legacy_pointer' for f in fallbacks)
    assert any(
        record.levelname == 'ERROR' and 'recording session cleanup failed' in record.getMessage()
        for record in caplog.records
    )


def test_delete_blip_is_mode_independent(monkeypatch):
    """Cleanup fail-open only ever delays a delete of an empty row."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_cleaner(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False


def test_delete_success_still_deletes(monkeypatch, cleanup_seams):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, result=True)

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is True


# ---------------------------------------------------------------------------
# Cross-boundary: one classifier, every writer.
# ---------------------------------------------------------------------------


def test_all_four_boundaries_shed_the_same_503(monkeypatch, blipping_store, caplog):
    """The renewal, open, event and cleanup arms classify 503 identically."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    blip = ServiceUnavailable('503: backend unavailable')

    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    def create_or_get_recording_session(*args, **kwargs):
        raise type(blip)(str(blip))

    def record_lifecycle_event(*args, **kwargs):
        raise type(blip)(str(blip))

    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        raise type(blip)(str(blip))

    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(recording_sessions, 'create_or_get_recording_session', create_or_get_recording_session)
    monkeypatch.setattr(recording_sessions, 'record_lifecycle_event', record_lifecycle_event)
    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )
        opened = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')
        event = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert renewed is False
    assert opened['lifecycle_version'] is None
    assert event['lifecycle_version'] is None
    assert deleted is False
    assert fallbacks == []
    assert not any(
        record.levelname == 'ERROR' and record.name == 'utils.conversations.lifecycle' for record in caplog.records
    )


# ---------------------------------------------------------------------------
# Classifier contract: membership, cause chains, and shape independence.
# ---------------------------------------------------------------------------


def test_classifier_direct_membership():
    """The availability classifier recognizes exactly the redial-able trio."""
    from database._client import is_transient_availability_error

    assert is_transient_availability_error(ServiceUnavailable('x'))
    assert is_transient_availability_error(DeadlineExceeded('x'))
    assert is_transient_availability_error(InternalServerError('x'))


def test_classifier_rejects_contention_and_expired_id_shapes():
    """The shapes the arm already had stay owned by their own classifiers."""
    from database._client import is_expired_transaction_error, is_transient_availability_error

    assert not is_transient_availability_error(Aborted('contention'))
    expired = InvalidArgument('The referenced transaction has expired or is no longer valid')
    assert not is_transient_availability_error(expired)
    assert is_expired_transaction_error(expired)


def test_classifier_rejects_permanent_and_unknown_shapes():
    from database._client import is_transient_availability_error

    assert not is_transient_availability_error(PermissionDenied('x'))
    assert not is_transient_availability_error(FailedPrecondition('the request must be modified'))
    assert not is_transient_availability_error(InvalidArgument('exceeds the maximum allowed size'))
    assert not is_transient_availability_error(TimeoutError('client-side deadline'))
    assert not is_transient_availability_error(RuntimeError('unknown'))
    assert not is_transient_availability_error(asyncio.CancelledError())


def test_classifier_sees_through_a_wrapped_blip():
    """The SDK wraps transport faults; the cause chain carries the evidence."""
    from database._client import is_transient_availability_error

    wrapped = RuntimeError('unary stream aborted')
    wrapped.__cause__ = ServiceUnavailable('503: backend unavailable')

    assert is_transient_availability_error(wrapped.__cause__)
    assert not is_transient_availability_error(wrapped)  # the wrapper itself is unknown


def test_renewal_absorbs_a_blip_raised_as_a_cause_chain(blipping_store, caplog):
    """A budget-raised wrapper whose cause is a 503 still sheds log-only."""
    _seed_session(blipping_store)
    blip = ServiceUnavailable('503: backend unavailable')
    # Raise the wrapper itself: unknown type, but its __cause__ is the blip.
    blipping_store.read_errors = [RuntimeError('budget wrapper')]
    blipping_store.read_errors[0].__cause__ = blip

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    # Deliberate: only the blip TYPE is the transient; an unknown wrapper stays loud.
    assert renewed is False
    assert any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_absorbs_the_budget_exhaustion_type_directly(blipping_store, caplog):
    """FirestoreContentionExhausted instances classify as transient without an Aborted."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [FirestoreContentionExhausted('exhausted for recording_session_lease_renewal')]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert any(
        'lease renewal contended' in record.getMessage() for record in caplog.records if record.levelname == 'WARNING'
    )


# ---------------------------------------------------------------------------
# Store-seam ordering: the budget runs first; the blip lands after it.
# ---------------------------------------------------------------------------


def test_renewal_budget_replays_contention_before_the_blip_lands(blipping_store, caplog):
    """Contention inside the budget recovers; the later blip sheds log-only."""
    _seed_session(blipping_store)
    # Two aborts replay on fresh transactions, then the third attempt blips.
    blipping_store.read_errors = [
        Aborted('contention'),
        Aborted('contention'),
        ServiceUnavailable('503: backend unavailable'),
    ]

    with caplog.at_level('INFO'):
        first = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )
        second = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert first is False and second is True
    # The blipped attempt never committed; the only commit is the clean second renewal.
    assert len(blipping_store.commits) == 1
    # The budget replayed both aborts on fresh transactions before the blip landed.
    retries = [
        record
        for record in caplog.records
        if 'firestore_transaction_contention' in record.getMessage() and 'outcome=retry' in record.getMessage()
    ]
    assert len(retries) == 2


def test_renewal_blip_between_two_clean_renewals_keeps_both_healthy(blipping_store):
    """A single blipped minute between clean minutes changes nothing durable."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [ServiceUnavailable('503: backend unavailable')]
    # Deplete the fence to a minute of runway so the clean renewals after the
    # blip land real stamps (the runway skip leaves a still-healthy fence
    # untouched by design).
    blipping_store.documents[_SESSION_PATH]['lease_expires_at'] = blipping_store.documents[_SESSION_PATH][
        'lease_expires_at'
    ] - timedelta(minutes=4)
    before = blipping_store.documents[_SESSION_PATH]['lease_expires_at']

    blipped = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )
    clean_after = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )
    clean_after_that = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )

    assert (blipped, clean_after, clean_after_that) == (False, True, True)
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] > before


# ---------------------------------------------------------------------------
# Event phases: every callback phase sheds the same way.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('phase', ['in_progress', 'processing', 'completed', 'failed', 'discarded'])
def test_event_blip_per_phase_sheds_to_legacy_envelope(monkeypatch, blipping_store, caplog, phase):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))
    _patch_event_writer(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', phase)

    assert envelope['recording_session_id'] == 'session'
    assert envelope['lifecycle_sequence'] is None
    assert fallbacks == []


# ---------------------------------------------------------------------------
# Cleanup out-param contract: a blipped delete leaves the snapshot empty.
# ---------------------------------------------------------------------------


def test_delete_blip_leaves_the_deleted_conversation_out_param_clean(monkeypatch, caplog):
    """Physical cleanup must never reason about a snapshot a blip prevented."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')

    received: dict[str, Any] = {}

    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        out = kwargs.get('deleted_conversation')
        if out is not None:
            received.update(out)
        raise ServiceUnavailable('503: backend unavailable')

    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )

    with caplog.at_level('WARNING'):
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False
    assert received == {}


def test_delete_success_passes_the_snapshot_through_the_out_param(monkeypatch, cleanup_seams):
    """The same out-param contract a real delete relies on survives the arm."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    snapshot = {'id': 'conversation', 'status': 'in_progress', 'transcript_segments': []}

    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        out = kwargs.get('deleted_conversation')
        if out is not None:
            out.update(snapshot)
        return True

    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is True


# ---------------------------------------------------------------------------
# Attribution: every writer's transient WARNING names its session.
# ---------------------------------------------------------------------------


def test_open_blip_warning_names_uid_session_and_proposed(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    with caplog.at_level('WARNING'):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    warning = next(record for record in caplog.records if 'open contended' in record.getMessage())
    message = warning.getMessage()
    assert 'uid=uid' in message and 'session=session' in message and 'proposed=conversation' in message


def test_event_blip_warning_names_uid_session_and_conversation(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    with caplog.at_level('WARNING'):
        lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    warning = next(record for record in caplog.records if 'event contended' in record.getMessage())
    message = warning.getMessage()
    assert 'uid=uid' in message and 'session=session' in message and 'conversation=conversation' in message


def test_delete_blip_warning_names_uid_and_conversation(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    with caplog.at_level('WARNING'):
        lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    warning = next(record for record in caplog.records if 'cleanup contended' in record.getMessage())
    message = warning.getMessage()
    assert 'uid=uid' in message and 'conversation=conversation' in message and 'session=session' in message


# ---------------------------------------------------------------------------
# Enforce matrix: every writer re-raises its own blip in enforce mode.
# ---------------------------------------------------------------------------


def test_open_transactional_blip_still_raises_in_enforce(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(monkeypatch, error=DeadlineExceeded('504: deadline exceeded'))

    with pytest.raises(DeadlineExceeded):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')


def test_event_blip_still_raises_in_enforce_for_a_deadline(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_event_writer(monkeypatch, error=DeadlineExceeded('504: deadline exceeded'))

    with pytest.raises(DeadlineExceeded):
        lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')


def test_delete_blip_in_enforce_mode_stays_absorbed(monkeypatch):
    """Mode-independence is the cleanup arm's contract — enforce changes nothing."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_cleaner(monkeypatch, error=DeadlineExceeded('504: deadline exceeded'))

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False


# ---------------------------------------------------------------------------
# Shadow mode: the open/event fail-open envelope carries the legacy nulls.
# ---------------------------------------------------------------------------


def test_open_blip_in_shadow_mode_sheds_to_the_same_legacy_envelope(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['lifecycle_version'] is None
    assert binding['mapping_conflict'] is False
    assert any('open contended' in record.getMessage() for record in caplog.records if record.levelname == 'WARNING')


def test_event_blip_in_shadow_mode_sheds_to_the_same_legacy_envelope(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')
    _patch_event_writer(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    assert envelope['lifecycle_version'] is None
    assert envelope['lifecycle_phase'] is None
    assert envelope['lifecycle_sequence'] is None


# ---------------------------------------------------------------------------
# Extended contracts: subclasses, sequences, fan-out isolation, mode matrices.
# ---------------------------------------------------------------------------


def test_classifier_recognizes_subclasses_of_the_trio():
    """SDK subclasses (grpc-specific 503 specializations) classify the same."""

    class GatewayTimeout(DeadlineExceeded):
        pass

    class DataPlane500(InternalServerError):
        pass

    from database._client import is_transient_availability_error

    assert is_transient_availability_error(GatewayTimeout('504'))
    assert is_transient_availability_error(DataPlane500('500'))


def test_renewal_survives_a_three_window_blip_run(blipping_store, caplog):
    """A sustained blip run stays bounded: three warnings, zero tracebacks."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(b)(str(b)) for b in _BLIPS]

    with caplog.at_level('WARNING'):
        outcomes = [
            lifecycle_service.renew_live_recording_session_lease(
                'uid', 'session', 'conversation', firestore_client=blipping_store
            )
            for _ in range(3)
        ]

    assert outcomes == [False, False, False]
    warnings = [r for r in caplog.records if r.levelname == 'WARNING' and 'lease renewal contended' in r.getMessage()]
    assert len(warnings) == 3
    assert all(r.exc_info is None for r in warnings)


def test_open_probe_and_transactional_blips_both_fire_their_own_warning(monkeypatch, caplog):
    """A blipped probe followed by a blipped open logs each arm exactly once."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=ServiceUnavailable('503: backend unavailable'))
    _patch_transactional_open(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['lifecycle_version'] is None
    messages = [r.getMessage() for r in caplog.records if r.levelname == 'WARNING']
    assert any('open probe contended' in m for m in messages)
    assert any('open contended' in m for m in messages)


def test_delete_blip_touches_no_physical_cleanup(monkeypatch, cleanup_seams):
    """A blipped delete must not fan out index/photo/audio cleanup."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=ServiceUnavailable('503: backend unavailable'))

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False
    assert cleanup_seams == []


def test_renewal_blip_with_identity_mismatch_still_refuses(blipping_store):
    """A blip must not widen the identity fence: mismatch refuses before the write."""
    _seed_session(blipping_store)
    before = blipping_store.documents[_SESSION_PATH]['lease_expires_at']

    # The clean mismatch call refuses: nothing is written for the wrong identity.
    mismatched = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'other-conversation', firestore_client=blipping_store
    )
    assert mismatched is False
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] == before

    # A later blipped call for the RIGHT identity sheds transiently — no write either.
    blipping_store.read_errors = [ServiceUnavailable('503: backend unavailable')]
    blipped = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )
    assert blipped is False
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] == before


def test_accepted_event_with_a_pending_blip_still_returns_the_durable_envelope(monkeypatch):
    """The blip must be consumed by the write, not poison a clean append."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(
        monkeypatch,
        result={'accepted': True, 'recording_session_id': 'session', 'conversation_id': 'conversation'},
    )

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    assert envelope['accepted'] is True
    assert envelope['recording_session_id'] == 'session'


def test_open_clean_probe_and_clean_open_in_enforce_mode_is_unchanged(monkeypatch):
    """No blip: enforce mode's happy path is byte-identical to dual_write's."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(
        monkeypatch,
        result={
            'recording_session_id': 'session',
            'conversation_id': 'conversation',
            'lifecycle_version': 1,
            'mapping_conflict': False,
        },
    )

    binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['requires_rollover'] is False
    assert binding['recording_session_id'] == 'session'


def test_delete_success_in_enforce_mode_still_deletes(monkeypatch, cleanup_seams):
    """Enforce mode changes the failure posture, not the success path."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_cleaner(monkeypatch, result=True)

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is True
    assert cleanup_seams == ['index', 'photos', 'audio']


def test_accepted_event_in_enforce_mode_returns_the_durable_envelope(monkeypatch):
    """Enforce mode with a clean append returns the store's own envelope."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_event_writer(
        monkeypatch,
        result={'accepted': True, 'recording_session_id': 'session', 'conversation_id': 'conversation'},
    )

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    assert envelope['accepted'] is True


@pytest.mark.parametrize('mode', ['shadow', 'dual_write'])
def test_renewal_blip_behavior_is_mode_independent(blipping_store, monkeypatch, caplog, mode):
    """The renewal's transient arm sits below every non-enforce mode."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: mode)
    _seed_session(blipping_store)
    blipping_store.read_errors = [ServiceUnavailable('503: backend unavailable')]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert any('lease renewal contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')


def test_transient_warning_carries_no_traceback_even_at_error_level(blipping_store, caplog):
    """The arm's log shape survives an ERROR-level capture: still exc_info-free."""
    import logging as _logging

    _seed_session(blipping_store)
    blipping_store.read_errors = [ServiceUnavailable('503: backend unavailable')]

    with caplog.at_level(_logging.ERROR):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    # No lifecycle ERROR was emitted at all, and nothing captured a traceback.
    lifecycle_records = [r for r in caplog.records if r.name == 'utils.conversations.lifecycle']
    assert lifecycle_records == []
    assert all(r.exc_info is None for r in caplog.records)


def test_delete_success_passes_the_real_snapshot_through(monkeypatch, cleanup_seams):
    """The success path's out-param carries the deleted row's stored fields."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    seen: dict[str, Any] = {}

    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        out = kwargs.get('deleted_conversation')
        assert out is not None
        out.update({'audio_files': [{'path': 'a.opus'}]})
        seen['had_audio'] = bool(out.get('audio_files'))
        return True

    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is True
    assert seen['had_audio'] is True


def test_renewal_blip_and_recovery_both_name_the_shared_budget(blipping_store, caplog):
    """Correlation: the budget's correlation key stays the renewal's own."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [Aborted('contention'), ServiceUnavailable('503: backend unavailable')]

    with caplog.at_level('INFO'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    budget_lines = [r.getMessage() for r in caplog.records if 'firestore_transaction_contention' in r.getMessage()]
    assert budget_lines and all('recording_session_lease_renewal' in m for m in budget_lines)


def test_open_probe_blip_conversation_field_is_the_proposed_id(monkeypatch, caplog):
    """The probe degrade attributes the PROPOSED conversation, not a stored one."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=ServiceUnavailable('503: backend unavailable'))
    _patch_transactional_open(
        monkeypatch,
        result={
            'recording_session_id': 'session',
            'conversation_id': 'conversation',
            'lifecycle_version': 1,
            'mapping_conflict': False,
        },
    )

    with caplog.at_level('WARNING'):
        lifecycle_service.open_live_recording_session('uid', 'session', 'proposed-id')

    warning = next(record for record in caplog.records if 'open probe contended' in record.getMessage())
    assert 'proposed=proposed-id' in warning.getMessage()


def test_renewal_503_and_504_interleave_stays_bounded_and_nonwedge(blipping_store, caplog):
    """Any interleaving of blip classes keeps the arm bounded and the fence alive."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [
        ServiceUnavailable('503: backend unavailable'),
        DeadlineExceeded('504: deadline exceeded'),
        ServiceUnavailable('503: backend unavailable'),
        DeadlineExceeded('504: deadline exceeded'),
    ]

    with caplog.at_level('WARNING'):
        outcomes = [
            lifecycle_service.renew_live_recording_session_lease(
                'uid', 'session', 'conversation', firestore_client=blipping_store
            )
            for _ in range(4)
        ]

    assert outcomes == [False, False, False, False]
    assert not any('lease renewal failed' in r.getMessage() for r in caplog.records if r.levelname == 'ERROR')
    final = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )
    assert final is True
