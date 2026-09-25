"""Regression test for #11742: the pusher kept syncing audio into deleted conversations.

Every listen generation discarded as "empty" deletes the Firestore conversation while the
pusher session keeps running. The session's remaining private-cloud batches were still
uploaded to ``chunks/{uid}/{conversation_id}/``, where nothing can ever reference, play or
delete them — 41% of sampled chunk prefixes in prod belonged to conversations that no
longer exist. Once ``update_conversation`` reports the owner is gone, the session must stop
uploading for that conversation.
"""

import asyncio
import struct
from collections import deque
from unittest.mock import MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

import routers.pusher as pusher
import utils.pusher_protocol as pusher_protocol

UID = 'uid'
CONVERSATION_ID = 'conversation'
SAMPLE_RATE = 8000

CONVERSATION_FRAME = struct.pack('<I', 103) + CONVERSATION_ID.encode()
AUDIO_FRAME = struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\x00' * 64


class _AudioFile:
    def model_dump(self) -> dict:
        return {'path': 'audio.wav'}


class SequencedWebSocket:
    """Sends a second audio chunk only after the first flush has been handled.

    The pusher's private-cloud worker is a separate task, so without this handshake the
    two chunks would coalesce into a single batch and the test could not observe whether
    the second one is still uploaded.
    """

    def __init__(self, first_flush_handled: asyncio.Event):
        self.frames = deque([CONVERSATION_FRAME, AUDIO_FRAME])
        self.first_flush_handled = first_flush_handled
        self.second_chunk_sent = False
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None

    async def accept(self):
        return None

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_bytes(self):
        if self.frames:
            return self.frames.popleft()
        if not self.second_chunk_sent:
            await self.first_flush_handled.wait()
            self.second_chunk_sent = True
            return AUDIO_FRAME
        raise WebSocketDisconnect(1000)


@pytest.fixture
def private_cloud_session(monkeypatch):
    """Drive a private-cloud sync session where each audio frame flushes immediately."""
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    # Flush every queued chunk on the next worker tick instead of after 60s of audio.
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0.0)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 0.0)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.01)

    first_flush_handled = asyncio.Event()
    uploaded: list[str] = []
    fallbacks: list[dict] = []

    def upload(chunks, uid, conversation_id, protection_level):
        uploaded.append(conversation_id)

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    monkeypatch.setattr(
        pusher.conversations_db, 'create_audio_files_from_chunks', lambda uid, conversation_id: [_AudioFile()]
    )
    monkeypatch.setattr(pusher, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    def run(conversation_exists: bool):
        def update_conversation(uid, conversation_id, update_data):
            first_flush_handled.set()
            return conversation_exists

        monkeypatch.setattr(pusher.conversations_db, 'update_conversation', update_conversation)
        return SequencedWebSocket(first_flush_handled)

    return {'run': run, 'uploaded': uploaded, 'fallbacks': fallbacks}


@pytest.mark.asyncio
async def test_deleted_conversation_stops_further_audio_uploads(private_cloud_session):
    websocket = private_cloud_session['run'](conversation_exists=False)

    await pusher._websocket_util_trigger(websocket, UID, SAMPLE_RATE)

    # The first batch races the delete and is unavoidable; the second must not be uploaded.
    assert private_cloud_session['uploaded'] == [CONVERSATION_ID]
    assert private_cloud_session['fallbacks'] == [
        {
            'component': 'pusher',
            'from_mode': 'private_cloud_sync',
            'to_mode': 'drop',
            'reason': 'policy',
            'outcome': 'exhausted',
            'log': pusher.logger,
        }
    ]


@pytest.mark.asyncio
async def test_live_conversation_keeps_syncing_audio(private_cloud_session):
    websocket = private_cloud_session['run'](conversation_exists=True)

    await pusher._websocket_util_trigger(websocket, UID, SAMPLE_RATE)

    assert private_cloud_session['uploaded'] == [CONVERSATION_ID, CONVERSATION_ID]
    assert private_cloud_session['fallbacks'] == []
