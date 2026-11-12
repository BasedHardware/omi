"""The account-deletion fence settles as a policy latch on every custody path.

While an account deletion wipe owns the storage authority's gate, every
owner-scoped GCS write for that account is refused with
``DestructiveOperationInProgress``. The refusal is checked before the
upload, so it carries no unknown remote outcome — it is a permanent policy
state, and it lasts for as long as the wipe runs (hours).

The encoded-batch uploader already latched the fence: one warning, the
batch dropped as a policy drop, later batches fast-refused, the session
kept healthy. The durable custody window commit path did not: the refusal
escaped through ``commit_durable_window``'s unknown-outcome guard (latching
``durable_commit_unresolved`` for a commit that never dispatched), the
receive loop's catch-all (``Could not process audio``, close 1011,
application-fault classification), and the shutdown tail's generic failure
arm (a ``finish_receive``-named traceback booking a ``window_tail`` failure
for a commit the fence refused pre-dispatch). A deleting user's client
reconnected into the same permanent fence and burned the refusal again —
the prod traceback shape the sensor counts.

The fence now latches the session exactly like the encoded path: the
refused window drops as a policy drop, later flushes fast-refuse at
enqueue, no custody-unresolved latch, no reconnect hold, no inline finish,
close 1000, one warning — and real storage failures keep every loud
behavior they had.

These tests drive the real session boundary (``pusher._websocket_util_trigger``)
against the real commit path, a fake bucket, and a fence-refusing writer.

Failure-Class: FC-account-deletion-fence-refusal-classified-as-custody-commit-failure
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
from google.api_core.exceptions import ServiceUnavailable
from prometheus_client import REGISTRY
from starlette.websockets import WebSocketState
from fastapi.websockets import WebSocketDisconnect

import routers.pusher as pusher
from database.legal_holds import DestructiveOperationInProgress
from utils import pusher_audio_projection
from utils.firestore_transient_types import is_transient_availability_error
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
    """``storage.archive_capture_bytes`` double that passes the first ``passes``
    calls against the fake bucket and answers the deletion fence afterwards.

    Mirrors the real writer's custody contract (content-addressed plaintext
    digest path, create-if-absent, sha256 metadata) so the committed prefix
    of a session behaves exactly like production; the fence models the owner
    gate's pre-write refusal for the account deletion window.
    """

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
            self.bucket_ref.writes.append(self.name)

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
    monkeypatch.setattr(
        pusher.PusherAudioProjection, 'refresh', lambda self, conversation_id, paths=None, force=False: None
    )
    return real_storage


@pytest.fixture
def spies(monkeypatch):
    """Boundary-accounting spies: window_tail booking, would-drop, holds, finishes."""

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


def _receipts(sock):
    return [AudioReceipt(**json.loads(frame[4:])['receipt']) for frame in _custody_acks(sock)]


def _fenced_writer(monkeypatch, bucket, passes=0):
    archive = FencedAfterArchive(bucket, passes)
    monkeypatch.setattr(storage, 'archive_capture_bytes', archive)
    return archive


def _error_records(caplog, text):
    return [record for record in caplog.records if text in record.getMessage()]


def _traceback_records(caplog):
    return [record for record in caplog.records if record.exc_info]


def _fence_warnings(caplog):
    return [record for record in caplog.records if FENCE_WARNING in record.getMessage()]


async def _drive(sock, uid='owner', sample_rate=16000, audio_custody=1, **kwargs):
    await pusher._websocket_util_trigger(sock, uid, sample_rate, audio_custody=audio_custody, **kwargs)


# ---------------------------------------------------------------------------
# Typed contract
# ---------------------------------------------------------------------------


def test_deletion_fence_error_is_importable_from_the_pusher_module():
    assert getattr(pusher, 'DestructiveOperationInProgress', None) is not None


def test_deletion_fence_error_is_the_legal_holds_class():
    assert pusher.DestructiveOperationInProgress is DestructiveOperationInProgress


def test_deletion_fence_error_is_a_runtime_error_subclass():
    assert issubclass(DestructiveOperationInProgress, RuntimeError)


def test_commit_shed_does_not_classify_the_deletion_fence_as_a_blip():
    fence = DestructiveOperationInProgress('external data write blocked by account deletion')
    assert audio_outbox._is_commit_availability_blip(fence) is False


def test_admission_shed_does_not_classify_the_deletion_fence_as_transient():
    fence = DestructiveOperationInProgress('external data write blocked by account deletion')
    assert is_transient_availability_error(fence) is False


def test_fenced_session_close_1000_maps_to_a_success_outcome():
    assert pusher_session_outcome(1000, application_failed=False) == 'success'


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


# ---------------------------------------------------------------------------
# Tail fence: the buffered window is refused at the shutdown flush
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tail_fence_settles_close_1000_not_1011(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert sock.close_code == 1000


@pytest.mark.asyncio
async def test_tail_fence_books_no_window_tail_failure(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert 'window_tail' not in spies.window_tail_failures


@pytest.mark.asyncio
async def test_tail_fence_books_no_would_drop(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert spies.would_drop == []


@pytest.mark.asyncio
async def test_tail_fence_places_no_reconnect_hold(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert spies.holds == []


@pytest.mark.asyncio
async def test_tail_fence_logs_exactly_one_warning_naming_the_deletion_fence(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    warnings = _fence_warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_tail_fence_logs_no_traceback(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert _traceback_records(caplog) == []
    assert _error_records(caplog, TAIL_TRACEBACK) == []


@pytest.mark.asyncio
async def test_tail_fence_is_refused_on_the_first_attempt_without_shed_retries(session, spies, caplog, monkeypatch):
    archive = _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 1


@pytest.mark.asyncio
async def test_tail_fence_does_not_latch_the_custody_unresolved_fence(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert _error_records(caplog, CUSTODY_UNRESOLVED_WARNING) == []


@pytest.mark.asyncio
async def test_tail_fence_runs_no_inline_finish(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert spies.finishes == []


@pytest.mark.asyncio
async def test_tail_fence_producer_stays_unacknowledged(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert _custody_acks(sock) == []


@pytest.mark.asyncio
async def test_tail_fence_increments_the_policy_drop_counter_once(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    before = _drop_total()
    await _drive(sock)
    assert _drop_total() == before + 1


@pytest.mark.asyncio
async def test_tail_fence_records_the_policy_fallback(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    before = _policy_fallback_total()
    await _drive(sock)
    assert _policy_fallback_total() == before + 1


# ---------------------------------------------------------------------------
# Mid-session fence: the first window commit is refused, the session survives
# ---------------------------------------------------------------------------


def _three_window_session(monkeypatch, session, passes=0):
    archive = _fenced_writer(monkeypatch, session, passes=passes)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog_level = logging.DEBUG
    return archive, caplog_level


@pytest.mark.asyncio
async def test_mid_session_fence_keeps_the_session_close_1000(session, spies, caplog, monkeypatch):
    _three_window_session(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(3)))
    await _drive(sock)
    assert sock.close_code == 1000


@pytest.mark.asyncio
async def test_mid_session_fence_stops_all_writer_calls_at_the_refusal(session, spies, caplog, monkeypatch):
    archive, _ = _three_window_session(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(3)))
    await _drive(sock)
    assert archive.calls == 1


@pytest.mark.asyncio
async def test_mid_session_fence_consumes_every_later_frame(session, spies, caplog, monkeypatch):
    _three_window_session(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    payloads = _payloads(3)
    sock = SessionSocket(_session_frames('conversation', payloads))
    await _drive(sock)
    assert not sock.frames, 'a fence-latched session must keep answering its peer'


@pytest.mark.asyncio
async def test_mid_session_fence_logs_exactly_one_warning_despite_later_flushes(session, spies, caplog, monkeypatch):
    _three_window_session(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(3)))
    await _drive(sock)
    assert len(_fence_warnings(caplog)) == 1


@pytest.mark.asyncio
async def test_mid_session_fence_books_no_application_error_line(session, spies, caplog, monkeypatch):
    _three_window_session(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(3)))
    await _drive(sock)
    assert _error_records(caplog, MID_SESSION_ERROR) == []
    assert _traceback_records(caplog) == []


@pytest.mark.asyncio
async def test_mid_session_fence_increments_the_drop_counter_once(session, spies, caplog, monkeypatch):
    _three_window_session(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(3)))
    before = _drop_total()
    await _drive(sock)
    assert _drop_total() == before + 1


@pytest.mark.asyncio
async def test_mid_session_fence_books_no_failure_accounting(session, spies, caplog, monkeypatch):
    _three_window_session(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(3)))
    await _drive(sock)
    assert spies.window_tail_failures == []
    assert spies.would_drop == []
    assert spies.holds == []


@pytest.mark.asyncio
async def test_mid_session_fence_runs_no_inline_finish(session, spies, caplog, monkeypatch):
    _three_window_session(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(3)))
    await _drive(sock)
    assert spies.finishes == []


# ---------------------------------------------------------------------------
# Fence after committed windows: the committed prefix keeps its receipts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fence_after_one_committed_window_acknowledges_only_the_commit(session, spies, caplog, monkeypatch):
    # Window 1 commits (two archive calls: media + manifest), window 2 is
    # refused at its media call.
    _fenced_writer(monkeypatch, session, passes=2)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    acks = _custody_acks(sock)
    assert len(acks) == 1


@pytest.mark.asyncio
async def test_fence_after_one_committed_window_keeps_a_valid_receipt(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=2)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    receipts = _receipts(sock)
    assert len(receipts) == 1
    assert receipts[0].samples == len(_payloads(1)[0]) // 2
    assert receipts[0].conversation_id == 'conversation'


@pytest.mark.asyncio
async def test_fence_after_one_committed_window_settles_clean(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=2)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert sock.close_code == 1000
    assert spies.holds == []
    assert len(_fence_warnings(caplog)) == 1
    assert _traceback_records(caplog) == []


@pytest.mark.asyncio
async def test_manifest_op_fence_leaves_no_receipt_and_settles_clean(session, spies, caplog, monkeypatch):
    # Window 1's media call succeeds; its manifest call is fenced: the
    # partially written window gets the same policy settlement (the wipe's
    # purge verification owns any stray media object).
    _fenced_writer(monkeypatch, session, passes=1)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert _custody_acks(sock) == []
    assert sock.close_code == 1000
    assert spies.holds == []
    assert _traceback_records(caplog) == []


@pytest.mark.asyncio
async def test_manifest_op_fence_stops_writer_calls_at_the_refusal(session, spies, caplog, monkeypatch):
    archive = _fenced_writer(monkeypatch, session, passes=1)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert archive.calls == 2


# ---------------------------------------------------------------------------
# Gate-boundary fidelity: the fence refusal enters through the owner gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_gate_refusal_at_the_real_boundary_settles_the_same(session, spies, caplog, monkeypatch):
    """The gate itself refuses (as ``external_write_fence`` does in prod)."""

    @contextlib.contextmanager
    def fenced_gate(uid, bucket_obj=None):
        raise DestructiveOperationInProgress('external data write blocked by account deletion')
        yield None  # pragma: no cover - the raise replaces the yield

    monkeypatch.setattr(storage, 'owner_storage_write_gate', fenced_gate)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert sock.close_code == 1000
    assert len(_fence_warnings(caplog)) == 1
    assert _traceback_records(caplog) == []
    assert spies.holds == []


@pytest.mark.asyncio
async def test_owner_gate_refusal_precedes_any_bucket_write(session, spies, caplog, monkeypatch):
    @contextlib.contextmanager
    def fenced_gate(uid, bucket_obj=None):
        raise DestructiveOperationInProgress('external data write blocked by account deletion')
        yield None  # pragma: no cover

    monkeypatch.setattr(storage, 'owner_storage_write_gate', fenced_gate)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert session.writes == []


# ---------------------------------------------------------------------------
# Flush-entry fidelity: switch, discontinuity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_switch_flush_fence_keeps_the_session_alive(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    frames = _session_frames('conversation-a', _payloads(1))
    frames.append(struct.pack('<I', 103) + b'conversation-b')
    frames.extend(_session_frames(None, _payloads(1), start=2000.0))
    sock = SessionSocket(frames)
    await _drive(sock)
    assert sock.close_code == 1000
    assert len(_fence_warnings(caplog)) == 1
    assert _error_records(caplog, MID_SESSION_ERROR) == []


@pytest.mark.asyncio
async def test_conversation_switch_flush_fence_drops_the_buffered_window(session, spies, caplog, monkeypatch):
    archive = _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    frames = _session_frames('conversation-a', _payloads(1))
    frames.append(struct.pack('<I', 103) + b'conversation-b')
    sock = SessionSocket(frames)
    before = _drop_total()
    await _drive(sock)
    assert archive.calls == 1
    assert _drop_total() == before + 1


@pytest.mark.asyncio
async def test_v2_discontinuity_flush_fence_settles_clean(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    start = 1000.0
    step = 0.01
    frames = _session_frames('conversation', _payloads(2), start=start, step=step)
    # A 1.0s jump is far past the 1ms continuity tolerance: the discontinuity
    # flush commits the buffered run — and the fence refuses it.
    frames.append(struct.pack('<Id', 101, start + 2 * step + 1.0) + _payloads(1)[0])
    sock = SessionSocket(frames)
    await _drive(sock, audio_timeline=2)
    assert sock.close_code == 1000
    assert _custody_acks(sock) == []
    assert len(_fence_warnings(caplog)) == 1
    assert _traceback_records(caplog) == []


@pytest.mark.asyncio
async def test_v2_discontinuity_flush_fence_increments_the_drop_counter(session, spies, caplog, monkeypatch):
    _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    start = 1000.0
    step = 0.01
    frames = _session_frames('conversation', _payloads(2), start=start, step=step)
    frames.append(struct.pack('<Id', 101, start + 2 * step + 1.0) + _payloads(1)[0])
    sock = SessionSocket(frames)
    before = _drop_total()
    await _drive(sock, audio_timeline=2)
    assert _drop_total() == before + 1


# ---------------------------------------------------------------------------
# Encoded-path parity: the landed worker latch is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_encoded_path_upload_fence_still_latches_the_worker(session, spies, caplog, monkeypatch):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')

    def fenced_upload(chunks, uid, conv_id, protection, **kwargs):
        raise DestructiveOperationInProgress('external data write blocked by account deletion')

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', fenced_upload)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert sock.close_code == 1000
    assert len(_fence_warnings(caplog)) >= 1
    assert _traceback_records(caplog) == []


@pytest.mark.asyncio
async def test_encoded_path_latch_books_no_failure_accounting(session, spies, caplog, monkeypatch):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')

    def fenced_upload(chunks, uid, conv_id, protection, **kwargs):
        raise DestructiveOperationInProgress('external data write blocked by account deletion')

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', fenced_upload)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert spies.window_tail_failures == []
    assert _error_records(caplog, MID_SESSION_ERROR) == []


# ---------------------------------------------------------------------------
# Real-failure parity: non-fence failures keep every loud behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_availability_failure_at_the_tail_still_books_window_tail(session, spies, caplog, monkeypatch):
    archive = FencedAfterArchive(session, passes=0)

    def failing(uid, raw, prefix, name, metadata, *, data_protection_level=None, manifest_identity=None):
        archive.calls += 1
        raise ServiceUnavailable('storage unavailable')

    monkeypatch.setattr(storage, 'archive_capture_bytes', failing)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert sock.close_code == 1011
    assert 'window_tail' in spies.window_tail_failures
    assert spies.holds == [('conversation', False)]
    assert _traceback_records(caplog) != []


@pytest.mark.asyncio
async def test_availability_failure_mid_session_still_ends_1011(session, spies, caplog, monkeypatch):
    def failing(uid, raw, prefix, name, metadata, *, data_protection_level=None, manifest_identity=None):
        raise ServiceUnavailable('storage unavailable')

    monkeypatch.setattr(storage, 'archive_capture_bytes', failing)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(2)))
    await _drive(sock)
    assert sock.close_code == 1011
    assert len(_error_records(caplog, MID_SESSION_ERROR)) == 1


@pytest.mark.asyncio
async def test_availability_failure_latches_the_custody_unresolved_fence(session, spies, caplog, monkeypatch):
    def failing(uid, raw, prefix, name, metadata, *, data_protection_level=None, manifest_identity=None):
        raise ServiceUnavailable('storage unavailable')

    monkeypatch.setattr(storage, 'archive_capture_bytes', failing)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert _error_records(caplog, CUSTODY_UNRESOLVED_WARNING) != []
    assert _fence_warnings(caplog) == []


# ---------------------------------------------------------------------------
# Fence-reach parity: sessions that never write are never fenced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_disabled_session_never_reaches_the_fence(session, spies, caplog, monkeypatch):
    archive = _fenced_writer(monkeypatch, session, passes=0)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    caplog.set_level(logging.DEBUG)
    sock = SessionSocket(_session_frames('conversation', _payloads(1)))
    await _drive(sock)
    assert archive.calls == 0
    assert sock.close_code == 1000
    assert _fence_warnings(caplog) == []


@pytest.mark.asyncio
async def test_empty_buffer_tail_never_touches_the_writer_or_the_latch(session, spies, caplog, monkeypatch):
    archive = _fenced_writer(monkeypatch, session, passes=0)
    caplog.set_level(logging.DEBUG)
    frames = [struct.pack('<I', 103) + b'conversation']
    sock = SessionSocket(frames)
    before = _drop_total()
    await _drive(sock)
    assert archive.calls == 0
    assert sock.close_code == 1000
    assert _fence_warnings(caplog) == []
    assert _drop_total() == before
