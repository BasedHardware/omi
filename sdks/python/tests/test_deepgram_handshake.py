"""Deepgram's connect() uses handshake headers that need websockets>=14."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

from omi.stt.deepgram import DeepgramTranscriber

ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_requires_handshake_capable_websockets() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"websockets>=14.0"' in text


def test_requirements_requires_handshake_capable_websockets() -> None:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "websockets>=14.0" in text.splitlines()


def test_deepgram_passes_token_as_additional_headers(monkeypatch) -> None:
    captured: dict = {}

    class FakeSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send(self, message):
            captured["sent"] = message

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Future()

    def connect(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeSocket()

    fake = types.ModuleType("websockets")
    fake.connect = connect
    monkeypatch.setitem(sys.modules, "websockets", fake)

    transcripts: list[str] = []

    async def scenario() -> None:
        audio: asyncio.Queue[bytes] = asyncio.Queue()
        audio.put_nowait(b"\x00\x00")
        worker = asyncio.create_task(DeepgramTranscriber("test-key").run(audio, transcripts.append))
        for _ in range(50):
            if "kwargs" in captured:
                break
            await asyncio.sleep(0.01)
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())

    assert captured["kwargs"]["additional_headers"] == {"Authorization": "Token test-key"}
    assert "api.deepgram.com" in captured["url"]
    assert transcripts == []
