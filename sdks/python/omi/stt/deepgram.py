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
        drain_timeout: float = 5.0,
    ) -> None:
        if not api_key:
            raise ValueError("Deepgram api_key is required")
        self.api_key = api_key
        self.sample_rate = sample_rate
        self.model = model
        self.language = language
        self.drain_timeout = drain_timeout

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

                    send_task = asyncio.create_task(send_audio())
                    recv_task = asyncio.create_task(receive())
                    tasks = (send_task, recv_task)
                    try:
                        done, _ = await asyncio.wait(
                            tasks, return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in done:
                            task.result()
                        # A clean receive EOF must also trigger the retry loop.
                        raise ConnectionError("Deepgram connection closed")
                    except asyncio.CancelledError:
                        send_task.cancel()
                        await asyncio.gather(send_task, return_exceptions=True)
                        try:
                            await asyncio.wait_for(
                                ws.send(json.dumps({"type": "CloseStream"})),
                                timeout=self.drain_timeout or 5.0,
                            )
                            await asyncio.wait_for(
                                asyncio.shield(recv_task), timeout=self.drain_timeout
                            )
                        except Exception:
                            pass
                        raise
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as exc:
                print(f"Deepgram error: {exc}")
                await asyncio.sleep(1)
