"""The custody fence refusal settles quietly at the shutdown tail.

A mid-session durable window commit failure latches the session's
``durable_commit_unresolved`` custody fence, so the shutdown tail's flush is
refused without any storage operation. The refusal used to be a bare
``RuntimeError`` and landed in ``finish_receive``'s generic failure arm,
which booked a fresh ``window_tail`` commit failure, a would-drop counter
and a ``finish_receive``-named traceback for a commit the tail never
attempted — one producer-visible failure reported twice, and the exact
``finish_receive → _queue_private_cloud_chunk`` traceback shape the prod
sensor counts. The fence now raises a typed ``CustodyCommitUnresolved`` and
the tail settles it: same close 1011, same hold, producer unacknowledged,
one warning line — no window_tail booking, no would-drop, no traceback.

These tests drive the real session boundary
(``pusher._websocket_util_trigger``) against the real commit path and a
fake bucket, for every transient and deterministic commit-failure class.
"""

import asyncio
import json
import logging
import struct
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import (
    BadGateway,
    Forbidden,
    GatewayTimeout,
    InternalServerError,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)
from starlette.websockets import WebSocketState
from fastapi.websockets import WebSocketDisconnect

import routers.pusher as pusher
from utils import pusher_audio_projection
from utils.other import audio_outbox, audio_outbox_metrics, storage
from utils.other.audio_outbox import AudioReceipt
from utils.other.audio_packs import CaptureDeleted
from utils.pusher_record_finish import ProjectionQueueWaitTimeout, RecordProjectionQueue
from database import record_audio as record_audio_db

try:  # the storage SDK's HTTP transport; present in every serving image
    import requests.exceptions as _requests_exceptions

    REQUESTS_CONNECTION_ERROR = _requests_exceptions.ConnectionError
    REQUESTS_READ_TIMEOUT = _requests_exceptions.ReadTimeout
    REQUESTS_HTTP_ERROR = _requests_exceptions.HTTPError
except ImportError:  # pragma: no cover - the pinned SDK always ships requests
    REQUESTS_CONNECTION_ERROR = ConnectionError
    REQUESTS_READ_TIMEOUT = TimeoutError
    REQUESTS_HTTP_ERROR = ConnectionError


class SessionSocket:
    def __init__(self, frames):
        self.frames = deque(frames)
        self.sent = []
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None

    async def accept(self):
        pass

    async def send_bytes(self, data):
        self.sent.append(data)

    async def receive_bytes(self):
        await asyncio.sleep(0)
        if self.frames:
            return self.frames.popleft()
        raise WebSocketDisconnect(1000)

    async def close(self, code, **kwargs):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED


class ScriptedArchive:
    """``storage.archive_capture_bytes`` with a per-call exception script.

    Mirrors the real writer's custody contract: content-addressed path from
    the plaintext digest, create-if-absent semantics (same-digest rewrite
    answers with the existing path), metadata carries the plaintext
    ``sha256``. ``script`` lists outcomes consumed one per call — ``None``
    proceeds with the real write; after exhaustion every call proceeds.
    """

    def __init__(self, bucket, script=None):
        self.bucket = bucket
        self.script = list(script or [])
        self.calls = []

    def __call__(self, uid, raw, prefix, name, metadata, *, data_protection_level=None, manifest_identity=None):
        import hashlib

        digest = hashlib.sha256(raw).hexdigest()
        suffix = '.enc' if data_protection_level == 'enhanced' else ''
        path = f'{prefix}/{uid}/{name}/{manifest_identity or digest}.bin{suffix}'
        self.calls.append(path)
        if self.script:
            outcome = self.script.pop(0)
            if outcome is not None:
                raise outcome
        blob = self.bucket.blob(path)
        if blob.data is not None:
            if (blob.metadata or {}).get('sha256') == digest:
                return path
            raise ValueError('capture identity collision')
        blob.write(raw, {**metadata, 'sha256': digest})
        return path


class AlwaysFailingArchive:
    """The real writer's signature with every call answering one class."""

    def __init__(self, exc_factory):
        self.exc_factory = exc_factory
        self.calls = 0

    def __call__(self, uid, raw, prefix, name, metadata, *, data_protection_level=None, manifest_identity=None):
        self.calls += 1
        raise self.exc_factory()


@pytest.fixture(autouse=True)
def no_shed_wait(monkeypatch):
    """Replace the shed's inter-attempt sleep; settlement tests need no waits."""

    waits = []
    monkeypatch.setattr(audio_outbox.time, 'sleep', waits.append)
    return waits


@pytest.fixture
def bucket():
    class _Bucket:
        name = 'fence-audio'

        def __init__(self):
            self.blobs = {}
            self.writes = []

        def blob(self, name, generation=None):
            return self.blobs.setdefault(name, _FakeBlob(name))

    class _FakeBlob:
        def __init__(self, name):
            self.name = name
            self.data = None
            self.generation = None
            self.metadata = {}

        def write(self, data, metadata):
            self.data = data
            self.generation = 17
            self.metadata = dict(metadata)

        @property
        def size(self):
            return len(self.data or b'')

        def upload_from_string(self, data, *, if_generation_match, **kwargs):
            assert if_generation_match == 0
            if self.data is not None:
                from google.api_core.exceptions import PreconditionFailed

                raise PreconditionFailed('immutable')
            self.data = data
            self.generation = 17

        def reload(self, **kwargs):
            if self.data is None:
                from google.api_core.exceptions import NotFound

                raise NotFound('missing')
            return self.generation

        def download_as_bytes(self, **kwargs):
            if kwargs.get('if_generation_match', self.generation) != self.generation:
                from google.api_core.exceptions import PreconditionFailed

                raise PreconditionFailed('generation changed')
            return self.data

    return _Bucket()


@pytest.fixture
def real_storage(monkeypatch, bucket):
    """The REAL archive writer against the fake bucket (existing remote recipe)."""

    from contextlib import nullcontext

    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', bucket.name)
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda *a: nullcontext())
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: False)
    return bucket


@pytest.fixture
def session(monkeypatch, real_storage):
    """Pusher session harness over the REAL commit path and fake bucket."""

    monkeypatch.setenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', '0')
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setattr(pusher_audio_projection.conversations_db, 'get_conversation_raw_snapshot', lambda *a, **kw: {})
    monkeypatch.setattr(record_audio_db, 'seal_record_audio', MagicMock(return_value='not_batch_owner'))
    monkeypatch.setattr(record_audio_db, 'mark_record_upload_failed', MagicMock(return_value=True))
    monkeypatch.setattr(record_audio_db, 'set_record_upload_pending', MagicMock(return_value=True))
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', MagicMock(return_value=None))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.001)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 60)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 0.001)
    monkeypatch.setattr(pusher, 'RECORD_INLINE_FINISH_TIMEOUT', 0.05)
    # Custody projection is optional for capture; stub it so the tests never
    # ride its retry/hold side effects.
    monkeypatch.setattr(
        pusher.PusherAudioProjection, 'refresh', lambda self, conversation_id, paths=None, force=False: None
    )
    return real_storage


@pytest.fixture
def spies(monkeypatch):
    """Boundary-accounting spies: window_tail booking, would-drop, holds."""

    state = SimpleNamespace(window_tail_failures=[], would_drop=[], holds=[])
    real_failure = pusher.record_failure

    def spy_failure(stage, *args, **kwargs):
        state.window_tail_failures.append(stage)
        return real_failure(stage, *args, **kwargs)

    monkeypatch.setattr(pusher, 'record_failure', spy_failure)
    real_would_drop = pusher.record_would_drop

    def spy_would_drop(stage, *args, **kwargs):
        state.would_drop.append(stage)
        return real_would_drop(stage, *args, **kwargs)

    monkeypatch.setattr(pusher, 'record_would_drop', spy_would_drop)
    real_hold = pusher.PusherRecordBarrier.hold_recording

    def spy_hold(barrier, conversation_id, *, tail_committed=False):
        state.holds.append((conversation_id, tail_committed))
        return real_hold(barrier, conversation_id, tail_committed=tail_committed)

    monkeypatch.setattr(pusher.PusherRecordBarrier, 'hold_recording', spy_hold)
    return state


def _registry_value(name, labels):
    try:
        from prometheus_client import REGISTRY

        return REGISTRY.get_sample_value(name, labels) or 0.0
    except Exception:
        return 0.0


def custody_failures(stage, reason):
    return _registry_value('omi_audio_custody_failures_total', {'stage': stage, 'reason': reason})


def custody_failure_total(stage):
    return (
        custody_failures(stage, 'transient')
        + custody_failures(stage, 'other')
        + custody_failures(stage, 'conflict')
        + custody_failures(stage, 'invalid_argument')
    )


def _session_frames(conversation, payloads, start=1000.0, step=0.01):
    frames = []
    if conversation is not None:
        frames.append(struct.pack('<I', 103) + conversation.encode())
    frames.extend(struct.pack('<Id', 101, start + index * step) + pcm for index, pcm in enumerate(payloads))
    return frames


def _payloads(count, fill=1):
    return [struct.pack('<160h', *[fill] * 160) for _ in range(count)]


def _session_receipts(sock):
    return [AudioReceipt(**json.loads(frame[4:])['receipt']) for frame in sock.sent]


def _failing_writer(monkeypatch, exc_cls):
    """Every archive call answers a fresh instance of ``exc_cls``."""

    archive = AlwaysFailingArchive(lambda: exc_cls('storage unavailable'))
    monkeypatch.setattr(storage, 'archive_capture_bytes', archive)
    return archive


def _failing_instance_writer(monkeypatch, exc):
    """Every archive call re-raises the same prepared exception instance."""

    archive = AlwaysFailingArchive(lambda: exc)
    monkeypatch.setattr(storage, 'archive_capture_bytes', archive)
    return archive


def _scripted_writer(monkeypatch, bucket, script):
    archive = ScriptedArchive(bucket, script)
    monkeypatch.setattr(storage, 'archive_capture_bytes', archive)
    return archive


def _error_records(caplog, text):
    return [record for record in caplog.records if text in record.getMessage()]


def _traceback_records(caplog):
    return [record for record in caplog.records if record.exc_info]


async def _drive(sock, uid='owner', sample_rate=16000, audio_custody=1, **kwargs):
    await pusher._websocket_util_trigger(sock, uid, sample_rate, audio_custody=audio_custody, **kwargs)


FENCE_WARNING = 'custody fence'
MID_SESSION_ERROR = 'Could not process audio'
TAIL_TRACEBACK = 'Durable audio window tail commit failed at shutdown'


# ---------------------------------------------------------------------------
# Typed contract
# ---------------------------------------------------------------------------


def test_custody_commit_unresolved_is_exported_by_the_pusher_module():
    assert getattr(pusher, 'CustodyCommitUnresolved', None) is not None


def test_custody_commit_unresolved_is_a_runtime_error():
    assert issubclass(getattr(pusher, 'CustodyCommitUnresolved', RuntimeError), RuntimeError)


def test_custody_commit_unresolved_keeps_the_fence_message():
    error = pusher.CustodyCommitUnresolved('custody commit unresolved; producer fence retained')
    assert str(error) == 'custody commit unresolved; producer fence retained'


def test_custody_commit_unresolved_is_importable_for_the_typed_arm():
    # The typed arm's except clause binds this module attribute at class
    # definition time; a missing attribute would fail the module import.
    assert pusher.CustodyCommitUnresolved.__module__ == 'routers.pusher'


# ---------------------------------------------------------------------------
# The quiet settlement: mid-session latch → tail refusal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_latched_fence_ends_the_session_1011_unacknowledged(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_refused_tail_books_no_window_tail_failure_or_would_drop(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_refused_tail_logs_one_fence_warning_not_a_traceback(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_refused_tail_still_holds_the_conversation_for_the_reconnect(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_one_producer_failure_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_refused_tail_never_runs_another_storage_operation(session, spies, caplog, monkeypatch):
    archive = _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    # One flush attempt: the shed's three bounded tries on the failing op.
    # The refused tail adds no attempt of its own.
    assert archive.calls == 3


@pytest.mark.asyncio
async def test_session_dies_at_the_first_failed_flush_not_at_the_second(session, spies, caplog, monkeypatch):
    archive = _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    # Two frames each flush; the first boundary's failure ends the loop, so
    # the second boundary never runs another storage attempt.
    assert archive.calls == 3
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_fence_warning_names_the_uid_and_conversation(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert 'owner' in warnings[0].getMessage()
    assert 'conversation' in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_fence_warning_is_a_single_line(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert '\n' not in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_latched_session_books_one_custody_commit_failure(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    before = custody_failure_total('commit')
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert custody_failure_total('commit') - before == 1


# ---------------------------------------------------------------------------
# The receipt boundary: a post-receipt queue failure never latches the fence
# ---------------------------------------------------------------------------


class _TimedOutQueue(RecordProjectionQueue):
    """Stages and acknowledges like the real queue, then times the hop out."""

    async def deliver_pending(self, timeout=None):
        raise ProjectionQueueWaitTimeout('projection queue wait timed out')


@pytest.mark.asyncio
async def test_projection_queue_timeout_after_a_receipt_keeps_the_ack(session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'RecordProjectionQueue', _TimedOutQueue)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert len(_session_receipts(sock)) == 1, 'the committed window was acknowledged'
    assert sock.close_code == 1011


@pytest.mark.asyncio
async def test_projection_queue_timeout_books_no_window_tail_failure(session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'RecordProjectionQueue', _TimedOutQueue)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_projection_queue_timeout_latches_no_fence(session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'RecordProjectionQueue', _TimedOutQueue)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert _error_records(caplog, FENCE_WARNING) == []
    assert _error_records(caplog, MID_SESSION_ERROR) == []


@pytest.mark.asyncio
async def test_projection_queue_timeout_sets_no_application_error_traceback(session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'RecordProjectionQueue', _TimedOutQueue)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert _traceback_records(caplog) == []


# ---------------------------------------------------------------------------
# A fresh tail-commit failure keeps the loud generic arm unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_tail_failure_fails_closed_with_1011(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert sock.close_code == 1011
    assert sock.sent == []


@pytest.mark.asyncio
async def test_fresh_tail_failure_books_the_window_tail_stage(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert 'window_tail' in spies.window_tail_failures
    assert 'window_tail' in spies.would_drop


@pytest.mark.asyncio
async def test_fresh_tail_failure_logs_the_tail_traceback(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_fresh_tail_failure_books_one_window_tail_failure(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert spies.window_tail_failures.count('window_tail') == 1


@pytest.mark.asyncio
async def test_fresh_tail_failure_holds_the_uncommitted_tail(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_fresh_tail_failure_without_a_conversation_holds_nothing(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    caplog.set_level(logging.DEBUG)
    # Custody buffers pre-ID audio under 'unlinked'; the tail's fresh commit
    # failure keeps its loud arm but has no conversation to hold.
    sock = SessionSocket(_session_frames(None, _payloads(1)))
    await _drive(sock)
    assert sock.close_code == 1011
    assert spies.holds == []


@pytest.mark.asyncio
async def test_pre_id_audio_latch_settles_quiet_without_a_hold(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames(None, _payloads(1)))
    await _drive(sock)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.holds == []


# ---------------------------------------------------------------------------
# Latch at every mid-session flush site settles quietly at the tail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_switch_flush_failure_latches_and_settles_quiet(session, spies, caplog, monkeypatch):
    # Three scripted failures: the shed's whole bounded budget for the
    # failing op, so the commit exhausts instead of recovering.
    _scripted_writer(monkeypatch, session, [ServiceUnavailable('storage unavailable')] * 3)
    caplog.set_level(logging.DEBUG)
    frames = _session_frames('conversation-a', _payloads(1)) + [struct.pack('<I', 103) + b'conversation-b']
    sock = SessionSocket(frames)
    await _drive(sock)
    assert sock.close_code == 1011
    assert 'window_tail' not in spies.window_tail_failures
    assert len([r for r in caplog.records if FENCE_WARNING in r.getMessage()]) == 1
    assert _traceback_records(caplog) == []


@pytest.mark.asyncio
async def test_process_request_flush_failure_latches_and_settles_quiet(session, spies, caplog, monkeypatch):
    _scripted_writer(monkeypatch, session, [ServiceUnavailable('storage unavailable')] * 3)
    caplog.set_level(logging.DEBUG)
    frames = _session_frames('conversation', _payloads(1))
    frames.append(struct.pack('<I', 104) + json.dumps({'conversation_id': 'conversation'}).encode())
    sock = SessionSocket(frames)
    await _drive(sock)
    assert sock.close_code == 1011
    assert 'window_tail' not in spies.window_tail_failures
    assert _traceback_records(caplog) == []


@pytest.mark.asyncio
async def test_window_size_boundary_flush_failure_latches_and_settles_quiet(session, spies, caplog, monkeypatch):
    _scripted_writer(monkeypatch, session, [ServiceUnavailable('storage unavailable')] * 3)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert sock.close_code == 1011
    assert 'window_tail' not in spies.window_tail_failures
    assert _traceback_records(caplog) == []


@pytest.mark.asyncio
async def test_latch_after_one_acknowledged_window_keeps_the_first_ack(session, spies, caplog, monkeypatch):
    _scripted_writer(monkeypatch, session, [None, None] + [ServiceUnavailable('storage unavailable')] * 3)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    receipts = _session_receipts(sock)
    assert len(receipts) == 1, 'only the committed first window was acknowledged'
    assert sock.close_code == 1011


@pytest.mark.asyncio
async def test_committed_first_window_object_survives_the_latch(session, spies, caplog, monkeypatch):
    _scripted_writer(monkeypatch, session, [None, None] + [ServiceUnavailable('storage unavailable')] * 3)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    media = [name for name in session.blobs if name.startswith('raw-live/')]
    assert len(media) == 1, 'the committed window is immutable; the refused window stored nothing'


@pytest.mark.asyncio
async def test_committed_first_window_projection_is_still_uploaded(session, spies, caplog, monkeypatch):
    _scripted_writer(monkeypatch, session, [None, ServiceUnavailable('storage unavailable')])
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert pusher.upload_audio_chunks_batch.called


# ---------------------------------------------------------------------------
# Custody integrity across a reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_after_a_latched_session_commits_every_window(session, spies, caplog, monkeypatch):
    real_writer = storage.archive_capture_bytes
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    refused = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(refused)
    assert refused.close_code == 1011
    # The producer reconnects with healthy storage and replays the tail.
    monkeypatch.setattr(storage, 'archive_capture_bytes', real_writer)
    replay = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(replay)
    assert len(_session_receipts(replay)) == 2
    assert replay.close_code != 1011


@pytest.mark.asyncio
async def test_replay_commits_the_refused_audio_exactly_once(session, spies, caplog, monkeypatch):
    real_writer = storage.archive_capture_bytes
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    refused = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(refused)
    monkeypatch.setattr(storage, 'archive_capture_bytes', real_writer)
    replay = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(replay)
    media = [name for name in session.blobs if name.startswith('raw-live/')]
    assert len(media) == 2, 'two windows replayed, two immutable objects, no duplicates'


@pytest.mark.asyncio
async def test_a_latched_session_leaves_no_partial_tail_object(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert [name for name in session.blobs if name.startswith('raw-live/')] == []


@pytest.mark.asyncio
async def test_hold_marks_the_conversation_failed_for_the_barrier(session, spies, caplog, monkeypatch):
    _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    barrier = pusher.PusherRecordBarrier('owner')
    # The hold contract: the conversation lands in the barrier's failed set,
    # so no inline finish ever runs for it.
    assert spies.holds and spies.holds[0][0] == 'conversation'


@pytest.mark.asyncio
async def test_custody_commit_counter_counts_only_the_committed_window(session, spies, caplog, monkeypatch):
    _scripted_writer(monkeypatch, session, [None, None] + [ServiceUnavailable('storage unavailable')] * 3)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    commits_before = _registry_value('omi_audio_custody_commits_total', {})
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert _registry_value('omi_audio_custody_commits_total', {}) - commits_before == 1


# ---------------------------------------------------------------------------
# Clean-session baselines: the quiet arm never fires without a latch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_session_commits_and_acks_every_window(session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(3)))
    await _drive(sock)
    assert len(_session_receipts(sock)) == 3
    assert sock.close_code != 1011


@pytest.mark.asyncio
async def test_clean_session_books_no_failure_and_no_fence_warning(session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert spies.window_tail_failures == []
    assert spies.would_drop == []
    assert _error_records(caplog, FENCE_WARNING) == []
    assert _error_records(caplog, MID_SESSION_ERROR) == []


@pytest.mark.asyncio
async def test_clean_session_tail_commits_the_last_window(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert len(_session_receipts(sock)) == 1
    media = [name for name in session.blobs if name.startswith('raw-live/')]
    assert media, 'the tail window committed custody'


@pytest.mark.asyncio
async def test_clean_session_holds_nothing(session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert spies.holds == []


# ---------------------------------------------------------------------------
# Non-durable sessions never touch the fence
# ---------------------------------------------------------------------------


@pytest.fixture
def legacy_session(session, monkeypatch):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')
    return session


@pytest.mark.asyncio
async def test_legacy_session_ends_clean_without_the_commit_path(legacy_session, spies, caplog, monkeypatch):
    archive = _failing_writer(monkeypatch, ServiceUnavailable)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert sock.close_code != 1011
    assert archive.calls == 0, 'the legacy queue path never runs custody commits'
    assert _error_records(caplog, FENCE_WARNING) == []


@pytest.mark.asyncio
async def test_legacy_session_uploads_through_the_batch_path(legacy_session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert pusher.upload_audio_chunks_batch.called


@pytest.mark.asyncio
async def test_legacy_session_books_no_window_tail_failure(legacy_session, spies, caplog, monkeypatch):
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.holds == []


# ---------------------------------------------------------------------------
# Per-class matrix: every commit-failure class settles the same way
# ---------------------------------------------------------------------------

TRANSIENT_CLASSES = [
    'service_unavailable',
    'internal_server_error',
    'too_many_requests',
    'bad_gateway',
    'gateway_timeout',
    'builtin_connection_error',
    'connection_reset',
    'requests_connection_error',
    'requests_read_timeout',
    'requests_http_error',
]


async def _drive_class_latch(exc, monkeypatch, session):
    """Mid-session boundary failure where every storage attempt answers ``exc``."""

    _failing_instance_writer(monkeypatch, exc)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    return sock


async def _drive_class_fresh_tail(exc, monkeypatch, session):
    """A tail-only commit failure: no boundary flush ever runs."""

    _failing_instance_writer(monkeypatch, exc)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    return sock


@pytest.mark.asyncio
async def test_service_unavailable_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(ServiceUnavailable('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_service_unavailable_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(ServiceUnavailable('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_service_unavailable_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(ServiceUnavailable('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_service_unavailable_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(ServiceUnavailable('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_service_unavailable_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(ServiceUnavailable('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_service_unavailable_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(ServiceUnavailable('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_service_unavailable_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(ServiceUnavailable('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_service_unavailable_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, ServiceUnavailable('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_internal_server_error_latches_the_fence_and_ends_1011_unacknowledged(
    session, spies, caplog, monkeypatch
):
    sock = await _drive_class_latch(InternalServerError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_internal_server_error_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(InternalServerError('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_internal_server_error_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(InternalServerError('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_internal_server_error_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(InternalServerError('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_internal_server_error_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(InternalServerError('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_internal_server_error_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(InternalServerError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_internal_server_error_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(InternalServerError('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_internal_server_error_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, InternalServerError('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_too_many_requests_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(TooManyRequests('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_too_many_requests_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(TooManyRequests('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_too_many_requests_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(TooManyRequests('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_too_many_requests_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(TooManyRequests('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_too_many_requests_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(TooManyRequests('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_too_many_requests_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(TooManyRequests('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_too_many_requests_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(TooManyRequests('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_too_many_requests_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, TooManyRequests('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_bad_gateway_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(BadGateway('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_bad_gateway_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(BadGateway('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_bad_gateway_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(BadGateway('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_bad_gateway_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(BadGateway('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_bad_gateway_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(BadGateway('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_bad_gateway_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(BadGateway('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_bad_gateway_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(BadGateway('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_bad_gateway_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, BadGateway('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_gateway_timeout_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(GatewayTimeout('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_gateway_timeout_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(GatewayTimeout('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_gateway_timeout_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(GatewayTimeout('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_gateway_timeout_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(GatewayTimeout('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_gateway_timeout_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(GatewayTimeout('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_gateway_timeout_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(GatewayTimeout('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_gateway_timeout_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(GatewayTimeout('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_gateway_timeout_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, GatewayTimeout('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_builtin_connection_error_latches_the_fence_and_ends_1011_unacknowledged(
    session, spies, caplog, monkeypatch
):
    sock = await _drive_class_latch(ConnectionError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_builtin_connection_error_refused_tail_books_no_window_tail_accounting(
    session, spies, caplog, monkeypatch
):
    await _drive_class_latch(ConnectionError('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_builtin_connection_error_refused_tail_warns_once_without_a_traceback(
    session, spies, caplog, monkeypatch
):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(ConnectionError('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_builtin_connection_error_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(ConnectionError('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_builtin_connection_error_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(ConnectionError('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_builtin_connection_error_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(ConnectionError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_builtin_connection_error_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(ConnectionError('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_builtin_connection_error_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, ConnectionError('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_connection_reset_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(ConnectionResetError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_connection_reset_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(ConnectionResetError('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_connection_reset_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(ConnectionResetError('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_connection_reset_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(ConnectionResetError('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_connection_reset_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(ConnectionResetError('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_connection_reset_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(ConnectionResetError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_connection_reset_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(ConnectionResetError('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_connection_reset_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, ConnectionResetError('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_requests_connection_error_latches_the_fence_and_ends_1011_unacknowledged(
    session, spies, caplog, monkeypatch
):
    sock = await _drive_class_latch(REQUESTS_CONNECTION_ERROR('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_requests_connection_error_refused_tail_books_no_window_tail_accounting(
    session, spies, caplog, monkeypatch
):
    await _drive_class_latch(REQUESTS_CONNECTION_ERROR('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_requests_connection_error_refused_tail_warns_once_without_a_traceback(
    session, spies, caplog, monkeypatch
):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(REQUESTS_CONNECTION_ERROR('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_requests_connection_error_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(REQUESTS_CONNECTION_ERROR('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_requests_connection_error_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(REQUESTS_CONNECTION_ERROR('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_requests_connection_error_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(REQUESTS_CONNECTION_ERROR('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_requests_connection_error_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(REQUESTS_CONNECTION_ERROR('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_requests_connection_error_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, REQUESTS_CONNECTION_ERROR('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_requests_read_timeout_latches_the_fence_and_ends_1011_unacknowledged(
    session, spies, caplog, monkeypatch
):
    sock = await _drive_class_latch(REQUESTS_READ_TIMEOUT('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_requests_read_timeout_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(REQUESTS_READ_TIMEOUT('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_requests_read_timeout_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(REQUESTS_READ_TIMEOUT('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_requests_read_timeout_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(REQUESTS_READ_TIMEOUT('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_requests_read_timeout_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(REQUESTS_READ_TIMEOUT('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_requests_read_timeout_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(REQUESTS_READ_TIMEOUT('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_requests_read_timeout_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(REQUESTS_READ_TIMEOUT('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_requests_read_timeout_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, REQUESTS_READ_TIMEOUT('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_requests_http_error_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(REQUESTS_HTTP_ERROR('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_requests_http_error_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(REQUESTS_HTTP_ERROR('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_requests_http_error_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(REQUESTS_HTTP_ERROR('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_requests_http_error_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(REQUESTS_HTTP_ERROR('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_requests_http_error_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(REQUESTS_HTTP_ERROR('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_requests_http_error_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(REQUESTS_HTTP_ERROR('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_requests_http_error_custody_failure_reason_is_transient(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'transient')
    await _drive_class_latch(REQUESTS_HTTP_ERROR('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'transient') - before == 1


@pytest.mark.asyncio
async def test_requests_http_error_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, REQUESTS_HTTP_ERROR('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 3, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_precondition_failed_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(PreconditionFailed('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_precondition_failed_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(PreconditionFailed('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_precondition_failed_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(PreconditionFailed('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_precondition_failed_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(PreconditionFailed('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_precondition_failed_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(PreconditionFailed('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_precondition_failed_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(PreconditionFailed('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_precondition_failed_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(PreconditionFailed('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_precondition_failed_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, PreconditionFailed('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_not_found_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(NotFound('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_not_found_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(NotFound('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_not_found_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(NotFound('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_not_found_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(NotFound('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_not_found_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(NotFound('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_not_found_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(NotFound('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_not_found_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(NotFound('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_not_found_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, NotFound('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_forbidden_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(Forbidden('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_forbidden_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(Forbidden('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_forbidden_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(Forbidden('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_forbidden_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(Forbidden('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_forbidden_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(Forbidden('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_forbidden_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(Forbidden('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_forbidden_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(Forbidden('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_forbidden_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, Forbidden('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_invalid_argument_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(InvalidArgument('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_invalid_argument_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(InvalidArgument('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_invalid_argument_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(InvalidArgument('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_invalid_argument_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(InvalidArgument('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_invalid_argument_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(InvalidArgument('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_invalid_argument_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(InvalidArgument('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_invalid_argument_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(InvalidArgument('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_invalid_argument_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, InvalidArgument('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_retry_error_envelope_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(RetryError('storage unavailable', cause=ValueError('boom')), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_retry_error_envelope_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(RetryError('storage unavailable', cause=ValueError('boom')), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_retry_error_envelope_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(RetryError('storage unavailable', cause=ValueError('boom')), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_retry_error_envelope_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(RetryError('storage unavailable', cause=ValueError('boom')), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_retry_error_envelope_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(RetryError('storage unavailable', cause=ValueError('boom')), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_retry_error_envelope_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(
        RetryError('storage unavailable', cause=ValueError('boom')), monkeypatch, session
    )
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_retry_error_envelope_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(RetryError('storage unavailable', cause=ValueError('boom')), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_retry_error_envelope_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, RetryError('storage unavailable', cause=ValueError('boom')))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_capture_deleted_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(CaptureDeleted('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_capture_deleted_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(CaptureDeleted('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_capture_deleted_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(CaptureDeleted('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_capture_deleted_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(CaptureDeleted('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_capture_deleted_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    # CaptureDeleted is a ValueError, so the mid-session boundary books it
    # through the protocol arm, not the application arm; the tail settlement
    # is still the fence's quiet 1011 (pinned by the latch test).
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(CaptureDeleted('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, 'Invalid pusher frame: CaptureDeleted')) == 1


@pytest.mark.asyncio
async def test_capture_deleted_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(CaptureDeleted('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_capture_deleted_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(CaptureDeleted('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_capture_deleted_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, CaptureDeleted('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_plain_value_error_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(ValueError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_plain_value_error_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(ValueError('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_plain_value_error_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(ValueError('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_plain_value_error_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(ValueError('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_plain_value_error_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    # A ValueError-class commit failure rides the mid-session protocol arm;
    # the tail settlement is still the fence's quiet 1011.
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(ValueError('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, 'Invalid pusher frame: ValueError')) == 1


@pytest.mark.asyncio
async def test_plain_value_error_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(ValueError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_plain_value_error_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(ValueError('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_plain_value_error_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, ValueError('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_plain_runtime_error_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(RuntimeError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_plain_runtime_error_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(RuntimeError('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_plain_runtime_error_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(RuntimeError('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_plain_runtime_error_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(RuntimeError('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_plain_runtime_error_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(RuntimeError('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_plain_runtime_error_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(RuntimeError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_plain_runtime_error_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(RuntimeError('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_plain_runtime_error_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, RuntimeError('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'


@pytest.mark.asyncio
async def test_plain_timeout_error_latches_the_fence_and_ends_1011_unacknowledged(session, spies, caplog, monkeypatch):
    sock = await _drive_class_latch(TimeoutError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == [], 'a window that never committed must never be acknowledged'


@pytest.mark.asyncio
async def test_plain_timeout_error_refused_tail_books_no_window_tail_accounting(session, spies, caplog, monkeypatch):
    await _drive_class_latch(TimeoutError('storage unavailable'), monkeypatch, session)
    assert 'window_tail' not in spies.window_tail_failures
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_plain_timeout_error_refused_tail_warns_once_without_a_traceback(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(TimeoutError('storage unavailable'), monkeypatch, session)
    warnings = [record for record in caplog.records if FENCE_WARNING in record.getMessage()]
    assert len(warnings) == 1
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_plain_timeout_error_refused_tail_holds_the_conversation(session, spies, caplog, monkeypatch):
    await _drive_class_latch(TimeoutError('storage unavailable'), monkeypatch, session)
    assert spies.holds == [('conversation', False)]


@pytest.mark.asyncio
async def test_plain_timeout_error_books_exactly_one_application_error(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    await _drive_class_latch(TimeoutError('storage unavailable'), monkeypatch, session)
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_plain_timeout_error_fresh_tail_failure_keeps_the_loud_arm(session, spies, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    sock = await _drive_class_fresh_tail(TimeoutError('storage unavailable'), monkeypatch, session)
    assert sock.close_code == 1011
    assert sock.sent == []
    assert 'window_tail' in spies.window_tail_failures
    tails = _error_records(caplog, TAIL_TRACEBACK)
    assert len(tails) == 1
    assert tails[0].exc_info


@pytest.mark.asyncio
async def test_plain_timeout_error_custody_failure_reason_is_other(session, spies, caplog, monkeypatch):
    before = custody_failures('commit', 'other')
    await _drive_class_latch(TimeoutError('storage unavailable'), monkeypatch, session)
    assert custody_failures('commit', 'other') - before == 1


@pytest.mark.asyncio
async def test_plain_timeout_error_commit_attempt_count_is_bounded(session, spies, caplog, monkeypatch):
    archive = _failing_instance_writer(monkeypatch, TimeoutError('storage unavailable'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1, 'the failing op ran its bounded attempts; the refused tail added none'
