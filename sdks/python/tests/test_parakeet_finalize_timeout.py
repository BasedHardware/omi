from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from omi.stt.parakeet import ParakeetTranscriber


def test_cancellation_bounds_a_blocked_finalize_send_and_joins_receiver():
    async def scenario():
        receiving = asyncio.Event()
        finalizing = asyncio.Event()
        send_cancelled = asyncio.Event()
        receiver_cancelled = asyncio.Event()

        class BlockedWebSocket:
            closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                self.closed = True

            async def recv(self):
                return '{"type": "ready"}'

            async def send(self, chunk):
                assert chunk == "finalize"
                finalizing.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    send_cancelled.set()

            def __aiter__(self):
                return self

            async def __anext__(self):
                receiving.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    receiver_cancelled.set()

        ws = BlockedWebSocket()
        with patch("websockets.connect", return_value=ws):
            transcriber = ParakeetTranscriber(
                "https://fixture.invalid", drain_timeout=0.01
            )
            task = asyncio.create_task(transcriber.run(asyncio.Queue()))
            await asyncio.wait_for(receiving.wait(), timeout=1)
            task.cancel()
            await asyncio.wait_for(finalizing.wait(), timeout=1)
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=0.5)

        assert send_cancelled.is_set()
        assert receiver_cancelled.is_set()
        assert ws.closed
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())
