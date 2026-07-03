import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from gpu_worker import GPUWorker

logger = logging.getLogger(__name__)


@dataclass
class StreamSession:
    stream_id: str
    created_at: float = field(default_factory=time.monotonic)
    last_chunk_at: float = field(default_factory=time.monotonic)
    chunks_processed: int = 0
    total_audio_seconds: float = 0.0


class StreamEngine:

    def __init__(
        self,
        gpu_worker: GPUWorker,
        max_concurrent_streams: int = 128,
        sample_rate: int = 16000,
        idle_timeout: int = 300,
        max_chunk_bytes: int = 512 * 1024,
    ):
        self._gpu_worker = gpu_worker
        self._max_concurrent = max_concurrent_streams
        self._sample_rate = sample_rate
        self._idle_timeout = idle_timeout
        self._max_chunk_bytes = max_chunk_bytes
        self._sessions: dict[str, StreamSession] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._reaper_task: Optional[asyncio.Task] = None
        self._metrics = {
            "total_streams_opened": 0,
            "total_streams_closed": 0,
            "total_chunks_processed": 0,
            "total_streams_reaped": 0,
        }

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self._idle_timeout > 0:
            self._reaper_task = asyncio.create_task(self._reap_idle_streams())

    async def stop(self) -> None:
        if self._reaper_task:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
        stream_ids = list(self._sessions.keys())
        for sid in stream_ids:
            try:
                await self.close_stream(sid)
            except Exception as exc:
                logger.warning(f"Error closing stream {sid} during shutdown: {exc}")

    async def _reap_idle_streams(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()
            to_reap = []
            for sid, session in self._sessions.items():
                idle = now - session.last_chunk_at
                if idle > self._idle_timeout:
                    to_reap.append(sid)
            for sid in to_reap:
                logger.warning(f"Reaping idle stream {sid} (idle {self._idle_timeout}s)")
                try:
                    await self.close_stream(sid)
                    self._metrics["total_streams_reaped"] += 1
                except Exception as exc:
                    logger.error(f"Failed to reap stream {sid}: {exc}")

    async def open_stream(self) -> dict:
        stream_id = str(uuid.uuid4())
        if len(self._sessions) >= self._max_concurrent:
            raise TooManyStreamsError(f"Active streams {len(self._sessions)} at limit {self._max_concurrent}")

        result = await self._gpu_worker.stream_open({"stream_id": stream_id}, self._loop)
        self._sessions[stream_id] = StreamSession(stream_id=stream_id)
        self._metrics["total_streams_opened"] += 1
        logger.info(f"Opened stream {stream_id} (active: {len(self._sessions)})")
        return result

    async def process_chunk(self, stream_id: str, audio_bytes: bytes) -> dict:
        if len(audio_bytes) > self._max_chunk_bytes:
            raise ChunkTooLargeError(f"Chunk {len(audio_bytes)} bytes exceeds limit {self._max_chunk_bytes}")

        session = self._sessions.get(stream_id)
        if session is None:
            raise ValueError(f"Unknown stream: {stream_id}")

        session.last_chunk_at = time.monotonic()
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        result = await self._gpu_worker.stream_chunk({"stream_id": stream_id, "audio_chunk": audio_np}, self._loop)

        session.chunks_processed += 1
        session.total_audio_seconds += len(audio_np) / self._sample_rate
        self._metrics["total_chunks_processed"] += 1
        return result

    async def close_stream(self, stream_id: str) -> dict:
        session = self._sessions.pop(stream_id, None)
        if session is None:
            return {"stream_id": stream_id, "status": "not_found"}

        try:
            result = await self._gpu_worker.stream_close({"stream_id": stream_id}, self._loop)
        except Exception as exc:
            logger.error(f"GPU close failed for stream {stream_id}: {exc}")
            return {"stream_id": stream_id, "status": "close_failed", "error": str(exc)}

        self._metrics["total_streams_closed"] += 1
        logger.info(
            f"Closed stream {stream_id} "
            f"(chunks={session.chunks_processed}, audio={session.total_audio_seconds:.1f}s)"
        )
        return result

    @property
    def active_streams(self) -> int:
        return len(self._sessions)

    @property
    def metrics(self) -> dict:
        return {**self._metrics, "active_streams": len(self._sessions)}


class TooManyStreamsError(Exception):
    pass


class ChunkTooLargeError(Exception):
    pass
