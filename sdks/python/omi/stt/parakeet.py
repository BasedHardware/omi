from __future__ import annotations

import asyncio
import json
import os
from asyncio import Queue
from typing import Callable, Optional


def parakeet_ws_url(api_url: str, sample_rate: int = 16000) -> str:
    base = api_url.strip().rstrip("/")
    base = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{base}/v3/stream?sample_rate={sample_rate}"


class ParakeetTranscriber:
    """Hosted Parakeet /v3/stream client (same wire format as backend streaming)."""

    def __init__(self, api_url: Optional[str] = None, *, sample_rate: int = 16000) -> None:
        self.api_url = api_url or os.getenv("HOSTED_PARAKEET_API_URL") or ""
        if not self.api_url:
            raise ValueError("HOSTED_PARAKEET_API_URL or api_url is required for Parakeet")
        self.sample_rate = sample_rate

    async def run(
        self,
        audio_queue: Queue[bytes],
        on_transcript: Optional[Callable[[str], None]] = None,
    ) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise ImportError("Parakeet engine requires websockets package") from exc

        url = parakeet_ws_url(self.api_url, self.sample_rate)
        async with websockets.connect(url, max_size=10 * 1024 * 1024) as ws:
            ready_raw = await asyncio.wait_for(ws.recv(), timeout=10)
            ready = json.loads(ready_raw) if isinstance(ready_raw, str) else None
            if not isinstance(ready, dict) or ready.get("type") != "ready":
                raise RuntimeError(f"Parakeet did not confirm ready: {ready_raw!r}")

            async def send_audio() -> None:
                while True:
                    chunk = await audio_queue.get()
                    await ws.send(chunk)

            async def receive() -> None:
                async for message in ws:
                    if isinstance(message, bytes):
                        continue
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    text = _extract_text(data)
                    if text:
                        if on_transcript:
                            on_transcript(text)
                        else:
                            print(text)

            await asyncio.gather(send_audio(), receive())


def _extract_text(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("text", "transcript"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val
    segs = data.get("segments")
    if isinstance(segs, list):
        parts = []
        for seg in segs:
            if isinstance(seg, dict):
                t = seg.get("text") or seg.get("transcript")
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        return " ".join(parts)
    return ""
