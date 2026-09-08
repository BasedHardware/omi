"""Feature-gated STT engines: deepgram (default), whisper (optional), parakeet (optional)."""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional, Protocol


class SttEngine(str, Enum):
    DEEPGRAM = "deepgram"
    WHISPER = "whisper"
    PARAKEET = "parakeet"


TranscriptHandler = Callable[[str], None]


class StreamingTranscriber(Protocol):
    async def run(self, audio_queue, on_transcript: Optional[TranscriptHandler] = None) -> None: ...


def create_transcriber(engine: SttEngine | str, **kwargs) -> StreamingTranscriber:
    name = SttEngine(engine)
    if name is SttEngine.DEEPGRAM:
        from .deepgram import DeepgramTranscriber

        return DeepgramTranscriber(**kwargs)
    if name is SttEngine.WHISPER:
        from .whisper import WhisperTranscriber

        return WhisperTranscriber(**kwargs)
    if name is SttEngine.PARAKEET:
        from .parakeet import ParakeetTranscriber

        return ParakeetTranscriber(**kwargs)
    raise ValueError(f"unknown STT engine: {engine}")


__all__ = ["SttEngine", "StreamingTranscriber", "create_transcriber", "TranscriptHandler"]
