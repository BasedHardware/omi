"""The empty-generation audio sweep survives every fault the GCS SDK itself retries.

Failure-Class: FC-post-commit-index-maintenance-terminal — work that runs after
the authoritative write has already committed is best-effort, and a momentary
fault in it may not rewrite the committed outcome as a failure. Sibling
instance of FC-typed-failure-collapsed-to-generic: GCS-specific retryable
faults were collapsed into the sweep's generic catch-all.

The empty-generation delete commits the Firestore row first and reclaims the
conversation's private-cloud audio second. The reclaim runs through
``delete_conversation_audio_files``, a GCS call path: prefix listings, object
deletes, linked-original scans. When any of those raised, the whole sweep
fell into the catch-all — a full ERROR traceback plus an
``omi_fallback_total`` exhausted event — reclassifying the already-committed
delete as a failed write on every failing attempt (prod backend-listen, the
``Failed to reclaim unreferenced audio`` traceback family, ×122/30m at the
2026-10-14 sensor window; line 786 in the deployed traceback).

The classification boundary was the bug's root: ``_is_storage_blip`` reused
the Firestore availability trio (503/504/500 and the drained-retry envelope),
but this boundary is GCS, and the storage SDK retries a different, wider set
(``google.cloud.storage.retry._RETRYABLE_TYPES``): 429 rate limits, 502 bad
gateways, the 504 GatewayTimeout spelling, transport connection resets,
chunked-encoding breaks, request timeouts and the auth-transport envelope.
Every one of those escaped as an unknown failure with its traceback.

Guards:
- the blip classifier mirrors the GCS SDK's own retry predicate exactly —
  every type the SDK itself retries is a deferral, nothing quieter is;
- a deferral owns its convergence: for a terminal (already-deleted) empty
  generation no serving path revisits the prefixes, so waiting for "the next
  reclamation" waited forever — the sweep now re-arms itself on a detached
  daemon thread for a bounded number of passes, and a retry that still fails
  loudly reports through the same arms instead of dying silently;
- permanent refusals (permission, bad request, 404) and truly unknown
  failures keep the failed-write classification with traceback and event;
- the purge verifier's residual signal and the registered-audio retention
  keep their existing arms (tick-182 regressions).

RED on the parent commit: the 429/502/transport tests fail with the catch-all
classification, and the retry-ownership tests fail on the un-owned deferral.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import (
    BadGateway,
    BadRequest,
    DeadlineExceeded,
    Forbidden,
    GatewayTimeout,
    InternalServerError,
    NotFound,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)
from google.auth.exceptions import TransportError
from requests.exceptions import ChunkedEncodingError as RequestsChunkedEncodingError
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from utils.conversations import lifecycle as lifecycle_service

# ── A. The blip boundary mirrors the GCS SDK's own retry predicate ──────────


def test_rate_limit_is_a_blip():
    assert lifecycle_service._is_storage_blip(TooManyRequests('429: rate limited'))


def test_bad_gateway_is_a_blip():
    assert lifecycle_service._is_storage_blip(BadGateway('502: bad gateway'))


def test_gateway_timeout_spelling_is_a_blip():
    """GCS answers sustained load with HTTP 504 ``GatewayTimeout``; the Firestore
    trio only knew the ``DeadlineExceeded`` spelling."""
    assert lifecycle_service._is_storage_blip(GatewayTimeout('504: gateway timeout'))


def test_deadline_exceeded_spelling_stays_a_blip():
    assert lifecycle_service._is_storage_blip(DeadlineExceeded('504: deadline exceeded'))


def test_service_unavailable_stays_a_blip():
    assert lifecycle_service._is_storage_blip(ServiceUnavailable('503: unavailable'))


def test_internal_server_error_stays_a_blip():
    assert lifecycle_service._is_storage_blip(InternalServerError('500: internal'))


def test_transport_connection_reset_is_a_blip():
    """The storage client's transports raise a bare ``ConnectionError`` outside
    the SDK's retry-wrapped calls (listing page iteration, downloads)."""
    assert lifecycle_service._is_storage_blip(ConnectionError('connection reset by peer'))


def test_requests_connection_error_is_a_blip():
    assert lifecycle_service._is_storage_blip(RequestsConnectionError('dial failed'))


def test_requests_timeout_is_a_blip():
    assert lifecycle_service._is_storage_blip(RequestsTimeout('read timed out'))


def test_requests_chunked_encoding_error_is_a_blip():
    assert lifecycle_service._is_storage_blip(RequestsChunkedEncodingError('broken chunk'))


def test_auth_transport_error_is_a_blip():
    assert lifecycle_service._is_storage_blip(TransportError('token endpoint unreachable'))


def test_drained_envelope_around_rate_limit_is_a_blip():
    assert lifecycle_service._is_storage_blip(RetryError('drained', TooManyRequests('429')))


def test_drained_envelope_around_bad_gateway_is_a_blip():
    assert lifecycle_service._is_storage_blip(RetryError('drained', BadGateway('502')))


def test_drained_envelope_around_transport_reset_is_a_blip():
    assert lifecycle_service._is_storage_blip(RetryError('drained', ConnectionError('reset')))


def test_causeless_envelope_stays_loud():
    assert not lifecycle_service._is_storage_blip(RetryError('drained', None))


def test_classifier_refuses_every_permanent_shape():
    assert not lifecycle_service._is_storage_blip(Forbidden('bucket policy'))
    assert not lifecycle_service._is_storage_blip(BadRequest('bad request'))
    assert not lifecycle_service._is_storage_blip(NotFound('gone'))
    assert not lifecycle_service._is_storage_blip(PermissionError('refused'))
    assert not lifecycle_service._is_storage_blip(ValueError('unrelated'))


def test_classifier_matches_the_storage_sdk_retryable_types():
    """The authoritative mirror: every exception type the installed storage SDK
    itself retries classifies as a deferral."""
    from google.cloud.storage.retry import _RETRYABLE_TYPES

    for exc_type in _RETRYABLE_TYPES:
        probe = exc_type('sdk-retryable probe')
        assert lifecycle_service._is_storage_blip(probe), f'{exc_type.__name__} must be a blip'


def test_classifier_matches_the_sdk_envelope_over_retryable_types():
    """The SDK's drained-retry envelope around any retryable type is the same
    bounded transient one layer up."""
    from google.cloud.storage.retry import _RETRYABLE_TYPES

    for exc_type in _RETRYABLE_TYPES:
        envelope = RetryError('Timeout of 120.0s exceeded', exc_type('probe'))
        assert lifecycle_service._is_storage_blip(envelope), f'envelope({exc_type.__name__}) must be a blip'


# ── B. A deferral arms the sweep's own retry ────────────────────────────────


class _RetrySpy:
    """Capture ``_schedule_sweep_retry`` calls instead of arming threads."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, tuple]] = []

    def __call__(self, attempt: Any, args: tuple, **kwargs: Any) -> bool:
        self.calls.append((attempt, args))
        return True


@pytest.fixture()
def retry_spy(monkeypatch) -> _RetrySpy:
    spy = _RetrySpy()
    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', spy, raising=False)
    return spy


def _fallback_spy(monkeypatch) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    monkeypatch.setattr(
        lifecycle_service,
        'record_fallback',
        lambda **kwargs: events.append(kwargs),
        raising=False,
    )
    return events


def _failing_sweep(monkeypatch, error: BaseException) -> None:
    def failing(*a: Any, **k: Any) -> None:
        raise error

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)


def test_rate_limit_deferral_arms_the_sweep_retry(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, TooManyRequests('429: rate limited'))
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and deferred[0].levelno == 30, 'a deferral is a warning, not a traceback'
    assert deferred[0].exc_info is None
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls, 'the deferral must arm its own retry'
    attempt, args = retry_spy.calls[0]
    assert args == ('uid', 'conv'), 'the retry re-attacks the exact same sweep'


def test_bad_gateway_deferral_arms_the_sweep_retry(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, BadGateway('502'))
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)
    assert retry_spy.calls, 'a 502 is the same owned deferral'


def test_transport_reset_deferral_arms_the_sweep_retry(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, ConnectionError('connection reset'))
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)
    assert retry_spy.calls, 'a transport reset is the same owned deferral'


def test_rate_limit_deferral_emits_no_degradation_event(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, TooManyRequests('429'))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert fallbacks == [], 'a deferral is not an omi_fallback_total exhaustion'


def test_drained_envelope_deferral_arms_the_sweep_retry(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, RetryError('drained', BadGateway('502')))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)
    assert retry_spy.calls and fallbacks == []


# ── C. The retry converges — bounded, loud on exhaustion, quiet on success ──


class _SyncThread:
    """Run the retry body inline: deterministic mechanics without wall time."""

    def __init__(self, target=None, name=None, daemon=None):
        self._target = target
        self.name = name
        self.daemon = daemon

    def start(self) -> None:
        self._target()


def test_sweep_retry_succeeds_on_its_first_pass():
    sleeps: list[float] = []
    attempts: list[tuple] = []

    def sweep(uid, conversation_id):
        attempts.append((uid, conversation_id))

    started = lifecycle_service._schedule_sweep_retry(
        sweep,
        ('uid', 'conv'),
        passes=2,
        delay=5.0,
        start_thread=_SyncThread,
        sleep=sleeps.append,
    )

    assert started is True
    assert attempts == [('uid', 'conv')], 'one clean pass reclaims and stops'
    assert sleeps == [5.0], 'exactly one bounded pause before the pass'


def test_sweep_retry_reclaims_after_one_more_blip():
    sleeps: list[float] = []
    attempts: list[int] = []

    def flippy(uid, conversation_id):
        attempts.append(1)
        if len(attempts) == 1:
            raise ServiceUnavailable('still blipping')

    lifecycle_service._schedule_sweep_retry(
        flippy,
        ('uid', 'conv'),
        passes=2,
        delay=5.0,
        start_thread=_SyncThread,
        sleep=sleeps.append,
    )

    assert len(attempts) == 2, 'the retry re-attacked after the blip'
    assert sleeps == [5.0, 5.0], 'one pause per pass, bounded'


def test_sweep_retry_exhausts_loudly_after_its_budget(monkeypatch, caplog):
    sleeps: list[float] = []
    attempts: list[int] = []

    def always_blip(uid, conversation_id):
        attempts.append(1)
        raise TooManyRequests('429 forever')

    with caplog.at_level('ERROR'):
        lifecycle_service._schedule_sweep_retry(
            always_blip,
            ('uid', 'conv'),
            passes=2,
            delay=1.0,
            start_thread=_SyncThread,
            sleep=sleeps.append,
        )

    assert len(attempts) == 2, 'the budget bounds the re-attacks'
    assert len(sleeps) == 2
    exhausted = [r for r in caplog.records if 'Unreferenced audio sweep retry exhausted' in r.getMessage()]
    assert exhausted and exhausted[0].levelno >= 40, 'the final exhaustion stays loud'
    assert exhausted[0].exc_info is not None, 'the last fault is reported, not swallowed'


def test_sweep_retry_keeps_the_loud_arm_on_a_permanent_failure(monkeypatch, caplog):
    """A retry that meets a permanent refusal reports it immediately instead of
    burning its remaining passes against work that cannot succeed."""
    sleeps: list[float] = []
    attempts: list[int] = []

    def refusing(uid, conversation_id):
        attempts.append(1)
        raise Forbidden('bucket policy refuses the delete')

    with caplog.at_level('ERROR'):
        lifecycle_service._schedule_sweep_retry(
            refusing,
            ('uid', 'conv'),
            passes=2,
            delay=1.0,
            start_thread=_SyncThread,
            sleep=sleeps.append,
        )

    assert len(attempts) == 1, 'a permanent failure is not re-attacked'
    assert len(sleeps) == 1, 'no further pauses after the refusal'
    exhausted = [r for r in caplog.records if 'Unreferenced audio sweep retry exhausted' in r.getMessage()]
    assert exhausted and exhausted[0].exc_info is not None


def test_sweep_retry_thread_is_detached_and_named():
    holders: list[Any] = []

    class RecordingThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon
            holders.append(self)

        def start(self) -> None:
            pass

    def clean(uid, conversation_id) -> None:
        return None

    lifecycle_service._schedule_sweep_retry(clean, ('uid', 'conv'), start_thread=RecordingThread)

    assert len(holders) == 1
    assert holders[0].daemon is True, 'the retry must never block interpreter exit'
    assert holders[0].name == 'unreferenced-audio-sweep-retry'
    assert holders[0].target is not None


# ── D. The committed outcome keeps its classification end to end ────────────


class _ContendingStore:
    """Minimal Firestore fake: the empty generation exists and the delete commits."""

    def __init__(self) -> None:
        self.documents: dict = {}

    def collection(self, name: str) -> Any:
        return _StoreCollection(self, (name,))

    def transaction(self, *a: Any, **k: Any) -> Any:
        return _StoreTransaction(self)


class _StoreCollection:
    def __init__(self, store: _ContendingStore, path: tuple) -> None:
        self._store = store
        self._path = path

    def document(self, doc_id: str) -> Any:
        return _StoreDocument(self._store, self._path + (doc_id,))


class _StoreDocument:
    def __init__(self, store: _ContendingStore, path: tuple) -> None:
        self._store = store
        self._path = path

    def collection(self, name: str) -> Any:
        return _StoreCollection(self._store, self._path + (name,))

    def get(self, transaction: Any = None) -> Any:
        return _StoreSnapshot(self._store.documents.get(self._path))

    def delete(self) -> None:
        self._store.documents.pop(self._path, None)


class _StoreSnapshot:
    def __init__(self, data: Any) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Any:
        return dict(self._data) if self._data else {}


class _StoreTransaction:
    def __init__(self, store: _ContendingStore) -> None:
        self._store = store
        self._read_only = False
        self._max_attempts = 1
        self._id = b'test-txn'

    def _rollback(self) -> None:
        pass

    def _clean_up(self) -> None:
        pass

    def _commit(self) -> None:
        pass

    def _add_write_pb(self, *a: Any, **k: Any) -> None:
        pass

    def _reset(self) -> None:
        pass

    def _begin(self, **kwargs: Any) -> None:
        pass

    def get(self, ref: Any) -> Any:
        return ref.get()

    def delete(self, ref: Any) -> None:
        ref.delete()

    def update(self, ref: Any, data: dict) -> None:
        doc = self._store.documents.setdefault(ref._path, {})
        doc.update(data)


def test_delete_stays_committed_when_the_sweep_hits_a_rate_limit(monkeypatch, caplog, retry_spy):
    """End to end: the public delete returns True while the sweep behind it is
    rate-limited — one bounded deferral, the retry armed, no ERROR anywhere."""
    from database import conversations as conversations_db
    from utils.conversations import typesense_index

    store = _ContendingStore()
    store.documents[('users', 'uid', 'conversations', 'conv')] = conversations_db.encode_conversation_for_write(
        'uid', {'id': 'conv', 'status': 'in_progress', 'transcript_segments': []}, 'standard'
    )

    _failing_sweep(monkeypatch, TooManyRequests('429: rate limited'))
    monkeypatch.setattr(typesense_index, 'delete_conversation_index_doc', lambda *a, **k: None)
    monkeypatch.setattr(lifecycle_service.conversations_db, 'delete_conversation_photos', lambda *a, **k: None)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        deleted = lifecycle_service.delete_empty_recording_conversation(
            'uid',
            'conv',
            'session',
            firestore_client=store,
        )

    assert deleted is True, 'the committed delete keeps its outcome'
    assert any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)
    assert not [r for r in caplog.records if r.levelno >= 40], 'no traceback, no ERROR'
    assert fallbacks == [], 'a deferral is not an omi_fallback_total exhaustion'
    assert retry_spy.calls, 'the deferral owns its convergence'


def test_registered_audio_is_still_retained_without_storage_or_retry(monkeypatch, caplog, retry_spy):
    touched: list[tuple] = []
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: touched.append(a),
        raising=False,
    )
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {'audio_files': [{'path': 'chunks/x'}]})

    assert touched == []
    assert retry_spy.calls == [], 'retention is a decision, not a fault — nothing to retry'
    assert any('Retained registered audio for empty conversation' in r.getMessage() for r in caplog.records)


def test_permanent_refusal_keeps_the_failed_write_arm_and_never_retries(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, Forbidden('bucket policy refuses the delete'))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('ERROR'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    failures = [r for r in caplog.records if 'Failed to reclaim unreferenced audio' in r.getMessage()]
    assert failures and failures[0].levelno >= 40 and failures[0].exc_info is not None
    assert fallbacks and fallbacks[0]['outcome'] == 'exhausted'
    assert retry_spy.calls == [], 'a permanent refusal is not deferrable — no retry is armed'


def test_unknown_failure_keeps_the_failed_write_arm_and_never_retries(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, RuntimeError('malformed sweep arguments'))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('ERROR'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    failures = [r for r in caplog.records if 'Failed to reclaim unreferenced audio' in r.getMessage()]
    assert failures and failures[0].exc_info is not None
    assert fallbacks and fallbacks[0]['outcome'] == 'exhausted'
    assert retry_spy.calls == []


def test_residual_arm_still_owns_the_verifier_signal(monkeypatch, caplog, retry_spy):
    """The torn-purge classification is untouched: INFO, no event, no retry —
    the residue converges under the verifier's own next pass."""
    _failing_sweep(monkeypatch, RuntimeError('owner storage purge left 1 objects under chunks/uid/conv/'))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
    assert retained and all(r.levelno == 20 for r in retained)
    assert fallbacks == []
    assert retry_spy.calls == [], 'the verifier signal is not a storage blip'


def test_purge_verifier_still_fails_closed_for_the_account_wipe():
    """The fail-closed contract the wipe depends on is independent of the sweep's
    deferral boundary."""
    from utils.other import storage as storage_mod

    class _LostDeleteBucket:
        def __init__(self, names: set[str]) -> None:
            self.names = set(names)
            self.delete_calls = 0

        def blob(self, name: str) -> Any:
            outer = self
            stuck = SimpleNamespace(name=name)

            def _delete() -> None:
                outer.delete_calls += 1

            stuck.delete = _delete
            return stuck

        def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
            return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]

    bucket = _LostDeleteBucket({'chunks/uid/conv/a.opus'})
    with pytest.raises(RuntimeError, match='owner storage purge left'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')
    assert bucket.delete_calls == 2, 'the settle re-attack happened before giving up'


# ── E. The real storage path delivers its fault to the same boundary ────────


class _RateLimitedBucket:
    """In-memory bucket whose deletes answer 429 once, then succeed."""

    def __init__(self, names: set[str]) -> None:
        self.names = set(names)
        self.rate_limited_once = True
        self.delete_calls = 0

    def blob(self, name: str) -> Any:
        outer = self
        blob = SimpleNamespace(name=name)

        def _delete() -> None:
            outer.delete_calls += 1
            if outer.rate_limited_once:
                outer.rate_limited_once = False
                raise TooManyRequests('429: rate limited')
            outer.names.discard(name)

        blob.delete = _delete
        return blob

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]


def test_real_storage_path_rate_limit_defers_and_arms_the_retry(monkeypatch, caplog, retry_spy):
    """End to end through the actual ``delete_conversation_audio_files``: a 429
    raised by a real bucket walk reaches the lifecycle boundary and is
    classified as a deferral with the retry armed — never the catch-all."""
    from utils.other import storage as storage_mod

    private = _RateLimitedBucket({'chunks/uid/conv/a.opus'})
    derived = _RateLimitedBucket(set())
    monkeypatch.setattr(
        storage_mod,
        '_get_storage_client',
        lambda: SimpleNamespace(bucket=lambda name: private if name == 'private' else derived),
        raising=False,
    )
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private', raising=False)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'derived')
    monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and deferred[0].levelno == 30, 'the real path\u2019s 429 defers without a traceback'
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert fallbacks == []
    assert retry_spy.calls, 'the deferral arms its own retry'
    assert private.delete_calls == 1, 'the sweep stopped at the rate-limited delete'


def test_grpc_specialized_rate_limit_subclass_inside_the_envelope():
    """A transport-specialized 429 subclass as the envelope cause keeps the
    verdict — the classifier reads identity, not exact spellings."""

    class GrpcRateLimit(TooManyRequests):
        pass

    assert lifecycle_service._is_storage_blip(GrpcRateLimit('429'))
    assert lifecycle_service._is_storage_blip(RetryError('drained', GrpcRateLimit('429')))


@pytest.mark.parametrize(
    'error',
    [
        TooManyRequests('429'),
        BadGateway('502'),
        GatewayTimeout('504'),
        ConnectionError('reset'),
        RetryError('drained', ServiceUnavailable('503')),
        TransportError('auth transport'),
    ],
)
def test_every_blip_shape_takes_the_same_owned_deferral(monkeypatch, caplog, retry_spy, error):
    """One boundary behavior for every shape the storage SDK itself retries:
    WARNING, no traceback, no degradation event, retry armed."""
    _failing_sweep(monkeypatch, error)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert fallbacks == []
    assert retry_spy.calls, 'every deferral owns its convergence'


def test_each_deferral_arms_its_own_retry(monkeypatch, retry_spy):
    """Two deferred sweeps arm two retries: ownership is per boundary crossing,
    so one conversation's exhausted budget never cancels another's."""
    _failing_sweep(monkeypatch, TooManyRequests('429'))
    _fallback_spy(monkeypatch)

    lifecycle_service._discard_unreferenced_audio('uid', 'conv-a', {})
    lifecycle_service._discard_unreferenced_audio('uid', 'conv-b', {})

    assert [args for _, args in retry_spy.calls] == [('uid', 'conv-a'), ('uid', 'conv-b')]
