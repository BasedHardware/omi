"""Regression: a multi-channel listen session must not accumulate ``channel_mix_buffers`` when
there is no audio-bytes consumer.

``decide_multi_channel_mix`` and the teardown flush both return should_mix/flush=False when
``audio_bytes_send`` is None, so appending every inbound frame unconditionally (the old behavior)
left the per-channel buffers growing for the whole session (~64 KB/s for stereo) until the worker
ran out of memory, taking every co-located live session down with it. The append must obey the same
condition the drain and flush already use.

Exercises the real ``ListenReceiver._handle_multi_channel_audio`` with the real
``decide_multi_channel_mix``/``mix_n_channel_buffers``/``resample_pcm``; the receiver is a minimal
stand-in supplying only the attributes the method reads (``use_custom_stt=True`` skips the STT
branch, which is the realistic custom-STT multi-channel desktop case, and captured audio still
flows to the mix path).
"""

import asyncio
from types import SimpleNamespace

import routers.listen.receiver as receiver

TARGET_SAMPLE_RATE = receiver.TARGET_SAMPLE_RATE


def _make_receiver(audio_bytes_send):
    return SimpleNamespace(
        host=SimpleNamespace(
            request=SimpleNamespace(codec='pcm', sample_rate=TARGET_SAMPLE_RATE, websocket=None),
            use_custom_stt=True,
            audio_bytes_send=audio_bytes_send,
            state=SimpleNamespace(last_audio_received_time=0.0),
        ),
        channel_id_to_index={0: 0, 1: 1},
        multi_opus_decoders=[None, None],
        stt_sockets_multi=[None, None],
        channel_mix_buffers=[bytearray(), bytearray()],
    )


def _frame(channel_id, payload):
    return bytes([channel_id]) + payload


async def _feed(recv, frames):
    for channel_id, payload in frames:
        await receiver.ListenReceiver._handle_multi_channel_audio(recv, _frame(channel_id, payload))


def test_multichannel_buffers_do_not_leak_without_audio_bytes_consumer():
    recv = _make_receiver(audio_bytes_send=None)
    pcm = b'\x01\x02' * 160  # 320 bytes
    asyncio.run(_feed(recv, [(0, pcm)] * 50))
    buffered = sum(len(b) for b in recv.channel_mix_buffers)
    # With no consumer nothing ever drains these buffers, so nothing may accumulate. The old code
    # held all 50 frames (~16000 bytes) and would keep growing for the whole session.
    assert buffered == 0


def test_multichannel_mix_still_drains_with_audio_bytes_consumer():
    sent = []
    recv = _make_receiver(audio_bytes_send=lambda mixed, ts: sent.append(mixed))
    pcm = b'\x01\x02' * 160
    # Feed both channels so decide_multi_channel_mix sees all buffers non-empty and mixes.
    asyncio.run(_feed(recv, [(0, pcm), (1, pcm)]))
    assert sent, "expected a mixed frame delivered to the audio-bytes consumer"
    assert sum(len(b) for b in recv.channel_mix_buffers) == 0
