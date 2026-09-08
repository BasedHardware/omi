from __future__ import annotations

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from omi.transcribe import transcribe
from omi.stt import SttEngine


def test_deepgram_requires_api_key():
    async def _test():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        with pytest.raises(ValueError, match="Deepgram api_key is required"):
            await transcribe(queue)

    asyncio.run(_test())


def test_deepgram_accepts_positional_api_key():
    async def _test():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        fake_transcriber = MagicMock()
        fake_transcriber.run = MagicMock(side_effect=lambda q, on_transcript=None: asyncio.sleep(0))

        with patch("omi.transcribe.create_transcriber", return_value=fake_transcriber) as mock_create:
            await transcribe(queue, "test-api-key")
            mock_create.assert_called_once_with(SttEngine.DEEPGRAM.value, api_key="test-api-key")

    asyncio.run(_test())


def test_deepgram_accepts_keyword_api_key():
    async def _test():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        fake_transcriber = MagicMock()
        fake_transcriber.run = MagicMock(side_effect=lambda q, on_transcript=None: asyncio.sleep(0))

        with patch("omi.transcribe.create_transcriber", return_value=fake_transcriber) as mock_create:
            await transcribe(queue, api_key="kw-api-key")
            mock_create.assert_called_once_with(SttEngine.DEEPGRAM.value, api_key="kw-api-key")

    asyncio.run(_test())


def test_whisper_does_not_require_api_key():
    async def _test():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        fake_transcriber = MagicMock()
        fake_transcriber.run = MagicMock(side_effect=lambda q, on_transcript=None: asyncio.sleep(0))

        with patch("omi.transcribe.create_transcriber", return_value=fake_transcriber) as mock_create:
            await transcribe(queue, engine="whisper", runner=lambda b: "hello")
            mock_create.assert_called_once_with(
                SttEngine.WHISPER.value,
                runner=mock_create.call_args[1]["runner"]
            )

    asyncio.run(_test())


def test_parakeet_does_not_require_api_key():
    async def _test():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        fake_transcriber = MagicMock()
        fake_transcriber.run = MagicMock(side_effect=lambda q, on_transcript=None: asyncio.sleep(0))

        with patch("omi.transcribe.create_transcriber", return_value=fake_transcriber) as mock_create:
            await transcribe(queue, engine="parakeet", api_url="https://parakeet.example")
            mock_create.assert_called_once_with(
                SttEngine.PARAKEET.value,
                api_url="https://parakeet.example"
            )

    asyncio.run(_test())


def test_transcribe_callable_positional_as_on_transcript():
    async def _test():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        callback = MagicMock()
        fake_transcriber = MagicMock()
        fake_transcriber.run = MagicMock(side_effect=lambda q, on_transcript=None: asyncio.sleep(0))

        with patch("omi.transcribe.create_transcriber", return_value=fake_transcriber) as mock_create:
            await transcribe(queue, callback, engine="whisper", runner=lambda b: "text")
            mock_create.assert_called_once()
            fake_transcriber.run.assert_called_once_with(queue, on_transcript=callback)

    asyncio.run(_test())
