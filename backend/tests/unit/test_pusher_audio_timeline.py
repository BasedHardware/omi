"""Pusher-side audio-timeline v2 wire behavior: ack, continuity, splits.

Old/new peer matrix: an opted-in connection gets opcode 202 before anything
else; a connection without the query parameter (old listen) sees no ack and
keeps legacy concatenation; an unsupported version is refused. v2 continuity:
a positive discontinuity flushes the partial chunk and never concatenates
across the gap (nor inside a pending 60 s batch), an exact replay is ignored,
a conflicting overlap fails closed, and a trimmed partial overlap continues
the run exactly.
"""

import asyncio
import json
import struct
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
