from __future__ import annotations

import asyncio
import json
from asyncio import Queue
from typing import Callable, Optional
from urllib.parse import urlencode


class DeepgramTranscriber:
    def __init__(
        self,
        api_key: str,
        *,
        sample_rate: int = 16000,
        model: str = "nova",
        language: str = "en-US",
    ) -> None:
        if not api_key:
            raise ValueError("Deepgram api_key is required")
        self.api_key = api_key
        self.sample_rate = sample_rate
        self.model = model
        self.language = language

    async def run(
        self,
        audio_queue: Queue[bytes],
        on_transcript: Optional[Callable[[str], None]] = None,
    ) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise ImportError("Deepgram engine requires websockets package") from exc

        query = urlencode(
            {
                "punctuate": "true",
                "model": self.model,
                "language": self.language,
                "encoding": "linear16",
                "sample_rate": self.sample_rate,
                "channels": 1,
            }
        )
        url = f"wss://api.deepgram.com/v1/listen?{query}"
        while True:
            try:
                async with websockets.connect(
                    url, additional_headers={"Authorization": f"Token {self.api_key}"}
                ) as ws:

                    async def send_audio() -> None:
                        while True:
                            chunk = await audio_queue.get()
                            await ws.send(chunk)

                    async def receive() -> None:
                        async for message in ws:
                            data = json.loads(message)
                            alt = (
                                data.get("channel", {})
                                .get("alternatives", [{}])[0]
                                .get("transcript", "")
                            )
                            if alt:
                                if on_transcript:
                                    on_transcript(alt)
                                else:
                                    print(alt)

                    await asyncio.gather(send_audio(), receive())
            except Exception as exc:
                print(f"Deepgram error: {exc}")
                await asyncio.sleep(1)
