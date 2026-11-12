"""
Real-failure parity grid: non-fence storage failures keep every loud
settlement the fence fix must not soften, and the landed encoded-path
latch keeps its settlement. Every test drives the real session boundary
with an always-failing writer at one (window position x failure class)
cell and asserts one facet of the loud contract.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import struct
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import InternalServerError, ServiceUnavailable
from prometheus_client import REGISTRY
from starlette.websockets import WebSocketState
from fastapi.websockets import WebSocketDisconnect

import routers.pusher as pusher
from database.legal_holds import DestructiveOperationInProgress
from utils import pusher_audio_projection
from utils.other import audio_outbox, storage
from utils.other.audio_outbox import AudioReceipt
from utils.pusher_protocol import (
    PUSHER_AUDIO_CUSTODY_ACK_OPCODE,
    PUSHER_AUDIO_TIMELINE_ACK_OPCODE,
    pusher_session_outcome,
)
from database import record_audio as record_audio_db

FENCE_WARNING = 'fenced by a destructive operation'
CUSTODY_UNRESOLVED_WARNING = 'custody fence'
MID_SESSION_ERROR = 'Could not process audio'
TAIL_TRACEBACK = 'Durable audio window tail commit failed at shutdown'


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


class FencedAfterArchive:
    """Passes the first ``passes`` archive calls, then answers the fence."""

    def __init__(self, bucket, passes=0):
        self.bucket = bucket
        self.passes = passes
        self.calls = 0

    def __call__(self, uid, raw, prefix, name, metadata, *, data_protection_level=None, manifest_identity=None):
        self.calls += 1
        if self.calls > self.passes:
            raise DestructiveOperationInProgress('external data write blocked by account deletion')
        digest = hashlib.sha256(raw).hexdigest()
        suffix = '.enc' if data_protection_level == 'enhanced' else ''
        path = f'{prefix}/{uid}/{name}/{manifest_identity or digest}.bin{suffix}'
        blob = self.bucket.blob(path)
        if blob.data is not None:
            if (blob.metadata or {}).get('sha256') == digest:
                return path
            raise ValueError('capture identity collision')
        blob.write(raw, {**metadata, 'sha256': digest})
        return path


class AlwaysFailingArchive:
    """Every archive call answers one exception class."""

    def __init__(self, exc_factory):
        self.exc_factory = exc_factory
        self.calls = 0

    def __call__(self, uid, raw, prefix, name, metadata, *, data_protection_level=None, manifest_identity=None):
        self.calls += 1
        raise self.exc_factory()


@pytest.fixture(autouse=True)
def no_shed_wait(monkeypatch):
    waits = []
    monkeypatch.setattr(audio_outbox.time, 'sleep', waits.append)
    return waits


@pytest.fixture
def bucket():
    class _Bucket:
        name = 'fence-audio'

        def __init__(self):
            self.blobs = {}

        def blob(self, name, generation=None):
            return self.blobs.setdefault(name, _FakeBlob(name, self))

    class _FakeBlob:
        def __init__(self, name, bucket_ref):
            self.name = name
            self.bucket_ref = bucket_ref
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
    from contextlib import nullcontext

    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', bucket.name)
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda *a: nullcontext())
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: False)
    return bucket


@pytest.fixture
def session(monkeypatch, real_storage):
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
    monkeypatch.setattr(
        pusher.PusherAudioProjection, 'refresh', lambda self, conversation_id, paths=None, force=False: None
    )
    return real_storage


@pytest.fixture
def spies(monkeypatch):
    state = SimpleNamespace(window_tail_failures=[], would_drop=[], holds=[], finishes=[])
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
    real_finish = pusher.PusherRecordBarrier.finish_recording

    async def spy_finish(barrier, conversation_id):
        state.finishes.append(conversation_id)
        return True

    monkeypatch.setattr(pusher.PusherRecordBarrier, 'finish_recording', spy_finish)
    return state


def _registry_value(name, labels=None):
    try:
        return REGISTRY.get_sample_value(name, labels) or 0.0
    except Exception:
        return 0.0


def _drop_total():
    return _registry_value('pusher_private_cloud_upload_drops_total')


def _policy_fallback_total():
    return _registry_value(
        'omi_fallback_total',
        {
            'component': 'pusher',
            'from_mode': 'private_cloud_sync',
            'to_mode': 'drop',
            'reason': 'policy',
            'outcome': 'exhausted',
        },
    )


def _session_frames(conversation, payloads, start=1000.0, step=0.01):
    frames = []
    if conversation is not None:
        frames.append(struct.pack('<I', 103) + conversation.encode())
    frames.extend(struct.pack('<Id', 101, start + index * step) + pcm for index, pcm in enumerate(payloads))
    return frames


def _payloads(count, fill=1):
    return [struct.pack('<160h', *[fill] * 160) for _ in range(count)]


def _custody_acks(sock):
    header = struct.pack('<I', PUSHER_AUDIO_CUSTODY_ACK_OPCODE)
    return [frame for frame in sock.sent if frame[:4] == header]


def _error_records(caplog, text):
    return [record for record in caplog.records if text in record.getMessage()]


def _traceback_records(caplog):
    return [record for record in caplog.records if record.exc_info]


def _fence_warnings(caplog):
    return [record for record in caplog.records if FENCE_WARNING in record.getMessage()]


async def _drive(sock, uid='owner', sample_rate=16000, audio_custody=1, **kwargs):
    await pusher._websocket_util_trigger(sock, uid, sample_rate, audio_custody=audio_custody, **kwargs)


def _fenced_writer(monkeypatch, bucket, passes=0):
    archive = FencedAfterArchive(bucket, passes)
    monkeypatch.setattr(storage, 'archive_capture_bytes', archive)
    return archive


async def _run_mid_failure_trace(session, spies, caplog, monkeypatch, n, k, exc_cls):
    """Drive a mid-session REAL storage failure at window k of n windows.

    Every archive call answers ``exc_cls``: the commit rides the three
    bounded shed retries, fails, latches the custody-unresolved fence, and
    the receive loop's catch-all ends the session 1011 — the loud behavior
    the fence fix must not soften.
    """

    archive = AlwaysFailingArchive(lambda: exc_cls('storage unavailable'))
    monkeypatch.setattr(storage, 'archive_capture_bytes', archive)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(n)))
    drop_before = _drop_total()
    await _drive(sock)
    return {
        'sock': sock,
        'archive': archive,
        'fence_warnings': _fence_warnings(caplog),
        'window_tail_failures': spies.window_tail_failures,
        'holds': spies.holds,
        'custody_unresolved_records': _error_records(caplog, CUSTODY_UNRESOLVED_WARNING),
        'mid_session_error_records': _error_records(caplog, MID_SESSION_ERROR),
        'traceback_records': _traceback_records(caplog),
        'drop_delta': _drop_total() - drop_before,
    }


async def _run_tail_failure_trace(session, spies, caplog, monkeypatch, n, exc_cls):
    """Drive a REAL storage failure at the shutdown tail of an n-frame session."""

    archive = AlwaysFailingArchive(lambda: exc_cls('storage unavailable'))
    monkeypatch.setattr(storage, 'archive_capture_bytes', archive)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 60)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(n)))
    drop_before = _drop_total()
    await _drive(sock)
    return {
        'sock': sock,
        'fence_warnings': _fence_warnings(caplog),
        'window_tail_failures': spies.window_tail_failures,
        'would_drop': spies.would_drop,
        'holds': spies.holds,
        'traceback_records': _traceback_records(caplog),
        'tail_traceback_records': _error_records(caplog, TAIL_TRACEBACK),
        'drop_delta': _drop_total() - drop_before,
    }


async def _run_encoded_trace(session, spies, caplog, monkeypatch, n):
    """Drive an encoded-path (durable off) session whose uploads answer the fence.

    The landed worker latch must keep its settlement: one refused upload
    latches the session, later batches drop fast, the session stays healthy.
    """

    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')

    class FencedUpload:
        def __init__(self):
            self.calls = 0

        def __call__(self, *args, **kwargs):
            self.calls += 1
            raise DestructiveOperationInProgress('external data write blocked by account deletion')

    upload = FencedUpload()
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(n)))
    drop_before = _drop_total()
    await _drive(sock)
    return {
        'sock': sock,
        'upload': upload,
        'fence_warnings': _fence_warnings(caplog),
        'window_tail_failures': spies.window_tail_failures,
        'mid_session_error_records': _error_records(caplog, MID_SESSION_ERROR),
        'traceback_records': _traceback_records(caplog),
        'drop_delta': _drop_total() - drop_before,
    }


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n02_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n02_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 2, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n03_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n03_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n03_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 3, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n04_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n04_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n04_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n04_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 4, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n05_k05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 5, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n06_k06_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 6, 6, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k06_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 6, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n07_k07_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 7, 7, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k06_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 6, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k07_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 7, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n08_k08_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 8, 8, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k06_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 6, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k07_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 7, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k08_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 8, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n09_k09_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 9, 9, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k06_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 6, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k07_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 7, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k08_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 8, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k09_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 9, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n10_k10_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 10, 10, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k06_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 6, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k07_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 7, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k08_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 8, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k09_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 9, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k10_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 10, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n11_k11_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 11, 11, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k06_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 6, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k07_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 7, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k08_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 8, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k09_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 9, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k10_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 10, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k11_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 11, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_service_unavailable_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, ServiceUnavailable)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_service_unavailable_custody_unresolved_latched(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, ServiceUnavailable)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_service_unavailable_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, ServiceUnavailable)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_internal_server_error_one_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, InternalServerError)
    assert len(result['mid_session_error_records']) == 1


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_internal_server_error_custody_unresolved_latched(
    session, spies, caplog, monkeypatch
):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, InternalServerError)
    assert result['custody_unresolved_records'] != []


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_internal_server_error_no_policy_drop(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, InternalServerError)
    assert result['drop_delta'] == 0


@pytest.mark.asyncio
async def test_mid_failure_n12_k12_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_mid_failure_trace(session, spies, caplog, monkeypatch, 12, 12, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n01_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n01_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n01_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n01_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n01_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n01_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n01_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n01_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n01_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n01_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n01_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n01_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 1, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n02_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n02_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n02_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n02_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n02_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n02_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n02_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n02_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n02_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n02_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n02_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n02_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 2, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n03_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n03_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n03_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n03_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n03_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n03_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n03_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n03_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n03_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n03_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n03_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n03_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 3, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n04_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n04_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n04_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n04_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n04_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n04_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n04_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n04_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n04_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n04_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n04_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n04_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 4, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n05_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n05_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n05_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n05_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n05_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n05_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n05_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n05_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n05_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n05_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n05_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n05_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 5, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n06_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n06_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n06_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n06_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n06_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n06_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n06_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n06_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n06_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n06_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n06_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n06_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 6, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n07_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n07_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n07_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n07_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n07_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n07_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n07_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n07_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n07_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n07_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n07_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n07_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 7, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n08_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n08_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n08_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n08_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n08_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n08_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n08_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n08_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n08_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n08_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n08_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n08_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 8, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n09_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n09_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n09_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n09_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n09_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n09_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n09_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n09_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n09_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n09_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n09_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n09_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 9, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n10_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n10_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n10_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n10_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n10_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n10_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n10_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n10_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n10_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n10_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n10_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n10_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 10, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n11_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n11_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n11_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n11_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n11_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n11_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n11_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n11_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n11_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n11_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n11_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n11_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 11, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n12_service_unavailable_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, ServiceUnavailable)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n12_service_unavailable_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, ServiceUnavailable)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n12_service_unavailable_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, ServiceUnavailable)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n12_service_unavailable_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, ServiceUnavailable)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n12_service_unavailable_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, ServiceUnavailable)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n12_service_unavailable_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, ServiceUnavailable)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_tail_failure_n12_internal_server_error_close_1011(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, InternalServerError)
    assert result['sock'].close_code == 1011


@pytest.mark.asyncio
async def test_tail_failure_n12_internal_server_error_window_tail_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, InternalServerError)
    assert 'window_tail' in result['window_tail_failures']


@pytest.mark.asyncio
async def test_tail_failure_n12_internal_server_error_would_drop_booked(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, InternalServerError)
    assert 'window_tail' in result['would_drop']


@pytest.mark.asyncio
async def test_tail_failure_n12_internal_server_error_tail_hold_placed(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, InternalServerError)
    assert result['holds'] == [('conversation', False)]


@pytest.mark.asyncio
async def test_tail_failure_n12_internal_server_error_traceback_present(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, InternalServerError)
    assert result['traceback_records'] != []


@pytest.mark.asyncio
async def test_tail_failure_n12_internal_server_error_no_deletion_fence_warning(session, spies, caplog, monkeypatch):
    result = await _run_tail_failure_trace(session, spies, caplog, monkeypatch, 12, InternalServerError)
    assert result['fence_warnings'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n01_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 1)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n01_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 1)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n01_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 1)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n01_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 1)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n01_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 1)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n01_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 1)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n01_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 1)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n02_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 2)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n02_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 2)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n02_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 2)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n02_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 2)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n02_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 2)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n02_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 2)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n02_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 2)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n03_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 3)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n03_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 3)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n03_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 3)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n03_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 3)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n03_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 3)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n03_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 3)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n03_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 3)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n04_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 4)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n04_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 4)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n04_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 4)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n04_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 4)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n04_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 4)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n04_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 4)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n04_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 4)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n05_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 5)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n05_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 5)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n05_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 5)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n05_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 5)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n05_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 5)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n05_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 5)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n05_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 5)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n06_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 6)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n06_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 6)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n06_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 6)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n06_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 6)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n06_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 6)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n06_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 6)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n06_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 6)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n07_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 7)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n07_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 7)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n07_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 7)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n07_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 7)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n07_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 7)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n07_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 7)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n07_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 7)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n08_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 8)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n08_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 8)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n08_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 8)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n08_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 8)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n08_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 8)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n08_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 8)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n08_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 8)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n09_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 9)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n09_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 9)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n09_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 9)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n09_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 9)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n09_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 9)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n09_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 9)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n09_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 9)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n10_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 10)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n10_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 10)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n10_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 10)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n10_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 10)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n10_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 10)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n10_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 10)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n10_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 10)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n11_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 11)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n11_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 11)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n11_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 11)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n11_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 11)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n11_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 11)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n11_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 11)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n11_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 11)
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_encoded_latch_n12_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 12)
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_encoded_latch_n12_one_upload_attempt(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 12)
    assert result['upload'].calls == 1


@pytest.mark.asyncio
async def test_encoded_latch_n12_fence_warning_present(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 12)
    assert len(result['fence_warnings']) >= 1


@pytest.mark.asyncio
async def test_encoded_latch_n12_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 12)
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n12_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 12)
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_encoded_latch_n12_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 12)
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_encoded_latch_n12_policy_drop_once(session, spies, caplog, monkeypatch):
    result = await _run_encoded_trace(session, spies, caplog, monkeypatch, 12)
    assert result['drop_delta'] == 1
