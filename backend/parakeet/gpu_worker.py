import asyncio
import gc
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import torch

logger = logging.getLogger(__name__)

_MAX_GPU_QUEUE = 512


class WorkType(Enum):
    BATCH_TRANSCRIBE = "batch_transcribe"
    SHUTDOWN = "shutdown"


@dataclass
class WorkItem:
    work_type: WorkType
    payload: Any
    future: Optional[asyncio.Future] = None
    loop: Optional[asyncio.AbstractEventLoop] = None
    sync_event: Optional[threading.Event] = None
    sync_result: Any = None
    sync_error: Optional[Exception] = None
    created_at: float = field(default_factory=time.monotonic)


class GPUWorker:
    def __init__(self):
        self._queue: queue.Queue[WorkItem] = queue.Queue(maxsize=_MAX_GPU_QUEUE)
        self._thread: Optional[threading.Thread] = None
        self._model = None
        self._poll_timeout = float(os.getenv("PARAKEET_GPU_POLL_TIMEOUT", "0.05"))
        self._gc_interval = int(os.getenv("PARAKEET_GC_INTERVAL", "50"))
        self._gc_counter = 0
        self._ready = threading.Event()
        self._load_error: Optional[Exception] = None
        self._running = False

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set() and self._load_error is None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="gpu-worker")
        self._thread.start()

    def wait_ready(self, timeout: float = 600) -> None:
        if not self._ready.wait(timeout=timeout):
            raise TimeoutError(f"GPU model did not load within {timeout}s")
        if self._load_error is not None:
            raise self._load_error

    def stop(self) -> None:
        if not self._running:
            return
        evt = threading.Event()
        try:
            self._queue.put(WorkItem(WorkType.SHUTDOWN, None, sync_event=evt), timeout=5)
        except queue.Full:
            pass
        self._running = False
        if self._thread:
            self._thread.join(timeout=30)

    def submit(self, payload: dict, loop: asyncio.AbstractEventLoop) -> asyncio.Future:
        if not self.is_ready:
            fut = loop.create_future()
            fut.set_exception(RuntimeError("GPU worker not ready"))
            return fut
        fut = loop.create_future()
        try:
            self._queue.put_nowait(WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop))
        except queue.Full:
            fut.set_exception(RuntimeError("GPU queue full"))
        return fut

    def submit_sync(self, payload: dict, timeout: float = 120.0) -> list:
        if not self.is_ready:
            raise RuntimeError("GPU worker not ready")
        evt = threading.Event()
        item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, sync_event=evt)
        try:
            self._queue.put(item, timeout=5)
        except queue.Full:
            raise RuntimeError("GPU queue full")
        if not evt.wait(timeout=timeout):
            raise TimeoutError("GPU transcription timed out")
        if item.sync_error is not None:
            raise item.sync_error
        return item.sync_result

    def _maybe_gc(self) -> None:
        gc.collect(0)
        self._gc_counter += 1
        if self._gc_counter >= self._gc_interval:
            gc.collect()
            self._gc_counter = 0

    def _run_loop(self) -> None:
        logger.info("GPU worker thread started")
        gc.disable()
        try:
            self._load_model()
            self._ready.set()
        except Exception as exc:
            logger.error(f"Model loading failed: {exc}")
            self._load_error = exc
            self._ready.set()
            return

        while self._running:
            try:
                item = self._queue.get(timeout=self._poll_timeout)
            except queue.Empty:
                continue

            if item.work_type == WorkType.SHUTDOWN:
                break

            try:
                result = self._batch_transcribe(item.payload)
                self._deliver_result(item, result)
            except Exception as exc:
                self._deliver_error(item, exc)
            finally:
                self._maybe_gc()

        self._drain_queue()
        logger.info("GPU worker thread stopped")

    @staticmethod
    def _deliver_result(item: WorkItem, result: Any) -> None:
        if item.sync_event is not None:
            item.sync_result = result
            item.sync_event.set()
        elif item.future is not None and item.loop is not None:
            item.loop.call_soon_threadsafe(_safe_set_result, item.future, result)

    @staticmethod
    def _deliver_error(item: WorkItem, exc: Exception) -> None:
        if item.sync_event is not None:
            item.sync_error = exc
            item.sync_event.set()
        elif item.future is not None and item.loop is not None:
            item.loop.call_soon_threadsafe(_safe_set_exception, item.future, exc)

    def _load_model(self) -> None:
        import nemo.collections.asr as nemo_asr

        model_name = os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
        device = os.getenv("PARAKEET_DEVICE", "cuda:0")
        do_compile = os.getenv("PARAKEET_TORCH_COMPILE", "false").lower() in ("true", "1", "yes")
        disable_cuda_graphs = os.getenv("PARAKEET_CUDA_GRAPHS", "false").lower() not in ("true", "1", "yes")

        torch.backends.cudnn.benchmark = True
        if hasattr(torch, 'set_float32_matmul_precision'):
            torch.set_float32_matmul_precision('high')
        logger.info("Torch optimizations: cudnn.benchmark=True, matmul_precision=high")

        use_bf16 = (
            os.getenv("PARAKEET_BF16", "1") == "1" and torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        )

        logger.info(f"Loading batch model: {model_name}")
        model = nemo_asr.models.ASRModel.from_pretrained(model_name, map_location=device)
        if use_bf16:
            logger.info(f"Converting {model_name} to BF16 (halves GPU memory)")
            model = model.to(torch.bfloat16)
        model.eval()

        if disable_cuda_graphs:
            if hasattr(model, 'decoding') and hasattr(model.decoding, 'decoding'):
                disabled = model.decoding.decoding.disable_cuda_graphs()
                logger.info(f"CUDA graph decoding disabled (was active: {disabled})")

        if do_compile:
            logger.info("Compiling batch model with torch.compile")
            model = torch.compile(model)

        self._model = model
        torch.cuda.empty_cache()

        vram_used = torch.cuda.memory_allocated() / 1024**2
        vram_total = torch.cuda.get_device_properties(0).total_memory / 1024**2
        logger.info(f"VRAM after model load: {vram_used:.0f}MiB / {vram_total:.0f}MiB")
        logger.info("Batch model loaded and ready")

    @torch.inference_mode()
    def _batch_transcribe(self, payload: dict) -> list:
        audio_paths = payload["audio_paths"]
        timestamps = payload.get("timestamps", True)
        batch_size = payload.get("batch_size", len(audio_paths))

        results = self._model.transcribe(
            audio_paths,
            batch_size=batch_size,
            timestamps=timestamps,
            return_hypotheses=timestamps,
            num_workers=0,
            verbose=False,
        )

        serialized = self._extract_results(results, timestamps)
        del results
        return serialized

    @staticmethod
    def _extract_results(results, timestamps: bool) -> list:
        out = []
        items = results if isinstance(results, list) else [results]
        for r in items:
            if timestamps and hasattr(r, 'text') and hasattr(r, 'timestamp'):
                ts = {}
                if isinstance(r.timestamp, dict):
                    for k, entries in r.timestamp.items():
                        if k == 'timestep':
                            continue
                        ts[k] = [
                            {
                                ek: (
                                    round(ev, 4)
                                    if isinstance(ev, float)
                                    else str(ev) if not isinstance(ev, (int, str)) else ev
                                )
                                for ek, ev in e.items()
                            }
                            for e in entries
                        ]
                out.append({"text": str(r.text), "timestamp": ts})
            elif hasattr(r, 'text'):
                out.append({"text": str(r.text)})
            else:
                out.append({"text": str(r)})
        return out

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if item.work_type != WorkType.SHUTDOWN:
                    err = RuntimeError("GPU worker shutting down")
                    self._deliver_error(item, err)
            except queue.Empty:
                break


def _safe_set_result(future: asyncio.Future, result: Any) -> None:
    if not future.done():
        future.set_result(result)


def _safe_set_exception(future: asyncio.Future, exc: Exception) -> None:
    if not future.done():
        future.set_exception(exc)
