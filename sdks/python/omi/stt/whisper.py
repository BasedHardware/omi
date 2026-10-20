from __future__ import annotations

import asyncio
from asyncio import Queue
from typing import Callable, Optional


class WhisperTranscriber:
    """Optional local Whisper. Requires optional dependency ``openai-whisper`` or injected runner.

    Feature gate: only importable/usable when a runner is provided or whisper is installed.

    Cancelling ``run()`` finishes a batch already being transcribed and transcribes PCM
    still sitting in the local buffer, then re-raises ``CancelledError``. ``drain_timeout``
    bounds that wait (default 5 seconds). ``drain_timeout <= 0`` skips it so a slow runner
    cannot hold cancellation open. Audio still waiting on the queue is left there.
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
        inflight: Optional[asyncio.Task[str]] = None
        try:
            while True:
                chunk = await audio_queue.get()
                buffer.extend(chunk)
                if len(buffer) < target:
                    continue
                pcm = bytes(buffer)
                buffer.clear()
                inflight = asyncio.create_task(asyncio.to_thread(self._transcribe_pcm, pcm))
                # shield keeps the batch alive when this task is cancelled; the
                # handler below waits for it under drain_timeout.
                text = await asyncio.shield(inflight)
                inflight = None
                self._deliver(text, on_transcript)
        except asyncio.CancelledError:
            # Python 3.11 keeps the cancellation request armed, so the next await
            # re-raises before the drain can run. Clear it, finish the bounded
            # drain, then re-raise so callers still observe cancellation.
            current = asyncio.current_task()
            uncancel = getattr(current, "uncancel", None) if current is not None else None
            cancelling = getattr(current, "cancelling", None) if current is not None else None
            # uncancel/cancelling exist on 3.11+. 3.10 does not re-arm cancellation.
            if uncancel is not None and cancelling is not None:
                while cancelling():
                    uncancel()
            try:
                await self._drain_on_cancel(inflight, buffer, on_transcript)
            except Exception:
                pass
            raise

    async def _drain_on_cancel(
        self,
        inflight: Optional[asyncio.Task[str]],
        buffer: bytearray,
        on_transcript: Optional[Callable[[str], None]],
    ) -> None:
        if self.drain_timeout <= 0:
            if inflight is None:
                return
            if inflight.done() and not inflight.cancelled():
                try:
                    self._deliver(inflight.result(), on_transcript)
                except Exception:
                    return
                return
            inflight.cancel()
            await asyncio.gather(inflight, return_exceptions=True)
            return
        if inflight is not None:
            self._deliver(await self._bounded_result(inflight), on_transcript)
            return
        if not buffer:
            return
        pcm = bytes(buffer)
        buffer.clear()
        work = asyncio.create_task(asyncio.to_thread(self._transcribe_pcm, pcm))
        self._deliver(await self._bounded_result(work), on_transcript)

    async def _bounded_result(self, work: asyncio.Task[str]) -> str:
        try:
            text = await asyncio.wait_for(asyncio.shield(work), timeout=self.drain_timeout)
        except Exception:
            if not work.done():
                work.cancel()
            return ""
        return text if isinstance(text, str) else ""

    def _deliver(self, text: str, on_transcript: Optional[Callable[[str], None]]) -> None:
        if not text:
            return
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
