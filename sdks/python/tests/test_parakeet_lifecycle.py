from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from omi.stt.parakeet import ParakeetTranscriber


class FakeWebSocket:
    def __init__(
        self,
        ready_message: str = '{"type": "ready"}',
        messages: list[str | bytes] | None = None,
        send_error: Exception | None = None,
        receive_error: Exception | None = None,
    ) -> None:
        self.ready_message = ready_message
        self.messages = list(messages or [])
        self.send_error = send_error
        self.receive_error = receive_error
        self.sent_chunks: list[bytes | str] = []
        self.closed = False

    async def recv(self) -> str:
        return self.ready_message

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


def test_parakeet_normal_close_idle_queue():
    """When server closes normally and queue is idle, run() must return cleanly without hanging."""
    async def _test():
        fake_ws = FakeWebSocket(messages=[json.dumps({"text": "initial transcript"})])
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        received = []

        with patch("websockets.connect", return_value=fake_ws):
            transcriber = ParakeetTranscriber("https://test.parakeet.example")
            await asyncio.wait_for(
                transcriber.run(queue, on_transcript=lambda t: received.append(t)),
                timeout=1.0,
            )

        assert received == ["initial transcript"]
        assert fake_ws.closed is True

    asyncio.run(_test())


def test_parakeet_audio_and_transcript_delivery():
    """Audio in queue is transmitted, transcript is dispatched, and session closes cleanly."""
    async def _test():
        fake_ws = FakeWebSocket(messages=[json.dumps({"text": "transcribed audio"})])
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        await queue.put(b"\x00\x01\x02\x03")
        received = []

        with patch("websockets.connect", return_value=fake_ws):
            transcriber = ParakeetTranscriber("https://test.parakeet.example")
            await asyncio.wait_for(
                transcriber.run(queue, on_transcript=lambda t: received.append(t)),
                timeout=1.0,
            )

        assert b"\x00\x01\x02\x03" in fake_ws.sent_chunks
        assert received == ["transcribed audio"]

    asyncio.run(_test())


def test_parakeet_send_error_cancels_sibling():
    """Send errors raise out of run() and cancel the receive task."""
    async def _test():
        fake_ws = FakeWebSocket(
            messages=[json.dumps({"text": "ignored"})],
            send_error=ConnectionResetError("send reset"),
        )
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        await queue.put(b"bad-data")

        with patch("websockets.connect", return_value=fake_ws):
            transcriber = ParakeetTranscriber("https://test.parakeet.example")
            with pytest.raises(ConnectionResetError, match="send reset"):
                await asyncio.wait_for(transcriber.run(queue), timeout=1.0)

        assert fake_ws.closed is True

    asyncio.run(_test())


def test_parakeet_receive_error_cancels_sibling():
    """Receive errors raise out of run() and cancel the sender task."""
    async def _test():
        fake_ws = FakeWebSocket(receive_error=RuntimeError("connection dropped unexpectedly"))
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        with patch("websockets.connect", return_value=fake_ws):
            transcriber = ParakeetTranscriber("https://test.parakeet.example")
            with pytest.raises(RuntimeError, match="connection dropped unexpectedly"):
                await asyncio.wait_for(transcriber.run(queue), timeout=1.0)

        assert fake_ws.closed is True

    asyncio.run(_test())


def test_parakeet_callback_exception_cancels_sibling():
    """Exceptions in on_transcript callback raise out of run() and cancel the sender."""
    async def _test():
        fake_ws = FakeWebSocket(messages=[json.dumps({"text": "crash me"})])
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def crashing_callback(_text: str):
            raise ValueError("callback crashed")

        with patch("websockets.connect", return_value=fake_ws):
            transcriber = ParakeetTranscriber("https://test.parakeet.example")
            with pytest.raises(ValueError, match="callback crashed"):
                await asyncio.wait_for(
                    transcriber.run(queue, on_transcript=crashing_callback),
                    timeout=1.0,
                )

        assert fake_ws.closed is True

    asyncio.run(_test())


def test_parakeet_caller_cancellation():
    """Cancelling run() task cleans up internal send and receive tasks."""
    async def _test():
        class HangingWebSocket(FakeWebSocket):
            async def __anext__(self):
                await asyncio.sleep(100)

        fake_ws = HangingWebSocket()
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        with patch("websockets.connect", return_value=fake_ws):
            transcriber = ParakeetTranscriber("https://test.parakeet.example")
            task = asyncio.create_task(transcriber.run(queue))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert fake_ws.closed is True
        assert fake_ws.sent_chunks[-1] == "finalize"

    asyncio.run(_test())


def test_parakeet_server_eof_does_not_send_finalize():
    """Server close is not client Stop — do not send finalize."""
    async def _test():
        fake_ws = FakeWebSocket(messages=[json.dumps({"text": "initial transcript"})])
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        with patch("websockets.connect", return_value=fake_ws):
            transcriber = ParakeetTranscriber("https://test.parakeet.example")
            await asyncio.wait_for(transcriber.run(queue), timeout=1.0)

        assert "finalize" not in fake_ws.sent_chunks
        assert fake_ws.closed is True

    asyncio.run(_test())
