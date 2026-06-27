"""
Tests for async vision streaming behavior.

Covers:
- Async producer yields chunks progressively via callback queue
- Queue-based producer/consumer pattern works with asyncio.create_task
- Error in producer still terminates queue
"""

import asyncio
import os

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


class AsyncStreamingCallback:
    """Mirrors the production AsyncStreamingCallback from agentic.py."""

    def __init__(self):
        self.queue = asyncio.Queue()

    async def put_data(self, text):
        await self.queue.put(f"data: {text}")

    async def end(self):
        await self.queue.put(None)


async def _fake_vision_stream(chunks, callback):
    """Simulates the async _ask_vision_stream producer."""
    output_list = []
    for content in chunks:
        await asyncio.sleep(0.01)  # simulate network latency
        if content is not None:
            await callback.put_data(content)
            output_list.append(content)
    await callback.end()
    return ''.join(output_list)


class TestAsyncVisionStreamPattern:
    """Test the producer/consumer pattern used in _execute_file_chat_stream."""

    @pytest.mark.asyncio
    async def test_chunks_arrive_progressively(self):
        """Consumer receives chunks as producer yields them, not all at once."""
        callback = AsyncStreamingCallback()
        chunks = ["Hello", " world", "!"]

        # Track when chunks arrive
        received = []
        received_times = []

        async def _produce():
            return await _fake_vision_stream(chunks, callback)

        task = asyncio.create_task(_produce())

        # Drain queue concurrently (mirrors graph.py pattern)
        loop = asyncio.get_event_loop()
        while True:
            chunk = await callback.queue.get()
            if chunk:
                received.append(chunk)
                received_times.append(loop.time())
            else:
                break

        answer = await task

        assert answer == "Hello world!"
        assert received == ["data: Hello", "data:  world", "data: !"]
        assert len(received_times) == 3
        # Chunks should arrive at different times (progressive, not burst)
        assert received_times[-1] - received_times[0] >= 0.02

    @pytest.mark.asyncio
    async def test_empty_stream_terminates(self):
        """Empty producer still sends end signal to consumer."""
        callback = AsyncStreamingCallback()

        async def _produce():
            return await _fake_vision_stream([], callback)

        task = asyncio.create_task(_produce())

        received = []
        while True:
            chunk = await callback.queue.get()
            if chunk:
                received.append(chunk)
            else:
                break

        answer = await task
        assert answer == ""
        assert received == []

    @pytest.mark.asyncio
    async def test_producer_error_mid_stream_terminates_queue(self):
        """Mid-stream error: queue receives end sentinel via try/finally."""
        callback = AsyncStreamingCallback()

        async def _failing_mid_stream():
            """Mirrors _ask_vision_stream: try/finally wraps entire body."""
            try:
                await callback.put_data("chunk1")
                raise ValueError("simulated OpenAI stream error")
            finally:
                await callback.end()

        task = asyncio.create_task(_failing_mid_stream())

        received = []
        while True:
            chunk = await asyncio.wait_for(callback.queue.get(), timeout=2.0)
            if chunk:
                received.append(chunk)
            else:
                break  # Got None sentinel — queue properly terminated

        assert received == ["data: chunk1"]

        with pytest.raises(ValueError, match="simulated OpenAI stream error"):
            await task

    @pytest.mark.asyncio
    async def test_producer_error_before_stream_terminates_queue(self):
        """Early error (e.g. files.content fails): queue still gets sentinel."""
        callback = AsyncStreamingCallback()

        async def _failing_early():
            """Mirrors _ask_vision_stream failing during file fetch."""
            try:
                raise ConnectionError("simulated files.content failure")
            finally:
                await callback.end()

        task = asyncio.create_task(_failing_early())

        # Consumer should get the end sentinel without hanging
        chunk = await asyncio.wait_for(callback.queue.get(), timeout=2.0)
        assert chunk is None  # End sentinel, no data chunks

        with pytest.raises(ConnectionError, match="simulated files.content failure"):
            await task

    @pytest.mark.asyncio
    async def test_concurrent_health_not_blocked(self):
        """A slow vision stream should not block other async work."""
        callback = AsyncStreamingCallback()

        async def _slow_producer():
            for i in range(3):
                await asyncio.sleep(0.05)
                await callback.put_data(f"chunk{i}")
            await callback.end()

        task = asyncio.create_task(_slow_producer())

        # Simulate a "health check" running concurrently
        health_start = asyncio.get_event_loop().time()
        health_done = asyncio.Event()

        async def _health_check():
            await asyncio.sleep(0.01)
            health_done.set()

        asyncio.create_task(_health_check())

        # Health check should complete while producer is still running
        await asyncio.wait_for(health_done.wait(), timeout=0.1)
        health_elapsed = asyncio.get_event_loop().time() - health_start

        # Health check completed in ~10ms, not blocked by 150ms producer
        assert health_elapsed < 0.05

        # Clean up
        while True:
            chunk = await callback.queue.get()
            if not chunk:
                break
        await task


class TestSyncCallbackErrorPaths:
    """Test the synchronous callback error-handling patterns (end_nowait).

    These mirror the try/finally and try/except patterns in:
    - ask_stream (sync OpenAI Assistants path)
    - process_chat_with_file_stream (_ensure_thread_and_assistant failure)
    """

    class SyncStreamingCallback:
        """Mirrors the synchronous callback interface used by ask_stream."""

        def __init__(self):
            self.queue = asyncio.Queue()
            self.ended = False

        def put_data_nowait(self, text):
            self.queue.put_nowait(f"data: {text}")

        def end_nowait(self):
            self.ended = True
            self.queue.put_nowait(None)

    @pytest.mark.asyncio
    async def test_ask_stream_fill_question_failure_ends_callback(self):
        """If _fill_question raises inside ask_stream, callback still gets end sentinel."""
        callback = self.SyncStreamingCallback()

        def _failing_ask_stream(callback):
            """Mirrors ask_stream: _fill_question inside try/finally."""
            output_list = []
            try:
                # _fill_question fails (e.g., thread deleted, network error)
                raise ConnectionError("simulated _fill_question failure")
            finally:
                callback.end_nowait()
            return ''.join(output_list)

        with pytest.raises(ConnectionError, match="simulated _fill_question failure"):
            _failing_ask_stream(callback)

        assert callback.ended is True
        chunk = callback.queue.get_nowait()
        assert chunk is None  # End sentinel delivered

    @pytest.mark.asyncio
    async def test_ask_stream_mid_stream_failure_ends_callback(self):
        """If streaming fails mid-way, try/finally still calls end_nowait."""
        callback = self.SyncStreamingCallback()

        def _failing_mid_stream(callback):
            output_list = []
            try:
                callback.put_data_nowait("chunk1")
                callback.put_data_nowait("chunk2")
                raise RuntimeError("simulated stream.text_deltas error")
            finally:
                callback.end_nowait()
            return ''.join(output_list)

        with pytest.raises(RuntimeError, match="simulated stream.text_deltas error"):
            _failing_mid_stream(callback)

        assert callback.ended is True
        received = []
        while not callback.queue.empty():
            item = callback.queue.get_nowait()
            received.append(item)
        assert received == ["data: chunk1", "data: chunk2", None]

    @pytest.mark.asyncio
    async def test_ensure_thread_failure_ends_callback_before_ask_stream(self):
        """process_chat_with_file_stream: if _ensure_thread_and_assistant fails,
        callback.end_nowait() is called before re-raise (ask_stream never runs)."""
        callback = self.SyncStreamingCallback()

        def _process_chat_pattern(callback):
            """Mirrors process_chat_with_file_stream non-image path."""
            try:
                # _ensure_thread_and_assistant fails
                raise Exception("Failed to create OpenAI thread: connection timeout")
            except Exception:
                callback.end_nowait()
                raise

        with pytest.raises(Exception, match="Failed to create OpenAI thread"):
            _process_chat_pattern(callback)

        assert callback.ended is True
        chunk = callback.queue.get_nowait()
        assert chunk is None


class TestProducerConsumerCallbackData:
    """Test the full producer/consumer pattern from _execute_file_chat_stream,
    including callback_data population on success and error."""

    @pytest.mark.asyncio
    async def test_success_populates_callback_data(self):
        """On success, callback_data gets answer, memories_found, ask_for_nps."""
        callback = AsyncStreamingCallback()
        callback_data = {}

        async def _produce():
            output = []
            try:
                for text in ["Hello", " from", " file"]:
                    await asyncio.sleep(0.01)
                    await callback.put_data(text)
                    output.append(text)
            finally:
                await callback.end()
            return ''.join(output)

        task = asyncio.create_task(_produce())

        received = []
        while True:
            chunk = await callback.queue.get()
            if chunk:
                received.append(chunk)
            else:
                break

        answer = await task

        # Mirrors graph.py callback_data population
        callback_data['answer'] = answer
        callback_data['memories_found'] = []
        callback_data['ask_for_nps'] = True

        assert callback_data['answer'] == "Hello from file"
        assert callback_data['memories_found'] == []
        assert callback_data['ask_for_nps'] is True
        assert len(received) == 3

    @pytest.mark.asyncio
    async def test_error_populates_callback_data_error(self):
        """On producer error, callback_data gets error string."""
        callback = AsyncStreamingCallback()
        callback_data = {}

        async def _produce():
            try:
                await callback.put_data("partial")
                raise ValueError("OpenAI API error")
            finally:
                await callback.end()

        task = asyncio.create_task(_produce())

        received = []
        while True:
            chunk = await asyncio.wait_for(callback.queue.get(), timeout=2.0)
            if chunk:
                received.append(chunk)
            else:
                break

        # Mirrors graph.py error handling
        try:
            await task
        except Exception as e:
            callback_data['error'] = str(e)

        assert callback_data['error'] == "OpenAI API error"
        assert received == ["data: partial"]

    @pytest.mark.asyncio
    async def test_none_callback_data_no_crash(self):
        """When callback_data is None, producer/consumer still works without error."""
        callback = AsyncStreamingCallback()
        callback_data = None  # Mirrors graph.py when callback_data is None

        async def _produce():
            try:
                await callback.put_data("data")
            finally:
                await callback.end()
            return "data"

        task = asyncio.create_task(_produce())

        while True:
            chunk = await callback.queue.get()
            if not chunk:
                break

        answer = await task

        # Mirrors graph.py: only write to callback_data if not None
        if callback_data is not None:
            callback_data['answer'] = answer

        assert answer == "data"
