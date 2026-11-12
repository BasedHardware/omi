"""v2 discontinuity flush fence settlement grid (durable custody).

Generated settlement grid: every test drives the real pusher session
boundary (``pusher._websocket_util_trigger``) against the real custody
commit path with a fence-refusing writer at one matrix cell
(flush entry x window position x fenced archive op) and asserts one
facet of the policy-latch settlement contract. Expected writer-call and
receipt counts are literals derived from the custody pair contract
(two archive calls per committed window). See
backend/docs/pusher-deletion-fence-custody-settlement.md.
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


async def _run_fence_trace(session, spies, caplog, monkeypatch, entry, n, k, op):
    """Drive one fence cell of the behavior matrix and collect every observable.

    A committed custody window costs exactly two archive calls (media, then
    manifest). ``passes`` lets the calls of windows 1..k-1 (plus the fenced
    window's media call for ``op='manifest'``) proceed and fences the rest.
    """

    if entry == 'size_trigger':
        passes = 2 * (k - 1) + (1 if op == 'manifest' else 0)
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
        frames = _session_frames('conversation', _payloads(n))
        kwargs = {}
    elif entry == 'switch_flush':
        passes = 1 if op == 'manifest' else 0
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 60)
        frames = _session_frames('conversation-a', _payloads(k))
        frames.append(struct.pack('<I', 103) + b'conversation-b')
        frames.extend(_session_frames(None, _payloads(n - k), start=2000.0))
        kwargs = {}
    elif entry == 'discontinuity_flush':
        passes = 1 if op == 'manifest' else 0
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 60)
        frames = _session_frames('conversation', _payloads(k), step=0.0005)
        frames.append(struct.pack('<Id', 101, 1000.0 + k * 0.0005 + 1.0) + _payloads(1)[0])
        if n - k - 1 > 0:
            frames.extend(_session_frames(None, _payloads(n - k - 1), start=1000.0 + k * 0.0005 + 1.0, step=0.0005))
        kwargs = {'audio_timeline': 2}
    else:  # tail_flush
        passes = 1 if op == 'manifest' else 0
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 60)
        frames = _session_frames('conversation', _payloads(n))
        kwargs = {}
    archive = _fenced_writer(monkeypatch, session, passes=passes)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(frames)
    drop_before = _drop_total()
    await _drive(sock, **kwargs)
    if entry == 'size_trigger':
        expected_calls = 2 * (k - 1) + (2 if op == 'manifest' else 1)
        expected_receipts = k - 1
    else:
        expected_calls = 2 if op == 'manifest' else 1
        expected_receipts = 0
    assert archive.calls == expected_calls
    return {
        'sock': sock,
        'archive': archive,
        'custody_acks': _custody_acks(sock),
        'fence_warnings': _fence_warnings(caplog),
        'window_tail_failures': spies.window_tail_failures,
        'would_drop': spies.would_drop,
        'holds': spies.holds,
        'finish_calls': spies.finishes,
        'traceback_records': _traceback_records(caplog),
        'tail_traceback_records': _error_records(caplog, TAIL_TRACEBACK),
        'custody_unresolved_records': _error_records(caplog, CUSTODY_UNRESOLVED_WARNING),
        'mid_session_error_records': _error_records(caplog, MID_SESSION_ERROR),
        'drop_delta': _drop_total() - drop_before,
    }


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n03_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 3, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n04_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 4, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n05_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 5, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n06_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 6, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n07_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 7, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n08_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 8, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n09_k07_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 9, 7, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k07_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 7, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n10_k08_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 10, 8, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k07_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 7, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k08_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 8, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n11_k09_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 11, 9, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k07_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 7, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k08_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 8, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k09_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 9, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n12_k10_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 12, 10, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k07_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 7, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k08_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 8, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k09_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 9, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k10_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 10, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n13_k11_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 13, 11, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k07_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 7, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k08_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 8, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k09_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 9, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k10_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 10, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k11_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 11, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n14_k12_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 14, 12, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k07_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 7, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k08_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 8, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k09_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 9, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k10_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 10, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k11_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 11, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k12_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 12, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n15_k13_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 15, 13, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k01_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 1, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k02_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 2, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k03_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 3, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k04_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 4, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k05_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 5, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k06_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 6, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k07_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 7, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k08_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 8, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k09_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 9, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k10_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 10, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k11_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 11, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k12_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 12, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k13_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 13, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['archive'].calls == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_media_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'media')
    assert 'no retry' in result['fence_warnings'][0].getMessage()


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_close_1000(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['sock'].close_code == 1000


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_no_window_tail_booking(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert 'window_tail' not in result['window_tail_failures']


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_no_would_drop(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['would_drop'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_no_holds(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['holds'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_no_traceback(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_one_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert len(result['fence_warnings']) == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_warning_level(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['fence_warnings'][0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_calls_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['archive'].calls == 2


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_receipts_literal(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert len(result['custody_acks']) == 0


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_drop_counter_once(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['drop_delta'] == 1


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_no_unresolved_warning(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['custody_unresolved_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_no_mid_session_error(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['mid_session_error_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_no_inline_finish(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['finish_calls'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_no_tail_traceback_text(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert result['tail_traceback_records'] == []


@pytest.mark.asyncio
async def test_discontinuity_flush_n16_k14_manifest_warning_names_no_retry(session, spies, caplog, monkeypatch):
    result = await _run_fence_trace(session, spies, caplog, monkeypatch, 'discontinuity_flush', 16, 14, 'manifest')
    assert 'no retry' in result['fence_warnings'][0].getMessage()
