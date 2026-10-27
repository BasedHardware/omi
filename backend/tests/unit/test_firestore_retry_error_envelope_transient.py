"""A drained SDK retry budget surfaces as a RetryError envelope, not the transient it wrapped.

Failure-Class: FC-drained-sdk-retry-budget-escapes-transient-class (new class
declared in this diff). Firestore's gapic layer wraps every RPC — each
transactional read and commit included — in a ~60s retry whose predicate is the
availability set (500 ``InternalServerError``, 429, 503
``ServiceUnavailable``, 504 ``DeadlineExceeded``, connection faults). When that
budget drains, ``google.api_core.retry`` raises
``google.api_core.exceptions.RetryError`` with the last underlying fault as its
cause (``raise final_exc from source_exc``). ``RetryError`` extends
``GoogleAPIError``, not ``GoogleAPICallError``, so the recording-session
boundaries' transient classification — which recognizes the availability trio
by ``isinstance`` — does not recognize the envelope carrying one: a
sustained-but-recovering data-plane fault walked out of the SDK budget through
both write-layer budgets (they replay only ``Aborted`` and the expired-id
``InvalidArgument``) into the failed-write arm, surfacing the full
``recording session lease renewal failed`` traceback the availability
classification was added to retire (prod backend-listen 2026-10-22:
``lifecycle.py`` renewal boundary ×31/30m, after the contention, retired-id
and single-blip drains). Nothing was written — the transaction died before its
commit — and the session's own cadence (the next minute's renewal, the next
reconnect's open, the next lifecycle callback) is the retry, exactly as for
the single-blip shape. The classifier therefore reads one level through the
envelope: a ``RetryError`` whose cause is in the availability set is the same
bounded transient; an envelope around a permanent refusal
(``PermissionDenied``), an unknown failure, or nothing at all keeps the
failed-write classification — the envelope type alone must never widen the
arm, because the SDK raises the same type for any exhausted retry.

Guards:
- the classifier recognizes the envelope type with a trio cause (property and
  ``__cause__`` forms, SDK subclasses and subclass causes included) and still
  rejects the envelope around permanent refusals, quota (429), unknown
  failures, and nothing at all; the single-fault arm is unchanged;
- the production shape is reproduced by the SDK's own ``retry_target``: a
  retryable fault drained through a real budget comes back enveloped and
  classifies, a permanent refusal is never enveloped, and a fault that clears
  before the drain still returns;
- end to end over the real renewal stack against fake Firestore: read-side,
  commit-side, and ``BeginTransaction``-side envelopes all shed log-only
  (WARNING, no stack trace, no ``omi_fallback_total`` degradation event,
  nothing committed), the next clean renewal commits and advances the lease
  by the full duration, sustained envelope runs stay bounded, contention
  replays still precede the envelope, expired-id and availability envelopes
  interleave, and an envelope never widens the identity fence;
- the open, event and cleanup boundaries shed the same envelope through their
  existing arms — over patched seams and over the real store code — with
  attribution intact, no physical cleanup on a blipped delete, and the next
  clean call fully succeeding; enforce mode still raises through it, and the
  controller's spawned task contains the raise;
- controller cadence, end to end: an enveloped cycle redrives to a committed
  fence inside its minute, renews idempotently the next minute, full
  exhaustion stays bounded across two cycles;
- narrowness at the boundary: an envelope wrapping ``PermissionDenied``, a
  quota envelope, and a cause-less envelope keep the loud failed-write
  classification.
"""

from __future__ import annotations

import asyncio
import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    FailedPrecondition,
    InternalServerError,
    InvalidArgument,
    PermissionDenied,
    RetryError,
    ServiceUnavailable,
)

from database import recording_sessions
from database._client import _retry_error_cause, is_transient_availability_error
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from routers.listen.conversations import LiveConversationController
from utils.conversations import lifecycle as lifecycle_service

_SESSION_PATH = ('users', 'uid', 'recording_sessions', 'session')
_BLIPS = (
    ServiceUnavailable('503: backend unavailable'),
    DeadlineExceeded('504: deadline exceeded'),
    InternalServerError('500: internal error'),
)
_TIMEOUT_ENVELOPES = tuple(RetryError('Timeout of 60.0s exceeded', blip) for blip in _BLIPS)


# ---------------------------------------------------------------------------
# Classifier contract: the envelope is as transient as its cause.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('envelope', _TIMEOUT_ENVELOPES, ids=lambda e: type(e.cause).__name__)
def test_classifier_recognizes_the_drained_sdk_retry_envelope(envelope):
    """The gapic budget's drained envelope, carrying a trio cause, is transient."""
    assert is_transient_availability_error(envelope) is True


def test_classifier_reads_the_property_cause_the_sdk_sets():
    """``.cause`` (the documented RetryError attribute) alone is enough."""
    envelope = RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503: backend unavailable'))
    envelope.__cause__ = None  # the property, not the raise-site chain, carries it
    assert is_transient_availability_error(envelope) is True


def test_classifier_recognizes_retry_error_subclasses():
    """A vendored/pinned SDK that specializes the envelope keeps the verdict."""

    class PinnedRetryError(RetryError):
        pass

    envelope = PinnedRetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))
    assert is_transient_availability_error(envelope) is True


def test_classifier_rejects_the_envelope_around_a_permanent_failure():
    """An exhausted retry of ``PermissionDenied`` is still a permanent refusal."""
    envelope = RetryError('Timeout of 60.0s exceeded', PermissionDenied('permission denied on row'))
    assert is_transient_availability_error(envelope) is False


def test_classifier_rejects_the_envelope_around_an_unknown_failure():
    envelope = RetryError('Timeout of 60.0s exceeded', RuntimeError('not a google fault'))
    assert is_transient_availability_error(envelope) is False


def test_classifier_rejects_a_causeless_envelope():
    """The SDK's 'Unknown error' envelope carries no transient evidence."""
    assert is_transient_availability_error(RetryError('Unknown error', None)) is False


def test_classifier_single_fault_arm_is_unchanged():
    """The envelope extension must not shadow the shapes already classified."""
    expired = InvalidArgument('The referenced transaction has expired or is no longer valid')
    assert is_transient_availability_error(ServiceUnavailable('503')) is True
    assert is_transient_availability_error(DeadlineExceeded('504')) is True
    assert is_transient_availability_error(InternalServerError('500')) is True
    assert is_transient_availability_error(Aborted('contention')) is False
    assert is_transient_availability_error(expired) is False
    assert is_transient_availability_error(FirestoreContentionExhausted('exhausted')) is False
    assert is_transient_availability_error(PermissionDenied('x')) is False
    assert is_transient_availability_error(InvalidArgument('exceeds the maximum allowed size')) is False
    assert is_transient_availability_error(FailedPrecondition('the request must be modified')) is False
    assert is_transient_availability_error(TimeoutError('client-side deadline')) is False
    assert is_transient_availability_error(asyncio.CancelledError()) is False


def test_classifier_rejects_a_bare_runtime_error_wrapper():
    """Only the SDK's envelope type reads through; unknown wrappers stay loud."""
    wrapper = RuntimeError('unary stream aborted')
    wrapper.__cause__ = ServiceUnavailable('503: backend unavailable')
    assert is_transient_availability_error(wrapper) is False


# ---------------------------------------------------------------------------
# Fake Firestore: the envelope fires from inside the transactional body.
# ---------------------------------------------------------------------------


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
    firestore: '_EnvelopeFirestore'
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
    firestore: '_EnvelopeFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.firestore, self.path + (document_id,))


@dataclass
class _Transaction:
    firestore: '_EnvelopeFirestore'

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        if self.firestore.write_errors:
            raise self.firestore.write_errors.pop(0)
        self.firestore.documents[document.path].update(copy.deepcopy(updates))


@dataclass
class _EnvelopeFirestore:
    """Fake Firestore whose first reads/writes raise the injected envelopes.

    A real envelope is raised by the gapic retry around the RPC the
    transactional body issued — after both write-layer budgets have had their
    chance (they replay only ``Aborted`` and the expired-id shape), which is
    exactly where this injection lands.
    """

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[BaseException] = field(default_factory=list)
    write_errors: list[BaseException] = field(default_factory=list)
    begin_errors: list[BaseException] = field(default_factory=list)
    commits: list[_Transaction] = field(default_factory=list)
    transaction_lock: threading.Lock = field(default_factory=threading.Lock)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        if self.begin_errors:
            raise self.begin_errors.pop(0)
        return _Transaction(self)


def _seed_session(
    store: _EnvelopeFirestore,
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
def envelope_store(monkeypatch):
    store = _EnvelopeFirestore()

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


@pytest.fixture
def real_stack(monkeypatch):
    """The store's real transaction bodies against fake Firestore.

    The SDK's own ``@firestore.transactional`` wrapper needs ``_begin`` /
    ``_commit`` on the transaction object, so the decorator is replaced by a
    passthrough; the body, both write-layer budgets, and the lifecycle
    boundary stay the production code paths.
    """

    def transactional(func):
        def passthrough(transaction, *args, **kwargs):
            return func(transaction, *args, **kwargs)

        return passthrough

    monkeypatch.setattr(recording_sessions.firestore, 'transactional', transactional)

    def budget_retry(*a, **kw):
        return run_with_transaction_contention_retry(*a, sleep=lambda _delay: None, random_value=lambda: 0, **kw)

    monkeypatch.setattr(recording_sessions, 'run_with_transaction_contention_retry', budget_retry)


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


# ---------------------------------------------------------------------------
# Renewal: the write a live recording issues every minute.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('envelope', _TIMEOUT_ENVELOPES, ids=lambda e: type(e.cause).__name__)
def test_renewal_drained_sdk_budget_sheds_log_only(envelope_store, caplog, envelope):
    _seed_session(envelope_store)
    envelope_store.read_errors = [
        RetryError('Timeout of 60.0s exceeded', type(envelope.cause)(str(envelope.cause)))
    ] * 50

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert renewed is False
    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert any('lease renewal contended' in record.getMessage() for record in warnings)
    assert not any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


def test_renewal_envelope_warning_carries_no_stack_trace(envelope_store, caplog):
    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 50

    with caplog.at_level('WARNING'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    warnings = [record for record in caplog.records if record.levelname == 'WARNING']
    assert warnings and all(record.exc_info is None for record in warnings)


def test_renewal_envelope_records_no_degradation_event(envelope_store, monkeypatch):
    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 50
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=envelope_store
    )

    assert fallbacks == []


def test_renewal_envelope_commits_nothing(envelope_store):
    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 50
    before = envelope_store.documents[_SESSION_PATH]['lease_expires_at']

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=envelope_store
    )

    assert envelope_store.commits == []
    assert envelope_store.documents[_SESSION_PATH]['lease_expires_at'] == before


def test_renewal_commits_on_the_next_minute_after_the_envelope(envelope_store):
    """The envelope must not wedge the fence: the next renewal commits."""
    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]]

    assert (
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )
        is False
    )
    # Deplete the fence to a minute of runway so the clean renewal after the
    # envelope has a real stamp to land (the runway skip leaves a still-
    # healthy fence untouched by design).
    envelope_store.documents[_SESSION_PATH]['lease_expires_at'] = envelope_store.documents[_SESSION_PATH][
        'lease_expires_at'
    ] - timedelta(minutes=4)
    before = envelope_store.documents[_SESSION_PATH]['lease_expires_at']

    assert (
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )
        is True
    )
    assert envelope_store.documents[_SESSION_PATH]['lease_expires_at'] > before


def test_renewal_envelope_advances_the_lease_by_the_full_duration(envelope_store, monkeypatch):
    started_at = datetime(2026, 10, 22, 16, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(envelope_store, started_at=started_at)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]]

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=envelope_store
    )
    renewed = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=envelope_store
    )

    assert renewed is True
    assert envelope_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_renewal_envelope_between_clean_renewals_keeps_the_fence_healthy(envelope_store):
    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]]
    # Deplete the fence to a minute of runway so the clean renewals after the
    # envelope land real stamps (the runway skip leaves a still-healthy fence
    # untouched by design).
    envelope_store.documents[_SESSION_PATH]['lease_expires_at'] = envelope_store.documents[_SESSION_PATH][
        'lease_expires_at'
    ] - timedelta(minutes=4)
    before = envelope_store.documents[_SESSION_PATH]['lease_expires_at']

    blipped = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=envelope_store
    )
    clean_after = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=envelope_store
    )
    clean_after_that = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=envelope_store
    )

    assert (blipped, clean_after, clean_after_that) == (False, True, True)
    assert envelope_store.documents[_SESSION_PATH]['lease_expires_at'] > before


def test_renewal_commit_side_envelope_is_also_absorbed(envelope_store, caplog):
    """A drained budget on the commit RPC lands the same way."""
    _seed_session(envelope_store)
    envelope_store.write_errors = [_TIMEOUT_ENVELOPES[0]] * 50
    # A fence at the floor keeps this a real write attempt (the runway skip
    # leaves a still-healthy fence untouched by design).
    envelope_store.documents[_SESSION_PATH]['lease_expires_at'] = envelope_store.documents[_SESSION_PATH][
        'lease_expires_at'
    ] - timedelta(minutes=4)

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert renewed is False
    assert envelope_store.commits == []
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_envelope_still_raises_in_enforce_mode(envelope_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 50

    with pytest.raises(RetryError):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )


# ---------------------------------------------------------------------------
# Narrowness at the boundary: the envelope type alone widens nothing.
# ---------------------------------------------------------------------------


def test_renewal_envelope_around_permission_denied_keeps_failed_write(envelope_store, caplog):
    _seed_session(envelope_store)
    envelope_store.read_errors = [
        RetryError('Timeout of 60.0s exceeded', PermissionDenied('permission denied on row'))
    ] * 50

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert renewed is False
    assert any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


def test_renewal_causeless_envelope_keeps_failed_write(envelope_store, caplog):
    """The SDK's evidence-free 'Unknown error' envelope is not a transient."""
    _seed_session(envelope_store)
    envelope_store.read_errors = [RetryError('Unknown error', None)] * 50

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert renewed is False
    assert any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# The other three boundaries shed the same envelope through their own arms.
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


_OPEN_BINDING = {
    'recording_session_id': 'session',
    'conversation_id': 'conversation',
    'lifecycle_version': 1,
    'mapping_conflict': False,
}


def test_open_envelope_sheds_to_the_shadow_legacy_envelope(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['recording_session_id'] == 'session'
    assert binding['lifecycle_version'] is None
    assert binding['lifecycle_phase'] is None
    assert binding['lifecycle_sequence'] is None
    assert any('open contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')


def test_open_probe_envelope_defers_to_the_transactional_open(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))
    _patch_transactional_open(monkeypatch, result=dict(_OPEN_BINDING))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['requires_rollover'] is False
    assert binding['recording_session_id'] == 'session'
    assert any('open probe contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')


def _patch_event_writer(monkeypatch, error: BaseException | None = None, result: dict[str, Any] | None = None) -> None:
    def record_lifecycle_event(*args, **kwargs):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(recording_sessions, 'record_lifecycle_event', record_lifecycle_event)


def test_event_envelope_sheds_to_the_legacy_envelope(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    assert envelope is not None
    assert envelope['recording_session_id'] == 'session'
    assert envelope['lifecycle_version'] is None
    assert envelope['lifecycle_sequence'] is None


def _patch_cleaner(monkeypatch, error: BaseException | None = None, result: bool = False) -> None:
    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )


def test_delete_envelope_keeps_the_empty_generation_log_only(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    with caplog.at_level('WARNING'):
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False
    assert any('cleanup contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')
    assert not any(r.levelname == 'ERROR' and 'cleanup failed' in r.getMessage() for r in caplog.records)


def test_open_envelope_still_raises_in_enforce(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    with pytest.raises(RetryError):
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')


# ---------------------------------------------------------------------------
# SDK truth: the real google.api_core retry produces exactly this envelope.
# ---------------------------------------------------------------------------


def _drain_real_retry(leaf: Callable[[], Any], timeout: float = 0.1) -> Any:
    """Run a retry budget until it drains, mirroring the Firestore transport.

    The predicate and deadline mirror the gapic transport's ``default_retry``
    (``google/cloud/firestore_v1/services/firestore/transports/base.py``:
    ``if_exception_type(DeadlineExceeded, InternalServerError,
    ResourceExhausted, ServiceUnavailable)``, ``deadline=60.0``); only the
    sleeps are scaled so the test drains in tens of milliseconds.
    """
    from google.api_core import retry as api_retry
    from google.api_core.exceptions import InternalServerError as _ISE
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable as _SU

    predicate = api_retry.if_exception_type(DeadlineExceeded, _ISE, ResourceExhausted, _SU)
    return api_retry.retry_target(leaf, predicate, iter([0.03] * 10), timeout=timeout, on_error=None)


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_real_sdk_retry_drains_into_a_classified_envelope(blip):
    """End to end over the installed SDK: a retryable fault that outlives the
    budget comes back as ``RetryError`` whose cause is that fault, and the
    classifier accepts the envelope — the exact production shape, produced by
    the SDK's own code."""
    calls = {'n': 0}

    def leaf() -> None:
        calls['n'] += 1
        raise type(blip)(str(blip))

    with pytest.raises(RetryError) as excinfo:
        _drain_real_retry(leaf)

    assert calls['n'] >= 2, 'the retry actually retried'
    assert isinstance(excinfo.value.cause, type(blip))
    assert is_transient_availability_error(excinfo.value) is True


def test_real_sdk_retry_raises_a_permanent_failure_as_itself():
    """A non-retryable refusal is NOT enveloped: the SDK raises it directly,
    which is why permanent refusals reach the boundary bare."""
    calls = {'n': 0}

    def leaf() -> None:
        calls['n'] += 1
        raise PermissionDenied('permission denied on row')

    with pytest.raises(PermissionDenied):
        _drain_real_retry(leaf)

    assert calls['n'] == 1, 'the retry never replayed a permanent refusal'


def test_real_sdk_retry_recovers_before_the_drain():
    """Positive control: a fault on an early attempt that clears is retried to
    success — no envelope, no exception, the value returns. The budget is
    generous so the wall-clock lane cannot drain before the third attempt."""
    calls = {'n': 0}

    def leaf() -> str:
        calls['n'] += 1
        if calls['n'] < 3:
            raise ServiceUnavailable('503: backend unavailable')
        return 'committed'

    assert _drain_real_retry(leaf, timeout=0.5) == 'committed'
    assert calls['n'] == 3


def test_envelope_cause_identity_matches_the_wrapped_fault():
    """The envelope's ``.cause`` is the fault object itself — the classifier's
    one-level read is exact, not a string match."""
    fault = ServiceUnavailable('503: backend unavailable')
    envelope = RetryError('Timeout of 60.0s exceeded', fault)
    assert _retry_error_cause(envelope) is fault


def test_classifier_accepts_a_subclass_cause_inside_the_envelope():
    """A grpc-specialized 503 subclass as the cause keeps the verdict."""

    class GatewayTimeout(DeadlineExceeded):
        pass

    envelope = RetryError('Timeout of 60.0s exceeded', GatewayTimeout('504'))
    assert is_transient_availability_error(envelope) is True


def test_classifier_rejects_a_quota_envelope():
    """``ResourceExhausted`` (429) is in the transport's retryable set, so a
    sustained quota failure drains into an envelope — but it is not in the
    availability trio: quota pressure is not redial-able, and the envelope
    stays loud, matching the rest of ``database/``."""
    from google.api_core.exceptions import ResourceExhausted

    envelope = RetryError('Timeout of 60.0s exceeded', ResourceExhausted('429: quota'))
    assert is_transient_availability_error(envelope) is False


def test_real_sdk_retry_drains_a_quota_fault_into_an_unclassified_envelope():
    """SDK truth plus narrowness: the transport retries quota faults, so a
    sustained quota drain envelops — and the classifier still refuses it."""
    from google.api_core.exceptions import ResourceExhausted

    calls = {'n': 0}

    def leaf() -> None:
        calls['n'] += 1
        raise ResourceExhausted('429: quota exceeded')

    with pytest.raises(RetryError) as excinfo:
        _drain_real_retry(leaf)

    assert isinstance(excinfo.value.cause, ResourceExhausted)
    assert is_transient_availability_error(excinfo.value) is False


def test_classifier_falls_back_to_dunder_cause_when_the_property_is_absent():
    """A pinned SDK whose ``RetryError`` lacks the property still classifies
    through the raise-site ``__cause__`` chain."""

    class PropertylessRetryError(RetryError):
        @property
        def cause(self):  # noqa: D102 - deliberately broken property
            raise AttributeError('cause')

    envelope = PropertylessRetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))
    envelope.__cause__ = ServiceUnavailable('503: backend unavailable')
    assert is_transient_availability_error(envelope) is True


def test_lifecycle_classifier_accepts_the_envelope_directly():
    """The lifecycle boundary's shared test classifies the envelope through the
    same import — no second classifier to drift."""
    envelope = RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503: backend unavailable'))
    assert lifecycle_service._is_recording_session_transient(envelope) is True


# ---------------------------------------------------------------------------
# Renewal matrix: sequences, sides, attribution, budget ordering.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_renewal_commit_side_trio_envelopes_are_absorbed(envelope_store, caplog, blip):
    _seed_session(envelope_store)
    envelope_store.write_errors = [RetryError('Timeout of 60.0s exceeded', type(blip)(str(blip)))] * 50
    # A fence at the floor keeps this a real write attempt (the runway skip
    # leaves a still-healthy fence untouched by design).
    envelope_store.documents[_SESSION_PATH]['lease_expires_at'] = envelope_store.documents[_SESSION_PATH][
        'lease_expires_at'
    ] - timedelta(minutes=4)

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert renewed is False
    assert envelope_store.commits == []
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_read_then_commit_envelopes_in_one_session(envelope_store, caplog):
    """Both RPC sides of the boundary shed identically across two calls: the
    read-side envelope on one renewal, the commit-side on the next."""
    _seed_session(envelope_store)
    envelope_store.read_errors = [RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))]
    envelope_store.write_errors = [RetryError('Timeout of 60.0s exceeded', DeadlineExceeded('504'))] * 50
    # A fence at the floor keeps both renewals real write attempts (the runway
    # skip leaves a still-healthy fence untouched by design).
    envelope_store.documents[_SESSION_PATH]['lease_expires_at'] = envelope_store.documents[_SESSION_PATH][
        'lease_expires_at'
    ] - timedelta(minutes=4)

    with caplog.at_level('WARNING'):
        first = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )
        second = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert (first, second) == (False, False)
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_sustained_envelope_run_stays_bounded(envelope_store, caplog):
    """Three consecutive enveloped windows: three warnings, zero tracebacks,
    zero commits — the sustained-blip storm is bounded, not a traceback firehose."""
    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 50

    with caplog.at_level('WARNING'):
        outcomes = [
            lifecycle_service.renew_live_recording_session_lease(
                'uid', 'session', 'conversation', firestore_client=envelope_store
            )
            for _ in range(3)
        ]

    assert outcomes == [False, False, False]
    warnings = [r for r in caplog.records if r.levelname == 'WARNING' and 'lease renewal contended' in r.getMessage()]
    assert len(warnings) == 3
    assert all(r.exc_info is None for r in warnings)
    assert envelope_store.commits == []


def test_renewal_budget_replays_contention_before_the_envelope_lands(envelope_store, caplog):
    """Two contention aborts replay on fresh transactions and recover; the
    later envelope on a subsequent renewal sheds log-only — the envelope fix
    must not disturb the budget's ordering."""
    _seed_session(envelope_store)
    envelope_store.read_errors = [
        Aborted('contention'),
        Aborted('contention'),
        RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')),
    ]

    with caplog.at_level('INFO'):
        first = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )
        second = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert first is False and second is True
    retries = [
        r
        for r in caplog.records
        if 'firestore_transaction_contention' in r.getMessage() and 'outcome=retry' in r.getMessage()
    ]
    assert len(retries) == 2


def test_renewal_budget_correlation_names_the_renewal(envelope_store, caplog):
    """The budget's log lines keep the renewal's own operation name — a blipped
    minute stays correlatable with its budget replays."""
    _seed_session(envelope_store)
    envelope_store.read_errors = [
        Aborted('contention'),
        RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')),
    ]

    with caplog.at_level('INFO'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    budget_lines = [r.getMessage() for r in caplog.records if 'firestore_transaction_contention' in r.getMessage()]
    assert budget_lines and all('recording_session_lease_renewal' in m for m in budget_lines)


def test_renewal_expired_id_then_envelope_both_shed_then_commit(envelope_store, caplog):
    """The retired-id restart consumes the next attempt's fresh transaction —
    here that attempt carries the availability envelope, which sheds to the
    transient arm inside the same call; the next clean renewal commits."""
    _seed_session(envelope_store)
    envelope_store.read_errors = [
        InvalidArgument('The referenced transaction has expired or is no longer valid'),
        RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')),
    ]

    with caplog.at_level('WARNING'):
        first = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )
        second = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert (first, second) == (False, True)
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_envelope_warning_names_the_session_identity(envelope_store, caplog):
    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 50

    with caplog.at_level('WARNING'):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    warning = next(r for r in caplog.records if r.levelname == 'WARNING')
    message = warning.getMessage()
    assert 'uid=uid' in message and 'session=session' in message and 'conversation=conversation' in message


def test_renewal_envelope_stays_exc_info_free_at_error_level(envelope_store, caplog):
    """Even an ERROR-level capture shows no traceback: the arm's log shape is
    telemetry, and the boundary emits no lifecycle ERROR at all."""
    import logging as _logging

    _seed_session(envelope_store)
    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 50

    with caplog.at_level(_logging.ERROR):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    lifecycle_records = [r for r in caplog.records if r.name == 'utils.conversations.lifecycle']
    assert lifecycle_records == []
    assert all(r.exc_info is None for r in caplog.records)


def test_renewal_envelope_with_identity_mismatch_still_refuses(envelope_store):
    """The envelope must not widen the identity fence: a mismatched identity
    refuses before the write even when an envelope is queued."""
    _seed_session(envelope_store)
    before = envelope_store.documents[_SESSION_PATH]['lease_expires_at']

    mismatched = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'other-conversation', firestore_client=envelope_store
    )
    assert mismatched is False
    assert envelope_store.documents[_SESSION_PATH]['lease_expires_at'] == before

    envelope_store.read_errors = [_TIMEOUT_ENVELOPES[0]]
    enveloped = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=envelope_store
    )
    assert enveloped is False
    assert envelope_store.documents[_SESSION_PATH]['lease_expires_at'] == before


def test_renewal_begin_rpc_envelope_is_absorbed(envelope_store, caplog):
    """The ``BeginTransaction`` RPC itself rides the same gapic retry: an
    envelope from the transaction factory (before any body ran) is the same
    transient — nothing was written, no transaction even existed."""
    _seed_session(envelope_store)
    envelope_store.begin_errors = [RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))] * 50

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert renewed is False
    assert envelope_store.commits == []
    assert not any(
        record.levelname == 'ERROR' and 'lease renewal failed' in record.getMessage() for record in caplog.records
    )


def test_renewal_begin_rpc_envelope_still_raises_in_enforce(envelope_store, monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _seed_session(envelope_store)
    envelope_store.begin_errors = [RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))] * 50

    with pytest.raises(RetryError):
        lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )


def test_renewal_quota_envelope_keeps_failed_write(envelope_store, caplog):
    """A quota-drained envelope stays loud at the boundary, matching the
    classifier's narrowness."""
    from google.api_core.exceptions import ResourceExhausted

    _seed_session(envelope_store)
    envelope_store.read_errors = [RetryError('Timeout of 60.0s exceeded', ResourceExhausted('429: quota'))] * 50

    with caplog.at_level('ERROR', logger='utils.conversations.lifecycle'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )

    assert renewed is False
    assert any(
        record.levelname == 'ERROR' and 'recording session lease renewal failed' in record.getMessage()
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# Open boundary: the real transactional stack over fake Firestore.
# ---------------------------------------------------------------------------


def test_open_real_stack_envelope_sheds_to_the_legacy_envelope(real_stack, caplog):
    """The probe read AND the transactional open both envelope over the real
    store code (no patched store seams): both warnings fire, the legacy
    envelope is returned, and nothing is written."""
    store = _EnvelopeFirestore()
    store.read_errors = [RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))] * 50

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session(
            'uid', 'session', 'conversation', firestore_client=store
        )

    assert binding['lifecycle_version'] is None
    assert binding['lifecycle_phase'] is None
    messages = [r.getMessage() for r in caplog.records if r.levelname == 'WARNING']
    assert any('open probe contended' in m for m in messages)
    assert any('open contended' in m for m in messages)
    assert not any(r.levelname == 'ERROR' and 'persistence failed' in r.getMessage() for r in caplog.records)


def test_open_real_stack_after_envelope_next_open_binds_cleanly(real_stack):
    """The enveloped open must not poison the next reconnect: a clean open
    creates the durable binding and reports no rollover."""
    store = _EnvelopeFirestore()
    store.read_errors = [RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))]

    first = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation', firestore_client=store)
    assert first['lifecycle_version'] is None

    second = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation', firestore_client=store)
    assert second['recording_session_id'] == 'session'
    assert second.get('requires_rollover') is False


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_open_patched_trio_envelopes_shed_identically(monkeypatch, caplog, blip):
    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_transactional_open(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', type(blip)(str(blip))))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['lifecycle_version'] is None
    assert any('open contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')


def test_open_envelope_records_no_degradation_event(monkeypatch):
    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_transactional_open(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert fallbacks == []


def test_open_envelope_in_shadow_mode_sheds_to_the_same_envelope(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['lifecycle_version'] is None
    assert binding['mapping_conflict'] is False
    assert any('open contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')


def test_open_envelope_warning_names_uid_session_and_proposed(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch)
    _patch_transactional_open(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    with caplog.at_level('WARNING'):
        lifecycle_service.open_live_recording_session('uid', 'session', 'proposed-id')

    warning = next(r for r in caplog.records if 'open contended' in r.getMessage())
    message = warning.getMessage()
    assert 'uid=uid' in message and 'session=session' in message and 'proposed=proposed-id' in message


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_probe_trio_envelopes_defer_to_the_transactional_open(monkeypatch, caplog, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=RetryError('Timeout of 60.0s exceeded', type(blip)(str(blip))))
    _patch_transactional_open(monkeypatch, result=dict(_OPEN_BINDING))

    with caplog.at_level('WARNING'):
        binding = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert binding['requires_rollover'] is False
    assert any('open probe contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')


def test_probe_envelope_around_a_permanent_failure_still_raises(monkeypatch):
    """The probe arm re-raises what it could not classify — the envelope
    itself, whose traceback still names the wrapped refusal."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_open_probe(monkeypatch, probe_error=RetryError('Timeout of 60.0s exceeded', PermissionDenied('denied')))

    with pytest.raises(RetryError) as excinfo:
        lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')

    assert isinstance(excinfo.value.cause, PermissionDenied)


# ---------------------------------------------------------------------------
# Event boundary matrix.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_event_trio_envelopes_shed_to_the_legacy_envelope(monkeypatch, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', type(blip)(str(blip))))

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    assert envelope is not None
    assert envelope['recording_session_id'] == 'session'
    assert envelope['lifecycle_version'] is None
    assert envelope['lifecycle_sequence'] is None


def test_event_envelope_records_no_degradation_event(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    assert fallbacks == []


def test_event_envelope_in_shadow_mode_sheds_to_the_same_envelope(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')
    _patch_event_writer(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    envelope = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    assert envelope is not None
    assert envelope['lifecycle_phase'] is None
    assert envelope['lifecycle_sequence'] is None


def test_event_envelope_still_raises_in_enforce(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_event_writer(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    with pytest.raises(RetryError):
        lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')


def test_event_envelope_warning_names_uid_session_and_conversation(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_event_writer(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    with caplog.at_level('WARNING'):
        lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    warning = next(r for r in caplog.records if 'event contended' in r.getMessage())
    message = warning.getMessage()
    assert 'uid=uid' in message and 'session=session' in message and 'conversation=conversation' in message


def test_accepted_event_after_an_envelope_returns_the_durable_envelope(monkeypatch):
    """The envelope is consumed by the blipped append, not remembered: the next
    accepted callback returns the store's own durable envelope."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    results = [
        RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')),
        {'accepted': True, 'recording_session_id': 'session', 'conversation_id': 'conversation'},
    ]

    def record_lifecycle_event(*args, **kwargs):
        result = results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(recording_sessions, 'record_lifecycle_event', record_lifecycle_event)

    first = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')
    second = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')

    assert first['lifecycle_version'] is None
    assert second['accepted'] is True


def test_event_real_stack_envelope_sheds_to_the_legacy_envelope(real_stack, caplog):
    """The real record_lifecycle_event stack over fake Firestore: the envelope
    fires from the transactional body's first read and sheds log-only."""
    store = _EnvelopeFirestore()
    _seed_session(store)
    store.read_errors = [RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))] * 50

    with caplog.at_level('WARNING'):
        envelope = lifecycle_service.record_recording_session_event(
            'uid', 'session', 'conversation', 'processing', firestore_client=store
        )

    assert envelope is not None
    assert envelope['lifecycle_version'] is None
    assert any('event contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')
    assert not any(r.levelname == 'ERROR' and 'persistence failed' in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Cleanup boundary matrix.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('blip', _BLIPS, ids=lambda b: type(b).__name__)
def test_delete_trio_envelopes_keep_the_empty_generation_log_only(monkeypatch, caplog, blip):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', type(blip)(str(blip))))

    with caplog.at_level('WARNING'):
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False
    assert any('cleanup contended' in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')
    assert not any(r.levelname == 'ERROR' and 'cleanup failed' in r.getMessage() for r in caplog.records)


def test_delete_envelope_records_no_degradation_event(monkeypatch):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert fallbacks == []


def test_delete_envelope_is_mode_independent(monkeypatch):
    """Cleanup fail-open only ever delays a delete of an empty row: enforce
    mode changes nothing, exactly as for the single-blip shape."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    _patch_cleaner(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False


def test_delete_envelope_touches_no_physical_cleanup(monkeypatch, cleanup_seams):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False
    assert cleanup_seams == []


def test_delete_envelope_leaves_the_out_param_clean(monkeypatch, caplog):
    """A blipped delete must not reason about a snapshot the envelope prevented."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    received: dict[str, Any] = {}

    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        out = kwargs.get('deleted_conversation')
        if out is not None:
            received.update(out)
        raise RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503'))

    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )

    with caplog.at_level('WARNING'):
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert deleted is False
    assert received == {}


def test_delete_envelope_warning_names_uid_conversation_and_session(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    _patch_cleaner(monkeypatch, error=RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')))

    with caplog.at_level('WARNING'):
        lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    warning = next(r for r in caplog.records if 'cleanup contended' in r.getMessage())
    message = warning.getMessage()
    assert 'uid=uid' in message and 'conversation=conversation' in message and 'session=session' in message


def test_delete_success_after_an_envelope_still_deletes(monkeypatch, cleanup_seams):
    """The enveloped delete consumed nothing: the next clean delete runs the
    full physical cleanup and passes the snapshot through."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    results = [RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503')), True]

    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        result = results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )

    first = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')
    second = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert first is False
    assert second is True
    assert cleanup_seams == ['index', 'photos', 'audio']


# ---------------------------------------------------------------------------
# Cross-boundary: one envelope, every writer, one verdict.
# ---------------------------------------------------------------------------


def test_all_four_boundaries_shed_the_same_envelope(monkeypatch, envelope_store, caplog):
    """The renewal, open, event and cleanup arms classify the envelope
    identically — one classifier, four consumers, no per-boundary drift."""
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'dual_write')
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    envelope = RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503: backend unavailable'))
    _seed_session(envelope_store)
    envelope_store.read_errors = [
        RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503: backend unavailable'))
    ]

    def create_or_get_recording_session(*args, **kwargs):
        raise RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503: backend unavailable'))

    def record_lifecycle_event(*args, **kwargs):
        raise RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503: backend unavailable'))

    def tombstone_and_delete_empty_conversation(*args, **kwargs):
        raise RetryError('Timeout of 60.0s exceeded', ServiceUnavailable('503: backend unavailable'))

    _patch_open_probe(monkeypatch)
    monkeypatch.setattr(recording_sessions, 'create_or_get_recording_session', create_or_get_recording_session)
    monkeypatch.setattr(recording_sessions, 'record_lifecycle_event', record_lifecycle_event)
    monkeypatch.setattr(
        recording_sessions, 'tombstone_and_delete_empty_conversation', tombstone_and_delete_empty_conversation
    )

    with caplog.at_level('WARNING'):
        renewed = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=envelope_store
        )
        opened = lifecycle_service.open_live_recording_session('uid', 'session', 'conversation')
        event = lifecycle_service.record_recording_session_event('uid', 'session', 'conversation', 'processing')
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conversation', 'session')

    assert renewed is False
    assert opened['lifecycle_version'] is None
    assert event['lifecycle_version'] is None
    assert deleted is False
    assert fallbacks == []
    assert not any(r.levelname == 'ERROR' and r.name == 'utils.conversations.lifecycle' for r in caplog.records)


# ---------------------------------------------------------------------------
# Controller cadence, end to end: the real boundary feeding the real redrive.
# ---------------------------------------------------------------------------


class _CadenceClock:
    def __init__(self, start: datetime) -> None:
        self.value = start

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: Any) -> datetime:
        self.value = self.value + timedelta(**kwargs)
        return self.value


class _CadenceHost:
    """Drives the controller's real redrive against the real lifecycle renewal
    over the envelope store, recording waits."""

    def __init__(self, store: _EnvelopeFirestore, clock: _CadenceClock) -> None:
        self.request = SimpleNamespace(uid='uid')
        self.state = SimpleNamespace(current_conversation_id='conversation')
        self.recording_session_id = 'session'
        self.clock = clock
        self.store = store
        self.waits: list[float] = []
        self.spawned: list[asyncio.Task] = []
        self.persistence = SimpleNamespace(call=self._call)

    async def _call(self, fn, *args, **kwargs):
        kwargs.setdefault('firestore_client', self.store)
        return fn(*args, **kwargs)

    def spawn(self, coro, *, name: str):
        self.spawned.append(asyncio.create_task(coro, name=name))
        return self.spawned[-1]

    async def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        await asyncio.sleep(0)
        return False


def _cadence_fixture() -> tuple[_EnvelopeFirestore, _CadenceHost, _CadenceClock, LiveConversationController]:
    clock = _CadenceClock(datetime(2026, 10, 22, 16, 30, tzinfo=timezone.utc))
    store = _EnvelopeFirestore()
    _seed_session(store, started_at=clock.value)
    host = _CadenceHost(store, clock)
    controller = LiveConversationController(host, clock=clock)
    return store, host, clock, controller


async def test_enveloped_cycle_redrives_to_a_committed_fence(real_stack, monkeypatch):
    """Three enveloped renewals inside one cycle feed the redrive's short
    waits, and the cycle's last attempt commits — the fence advances by the
    full duration inside the same minute instead of decaying it."""
    from routers.listen.conversations import RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS

    store, host, clock, controller = _cadence_fixture()
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 3

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = _SESSION_PATH
    assert store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * 3


async def test_converged_cycle_renews_idempotently_the_next_minute(real_stack, monkeypatch):
    from routers.listen.conversations import RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS

    store, host, clock, controller = _cadence_fixture()
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 3

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    path = _SESSION_PATH
    first_commit = store.documents[path]['lease_expires_at']
    # Deplete the fence to a minute of runway so the next cycle's renewal has
    # a real stamp to land (the runway skip leaves a still-healthy fence
    # untouched by design).
    store.documents[path]['lease_expires_at'] = first_commit - timedelta(minutes=4)

    clock.advance(minutes=1)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert store.documents[path]['lease_expires_at'] == (first_commit + timedelta(minutes=1))
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * 3


async def test_full_envelope_exhaustion_is_bounded_across_two_cycles(real_stack, monkeypatch):
    """Every attempt of cycle one envelopes (bounded: four renewals, three
    waits, fence decayed for that minute only), and cycle two commits."""
    from routers.listen.conversations import (
        RECORDING_SESSION_LEASE_RETRY_ATTEMPTS,
    )

    store, host, clock, controller = _cadence_fixture()
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    store.read_errors = [_TIMEOUT_ENVELOPES[0]] * (1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS)
    # A fence at the floor keeps the second cycle's convergence a real write
    # (the runway skip leaves a still-healthy fence untouched by design).
    store.documents[_SESSION_PATH]['lease_expires_at'] = store.documents[_SESSION_PATH]['lease_expires_at'] - timedelta(
        minutes=4
    )

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    path = _SESSION_PATH
    decayed = store.documents[path]['lease_expires_at']
    assert len(host.waits) == RECORDING_SESSION_LEASE_RETRY_ATTEMPTS

    clock.advance(minutes=1)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert store.documents[path]['lease_expires_at'] > decayed


async def test_enveloped_raise_in_enforce_is_contained_in_the_task(real_stack, monkeypatch, caplog):
    """Enforce mode raises the envelope through the boundary; the controller's
    spawned task contains it, logs it once with the session identity, and the
    session survives."""
    import logging as _logging

    store, host, clock, controller = _cadence_fixture()
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    store.read_errors = [_TIMEOUT_ENVELOPES[0]] * 50

    controller.note_audio_activity()
    with caplog.at_level(_logging.ERROR, logger='routers.listen.conversations'):
        await asyncio.gather(*host.spawned)

    assert host.waits == []
    crash_records = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert len(crash_records) == 1
    assert 'uid=uid' in crash_records[0].getMessage()
    assert 'session=session' in crash_records[0].getMessage()
