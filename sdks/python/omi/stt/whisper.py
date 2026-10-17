from __future__ import annotations

import asyncio
from asyncio import Queue
from typing import Callable, Optional


class WhisperTranscriber:
    """Optional local Whisper. Requires optional dependency ``openai-whisper`` or injected runner.

    Feature gate: only importable/usable when a runner is provided or whisper is installed.
    """

    def __init__(
        self,
        *,
        model_name: str = "tiny.en",
        runner: Optional[Callable[[bytes], str]] = None,
        drain_timeout: float = 5.0,
    ) -> None:
        self.model_name = model_name
        self.runner = runner
        self.drain_timeout = drain_timeout
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
        current_transcribe_task: Optional[asyncio.Task[str]] = None

        def emit(text: str) -> None:
            if text:
                if on_transcript:
                    on_transcript(text)
                else:
                    print(text)

        try:
            while True:
                chunk = await audio_queue.get()
                buffer.extend(chunk)
                if len(buffer) < target:
                    continue
                pcm = bytes(buffer)
                buffer.clear()
                current_transcribe_task = asyncio.create_task(
                    asyncio.to_thread(self._transcribe_pcm, pcm)
                )
                text = await asyncio.shield(current_transcribe_task)
                emit(text)
                current_transcribe_task = None
        except asyncio.CancelledError:
            timeout = self.drain_timeout if self.drain_timeout is not None else 5.0
            if timeout <= 0:
                if current_transcribe_task is not None and not current_transcribe_task.done():
                    current_transcribe_task.cancel()
                raise

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout

            def remaining_timeout() -> float:
                return max(0.0, deadline - loop.time())

            # 1. Complete in-flight batch if one was actively transcribing
            if current_transcribe_task is not None:
                try:
                    text = await asyncio.wait_for(
                        asyncio.shield(current_transcribe_task),
                        timeout=remaining_timeout(),
                    )
                    emit(text)
                except Exception:
                    pass

            # 2. Drain any remaining unread chunks in the queue into buffer
            while not audio_queue.empty():
                try:
                    buffer.extend(audio_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            # 3. Transcribe buffered tail
            if buffer:
                tail_pcm = bytes(buffer)
                buffer.clear()
                tail_task = asyncio.create_task(
                    asyncio.to_thread(self._transcribe_pcm, tail_pcm)
                )
                try:
                    tail_text = await asyncio.wait_for(
                        tail_task,
                        timeout=remaining_timeout(),
                    )
                    emit(tail_text)
                except Exception:
                    tail_task.cancel()
            raise

    def _transcribe_pcm(self, pcm: bytes) -> str:
        if self.runner is not None:
            return self.runner(pcm)
        import numpy as np  # type: ignore

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        result = self._model.transcribe(audio, fp16=False, language="en")
        return (result.get("text") or "").strip()
