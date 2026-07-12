"""Regression tests for listen teardown tail-audio flush ordering (#9237)."""

import struct
import time
from pathlib import Path

import pytest

from utils.transcribe_decisions import should_flush_final_multi_channel_mix

from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, frame_type, make_session


def mix_n_channel_buffers(buffers):
    """Local copy of routers.transcribe.mix_n_channel_buffers for hermetic tests."""
    min_len = min((len(b) for b in buffers), default=0)
    if min_len < 2:
        return b''
    min_len = min_len - (min_len % 2)
    num_samples = min_len // 2
    channel_samples = [struct.unpack(f'<{num_samples}h', b[:min_len]) for b in buffers]
    mixed = []
    for i in range(num_samples):
        s = sum(ch[i] for ch in channel_samples)
        mixed.append(max(-32768, min(32767, s)))
    return struct.pack(f'<{num_samples}h', *mixed)


async def _flush_tail_then_close(*, session, channel_mix_buffers, is_multi_channel: bool):
    """Mirrors the corrected _stream_handler finally ordering."""
    audio_bytes_send = session.audio_bytes_send
    if should_flush_final_multi_channel_mix(
        is_multi_channel=is_multi_channel,
        audio_bytes_enabled=True,
        buffers=channel_mix_buffers,
    ):
        mixed = mix_n_channel_buffers(channel_mix_buffers)
        if mixed:
            audio_bytes_send(mixed, time.time())
        for buf in channel_mix_buffers:
            buf.clear()
    await session.close()


async def _close_then_flush_tail(*, session, channel_mix_buffers, is_multi_channel: bool):
    """Buggy ordering: pusher close before tail enqueue loses audio on the wire."""
    await session.close()
    audio_bytes_send = session.audio_bytes_send
    if should_flush_final_multi_channel_mix(
        is_multi_channel=is_multi_channel,
        audio_bytes_enabled=True,
        buffers=channel_mix_buffers,
    ):
        mixed = mix_n_channel_buffers(channel_mix_buffers)
        if mixed:
            audio_bytes_send(mixed, time.time())
        for buf in channel_mix_buffers:
            buf.clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_teardown_tail_audio_flushed_when_enqueued_before_close():
    ws = FakePusherWebSocket()
    session = make_session(
        ws=ws,
        config_overrides={"is_multi_channel": True, "sample_rate": 16000},
    )
    await session.connect()

    channel_mix_buffers = [
        bytearray(struct.pack('<2h', 1000, 2000)),
        bytearray(struct.pack('<2h', 3000, 4000)),
    ]

    flush_started_with_audio = {}

    original_flush = session._flush

    async def tracking_flush():
        flush_started_with_audio["size"] = session.audio_total_size
        await original_flush()

    session._flush = tracking_flush

    await _flush_tail_then_close(
        session=session,
        channel_mix_buffers=channel_mix_buffers,
        is_multi_channel=True,
    )

    assert flush_started_with_audio["size"] > 0
    assert any(frame_type(frame) == 101 for frame in ws.sent)


@pytest.mark.anyio
async def test_teardown_close_before_tail_enqueue_drops_audio():
    ws = FakePusherWebSocket()
    session = make_session(
        ws=ws,
        config_overrides={"is_multi_channel": True, "sample_rate": 16000},
    )
    await session.connect()

    channel_mix_buffers = [
        bytearray(struct.pack('<2h', 1000, 2000)),
        bytearray(struct.pack('<2h', 3000, 4000)),
    ]

    await _close_then_flush_tail(
        session=session,
        channel_mix_buffers=channel_mix_buffers,
        is_multi_channel=True,
    )

    assert not any(frame_type(frame) == 101 for frame in ws.sent)
    assert session.audio_total_size > 0


def test_stream_handler_teardown_flushes_tail_before_pusher_close():
    transcribe_path = Path(__file__).resolve().parents[2] / "routers" / "transcribe.py"
    source = transcribe_path.read_text()
    handler_end = source.find('logger.info(f"_stream_handler ended')
    finally_start = source.rfind("    finally:", 0, handler_end)
    teardown = source[finally_start:handler_end]
    flush_pos = teardown.find("# Flush any remaining mixed audio to pusher")
    pusher_pos = teardown.find("# Pusher sockets")
    assert flush_pos != -1
    assert pusher_pos != -1
    assert flush_pos < pusher_pos
