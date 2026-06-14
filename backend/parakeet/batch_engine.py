import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from gpu_worker import GPUWorker, WorkType

logger = logging.getLogger(__name__)


@dataclass
class PendingRequest:
    audio_path: str
    timestamps: bool
    future: asyncio.Future
    owns_file: bool = False
    submitted_at: float = field(default_factory=time.monotonic)


class QueueFullError(Exception):
    pass


class BatchEngine:
    def __init__(
        self,
        gpu_worker: GPUWorker,
        max_batch_size: int = 32,
        max_wait_seconds: float = 0.002,
        max_queue_depth: int = 4096,
    ):
        self._gpu_worker = gpu_worker
        self._max_batch_size = max_batch_size
        self._max_wait_seconds = max_wait_seconds
        self._max_queue_depth = max_queue_depth
        self._pending: list[PendingRequest] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutting_down = False
        self._metrics = {
            "total_requests": 0,
            "total_batches": 0,
            "total_files": 0,
            "rejected_requests": 0,
        }

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        self._shutting_down = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        while self._pending:
            await self._flush_batch()

    async def submit(self, audio_path: str, timestamps: bool = True, owns_file: bool = False) -> dict:
        enqueued = False
        try:
            async with self._lock:
                if len(self._pending) >= self._max_queue_depth:
                    self._metrics["rejected_requests"] += 1
                    raise QueueFullError(f"Queue depth {len(self._pending)} exceeds limit {self._max_queue_depth}")

                future = self._loop.create_future()
                self._pending.append(
                    PendingRequest(
                        audio_path=audio_path,
                        timestamps=timestamps,
                        future=future,
                        owns_file=owns_file,
                    )
                )
                enqueued = True
                self._metrics["total_requests"] += 1

                if len(self._pending) >= self._max_batch_size:
                    asyncio.create_task(self._flush_batch())
        except BaseException:
            if owns_file and not enqueued:
                _unlink_safe(audio_path)
            raise

        return await future

    async def _flush_loop(self) -> None:
        while not self._shutting_down:
            await asyncio.sleep(self._max_wait_seconds)
            if self._pending:
                await self._flush_batch()

    async def _flush_batch(self) -> None:
        async with self._lock:
            if not self._pending:
                return
            batch = self._pending[: self._max_batch_size]
            self._pending = self._pending[self._max_batch_size :]

        self._metrics["total_batches"] += 1
        self._metrics["total_files"] += len(batch)
        logger.info(f"Flushing batch: {len(batch)} files")

        audio_paths = [r.audio_path for r in batch]
        timestamps = batch[0].timestamps if batch else True
        try:
            gpu_future = self._gpu_worker.submit(
                {
                    "audio_paths": audio_paths,
                    "timestamps": timestamps,
                    "batch_size": len(batch),
                },
                self._loop,
            )
            results = await gpu_future

            if isinstance(results, list) and len(results) == len(batch):
                for req, result in zip(batch, results):
                    if not req.future.done():
                        req.future.set_result(result)
            else:
                items = results if isinstance(results, list) else [results]
                for i, req in enumerate(batch):
                    if not req.future.done():
                        result = items[i] if i < len(items) else {"text": ""}
                        req.future.set_result(result)

        except RuntimeError as exc:
            err = QueueFullError(str(exc)) if "GPU queue full" in str(exc) else exc
            logger.error(f"Batch transcription failed: {exc}")
            for req in batch:
                if not req.future.done():
                    req.future.set_exception(err)
        except Exception as exc:
            logger.error(f"Batch transcription failed: {exc}")
            for req in batch:
                if not req.future.done():
                    req.future.set_exception(exc)
        finally:
            for req in batch:
                if req.owns_file:
                    _unlink_safe(req.audio_path)

    @property
    def metrics(self) -> dict:
        return {
            **self._metrics,
            "pending_requests": len(self._pending),
        }


def _unlink_safe(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
