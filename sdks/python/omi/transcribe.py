import asyncio
from typing import Any, Callable, Optional
from asyncio import Queue

from .stt import SttEngine, create_transcriber


async def transcribe(
    audio_queue: Queue[bytes],
    api_key: Optional[str] = None,
    on_transcript: Optional[Callable[[str], None]] = None,
    *,
    engine: str = SttEngine.DEEPGRAM.value,
    **engine_kwargs: Any,
) -> None:
    """Real-time transcription. Default engine: Deepgram (legacy).

    engine:
      - deepgram (default): requires api_key
      - parakeet: uses HOSTED_PARAKEET_API_URL or engine_kwargs api_url
      - whisper: optional local model / injected runner
    """
    if callable(api_key) and on_transcript is None:
        on_transcript = api_key
        api_key = None

    if engine == SttEngine.DEEPGRAM.value:
        key = api_key or engine_kwargs.pop("api_key", None)
        if not key:
            raise ValueError("Deepgram api_key is required")
        transcriber = create_transcriber(engine, api_key=key, **engine_kwargs)
    elif engine == SttEngine.PARAKEET.value:
        transcriber = create_transcriber(engine, **engine_kwargs)
    elif engine == SttEngine.WHISPER.value:
        transcriber = create_transcriber(engine, **engine_kwargs)
    else:
        raise ValueError(f"unknown engine: {engine}")
    await transcriber.run(audio_queue, on_transcript=on_transcript)
