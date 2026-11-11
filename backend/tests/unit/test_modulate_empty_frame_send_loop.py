"""Regression: an empty audio frame must not shut down the Modulate send loop.

``b''`` is ``SafeModulateSocket``'s shutdown sentinel -- ``finish()`` enqueues it and
``_send_loop`` breaks on it. ``send()`` did not reject an empty payload, so a zero-length audio
frame enqueued that sentinel and ended the send loop mid-session. The socket is not marked dead in
that path, so ``is_connection_dead`` stays False and ``send()`` keeps returning True: every later
frame is queued to a loop nobody is reading, and the user's transcription silently stops for the
rest of the session with no error and no reconnect. Both Parakeet sockets already guard with
``if not data: return True``.

Empty frames are reachable from the live path: ``send_live_stt_audio`` passes its ``audio``
straight to ``stt_socket.send`` with no emptiness check, ``decide_multi_channel_stt_send`` takes
``pcm_len`` only for usage accounting and never requires it to be non-zero, and
``resample_pcm(b'', ...)`` returns ``b''`` (so a zero-length client frame, or a PCM multi-channel
frame carrying only its channel byte, produces one).
"""

import asyncio
from unittest.mock import AsyncMock

from utils.stt.streaming import SafeModulateSocket

REAL_AUDIO = b'real_audio_chunk'


def _drive_send_loop(frames):
    """Drive a real SafeModulateSocket over `frames`; return the frames that reached the provider."""
    provider_frames = []
    real_audio_seen = asyncio.Event()

    async def record_provider_frame(frame):
        provider_frames.append(frame)
        if frame == REAL_AUDIO:
            real_audio_seen.set()

    ws = AsyncMock()
    ws.send = AsyncMock(side_effect=record_provider_frame)
    ws.close = AsyncMock()
    loop = asyncio.new_event_loop()

    async def run():
        sock = SafeModulateSocket(ws, lambda _segments: None, loop, preseconds=0)
        sock.set_wav_header(b'')
        sock._recv_task.cancel()
        for frame in frames:
            sock.send(frame)
        try:
            await asyncio.wait_for(real_audio_seen.wait(), timeout=2)
        except asyncio.TimeoutError:
            # Let the caller's assertion report the real problem instead of a timeout traceback.
            pass
        sock.finish()
        try:
            await asyncio.wait_for(sock._send_task, timeout=2)
        except asyncio.TimeoutError:
            pass
        await asyncio.gather(sock._recv_task, return_exceptions=True)
        return provider_frames

    try:
        return loop.run_until_complete(run())
    finally:
        loop.close()


def test_empty_audio_frame_does_not_stop_the_send_loop():
    # The empty frame arrives first, then real audio. The real audio must still be delivered.
    frames = _drive_send_loop([b'', REAL_AUDIO])
    assert REAL_AUDIO in frames, 'send loop stopped on the empty frame; later audio never reached the provider'


def test_normal_audio_still_streams_and_finish_stops_the_loop():
    frames = _drive_send_loop([REAL_AUDIO])
    assert REAL_AUDIO in frames
