"""Cancellation drain for the local Whisper engine.

No model, device, or network: the runner is injected.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from omi.stt.whisper import WhisperTranscriber
from omi.transcribe import transcribe

_BATCH_BYTES = 16000 * 2 * 5  # one full Whisper batch: 5s mono s16le


def _pcm(seconds: float) -> bytes:
    return b"\x00\x01" * int(16000 * seconds)


async def _wait_for_thread_event(event: threading.Event, timeout: float = 1) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out waiting for the runner")


async def _wait_until_queue_consumed(queue: asyncio.Queue, task: asyncio.Task) -> None:
    for _ in range(50):
        if queue.empty() and not task.done():
            await asyncio.sleep(0)
            if queue.empty() and not task.done():
                return
        await asyncio.sleep(0)
    raise AssertionError("transcriber did not consume queued audio")


def test_whisper_cancel_transcribes_buffered_tail():
    """A recording shorter than one batch is transcribed when run() is cancelled."""

    async def scenario():
        calls = []
        transcripts = []

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            return "hello"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(_pcm(1))
        task = asyncio.create_task(WhisperTranscriber(runner=runner).run(queue, transcripts.append))
        await _wait_until_queue_consumed(queue, task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == [32000]
        assert transcripts == ["hello"]
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())


def test_whisper_cancel_via_transcribe_wrapper():
    async def scenario():
        calls = []
        transcripts = []

        def runner(pcm: bytes) -> str:
            calls.append(pcm)
            return "hello"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00\x00" * 16000)
        task = asyncio.create_task(transcribe(queue, transcripts.append, engine="whisper", runner=runner))
        await _wait_until_queue_consumed(queue, task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == [b"\x00\x00" * 16000]
        assert transcripts == ["hello"]

    asyncio.run(scenario())


def test_whisper_cancel_keeps_inflight_batch_and_following_tail():
    """A full batch in flight is kept, and PCM taken after it is flushed on cancel."""

    async def scenario():
        calls = []
        transcripts = []
        started = threading.Event()
        release = threading.Event()
        emitted = asyncio.Event()

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            if len(pcm) == _BATCH_BYTES:
                started.set()
                assert release.wait(2)
                return "batch"
            return "tail"

        def on_transcript(text: str) -> None:
            transcripts.append(text)
            emitted.set()

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00" * _BATCH_BYTES)
        transcriber = WhisperTranscriber(runner=runner)
        task = asyncio.create_task(transcriber.run(queue, on_transcript))
        await _wait_for_thread_event(started)
        release.set()
        await asyncio.wait_for(emitted.wait(), 1)
        assert transcripts == ["batch"]

        queue.put_nowait(_pcm(1))
        await _wait_until_queue_consumed(queue, task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == [_BATCH_BYTES, 32000]
        assert transcripts == ["batch", "tail"]
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())


def test_whisper_cancel_waits_for_inflight_batch():
    async def scenario():
        transcripts = []
        started = threading.Event()
        release = threading.Event()

        def runner(pcm: bytes) -> str:
            started.set()
            assert release.wait(2)
            return "batch"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00" * _BATCH_BYTES)
        task = asyncio.create_task(WhisperTranscriber(runner=runner).run(queue, transcripts.append))
        await _wait_for_thread_event(started)
        task.cancel()
        await asyncio.sleep(0.05)
        assert transcripts == []
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert transcripts == ["batch"]
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())


def test_whisper_drain_timeout_abandons_slow_inflight_runner():
    async def scenario():
        transcripts = []
        started = threading.Event()
        release = threading.Event()

        def runner(pcm: bytes) -> str:
            started.set()
            release.wait(5)
            return "too late"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00" * _BATCH_BYTES)
        task = asyncio.create_task(WhisperTranscriber(runner=runner, drain_timeout=0.05).run(queue, transcripts.append))
        await _wait_for_thread_event(started)
        task.cancel()
        started_at = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await task
        elapsed = time.monotonic() - started_at
        release.set()
        await asyncio.sleep(0.05)

        assert elapsed < 1
        assert transcripts == []
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())


def test_whisper_drain_timeout_zero_skips_buffered_tail():
    async def scenario():
        calls = []

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            return "hello"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(_pcm(1))
        task = asyncio.create_task(WhisperTranscriber(runner=runner, drain_timeout=0).run(queue, lambda text: None))
        await _wait_until_queue_consumed(queue, task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == []

    asyncio.run(scenario())


def test_whisper_drain_timeout_zero_does_not_wait_for_inflight_runner():
    async def scenario():
        transcripts = []
        started = threading.Event()
        release = threading.Event()

        def runner(pcm: bytes) -> str:
            started.set()
            release.wait(5)
            return "too late"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00" * _BATCH_BYTES)
        task = asyncio.create_task(WhisperTranscriber(runner=runner, drain_timeout=0).run(queue, transcripts.append))
        await _wait_for_thread_event(started)
        task.cancel()
        started_at = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await task
        elapsed = time.monotonic() - started_at
        release.set()
        await asyncio.sleep(0.05)

        assert elapsed < 0.5
        assert transcripts == []
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())


def test_whisper_full_batch_emits_without_cancel():
    async def scenario():
        calls = []
        transcripts = []
        emitted = asyncio.Event()

        def runner(pcm: bytes) -> str:
            calls.append(len(pcm))
            return "hello"

        def on_transcript(text: str) -> None:
            transcripts.append(text)
            emitted.set()

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00" * _BATCH_BYTES)
        task = asyncio.create_task(WhisperTranscriber(runner=runner).run(queue, on_transcript))
        await asyncio.wait_for(emitted.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == [_BATCH_BYTES]
        assert transcripts == ["hello"]

    asyncio.run(scenario())


def test_whisper_cancel_with_empty_buffer_does_not_call_runner():
    async def scenario():
        calls = []

        def runner(pcm: bytes) -> str:
            calls.append(pcm)
            return "hello"

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        task = asyncio.create_task(WhisperTranscriber(runner=runner).run(queue))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls == []

    asyncio.run(scenario())


def test_whisper_runner_error_during_drain_still_cancels():
    async def scenario():
        def runner(pcm: bytes) -> str:
            raise RuntimeError("model failed")

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(_pcm(1))
        task = asyncio.create_task(WhisperTranscriber(runner=runner).run(queue))
        await _wait_until_queue_consumed(queue, task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())


def test_whisper_empty_tail_is_not_delivered():
    async def scenario():
        transcripts = []

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(_pcm(1))
        task = asyncio.create_task(WhisperTranscriber(runner=lambda pcm: "").run(queue, transcripts.append))
        await _wait_until_queue_consumed(queue, task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert transcripts == []

    asyncio.run(scenario())
