import struct
from collections import deque
from unittest.mock import MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

import routers.pusher as pusher


class FakeWebSocket:
    def __init__(self, frames=()):
        self.frames = deque(frames)
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
        raise WebSocketDisconnect(1000)


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_QUEUE_DROPS', MagicMock())


@pytest.mark.asyncio
@pytest.mark.parametrize('sample_rate', [0, 7999, 48001])
async def test_invalid_sample_rate_closes_with_policy_violation(sample_rate):
    websocket = FakeWebSocket()

    await pusher._websocket_util_trigger(websocket, 'uid', sample_rate)

    assert websocket.close_code == 1008


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'frame',
    [
        b'',
        b'\x01\x00\x00',
        struct.pack('<I', 999),
        struct.pack('<I', 101),
        struct.pack('<I', 102) + b'{',
    ],
)
async def test_malformed_frame_closes_with_unsupported_data(runtime, frame):
    websocket = FakeWebSocket([frame])

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert websocket.close_code == 1003


def test_bounded_append_reports_and_drops_oldest(monkeypatch):
    metric = MagicMock()
    monkeypatch.setattr(pusher, 'PUSHER_QUEUE_DROPS', metric)
    queue = deque(['old'], maxlen=1)

    assert pusher._append_bounded(queue, 'new', 'transcript') is True

    assert list(queue) == ['new']
    metric.labels.assert_called_once_with(queue='transcript')
    metric.labels.return_value.inc.assert_called_once_with()


@pytest.mark.asyncio
async def test_private_cloud_shutdown_exhausts_bounded_upload_attempts(runtime, monkeypatch):
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    upload = MagicMock(side_effect=RuntimeError('unavailable'))
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    frames = [
        struct.pack('<I', 103) + b'conversation',
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\x00\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert upload.call_count == pusher.PRIVATE_CLOUD_SYNC_MAX_RETRIES + 1
    assert websocket.close_code == 1000
