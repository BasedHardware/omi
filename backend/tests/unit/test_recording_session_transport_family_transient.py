"""The transport-family blips around the availability trio are the bounded transient too.

Failure-Class: FC-transport-family-blip-logged-as-failed-recording-session-write —
a session-boundary transient classifier that recognizes only the trio its RPC
budget replays (503 ``ServiceUnavailable`` / 504 ``DeadlineExceeded`` /
500 ``InternalServerError``) cannot see the transport-level availability faults
one hop out, so the same momentary, nothing-committed shapes — 502
``BadGateway``, the 504 ``GatewayTimeout`` spelling, the ``requests`` transport
family (connection resets, chunked-encoding breaks, read timeouts) and the
auth-transport ``TransportError`` envelope — walked into the failed-write arm:
a full ``recording session lease renewal failed`` traceback plus (on the
boundaries that emit one) an ``omi_fallback_total`` degradation event, on the
write a live recording issues every single minute (prod backend-listen
2026-10-30: the renewal boundary ×9/30m after the trio drain). The storage
SDK's own retry set is the boundary's truth for what the transport family
retries: its availability members (``google.cloud.storage.retry
._RETRYABLE_TYPES`` minus quota pressure) are exactly these shapes. Nothing is
written by a blipped attempt and the session's own cadence re-attempts the
write — the next minute's renewal, the next reconnect's open, the next
lifecycle callback — so the wider family sheds to the same log-only arm the
trio already owns: a WARNING without a stack trace, no degradation event. The
wider read is deliberately boundary-local: the shared classifier also feeds
the client-facing admission fence, which must keep answering exactly the trio,
and quota pressure (``TooManyRequests`` / ``ResourceExhausted``) keeps its
loud classification because it is not redial-able by the session's cadence.

Guards:
- every transport-family shape on the renewal keeps the log-only transient
  arm: WARNING naming the session, no failed-write ERROR, no stack trace, no
  ``omi_fallback_total`` degradation event, nothing committed;
- the fence does not wedge: the next renewal after each family blip commits
  and advances the lease; back-to-back family blips stay bounded;
- a drained-retry envelope around a family member sheds through its cause,
  exactly like the trio's envelope;
- the open, event and cleanup boundaries shed the family through the same
  shared classifier (the extension joins, never shadows: the trio, contention
  and expired-id shapes still classify, and every shape the trio kept loud
  stays loud);
- the shared classifier ``is_transient_availability_error`` itself does NOT
  answer the family (the client-facing admission fence keeps its exact trio);
- ``PermissionDenied``, the 1 MiB document-size ``InvalidArgument``,
  ``FailedPrecondition``, bare ``TimeoutError``, ``TooManyRequests`` and
  unknown failures keep the failed-write classification, and task cancellation
  is never absorbed;
- enforce mode still raises through every family shape.
"""

from __future__ import annotations

import asyncio
import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from google.api_core.exceptions import (
    Aborted,
    BadGateway,
    FailedPrecondition,
    GatewayTimeout,
    InvalidArgument,
    PermissionDenied,
    RetryError,
    ResourceExhausted,
    ServiceUnavailable,
    TooManyRequests,
)
from google.auth.exceptions import TransportError

from database import recording_sessions
from database._client import is_transient_availability_error
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from utils.conversations import lifecycle as lifecycle_service

_SESSION_PATH = ('users', 'uid', 'recording_sessions', 'session')


# The transport family the boundary now owns: the storage SDK's availability
# members around the trio (minus quota pressure), plus the auth-transport
# envelope. The two ``requests``-family members are stand-ins: the real
# classes live behind an import the utils tree forbids, and the boundary
# matches the family structurally by module name — the stand-ins prove the
# structural read, the explicit members prove the isinstance read.
class _FakeConnectionError(OSError):
    """Stand-in for ``requests.exceptions.ConnectionError``."""


_FakeConnectionError.__module__ = 'requests.exceptions'


class _FakeReadTimeout(OSError):
    """Stand-in for ``requests.exceptions.ReadTimeout``."""


_FakeReadTimeout.__module__ = 'requests.exceptions'


class _NotTransport(OSError):
    """An OSError that is NOT a transport fault — the family must not absorb it."""


_NotTransport.__module__ = 'builtins'

_FAMILY_BLIPS = (BadGateway('502: bad gateway'), GatewayTimeout('504: gateway timeout'))

_BLIPS = (
    *_FAMILY_BLIPS,
    _FakeConnectionError('connection reset by peer'),
    _FakeReadTimeout('read timed out'),
    TransportError('auth transport broke'),
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

    def document(self, document_id: str) -> '_DocumentRef':
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
    ``Aborted``), which is exactly how a real transport-family fault reaches
    the lifecycle owner.
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
def test_renewal_family_blip_is_log_only(blipping_store, caplog, blip):
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
def test_renewal_family_blip_carries_no_stack_trace(blipping_store, caplog, blip):
    """A family blip is telemetry-shaped, not a traceback: exc_info stays unset."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    with caplog.at_level('WARNING'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert warnings and all(record.exc_info is None for record in warnings)


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_family_blip_records_no_degradation_event(blipping_store, monkeypatch, blip):
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )

    assert fallbacks == []


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_family_blip_commits_nothing(blipping_store, blip):
    """A family-blipped attempt must leave the stored lease unchanged."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]
    before = blipping_store.documents[_SESSION_PATH]['lease_expires_at']

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )

    assert blipping_store.commits == []
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] == before


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_succeeds_on_the_next_minute_after_a_family_blip(blipping_store, blip):
    """The family blip must not wedge the fence: the next renewal commits."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    assert (
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )
        is False
    )
    assert (
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )
        is True
    )
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] is not None


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_absorbs_back_to_back_family_blips_bounded(blipping_store, caplog, blip):
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip)), type(blip)(str(blip)), type(blip)(str(blip))]

    with caplog.at_level('WARNING'):
        for _ in range(3):
            assert (
                lifecycle_service.renew_live_recording_session_lease(
                    'uid', 'session', 'conversation', firestore_client=blipping_store
                )
                is False
            )

    assert not [r for r in caplog.records if r.levelname == 'ERROR']


def test_renewal_envelope_around_a_family_member_is_the_transient(blipping_store, caplog):
    """A drained budget whose last fault is a family member sheds log-only."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [RetryError('retry budget drained', BadGateway('502 behind the envelope'))]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert not any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


def test_renewal_envelope_chained_not_wrapped_still_classifies(blipping_store, caplog):
    """The envelope's raise site chains the cause; ``__cause__`` covers it."""
    _seed_session(blipping_store)
    envelope = RetryError('retry budget drained', None)
    envelope.__cause__ = _FakeConnectionError('connection reset by peer')
    blipping_store.read_errors = [envelope]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert not any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


def test_renewal_envelope_around_a_permanent_failure_stays_loud(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [RetryError('retry budget drained', PermissionDenied('denied'))]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    errors = [r for r in caplog.records if r.levelname == 'ERROR']
    assert any('recording session lease renewal failed' in r.getMessage() for r in errors)


# ---------------------------------------------------------------------------
# The extension joins; it never shadows.
# ---------------------------------------------------------------------------


def test_the_trio_still_sheds_through_the_shared_classifier(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [ServiceUnavailable('503: backend unavailable')]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert any('lease renewal contended' in record.getMessage() for record in warnings)


def test_contention_exhaustion_still_sheds_through_the_shared_classifier(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [Aborted('contention')] * 50

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


@pytest.mark.parametrize(
    'loud',
    (
        PermissionDenied('denied'),
        InvalidArgument('1000: exceeds the maximum allowed size'),
        FailedPrecondition('the request must be modified'),
        TooManyRequests('429: quota exceeded'),
        TimeoutError('client-side deadline'),
        _NotTransport('some unrelated os fault'),
        ValueError('unknown failure'),
    ),
    ids=lambda e: type(e).__name__,
)
def test_loud_shapes_keep_the_failed_write_arm(blipping_store, caplog, loud):
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(loud)(str(loud))]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    errors = [r for r in caplog.records if r.levelname == 'ERROR']
    assert any('recording session lease renewal failed' in r.getMessage() for r in errors)
    assert any(r.exc_info is not None for r in errors)


def test_task_cancellation_is_never_absorbed(blipping_store):
    _seed_session(blipping_store)
    blipping_store.read_errors = [asyncio.CancelledError()]

    with pytest.raises(asyncio.CancelledError):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )


def test_enforce_mode_still_raises_through_family_shapes(blipping_store, monkeypatch):
    _seed_session(blipping_store)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    blipping_store.read_errors = [BadGateway('502: bad gateway')]

    with pytest.raises(BadGateway):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )


# ---------------------------------------------------------------------------
# Open boundary: the probe read defers; the transactional open sheds.
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
    def create_or_get_recording_session(
        uid, recording_session_id, proposed_conversation_id, *, firestore_client=None, **kwargs
    ):
        del uid, recording_session_id, proposed_conversation_id, firestore_client, kwargs
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(recording_sessions, 'create_or_get_recording_session', create_or_get_recording_session)


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_open_probe_family_blip_defers_to_the_transactional_open(monkeypatch, caplog, blip):
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


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_open_transactional_family_blip_sheds_to_the_legacy_envelope(monkeypatch, caplog, blip):
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
    assert not any(
        record.levelname == 'ERROR' and 'recording session persistence failed' in record.getMessage()
        for record in caplog.records
    )


def test_open_probe_family_blip_still_raises_in_enforce_mode(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_open_probe(monkeypatch, probe_error=BadGateway('502: bad gateway'))

    with pytest.raises(BadGateway):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')


def test_open_transactional_family_blip_still_raises_in_enforce_mode(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(monkeypatch, error=GatewayTimeout('504: gateway timeout'))

    with pytest.raises(GatewayTimeout):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')


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
def test_event_family_blip_sheds_to_legacy_envelope(monkeypatch, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=type(blip)(str(blip)))

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    assert envelope['recording_session_id'] == 'session'
    assert envelope['lifecycle_version'] is None
    assert envelope['lifecycle_sequence'] is None


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_event_family_blip_records_no_degradation_event(monkeypatch, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=type(blip)(str(blip)))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    assert fallbacks == []


def test_event_family_blip_still_raises_in_enforce(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_event_writer(monkeypatch, error=GatewayTimeout('504: gateway timeout'))

    with pytest.raises(GatewayTimeout):
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


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_cleanup_boundary_family_blip_is_mode_independent(monkeypatch, caplog, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=type(blip)(str(blip)))

    with caplog.at_level('WARNING'):
        result = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert result is False
    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert any('cleanup contended' in record.getMessage() for record in warnings)
    assert not any(
        record.levelname == 'ERROR' and 'recording session cleanup failed' in record.getMessage()
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# The shared classifier stays exactly the trio.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_shared_classifier_does_not_answer_the_family(blip):
    """The client-facing admission fence keeps its exact trio."""
    assert is_transient_availability_error(type(blip)(str(blip))) is False


def test_shared_classifier_trio_and_envelope_are_unchanged():
    assert is_transient_availability_error(ServiceUnavailable('503')) is True
    envelope = RetryError('drained', ServiceUnavailable('503'))
    assert is_transient_availability_error(envelope) is True
    assert is_transient_availability_error(BadGateway('502')) is False


def test_boundary_classifier_answers_the_family_directly():
    for blip in _BLIPS:
        assert lifecycle_service._is_wide_availability_blip(type(blip)(str(blip))) is True
    assert lifecycle_service._is_wide_availability_blip(ServiceUnavailable('503')) is False
    assert lifecycle_service._is_wide_availability_blip(PermissionDenied('denied')) is False
    assert lifecycle_service._is_wide_availability_blip(_NotTransport('unrelated')) is False


def test_family_blip_and_recovery_both_flow_through_the_shared_budget(blipping_store, caplog):
    """After the family drain, the next renewal still flows through the budget."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [BadGateway('502: bad gateway')]

    with caplog.at_level('WARNING'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )
        assert (
            lifecycle_service.renew_live_recording_session_lease(
                'uid', 'session', 'conversation', firestore_client=blipping_store
            )
            is True
        )

    assert any('lease renewal contended' in r.getMessage() for r in caplog.records)


def test_renewal_family_blip_behavior_is_mode_independent(blipping_store, monkeypatch, caplog):
    for mode in ('shadow', 'dual_write'):
        monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda mode=mode: mode)
        _seed_session(blipping_store)
        blipping_store.read_errors = [GatewayTimeout('504: gateway timeout')]

        with caplog.at_level('WARNING'):
            renewed = lifecycle_service.renew_live_recording_session_lease(
                'uid', 'session', 'conversation', firestore_client=blipping_store
            )

        assert renewed is False
        assert not any(r.levelname == 'ERROR' for r in caplog.records if 'lease renewal failed' in r.getMessage())
        caplog.clear()


# ---------------------------------------------------------------------------
# Renewal: attribution, cadence and correlation for the family arm.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_family_blip_warning_names_the_session(blipping_store, caplog, blip):
    """The contended WARNING keeps uid/session/conversation attribution."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    with caplog.at_level('WARNING'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    warning = next(record for record in caplog.records if record.levelname == 'WARNING')
    message = warning.getMessage()
    assert 'uid=uid' in message and 'session=session' in message and 'conversation=conversation' in message


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_family_blip_still_raises_in_enforce_mode(blipping_store, monkeypatch, caplog, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(blipping_store)
    blipping_store.read_errors = [type(blip)(str(blip))]

    with pytest.raises(type(blip)):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )


def test_renewal_family_interleave_stays_bounded_and_nonwedge(blipping_store, caplog):
    """Any interleaving of family classes keeps the arm bounded and the fence alive."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [
        BadGateway('502: bad gateway'),
        GatewayTimeout('504: gateway timeout'),
        _FakeConnectionError('connection reset by peer'),
        TransportError('auth transport broke'),
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


def test_renewal_family_blip_does_not_widen_the_identity_fence(blipping_store):
    """A family blip must not widen the identity fence: mismatch refuses first."""
    _seed_session(blipping_store)
    before = blipping_store.documents[_SESSION_PATH]['lease_expires_at']

    mismatched = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'other-conversation', firestore_client=blipping_store
    )
    assert mismatched is False
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] == before

    blipping_store.read_errors = [BadGateway('502: bad gateway')]
    blipped = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=blipping_store
    )
    assert blipped is False
    assert blipping_store.documents[_SESSION_PATH]['lease_expires_at'] == before


def test_renewal_family_warning_carries_no_traceback_even_at_error_level(blipping_store, caplog):
    """The arm's log shape survives an ERROR-level capture: still exc_info-free."""
    import logging as _logging

    _seed_session(blipping_store)
    blipping_store.read_errors = [BadGateway('502: bad gateway')]

    with caplog.at_level(_logging.ERROR):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    lifecycle_records = [r for r in caplog.records if r.name == 'utils.conversations.lifecycle']
    assert lifecycle_records == []
    assert all(r.exc_info is None for r in caplog.records)


def test_renewal_family_budget_correlation_names_the_operation(blipping_store, caplog):
    """The budget's correlation key stays the renewal's own across a family blip."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [Aborted('contention'), BadGateway('502: bad gateway')]

    with caplog.at_level('INFO'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    budget_lines = [r.getMessage() for r in caplog.records if 'firestore_transaction_contention' in r.getMessage()]
    assert budget_lines and all('recording_session_lease_renewal' in m for m in budget_lines)


def test_renewal_survives_a_three_window_family_blip_run(blipping_store, caplog):
    """A multi-window family burst ends in a committed renewal, not a wedge."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [
        BadGateway('502: bad gateway'),
        BadGateway('502: bad gateway'),
        GatewayTimeout('504: gateway timeout'),
    ]

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
    assert (
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )
        is True
    )


@pytest.mark.parametrize('blip', _FAMILY_BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_commit_side_family_blip_is_also_absorbed(blipping_store, caplog, blip):
    """A commit-side family fault is the same bounded transient (nothing committed)."""
    from datetime import timedelta

    _seed_session(blipping_store)
    blipping_store.write_errors = [type(blip)(str(blip))]
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
        r.levelname == 'ERROR' and 'recording session lease renewal failed' in r.getMessage() for r in caplog.records
    )


def test_renewal_envelope_around_gateway_timeout_sheds(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [RetryError('retry budget drained', GatewayTimeout('504: gateway timeout'))]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert not any(
        r.levelname == 'ERROR' and 'recording session lease renewal failed' in r.getMessage() for r in caplog.records
    )


def test_renewal_envelope_around_transport_error_sheds(blipping_store, caplog):
    _seed_session(blipping_store)
    blipping_store.read_errors = [RetryError('retry budget drained', TransportError('auth transport broke'))]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    assert not any(
        r.levelname == 'ERROR' and 'recording session lease renewal failed' in r.getMessage() for r in caplog.records
    )


def test_renewal_envelope_around_quota_stays_loud(blipping_store, caplog):
    """Quota pressure behind the envelope is not redial-able: keep the failed write."""
    _seed_session(blipping_store)
    blipping_store.read_errors = [RetryError('retry budget drained', TooManyRequests('429: quota exceeded'))]

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=blipping_store
        )

    assert renewed is False
    errors = [r for r in caplog.records if r.levelname == 'ERROR']
    assert any('recording session lease renewal failed' in r.getMessage() for r in errors)


# ---------------------------------------------------------------------------
# Open boundary: attribution, cadence and the family's structural limit.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_open_transactional_family_blip_records_no_degradation_event(monkeypatch, blip):
    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_transactional_open(monkeypatch, error=type(blip)(str(blip)))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert fallbacks == []


def test_open_probe_family_blip_warning_names_the_proposed_id(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=BadGateway('502: bad gateway'))
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


def test_open_probe_family_blip_then_next_open_fully_succeeds(monkeypatch):
    """The degraded probe must not poison the next (clean) open."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    calls = {'probe': 0}

    def get_recording_session(uid, recording_session_id, *, firestore_client=None):
        calls['probe'] += 1
        if calls['probe'] == 1:
            raise BadGateway('502: bad gateway')
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


def test_open_probe_and_transactional_family_blips_both_fire_their_own_warning(monkeypatch, caplog):
    """A blipped probe followed by a blipped open logs each arm exactly once."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=BadGateway('502: bad gateway'))
    _patch_transactional_open(monkeypatch, error=GatewayTimeout('504: gateway timeout'))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['lifecycle_version'] is None
    messages = [r.getMessage() for r in caplog.records if r.levelname == 'WARNING']
    assert any('open probe contended' in m for m in messages)
    assert any('open contended' in m for m in messages)


def test_open_probe_non_transport_oserror_still_raises(monkeypatch):
    """The family match is structural, not 'any OSError': a builtin one propagates."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=_NotTransport('some unrelated os fault'))

    with pytest.raises(_NotTransport):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')


def test_open_clean_probe_and_clean_open_is_unchanged(monkeypatch):
    """No blip: the open's happy path is unchanged by the wider classifier."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
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


# ---------------------------------------------------------------------------
# Event boundary: attribution and the store's own rejection path.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_event_family_blip_warning_names_session_conversation_and_phase(monkeypatch, caplog, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=type(blip)(str(blip)))

    with caplog.at_level('WARNING'):
        lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'kept')

    warning = next(record for record in caplog.records if record.levelname == 'WARNING')
    message = warning.getMessage()
    assert 'uid=uid' in message and 'session=session' in message
    assert 'conversation=conversation' in message and 'phase=kept' in message


def test_event_rejected_event_still_keeps_its_own_degradation_path(monkeypatch):
    """The family arm must not absorb the store's deliberate rejection."""
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
# Cleanup boundary: no degradation event, no physical fan-out on a family blip.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_cleanup_family_blip_records_no_degradation_event(monkeypatch, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=type(blip)(str(blip)))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert fallbacks == []


def test_cleanup_family_blip_touches_no_physical_cleanup(monkeypatch):
    """The blipped delete stops at the boundary: no search/photo/audio fan-out."""
    from utils.conversations import typesense_index

    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=BadGateway('502: bad gateway'))
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

    lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert touched == []


# ---------------------------------------------------------------------------
# The two classifiers: family membership, quota, structural limits.
# ---------------------------------------------------------------------------


def test_boundary_classifier_envelope_reads_through_the_cause_chain():
    """Each envelope level must be the SDK's own type; the chain decides."""
    nested = RetryError('outer', RetryError('inner', BadGateway('502')))
    assert lifecycle_service._is_wide_availability_blip(nested) is True
    wrapped_generic = RetryError('outer', RuntimeError('not an sdk envelope'))
    assert lifecycle_service._is_wide_availability_blip(wrapped_generic) is False


@pytest.mark.parametrize(
    'quota',
    (
        TooManyRequests('429: quota exceeded'),
        ResourceExhausted('429: resource exhausted'),
    ),
    ids=lambda e: type(e).__name__,
)
def test_boundary_classifier_ignores_quota_pressure(quota):
    """Quota pressure is not redial-able by the session's cadence: stays loud."""
    assert lifecycle_service._is_wide_availability_blip(quota) is False


@pytest.mark.parametrize(
    'osfault',
    (
        _NotTransport('unrelated os fault'),
        PermissionError('permission denied'),
        ConnectionResetError('builtin connection reset'),
    ),
    ids=lambda e: type(e).__name__,
)
def test_boundary_classifier_ignores_genuine_oserror_outside_requests(osfault):
    """Only the ``requests.exceptions`` module matches; builtins stay loud."""
    assert lifecycle_service._is_wide_availability_blip(osfault) is False


@pytest.mark.parametrize(
    'family',
    (
        BadGateway('502: bad gateway'),
        GatewayTimeout('504: gateway timeout'),
        _FakeConnectionError('connection reset by peer'),
        ConnectionResetError('builtin connection reset'),
    ),
    ids=lambda e: type(e).__name__,
)
def test_shared_classifier_rejects_family_and_builtin_oserror(family):
    """The admission fence keeps its exact trio: no family, no builtins."""
    assert is_transient_availability_error(family) is False
