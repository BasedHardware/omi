"""
Typed-contract grid for the deletion-fence settlement: exception
identities and hierarchy, classifier exclusions (the fence is never a
transient or a shed blip), outcome mapping, archive-double semantics,
frame/counter plumbing, and harness helper behavior. Direct unit cells,
no session drives except where marked.
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


def test_deletion_fence_error_is_the_legal_holds_class():
    assert pusher.DestructiveOperationInProgress is DestructiveOperationInProgress


def test_deletion_fence_error_message_is_the_gate_refusal():
    fence = DestructiveOperationInProgress('external data write blocked by account deletion')
    assert str(fence) == 'external data write blocked by account deletion'


def test_deletion_fence_error_carries_no_custody_shed_marker():
    fence = DestructiveOperationInProgress('external data write blocked by account deletion')
    assert getattr(fence, 'custody_shed_exhausted', False) is False


def test_commit_shed_does_not_classify_the_deletion_fence_as_a_blip():
    fence = DestructiveOperationInProgress('external data write blocked by account deletion')
    assert audio_outbox._is_commit_availability_blip(fence) is False


def test_admission_shed_does_not_classify_the_deletion_fence_as_transient():
    fence = DestructiveOperationInProgress('external data write blocked by account deletion')
    from utils.firestore_transient_types import is_transient_availability_error

    assert is_transient_availability_error(fence) is False


def test_authority_unavailable_keeps_its_own_loud_classification():
    from database.legal_holds import LegalHoldAuthorityUnavailable
    from utils.firestore_transient_types import is_transient_availability_error

    assert is_transient_availability_error(LegalHoldAuthorityUnavailable('down')) is False


def test_close_1000_without_application_failure_is_a_success_outcome():
    assert pusher_session_outcome(1000, application_failed=False) == 'success'


def test_close_1001_without_application_failure_is_a_success_outcome():
    assert pusher_session_outcome(1001, application_failed=False) == 'success'


def test_close_1011_stays_a_failure_outcome():
    assert pusher_session_outcome(1011, application_failed=False) == 'failure'


def test_close_1011_with_keepalive_sentence_stays_cancelled():
    assert pusher_session_outcome(1011, application_failed=False, peer_keepalive_timeout=True) == 'cancelled'


def test_application_failed_wins_over_the_close_code():
    assert pusher_session_outcome(1000, application_failed=True) == 'failure'


def test_fenced_archive_double_proceeds_within_its_budget(bucket):
    archive = FencedAfterArchive(bucket, passes=2)
    for _ in range(2):
        archive('owner', b'pcm', 'raw-live', 'w', {}, data_protection_level='standard')
    assert archive.calls == 2
    assert bucket.blobs, 'proceeding calls must land in the fake bucket'


def test_fenced_archive_double_fences_after_its_budget(bucket):
    archive = FencedAfterArchive(bucket, passes=1)
    archive('owner', b'pcm', 'raw-live', 'w', {}, data_protection_level='standard')
    with pytest.raises(DestructiveOperationInProgress):
        archive('owner', b'pcm', 'raw-live', 'w', {}, data_protection_level='standard')
    assert archive.calls == 2


def test_fenced_archive_double_keeps_the_content_addressed_path(bucket):
    archive = FencedAfterArchive(bucket, passes=1)
    path = archive('owner', b'pcm-bytes', 'raw-live', 'w', {}, data_protection_level='standard')
    digest = hashlib.sha256(b'pcm-bytes').hexdigest()
    assert path == f'raw-live/owner/w/{digest}.bin'


def test_fenced_archive_double_marks_enhanced_protection_paths(bucket):
    archive = FencedAfterArchive(bucket, passes=1)
    path = archive('owner', b'pcm-bytes', 'raw-live', 'w', {}, data_protection_level='enhanced')
    assert path.endswith('.bin.enc')


def test_custody_ack_opcode_is_203():
    assert PUSHER_AUDIO_CUSTODY_ACK_OPCODE == 203


def test_timeline_ack_opcode_is_202():
    assert PUSHER_AUDIO_TIMELINE_ACK_OPCODE == 202


def test_drop_counter_is_the_private_cloud_upload_drops_counter():
    before = _drop_total()
    pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc()
    assert _drop_total() == before + 1


def test_policy_fallback_bucket_is_reachable_under_the_recorded_labels():
    from utils.observability.fallback import record_fallback

    before = _policy_fallback_total()
    record_fallback(
        component='pusher',
        from_mode='private_cloud_sync',
        to_mode='drop',
        reason='policy',
        outcome='exhausted',
    )
    assert _policy_fallback_total() == before + 1


def test_session_frames_carry_the_conversation_id_header():
    frames = _session_frames('conv', _payloads(1))
    assert frames[0] == struct.pack('<I', 103) + b'conv'


def test_session_audio_frames_carry_the_v1_header():
    frames = _session_frames(None, _payloads(2), start=10.0, step=0.5)
    assert struct.unpack('<I', frames[0][:4])[0] == 101
    assert struct.unpack('d', frames[0][4:12])[0] == 10.0
    assert struct.unpack('d', frames[1][4:12])[0] == 10.5


def test_payloads_are_sample_aligned_pcm16():
    for payload in _payloads(3):
        assert len(payload) % 2 == 0
        assert len(payload) == 320


def test_custody_ack_filter_selects_only_receipt_frames():
    sock = SimpleNamespace(
        sent=[
            struct.pack('<I', PUSHER_AUDIO_TIMELINE_ACK_OPCODE) + b'x',
            struct.pack('<I', PUSHER_AUDIO_CUSTODY_ACK_OPCODE) + json.dumps({'receipt': {}}).encode(),
        ]
    )
    assert len(_custody_acks(sock)) == 1


def test_traceback_filter_selects_only_exc_info_records(caplog):
    import logging as _logging

    _logging.getLogger('probe').error('plain line')
    try:
        raise ValueError('with traceback')
    except ValueError:
        _logging.getLogger('probe').error('rich line', exc_info=True)
    assert len(_traceback_records(caplog)) == 1


def test_fence_warning_filter_matches_the_latch_phrase(caplog):
    import logging as _logging

    _logging.getLogger('probe').warning(
        'Durable custody window refused: account writes are fenced by a destructive operation (no retry)'
    )
    assert len(_fence_warnings(caplog)) == 1


def test_fenced_writer_helper_installs_the_double(monkeypatch, bucket):
    archive = _fenced_writer(monkeypatch, bucket, passes=0)
    assert isinstance(archive, FencedAfterArchive)
    assert storage.archive_capture_bytes is archive


@pytest.mark.asyncio
async def test_drive_helper_runs_the_real_session_boundary(session):
    sock = SessionSocket([])
    await _drive(sock)
    assert sock.close_code == 1000


def test_deletion_fence_import_survives_module_reload_semantics():
    import importlib

    import database.legal_holds as legal_holds

    importlib.reload(legal_holds)
    assert legal_holds.DestructiveOperationInProgress.__name__ == 'DestructiveOperationInProgress'


def test_legal_hold_gate_error_is_not_the_deletion_fence():
    from database.legal_holds import DestructiveGateTakeover, DestructiveOperationInProgress

    assert not issubclass(DestructiveGateTakeover, DestructiveOperationInProgress)


def test_fence_is_not_a_custody_unresolved_error():
    assert not issubclass(DestructiveOperationInProgress, pusher.CustodyCommitUnresolved)


def test_custody_unresolved_stays_a_runtime_error():
    assert issubclass(pusher.CustodyCommitUnresolved, RuntimeError)


def test_fenced_archive_zero_budget_fences_the_first_call(bucket):
    archive = FencedAfterArchive(bucket, passes=0)
    with pytest.raises(DestructiveOperationInProgress):
        archive('owner', b'pcm', 'raw-live', 'w', {}, data_protection_level='standard')
    assert bucket.blobs == {}


def test_drop_counter_has_no_labels():
    assert pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS._labelnames == ()


def test_policy_fallback_total_is_labelled_by_the_settlement_shape():
    from database.fsr_cache_telemetry import OMI_FALLBACK_TOTAL

    assert list(OMI_FALLBACK_TOTAL._labelnames) == ['component', 'from_mode', 'to_mode', 'reason', 'outcome']
