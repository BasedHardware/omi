import asyncio
import json
import struct
from collections import deque
from unittest.mock import MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

import routers.pusher as pusher
import utils.pusher_protocol as pusher_protocol


@pytest.fixture(autouse=True)
def emergency_legacy_contract(monkeypatch):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')


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
        await asyncio.sleep(0)
        if self.frames:
            return self.frames.popleft()
        raise WebSocketDisconnect(1000)


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS', MagicMock())


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
        struct.pack('<I', 102) + b'[]',
        struct.pack('<I', 102) + json.dumps({'segments': 'invalid'}).encode(),
        struct.pack('<I', 104) + json.dumps({'conversation_id': 1}).encode(),
        struct.pack('<I', 104) + json.dumps({'conversation_id': 'conv', 'finalization_result_protocol': True}).encode(),
        struct.pack('<I', 105) + json.dumps({'segment_ids': 'invalid'}).encode(),
    ],
)
async def test_malformed_frame_closes_with_unsupported_data(runtime, frame):
    websocket = FakeWebSocket([frame])

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert websocket.close_code == 1003


@pytest.mark.asyncio
async def test_pusher_forwards_finalization_result_protocol_to_worker(runtime, monkeypatch):
    calls = []
    tasks = []

    async def process(*args, **kwargs):
        calls.append((args, kwargs))

    def start(coro, *, name):
        task = asyncio.create_task(coro, name=name)
        tasks.append(task)
        return task

    monkeypatch.setattr(pusher, 'process_conversation_task', process)
    monkeypatch.setattr(pusher, 'start_background_task', start)
    websocket = FakeWebSocket(
        [
            struct.pack('<I', 104)
            + json.dumps(
                {
                    'conversation_id': 'conv-1',
                    'language': 'en',
                    'finalization_job_id': 'job-1',
                    'dispatch_generation': 2,
                    'finalization_result_protocol': 2,
                }
            ).encode()
        ]
    )

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)
    await asyncio.gather(*tasks)

    assert len(calls) == 1
    assert calls[0][1]['finalization_result_protocol'] == 2


def test_finalization_result_protocol_defaults_to_legacy_and_validates_integer():
    assert pusher._parse_finalization_result_protocol(None) == 1
    assert pusher._parse_finalization_result_protocol(2) == 2
    for value in (True, 0, '2'):
        with pytest.raises(ValueError, match='finalization_result_protocol'):
            pusher._parse_finalization_result_protocol(value)


def test_bounded_append_reports_and_drops_oldest(monkeypatch):
    metric = MagicMock()
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', metric)
    queue = deque(['old'], maxlen=1)

    assert pusher_protocol.append_bounded(queue, 'new', 'transcript') is True

    assert list(queue) == ['new']
    metric.labels.assert_called_once_with(queue='transcript')
    metric.labels.return_value.inc.assert_called_once_with()


def test_audio_budget_rejects_bytes_above_shared_limit(monkeypatch):
    drops = MagicMock()
    dropped_bytes = MagicMock()
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', drops)
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', dropped_bytes)
    budget = pusher_protocol.ByteBudget(4)
    buffer = bytearray()

    assert pusher_protocol.extend_bounded(buffer, b'1234', 'audio', budget) is True
    assert pusher_protocol.extend_bounded(buffer, b'5', 'audio', budget) is False

    assert buffer == b'1234'
    assert budget.used == 4
    dropped_bytes.labels.return_value.inc.assert_called_once_with(1)


def test_private_pending_evicts_oldest_and_releases_bytes(monkeypatch):
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    budget = pusher_protocol.ByteBudget(100)
    pending = {
        str(index): {'data': bytearray(b'12')}
        for index in range(pusher_protocol.PRIVATE_CLOUD_PENDING_MAX_CONVERSATIONS)
    }
    assert budget.reserve(sum(len(item['data']) for item in pending.values()))

    pusher_protocol.bound_private_pending(pending, budget)

    assert '0' not in pending
    assert len(pending) == pusher_protocol.PRIVATE_CLOUD_PENDING_MAX_CONVERSATIONS - 1
    assert budget.used == 2 * len(pending)


@pytest.mark.asyncio
async def test_private_cloud_shutdown_exhausts_bounded_upload_attempts(runtime, monkeypatch):
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    upload = MagicMock(side_effect=RuntimeError('unavailable'))
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    journey = MagicMock()
    monkeypatch.setattr(pusher, 'JourneyAttempt', MagicMock(return_value=journey))
    frames = [
        struct.pack('<I', 103) + b'conversation',
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\x00\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert upload.call_count == pusher.PRIVATE_CLOUD_SYNC_MAX_RETRIES + 1
    assert websocket.close_code == 1000
    pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc.assert_called_once_with()
    journey.finish.assert_called_once_with('failure')


def test_append_optional_evicts_oldest_and_releases_budget(monkeypatch):
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    budget = pusher_protocol.ByteBudget(100)
    queue = deque(maxlen=2)
    for i in range(3):
        assert budget.reserve(10)
        evicted = pusher_protocol.append_optional(
            queue, {'type': 'webhook', 'sample_rate': 8000, 'data': bytes([i]) * 10}, 'audio_bytes', budget
        )
        assert evicted == (1 if i == 2 else 0)
    assert [item['data'][0] for item in queue] == [1, 2]
    assert budget.used == 20
    pusher_protocol.PUSHER_QUEUE_DROPS.labels.assert_called_with(queue='audio_bytes')


def test_extend_optional_never_raises_and_evicts_stale_items_first(monkeypatch):
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    budget = pusher_protocol.ByteBudget(30)
    queue = deque(maxlen=5)
    assert budget.reserve(20)
    queue.append({'type': 'app', 'sample_rate': 8000, 'data': b'x' * 20})
    buffer = bytearray()
    # Needs 20 bytes with only 10 free: the stale queued item is evicted, never AudioBackpressure.
    assert pusher_protocol.extend_optional(buffer, b'y' * 20, 'audio_app_buffer', budget, queue) is True
    assert not queue and bytes(buffer) == b'y' * 20 and budget.used == 20
    # Nothing left to evict: the new optional data is dropped, still without raising.
    assert pusher_protocol.extend_optional(buffer, b'z' * 20, 'audio_app_buffer', budget, queue) is False
    assert bytes(buffer) == b'y' * 20 and budget.used == 20


def test_long_webhook_interval_at_48khz_still_delivers_within_the_optional_budget(monkeypatch):
    """A user-configured 120 s interval at 48 kHz (11.5 MB) must not strand a partial buffer
    below its own threshold once the 8 MB optional budget is exhausted (Codex review, #25541)."""
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    rate, seconds = 48000, 120
    threshold = pusher_protocol.optional_flush_bytes(rate, seconds)
    assert threshold <= pusher_protocol.OPTIONAL_AUDIO_MAX_BYTES // 4 < rate * seconds * 2
    budget = pusher_protocol.ByteBudget(pusher_protocol.OPTIONAL_AUDIO_MAX_BYTES)
    queue, buffer, delivered = deque(maxlen=20), bytearray(), 0
    for _ in range(300):  # 300 s of 1 s frames with a healthy consumer draining every frame
        pusher_protocol.extend_optional(buffer, b'\0' * (rate * 2), 'audio_webhook_buffer', budget, queue)
        if len(buffer) >= threshold:
            pusher_protocol.append_optional(
                queue, {'type': 'webhook', 'sample_rate': rate, 'data': bytes(buffer)}, 'audio_bytes', budget
            )
            buffer = bytearray()
        while queue:
            budget.release(len(queue.popleft()['data']))
            delivered += 1
    assert delivered > 0 and budget.used == len(buffer)


def test_short_intervals_keep_their_configured_flush_size():
    assert pusher_protocol.optional_flush_bytes(16000, 5) == 16000 * 5 * 2
    assert pusher_protocol.optional_flush_bytes(16000, 4) == 16000 * 4 * 2
