"""Regression tests for listen teardown tail-audio flushing (#9237)."""

import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routers.listen.receiver import ListenReceiver
from utils.stt.streaming import STTService
from utils.listen_audio import build_channel_config

from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, frame_type, make_session


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _receiver_with_tail_sender(audio_bytes_send):
    channels = build_channel_config('phone_call')
    host = SimpleNamespace(
        is_multi_channel=True,
        audio_bytes_send=audio_bytes_send,
        request=SimpleNamespace(sample_rate=16000),
        state=SimpleNamespace(last_audio_received_time=None),
    )
    return ListenReceiver(host, channels, {channel.channel_id: index for index, channel in enumerate(channels)})


@pytest.mark.anyio
async def test_teardown_tail_audio_flushes_through_real_receiver_before_pusher_close():
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, config_overrides={'is_multi_channel': True, 'sample_rate': 16000})
    await session.connect()
    receiver = _receiver_with_tail_sender(session.audio_bytes_send)
    receiver.channel_mix_buffers = [
        bytearray(struct.pack('<2h', 1000, 2000)),
        bytearray(struct.pack('<2h', 3000, 4000)),
    ]

    await receiver.flush_multi_channel_tail()
    await session.close()

    assert all(not buffer for buffer in receiver.channel_mix_buffers)
    assert any(frame_type(frame) == 101 for frame in ws.sent)


@pytest.mark.anyio
async def test_tail_flush_is_a_noop_when_audio_bytes_delivery_is_disabled():
    receiver = _receiver_with_tail_sender(None)
    receiver.channel_mix_buffers = [bytearray(b'\x01\x00'), bytearray(b'\x02\x00')]

    await receiver.flush_multi_channel_tail()

    assert receiver.channel_mix_buffers == [bytearray(b'\x01\x00'), bytearray(b'\x02\x00')]


@pytest.mark.anyio
async def test_partial_multichannel_stt_construction_drains_every_open_socket():
    first_socket = SimpleNamespace(drain_and_close=AsyncMock())
    host = SimpleNamespace(
        is_multi_channel=True,
        use_custom_stt=False,
        stt_service=STTService.parakeet,
        request=SimpleNamespace(websocket=MagicMock()),
        state=SimpleNamespace(),
        client_device_context=SimpleNamespace(platform='desktop'),
    )
    receiver = ListenReceiver(host, [SimpleNamespace(), SimpleNamespace()], {})
    receiver._create_stt_socket = AsyncMock(side_effect=[first_socket, RuntimeError('connect failed')])

    with patch('routers.listen.receiver.terminate_live_stt_session', new=AsyncMock()):
        assert await receiver.initialize_stt() is False

    first_socket.drain_and_close.assert_awaited_once_with()
    assert receiver.stt_sockets_multi == [None, None]


@pytest.mark.anyio
async def test_multichannel_teardown_continues_after_one_drain_failure():
    failing = SimpleNamespace(drain_and_close=AsyncMock(side_effect=RuntimeError('drain failed')), finish=MagicMock())
    healthy = SimpleNamespace(drain_and_close=AsyncMock(), finish=MagicMock())
    host = SimpleNamespace(is_multi_channel=True)
    receiver = ListenReceiver(host, [SimpleNamespace(), SimpleNamespace()], {})
    receiver.stt_sockets_multi = [failing, healthy]

    await receiver._drain_stt_sockets()

    failing.finish.assert_called_once_with()
    healthy.drain_and_close.assert_awaited_once_with()
    assert receiver.stt_sockets_multi == [None, None]
