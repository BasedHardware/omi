from __future__ import annotations

import asyncio
from asyncio import Queue
from typing import Callable, Optional


class WhisperTranscriber:
    """Optional local Whisper. Requires optional dependency ``openai-whisper`` or injected runner.

    Feature gate: only importable/usable when a runner is provided or whisper is installed.
    """

    def __init__(self, *, model_name: str = "tiny.en", runner: Optional[Callable[[bytes], str]] = None) -> None:
        self.model_name = model_name
        self.runner = runner
        self._model = None
        if runner is None:
            try:
                import whisper  # type: ignore
            except ImportError as exc:
                raise ImportError(
                    "Whisper engine requires optional dependency 'openai-whisper' "
                    "or an injected runner= callable. Install: pip install omi-sdk[whisper]"
                ) from exc
            self._model = whisper.load_model(model_name)

    async def run(
        self,
        audio_queue: Queue[bytes],
        on_transcript: Optional[Callable[[str], None]] = None,
    ) -> None:
        # Batch PCM for a simple offline-style loop (parity surface, not ultra-low-latency).
        buffer = bytearray()
        target = 16000 * 2 * 5  # ~5s mono s16le
        while True:
            chunk = await audio_queue.get()
            buffer.extend(chunk)
            if len(buffer) < target:
                continue
            pcm = bytes(buffer)
            buffer.clear()
            text = await asyncio.to_thread(self._transcribe_pcm, pcm)
            if text:
                if on_transcript:
                    on_transcript(text)
                else:
                    print(text)

    def _transcribe_pcm(self, pcm: bytes) -> str:
        if self.runner is not None:
            return self.runner(pcm)
        import numpy as np  # type: ignore

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        result = self._model.transcribe(audio, fp16=False, language="en")
        return (result.get("text") or "").strip()
