import asyncio
from typing import Any, Callable, Optional
from asyncio import Queue

from .stt import SttEngine, create_transcriber


async def transcribe(
    audio_queue: Queue[bytes],
    api_key: str,
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
    if engine == SttEngine.DEEPGRAM.value:
        transcriber = create_transcriber(engine, api_key=api_key, **engine_kwargs)
    elif engine == SttEngine.PARAKEET.value:
        transcriber = create_transcriber(engine, **engine_kwargs)
    elif engine == SttEngine.WHISPER.value:
        transcriber = create_transcriber(engine, **engine_kwargs)
    else:
        raise ValueError(f"unknown engine: {engine}")
    await transcriber.run(audio_queue, on_transcript=on_transcript)
