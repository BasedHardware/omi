"""Pusher-side audio-timeline v2 wire behavior: ack, continuity, splits.

Old/new peer matrix: an opted-in connection gets opcode 202 before anything
else; a connection without the query parameter (old listen) sees no ack and
keeps legacy concatenation; an unsupported version is refused. v2 continuity:
a positive discontinuity flushes the partial chunk and never concatenates
across the gap (nor inside a pending 60 s batch), an exact replay is ignored,
a conflicting overlap fails closed, and a trimmed partial overlap continues
the run exactly. Replays reaching past the live buffer are reconciled against
a digest ledger written only after the batch's upload succeeds: an
unverifiable overlap is never re-stored, but the frame's new tail past the
accepted end always survives (counted as a conflict).
"""

import asyncio
import json
import struct
import time
from unittest.mock import MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

import routers.pusher as pusher
import utils.pusher_protocol as pusher_protocol
from utils.pusher_protocol import AUDIO_TIMELINE_PROTOCOL, audio_timeline_ack_frame


class FakeWebSocket:
    def __init__(self, frames=()):
        self.frames = list(frames)
        self.client_state = WebSocketState.CONNECTED
        self.sent_bytes = []
        self.close_code = None

    async def accept(self):
        return None

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_bytes(self):
        await asyncio.sleep(0)
        if self.frames:
            return self.frames.pop(0)
        raise WebSocketDisconnect(1000)

    async def send_bytes(self, data):
        self.sent_bytes.append(data)


class UploadGatedWebSocket(FakeWebSocket):
    """Holds back the final frame until the first batch upload lands.

    The flushed-run digest ledger is written after upload success, so a replay
    reconciled against it must not be delivered while the flushed run is still
    only queued.
    """

    def __init__(self, frames, uploads):
        super().__init__(frames)
        self._uploads = uploads

    async def receive_bytes(self):
        if len(self.frames) == 1:
            deadline = time.monotonic() + 5.0
            while not self._uploads and time.monotonic() < deadline:
                await asyncio.sleep(0.002)
        return await super().receive_bytes()


class HeldOpenWebSocket(FakeWebSocket):
    """Stays connected until released, keeping the session out of shutdown."""

    def __init__(self, frames, release):
        super().__init__(frames)
        self._release = release

    async def receive_bytes(self):
        if not self.frames:
            await self._release.wait()
            raise WebSocketDisconnect(1000)
        return await super().receive_bytes()


def _audio(ts: float, pcm: bytes) -> bytes:
    return struct.pack('<I', 101) + struct.pack('<d', ts) + pcm


def _conversation(cid: str) -> bytes:
    return struct.pack('<I', 103) + cid.encode('utf-8')


RATE = 16000


@pytest.fixture
def env(monkeypatch):
    uploads = []

    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS', MagicMock())
    monkeypatch.setattr(pusher, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(pusher.ReadinessGate, 'is_serving', lambda: True)

    def upload(chunks, uid, cid, level=None):
        uploads.extend((cid, chunk) for chunk in chunks)
        return [f'chunks/{uid}/{cid}/{chunk["timestamp"]:.3f}.batch.bin' for chunk in chunks]

    async def update(uid, cid, data):
        return True

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    monkeypatch.setattr(pusher.conversations_db, 'update_conversation', update)
    monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda uid, cid: [])
    return uploads


async def _run(ws, *, audio_timeline=AUDIO_TIMELINE_PROTOCOL):
    await pusher._websocket_util_trigger(ws, 'uid-at', RATE, 'test', audio_timeline)


async def test_opted_in_connection_is_acknowledged_before_anything_else(env):
    pcm = b'\x01\x00' * RATE
    ws = FakeWebSocket([_conversation('c1'), _audio(100.0, pcm)])

    await _run(ws)

    assert ws.sent_bytes and ws.sent_bytes[0] == audio_timeline_ack_frame()
    assert json.loads(ws.sent_bytes[0][4:])['version'] == AUDIO_TIMELINE_PROTOCOL


async def test_old_listen_sees_no_ack_and_keeps_legacy_concatenation(env):
    pcm_a = b'\x01\x00' * (RATE // 2)
    # Legacy header semantics: the second run continues 0.5 s later and the
    # buffers concatenate exactly as before (no v2 split, no ack frame).
    ws = FakeWebSocket([_conversation('c1'), _audio(100.0, pcm_a), _audio(100.5, pcm_a)])

    await _run(ws, audio_timeline=None)

    assert ws.sent_bytes == []
    assert len(env) == 1
    _, chunk = env[0]
    assert len(chunk['data']) == len(pcm_a) * 2


async def test_unsupported_audio_timeline_version_is_refused(env):
    ws = FakeWebSocket([])
    await _run(ws, audio_timeline=3)
    assert ws.close_code == 1008


async def test_positive_discontinuity_flushes_partial_chunk_and_batch(env):
    pcm_a = b'\x01\x00' * (RATE // 2)  # 0.5 s
    ws = FakeWebSocket(
        [
            _conversation('c1'),
            _audio(100.0, pcm_a),
            # 10 s gap: the partial run must upload on its own, never concatenate.
            _audio(110.5, pcm_a),
        ]
    )

    await _run(ws)

    assert len(env) == 2
    (_, first), (_, second) = env
    assert first['timestamp'] == 100.0 and second['timestamp'] == 110.5
    assert len(first['data']) == len(pcm_a) and len(second['data']) == len(pcm_a)
    # v2 chunks carry authoritative spans.
    assert first['span']['samples'] == RATE // 2 and first['span']['start'] == 100.0


async def test_exact_duplicate_replay_is_ignored(env):
    pcm = b'\x02\x00' * (RATE // 2)
    ws = FakeWebSocket([_conversation('c1'), _audio(200.0, pcm), _audio(200.0, pcm)])

    await _run(ws)

    assert len(env) == 1
    assert len(env[0][1]['data']) == len(pcm)


async def test_conflicting_overlap_fails_closed(env):
    pcm = b'\x03\x00' * (RATE // 2)
    conflicting = b'\x04\x00' * (RATE // 2)
    ws = FakeWebSocket([_conversation('c1'), _audio(300.0, pcm), _audio(300.0, conflicting)])

    await _run(ws)

    assert len(env) == 1
    assert env[0][1]['data'] == pcm


async def test_partial_overlap_is_trimmed_and_continues_the_run(env):
    first_pcm = b'\x05\x00' * (RATE // 2)
    # Starts 0.25 s into the accepted range: the overlapping prefix must be
    # dropped and only the new tail stored.
    replay_prefix = b'\x05\x00' * (RATE // 4)
    new_tail = b'\x06\x00' * (RATE // 4)
    overlapping = replay_prefix + new_tail
    ws = FakeWebSocket([_conversation('c1'), _audio(400.0, first_pcm), _audio(400.25, overlapping)])

    await _run(ws)

    assert len(env) == 1
    _, chunk = env[0]
    assert chunk['data'] == first_pcm + new_tail
    assert chunk['span']['samples'] == RATE // 2 + RATE // 4


async def test_conversation_switch_flushes_and_rebinds(env):
    pcm = b'\x07\x00' * (RATE // 2)
    ws = FakeWebSocket(
        [
            _conversation('c1'),
            _audio(500.0, pcm),
            _conversation('c2'),
            _audio(500.5, pcm),
        ]
    )

    await _run(ws)

    conversations = [cid for cid, _chunk in env]
    assert conversations == ['c1', 'c2']
    assert env[0][1]['timestamp'] == 500.0 and env[1][1]['timestamp'] == 500.5


def test_ack_frame_is_stable():
    frame = audio_timeline_ack_frame()
    assert struct.unpack('<I', frame[:4])[0] == 202
    payload = json.loads(frame[4:])
    assert payload == {'type': 'audio_timeline_ack', 'version': AUDIO_TIMELINE_PROTOCOL}


async def test_conflicting_replay_reaching_past_live_buffer_keeps_new_tail(env):
    """A replay whose conflict window was already flushed keeps only the new tail.

    The first 60 s frame crosses the chunk threshold, so it is queued and the
    live buffer resets; the replayed frame overlaps only already-flushed audio
    with different bytes. The overlap can be neither byte-compared nor
    digest-matched, so it is never re-stored — but the bytes past the accepted
    end are fresh coverage and must not be lost with the frame.
    """
    from utils.metrics import OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL

    before = OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get()
    pcm = b'\x08\x00' * (RATE * 60)  # one 60 s run: queues a chunk, empties the live buffer
    tail = b'\x0a\x00' * (RATE // 2)
    replay = b'\x09\x00' * (RATE * 60) + tail  # same start, different bytes, new tail
    ws = FakeWebSocket([_conversation('c1'), _audio(2000.0, pcm), _audio(2000.0, replay)])

    await _run(ws)

    assert OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get() == before + 1
    assert len(env) == 1
    _, chunk = env[0]
    assert chunk['data'] == pcm + tail, 'the conflicting overlap is dropped; the new tail is kept'
    assert chunk['span']['samples'] == RATE * 60 + RATE // 2


async def test_mid_chunk_unverifiable_replay_keeps_the_new_tail(env):
    """A replay starting inside a flushed 60 s chunk no longer loses its tail.

    Only whole-run digests exist, so an overlap starting mid-run is
    unverifiable: the overlap is dropped (conflict counted) and the bytes past
    the accepted end continue the run from that end instead of becoming a
    coverage hole.
    """
    from utils.metrics import OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL

    before = OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get()
    pcm = b'\x0d\x00' * (RATE * 60)  # chunk [5000, 5060)
    tail = b'\x0e\x00' * (RATE * 30 + RATE // 2)  # 30.5 s of genuinely new audio
    replay = b'\x0f\x00' * (RATE * 30) + tail  # starts mid-chunk at 5030
    ws = FakeWebSocket([_conversation('c1'), _audio(5000.0, pcm), _audio(5030.0, replay)])

    await _run(ws)

    assert OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get() == before + 1
    assert len(env) == 1
    _, chunk = env[0]
    assert chunk['data'] == pcm + tail, 'the unverified overlap is dropped; the new tail is kept'
    assert chunk['timestamp'] == pytest.approx(5000.0)


async def test_batch_dropped_after_retries_leaves_no_digest_entry(env, monkeypatch):
    """A run whose upload never succeeds is never trusted on replay.

    The digest ledger is written only after `upload_audio_chunks_batch`
    succeeds, so a replay of a range whose batch burned its retry budget is
    unverifiable (a counted conflict) rather than digest-trusted — and its
    new tail is still kept.
    """
    from utils.metrics import OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL

    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.05)
    attempts = []

    def failing_upload(chunks, uid, cid, level=None):
        attempts.append(cid)
        raise RuntimeError('gcs down')

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', failing_upload)

    before = OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get()
    pcm = b'\x11\x00' * (RATE * 60)
    tail = b'\x12\x00' * (RATE // 2)
    replay = pcm + tail  # byte-identical prefix: only trustworthy with a ledger entry
    ws = FakeWebSocket([_conversation('c1'), _audio(7000.0, pcm), _audio(7000.0, replay)])

    await _run(ws)

    assert (
        OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get() == before + 1
    ), 'a range whose upload never landed must not be digest-trusted'
    assert len(attempts) >= 4, 'the replayed tail must still produce upload attempts'


async def test_queue_evicted_chunk_leaves_no_digest_entry(env, monkeypatch):
    """A chunk evicted by the bounded queue is never trusted on replay.

    Eviction is the documented OOM backpressure (drop oldest); a replay of the
    evicted range has no stored bytes to verify against, so it is a counted
    conflict whose new tail survives — not a digest match against an entry the
    eviction should have removed.
    """
    from utils.metrics import OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL, PUSHER_QUEUE_DROPS

    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_QUEUE_MAX_SIZE', 3)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 5.0)

    conflicts_before = OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get()
    drops_before = PUSHER_QUEUE_DROPS.labels(queue='private_cloud')._value.get()

    first = b'\x13\x00' * (RATE * 60)  # evicted by the bounded queue
    second = b'\x14\x00' * (RATE * 60)
    third = b'\x15\x00' * (RATE * 60)
    tail = b'\x16\x00' * (RATE // 2)
    replay = first + second + third + tail  # replays everything including the evicted run
    ws = FakeWebSocket(
        [
            _conversation('c1'),
            _audio(8000.0, first),
            _audio(8060.0, second),
            _audio(8120.0, third),
            _audio(8000.0, replay),
        ]
    )

    await _run(ws)

    assert (
        PUSHER_QUEUE_DROPS.labels(queue='private_cloud')._value.get() > drops_before
    ), 'the bounded queue must have evicted the oldest chunk'
    assert OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get() == conflicts_before + 1
    assert len(env) == 1
    _, chunk = env[0]
    assert chunk['data'] == second + third + tail, 'the evicted run is never re-stored; the tail is kept'


async def test_matching_replay_reaching_past_live_buffer_continues_run(env):
    """A flushed-range replay whose bytes match the stored digest is trusted.

    The replay frame is held back until the first batch's upload landed, so
    the post-success digest ledger is provably populated: the matching prefix
    is trusted and only the genuinely new tail is stored.
    """
    from utils.metrics import OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL

    conflicts_before = OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get()
    pcm = b'\x0b\x00' * (RATE * 60)
    tail = b'\x0c\x00' * (RATE // 2)
    replay = pcm + tail
    ws = UploadGatedWebSocket([_conversation('c1'), _audio(3000.0, pcm), _audio(3000.0, replay)], env)

    await _run(ws)

    assert (
        OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL._value.get() == conflicts_before
    ), 'a byte-identical replay of a successfully uploaded run is not a conflict'
    assert len(env) == 2
    (_, first), (_, second) = env
    assert first['data'] == pcm, 'the replayed prefix must be trimmed, not duplicated'
    assert second['data'] == tail
    assert second['timestamp'] == pytest.approx(3060.0)  # continues at the accepted end
