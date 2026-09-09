from __future__ import annotations

import asyncio
import json
import os
import re
from asyncio import Queue
from typing import Callable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def parakeet_ws_url(api_url: str, sample_rate: int = 16000) -> str:
    """Build Parakeet WebSocket URL with proper path and query composition."""
    api_url = api_url.strip()
    if not api_url:
        raise ValueError("api_url cannot be empty")

    if api_url.startswith("//"):
        normalized_url = "https:" + api_url
    elif not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", api_url):
        normalized_url = "https://" + api_url
    else:
        normalized_url = api_url

    parsed = urlsplit(normalized_url)
    if not parsed.netloc:
        raise ValueError(f"Invalid Parakeet API URL, missing host: {api_url!r}")

    # Scheme mapping: http/ws -> ws, otherwise wss
    scheme = parsed.scheme.lower()
    if scheme in ("http", "ws"):
        new_scheme = "ws"
    else:
        new_scheme = "wss"

    # Path composition: append /v3/stream
    path = parsed.path.rstrip("/")
    new_path = f"{path}/v3/stream" if path else "/v3/stream"

    # Query parameters: preserve repeated and blank values, update sample_rate
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    updated_pairs = []
    found_sample_rate = False
    for k, v in query_pairs:
        if k == "sample_rate":
            updated_pairs.append((k, str(sample_rate)))
            found_sample_rate = True
        else:
            updated_pairs.append((k, v))
    if not found_sample_rate:
        updated_pairs.append(("sample_rate", str(sample_rate)))

    new_query = urlencode(updated_pairs)

    # Omit fragment
    return urlunsplit((new_scheme, parsed.netloc, new_path, new_query, ""))


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

            tasks = (
                asyncio.create_task(send_audio()),
                asyncio.create_task(receive()),
            )
            try:
                done, _ = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


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
