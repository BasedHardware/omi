from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from omi.stt.deepgram import DeepgramTranscriber


class FakeWebSocket:
    def __init__(
        self,
        messages: list[str | bytes] | None = None,
        send_error: Exception | None = None,
        receive_error: Exception | None = None,
    ) -> None:
        self.messages = list(messages or [])
        self.send_error = send_error
        self.receive_error = receive_error
        self.sent_chunks: list[bytes | str] = []
        self.closed = False

    async def send(self, chunk: bytes | str) -> None:
        if self.send_error:
            raise self.send_error
        self.sent_chunks.append(chunk)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str | bytes:
        if self.receive_error:
            raise self.receive_error
        if self.messages:
            return self.messages.pop(0)
        raise StopAsyncIteration

    async def __aenter__(self) -> FakeWebSocket:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.closed = True


def test_deepgram_normal_close_idle_queue_reconnects():
    """When server closes normally and queue is idle, connection is drained and retry loop triggers."""
    async def _test():
        connections = 0
        reconnected = asyncio.Event()

        def make_fake_ws(*args, **kwargs):
            nonlocal connections
            connections += 1
            if connections == 1:
                # First connection closes normally with empty queue
                return FakeWebSocket()
            # Second connection reached
            reconnected.set()
            return FakeWebSocket()

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        with patch("websockets.connect", side_effect=make_fake_ws), \
             patch("asyncio.sleep", return_value=None):
            transcriber = DeepgramTranscriber("fake-key")
            task = asyncio.create_task(transcriber.run(queue))
            await asyncio.wait_for(reconnected.wait(), timeout=1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert connections >= 2

    asyncio.run(_test())


def test_deepgram_audio_and_transcript_delivery():
    """Audio chunks are transmitted and transcripts are delivered to callback."""
    async def _test():
        transcript_msg = json.dumps({
            "channel": {"alternatives": [{"transcript": "hello world"}]}
        })
        received = []
        delivered = asyncio.Event()

        def on_transcript(t: str):
            received.append(t)
            delivered.set()

        fake_ws = FakeWebSocket(messages=[transcript_msg])
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        await queue.put(b"\x00\x01\x02\x03")

        with patch("websockets.connect", return_value=fake_ws), \
             patch("asyncio.sleep", return_value=None):
            transcriber = DeepgramTranscriber("fake-key")
            task = asyncio.create_task(transcriber.run(queue, on_transcript=on_transcript))
            await asyncio.wait_for(delivered.wait(), timeout=1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert b"\x00\x01\x02\x03" in fake_ws.sent_chunks
        assert received == ["hello world"]

    asyncio.run(_test())


def test_deepgram_send_error_cancels_sibling():
    """Send error cancels sibling receiver and initiates reconnection."""
    async def _test():
        connections = 0
        reconnected = asyncio.Event()

        def make_fake_ws(*args, **kwargs):
            nonlocal connections
            connections += 1
            if connections == 1:
                return FakeWebSocket(send_error=ConnectionResetError("send failed"))
            reconnected.set()
            return FakeWebSocket()

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        await queue.put(b"chunk")

        with patch("websockets.connect", side_effect=make_fake_ws), \
             patch("asyncio.sleep", return_value=None):
            transcriber = DeepgramTranscriber("fake-key")
            task = asyncio.create_task(transcriber.run(queue))
            await asyncio.wait_for(reconnected.wait(), timeout=1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert connections >= 2

    asyncio.run(_test())


def test_deepgram_receive_error_cancels_sibling():
    """Receive error cancels sibling sender and initiates reconnection."""
    async def _test():
        connections = 0
        reconnected = asyncio.Event()

        def make_fake_ws(*args, **kwargs):
            nonlocal connections
            connections += 1
            if connections == 1:
                return FakeWebSocket(receive_error=RuntimeError("connection dropped"))
            reconnected.set()
            return FakeWebSocket()

        queue: asyncio.Queue[bytes] = asyncio.Queue()

        with patch("websockets.connect", side_effect=make_fake_ws), \
             patch("asyncio.sleep", return_value=None):
            transcriber = DeepgramTranscriber("fake-key")
            task = asyncio.create_task(transcriber.run(queue))
            await asyncio.wait_for(reconnected.wait(), timeout=1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert connections >= 2

    asyncio.run(_test())


def test_deepgram_callback_exception_cancels_sibling():
    """Callback exception cancels sibling sender and initiates reconnection."""
    async def _test():
        connections = 0
        reconnected = asyncio.Event()

        transcript_msg = json.dumps({
            "channel": {"alternatives": [{"transcript": "crash"}]}
        })

        def crashing_callback(_text: str):
            raise ValueError("callback crashed")

        def make_fake_ws(*args, **kwargs):
            nonlocal connections
            connections += 1
            if connections == 1:
                return FakeWebSocket(messages=[transcript_msg])
            reconnected.set()
            return FakeWebSocket()

        queue: asyncio.Queue[bytes] = asyncio.Queue()

        with patch("websockets.connect", side_effect=make_fake_ws), \
             patch("asyncio.sleep", return_value=None):
            transcriber = DeepgramTranscriber("fake-key")
            task = asyncio.create_task(transcriber.run(queue, on_transcript=crashing_callback))
            await asyncio.wait_for(reconnected.wait(), timeout=1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert connections >= 2

    asyncio.run(_test())


def test_deepgram_caller_cancellation():
    """Cancelling caller task cleanly terminates run() and cleans up internal tasks."""
    async def _test():
        class HangingWebSocket(FakeWebSocket):
            async def __anext__(self):
                await asyncio.sleep(100)

        fake_ws = HangingWebSocket()
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        with patch("websockets.connect", return_value=fake_ws):
            transcriber = DeepgramTranscriber("fake-key")
            task = asyncio.create_task(transcriber.run(queue))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert json.dumps({"type": "CloseStream"}) in fake_ws.sent_chunks
        assert fake_ws.sent_chunks[-1] == json.dumps({"type": "CloseStream"})
        assert fake_ws.closed is True

    asyncio.run(_test())


def test_deepgram_reconnect_after_eof_does_not_send_closestream():
    """Server EOF is a reconnect, not a client Stop — do not send CloseStream."""
    async def _test():
        connections = 0
        reconnected = asyncio.Event()
        first_ws: FakeWebSocket | None = None

        def make_fake_ws(*args, **kwargs):
            nonlocal connections, first_ws
            connections += 1
            if connections == 1:
                first_ws = FakeWebSocket()
                return first_ws
            reconnected.set()
            return FakeWebSocket()

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        with patch("websockets.connect", side_effect=make_fake_ws), \
             patch("asyncio.sleep", return_value=None):
            transcriber = DeepgramTranscriber("fake-key")
            task = asyncio.create_task(transcriber.run(queue))
            await asyncio.wait_for(reconnected.wait(), timeout=1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert first_ws is not None
        assert json.dumps({"type": "CloseStream"}) not in first_ws.sent_chunks

    asyncio.run(_test())
