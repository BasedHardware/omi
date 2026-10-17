from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
import pytest

from omi.stt.whisper import WhisperTranscriber
from omi.transcribe import transcribe


def test_whisper_drains_buffered_tail_on_cancellation():
    async def scenario():
        calls: list[int] = []
        transcripts: list[str] = []

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            return "hello"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00\x00" * 16000)  # 1 s of 16 kHz PCM16 (32000 bytes)

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


def test_whisper_transcribe_wrapper_drains_tail_on_cancellation():
    async def scenario():
        calls: list[int] = []
        transcripts: list[str] = []

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            return "wrapped_result"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00\x00" * 8000)  # 0.5 s (16000 bytes)

        task = asyncio.create_task(
            transcribe(queue, transcripts.append, engine="whisper", runner=runner)
        )
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == [16000]
        assert transcripts == ["wrapped_result"]

    asyncio.run(scenario())


def test_whisper_drains_both_inflight_and_queued_tail_on_cancellation():
    async def scenario():
        in_flight_started = asyncio.Event()
        can_finish_in_flight = asyncio.Event()
        calls: list[int] = []
        transcripts: list[str] = []

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            if len(pcm) == 160000:  # 5 s batch
                in_flight_started.set()
                # Simulate waiting for permission to complete
                while not can_finish_in_flight.is_set():
                    pass
                return "first_5s_batch"
            return "tail_batch"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        # Put 5s batch to trigger in-flight transcription
        queue.put_nowait(b"\x00\x00" * 16000 * 5)

        task = asyncio.create_task(
            WhisperTranscriber(runner=runner).run(queue, transcripts.append)
        )
        await in_flight_started.wait()

        # While 5s batch is in flight, put another 1s chunk in queue and cancel
        queue.put_nowait(b"\x00\x00" * 16000)
        task.cancel()

        # Allow in flight to finish
        can_finish_in_flight.set()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == [160000, 32000]
        assert transcripts == ["first_5s_batch", "tail_batch"]

    asyncio.run(scenario())


def test_whisper_cancellation_bounds_slow_runner_with_drain_timeout():
    async def scenario():
        started = asyncio.Event()

        def slow_runner(pcm: bytes) -> str:
            started.set()
            import time
            time.sleep(1.0)
            return "too_late"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00\x00" * 16000)

        transcriber = WhisperTranscriber(runner=slow_runner, drain_timeout=0.05)
        task = asyncio.create_task(transcriber.run(queue))
        await asyncio.sleep(0)  # queue consumed
        task.cancel()

        start_time = asyncio.get_running_loop().time()
        with pytest.raises(asyncio.CancelledError):
            await task
        elapsed = asyncio.get_running_loop().time() - start_time

        # Must exit near drain_timeout (0.05s), not 1.0s
        assert elapsed < 0.5

    asyncio.run(scenario())


def test_whisper_empty_queue_cancellation_exits_cleanly():
    async def scenario():
        transcripts: list[str] = []
        runner = MagicMock()

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        task = asyncio.create_task(
            WhisperTranscriber(runner=runner).run(queue, transcripts.append)
        )
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert runner.call_count == 0
        assert transcripts == []

    asyncio.run(scenario())
