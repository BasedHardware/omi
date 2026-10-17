from __future__ import annotations

import asyncio
import time
import pytest

from omi.stt.whisper import WhisperTranscriber
from omi.transcribe import transcribe


def test_whisper_cancellation_transcribes_buffered_tail():
    async def scenario():
        calls, transcripts = [], []

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            return "hello"

        queue = asyncio.Queue()
        queue.put_nowait(b"\x00\x00" * 16000)  # 1 s of 16 kHz PCM16
        task = asyncio.create_task(
            WhisperTranscriber(runner=runner).run(queue, transcripts.append)
        )
        await asyncio.sleep(0)  # run() consumes the chunk into buffer
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == [32000]
        assert transcripts == ["hello"]

    asyncio.run(scenario())


def test_whisper_cancellation_completes_in_flight_batch_and_drains_queue_tail():
    async def scenario():
        transcripts = []

        def runner(pcm: bytes) -> str:
            time.sleep(0.02)
            return f"segment_{len(pcm)}"

        queue = asyncio.Queue()
        # 5s of audio (160000 bytes) triggers full batch
        queue.put_nowait(b"\x00\x00" * 16000 * 5)
        # 1s tail remaining in queue
        queue.put_nowait(b"\x00\x00" * 16000)

        t = WhisperTranscriber(runner=runner)
        task = asyncio.create_task(t.run(queue, transcripts.append))
        await asyncio.sleep(0.005)  # Let full batch start transcribing in thread
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert transcripts == ["segment_160000", "segment_32000"]

    asyncio.run(scenario())


def test_whisper_cancellation_empty_buffer_does_not_call_runner():
    async def scenario():
        calls = []

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            return "empty"

        queue = asyncio.Queue()
        task = asyncio.create_task(
            WhisperTranscriber(runner=runner).run(queue)
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == []

    asyncio.run(scenario())


def test_whisper_cancellation_bounded_by_drain_timeout():
    async def scenario():
        def hanging_runner(pcm: bytes) -> str:
            time.sleep(2.0)
            return "late"

        queue = asyncio.Queue()
        queue.put_nowait(b"\x00\x00" * 16000)

        t = WhisperTranscriber(runner=hanging_runner, drain_timeout=0.05)
        t0 = time.time()
        task = asyncio.create_task(t.run(queue))
        await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        elapsed = time.time() - t0
        assert elapsed < 1.0, f"Cancellation exceeded bounded timeout: {elapsed}s"

    asyncio.run(scenario())


def test_whisper_transcribe_wrapper_drains_on_cancellation():
    async def scenario():
        transcripts = []

        def runner(pcm: bytes) -> str:
            return "wrapped_transcript"

        queue = asyncio.Queue()
        queue.put_nowait(b"\x00\x00" * 16000)

        task = asyncio.create_task(
            transcribe(
                queue,
                on_transcript=transcripts.append,
                engine="whisper",
                runner=runner,
                drain_timeout=1.0,
            )
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert transcripts == ["wrapped_transcript"]

    asyncio.run(scenario())


def test_whisper_drain_timeout_zero_skips_drain_on_cancellation():
    async def scenario():
        calls = []

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            return "skipped"

        queue = asyncio.Queue()
        queue.put_nowait(b"\x00\x00" * 16000)

        t = WhisperTranscriber(runner=runner, drain_timeout=0)
        task = asyncio.create_task(t.run(queue))
        await asyncio.sleep(0)  # queue item consumed into buffer
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # drain_timeout=0 explicitly opts out of draining on cancel
        assert calls == []

    asyncio.run(scenario())

