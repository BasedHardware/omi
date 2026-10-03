import asyncio
import logging
import math
import os
import time
import wave as _wave
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, cast

try:
    import soundfile as _sf_mod
except ImportError:
    _sf_mod = None

from gpu_worker import GPUWorker

# soundfile ships without precise type stubs; alias as Any.
_sf: Any = _sf_mod

logger = logging.getLogger(__name__)


@dataclass
class PendingRequest:
    audio_path: str
    timestamps: bool
    future: asyncio.Future[Any]
    owns_file: bool = False
    submitted_at: float = field(default_factory=time.monotonic)
    duration_sec: Optional[float] = None
    lane: str = 'backfill'
    queue_deadline: Optional[float] = None
    expire_handle: Optional[asyncio.TimerHandle] = field(default=None, repr=False)


class QueueFullError(Exception):
    pass


class QueueTimeoutError(Exception):
    pass


class BatchEngine:
    def __init__(
        self,
        gpu_worker: GPUWorker,
        max_batch_size: int = 32,
        max_wait_seconds: float = 0.002,
        max_queue_depth: int = 4096,
        on_batch_complete: Optional[Callable[[List[float], float, int], None]] = None,
        on_gpu_oom: Optional[Callable[[], None]] = None,
        vram_safety_factor: float = 0.8,
        vram_bytes_per_t2: float = 136.6,
        starvation_timeout_sec: float = 5.0,
        max_inflight: int = 2,
        on_queue_wait: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self._gpu_worker = gpu_worker
        self._max_batch_size = max_batch_size
        self._max_wait_seconds = max_wait_seconds
        self._max_queue_depth = max_queue_depth
        self._max_inflight = max_inflight
        self._pending: List[PendingRequest] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[Any]] = None
        self._flush_pending = False
        self._batches_inflight = 0
        self._inflight_tasks: Set[asyncio.Task[Any]] = set()
        self._inflight_sem: Optional[asyncio.Semaphore] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutting_down = False
        self._on_batch_complete = on_batch_complete
        self._on_queue_wait = on_queue_wait
        self._live_batches_since_backfill = 0
        self._on_gpu_oom = on_gpu_oom
        self._vram_safety_factor = vram_safety_factor
        self._vram_bytes_per_t2 = vram_bytes_per_t2
        self._starvation_timeout = starvation_timeout_sec
        self._vram_available_mb = 0.0
        self._vram_enabled = False
        self._attention_mode = "full"
        self._auto_threshold_sec = 300.0
        self._metrics: Dict[str, int] = {
            "total_requests": 0,
            "total_batches": 0,
            "total_files": 0,
            "rejected_requests": 0,
            "vram_limited_batches": 0,
        }

    def _try_init_vram(self) -> None:
        if self._vram_enabled or self._vram_safety_factor <= 0:
            return
        vram = self._gpu_worker.vram_info
        if vram.get("total_mb", 0) <= 0:
            return
        self._attention_mode = vram.get("attention_mode", "full")
        self._auto_threshold_sec = vram.get("auto_threshold_sec", 300.0)
        total_budget = vram["total_mb"] * self._vram_safety_factor - vram["baseline_mb"]
        self._vram_available_mb = max(total_budget / self._max_inflight, 0)
        self._vram_enabled = True
        if total_budget <= 0:
            logger.warning(
                f"VRAM budget is non-positive ({total_budget:.0f} MB) — "
                f"baseline exceeds safety cap. All batches capped to 1."
            )
        logger.info(
            f"VRAM-aware batching enabled: {self._vram_available_mb:.0f} MB per-batch budget "
            f"({total_budget:.0f} MB total / {self._max_inflight} inflight, "
            f"gpu_total={vram['total_mb']:.0f}, baseline={vram['baseline_mb']:.0f}, "
            f"safety={self._vram_safety_factor}, coeff={self._vram_bytes_per_t2})"
        )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._inflight_sem = asyncio.Semaphore(self._max_inflight)
        self._try_init_vram()
        if not self._vram_enabled:
            logger.info("VRAM-aware batching deferred (GPU worker still loading or safety_factor=0)")
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        self._shutting_down = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        for t in list(self._inflight_tasks):
            t.cancel()
        for t in list(self._inflight_tasks):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        while self._pending:
            await self._flush_batch()
        if self._inflight_sem:
            for _ in range(self._max_inflight):
                await self._inflight_sem.acquire()

    @staticmethod
    def _get_audio_duration(path: str) -> Optional[float]:
        try:
            with _wave.open(path) as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            pass
        if _sf is not None:
            try:
                info: Any = _sf.info(path)
                return info.duration
            except Exception:
                pass
        return None

    def _estimate_max_batch(self, max_duration_sec: float, duration_known: bool = True) -> int:
        if not self._vram_enabled or max_duration_sec <= 0:
            return self._max_batch_size
        if self._vram_available_mb <= 0:
            return 1
        if self._attention_mode == "local":
            return self._max_batch_size
        if self._attention_mode == "auto" and duration_known and max_duration_sec >= self._auto_threshold_sec:
            return self._max_batch_size
        T = max_duration_sec / 0.08
        per_file_mb = self._vram_bytes_per_t2 * T * T / (1024 * 1024)
        if per_file_mb <= 0:
            return self._max_batch_size
        return max(1, min(self._max_batch_size, int(self._vram_available_mb / per_file_mb)))

    def _effective_duration(self, req: PendingRequest) -> float:
        if req.duration_sec is not None:
            return req.duration_sec
        return self._auto_threshold_sec

    async def submit(
        self,
        audio_path: str,
        timestamps: bool = True,
        owns_file: bool = False,
        lane: str = 'backfill',
        *,
        queue_deadline: Optional[float] = None,
    ) -> Dict[str, Any]:
        enqueued = False
        req: Optional[PendingRequest] = None
        loop = cast(asyncio.AbstractEventLoop, self._loop)
        try:
            if lane not in ('live', 'backfill'):
                raise ValueError('Unknown Parakeet batch lane')
            if queue_deadline is not None:
                if lane != 'live':
                    raise ValueError('queue_deadline applies only to the live lane')
                if not math.isfinite(queue_deadline):
                    raise ValueError('queue_deadline must be finite')
            duration = self._get_audio_duration(audio_path)
            async with self._lock:
                self._prune_pending()
                if queue_deadline is not None and time.monotonic() >= queue_deadline:
                    raise QueueTimeoutError("Queue deadline expired before enqueue")
                if len(self._pending) >= self._max_queue_depth:
                    self._metrics["rejected_requests"] += 1
                    raise QueueFullError(f"Queue depth {len(self._pending)} exceeds limit {self._max_queue_depth}")

                future = loop.create_future()
                req = PendingRequest(
                    audio_path=audio_path,
                    timestamps=timestamps,
                    future=future,
                    owns_file=owns_file,
                    duration_sec=duration,
                    lane=lane,
                    queue_deadline=queue_deadline,
                )
                if queue_deadline is not None:
                    req.expire_handle = loop.call_at(queue_deadline, self._expire_queued, req)
                self._pending.append(req)
                enqueued = True
                self._metrics["total_requests"] += 1

                pending_count = len(self._pending)
                vram_limit = (
                    self._estimate_max_batch(
                        max(self._effective_duration(r) for r in self._pending),
                        duration_known=all(r.duration_sec is not None for r in self._pending),
                    )
                    if self._vram_enabled and self._pending
                    else self._max_batch_size
                )
                if pending_count >= min(self._max_batch_size, vram_limit) and not self._flush_pending:
                    self._flush_pending = True
                    t = asyncio.create_task(self._guarded_flush())
                    self._inflight_tasks.add(t)
                    t.add_done_callback(self._inflight_tasks.discard)
        except BaseException:
            if owns_file and not enqueued:
                _unlink_safe(audio_path)
            raise

        try:
            return await future
        except asyncio.CancelledError:
            self._remove_pending(req)
            raise

    def _cancel_expire(self, req: PendingRequest) -> None:
        handle = req.expire_handle
        req.expire_handle = None
        if handle is not None:
            handle.cancel()

    def _remove_pending(self, req: PendingRequest) -> bool:
        if req not in self._pending:
            return False
        self._pending.remove(req)
        self._cancel_expire(req)
        if not req.future.done():
            req.future.cancel()
        if req.owns_file:
            _unlink_safe(req.audio_path)
        return True

    def _expire_queued(self, req: PendingRequest) -> None:
        if req not in self._pending:
            return
        self._pending.remove(req)
        req.expire_handle = None
        if not req.future.done():
            req.future.set_exception(QueueTimeoutError("Queued request exceeded its deadline"))
        if req.owns_file:
            _unlink_safe(req.audio_path)

    def _prune_pending(self, now: Optional[float] = None) -> None:
        if not self._pending:
            return
        if now is None:
            now = time.monotonic()
        survivors: List[PendingRequest] = []
        for req in self._pending:
            if req.future.done():
                self._cancel_expire(req)
                if req.owns_file:
                    _unlink_safe(req.audio_path)
                continue
            if req.queue_deadline is not None and now >= req.queue_deadline:
                self._cancel_expire(req)
                req.future.set_exception(QueueTimeoutError("Queued request exceeded its deadline"))
                if req.owns_file:
                    _unlink_safe(req.audio_path)
                continue
            survivors.append(req)
        self._pending = survivors

    async def _flush_loop(self) -> None:
        while not self._shutting_down:
            await asyncio.sleep(self._max_wait_seconds)
            self._prune_pending()
            if self._pending and not self._flush_pending and self._batches_inflight == 0:
                self._flush_pending = True
                t = asyncio.create_task(self._guarded_flush())
                self._inflight_tasks.add(t)
                t.add_done_callback(self._inflight_tasks.discard)

    async def _guarded_flush(self) -> None:
        try:
            await self._flush_batch()
        finally:
            self._flush_pending = False

    def _form_vram_safe_batch(self, candidates: List[PendingRequest]) -> List[PendingRequest]:
        if not candidates or not self._vram_enabled:
            return candidates[: self._max_batch_size]

        now = time.monotonic()
        starved = [r for r in candidates if now - r.submitted_at > self._starvation_timeout]

        if starved:
            anchor = min(starved, key=lambda r: r.submitted_at)
            anchor_dur = self._effective_duration(anchor)
            any_unknown = anchor.duration_sec is None
            limit = self._estimate_max_batch(anchor_dur, duration_known=not any_unknown)
            others = sorted(
                [r for r in candidates if r is not anchor],
                key=lambda r: self._effective_duration(r),
            )
            batch = [anchor]
            for req in others:
                if len(batch) >= limit:
                    break
                candidate_max_dur = max(anchor_dur, self._effective_duration(req))
                has_unknown = any_unknown or req.duration_sec is None
                new_limit = self._estimate_max_batch(candidate_max_dur, duration_known=not has_unknown)
                if len(batch) + 1 <= new_limit:
                    batch.append(req)
                    any_unknown = has_unknown
            return batch

        sorted_candidates = sorted(candidates, key=lambda r: self._effective_duration(r))
        n = min(self._max_batch_size, len(sorted_candidates))
        while n > 1:
            longest = sorted_candidates[n - 1]
            longest_dur = self._effective_duration(longest)
            has_unknown = any(r.duration_sec is None for r in sorted_candidates[:n])
            limit = self._estimate_max_batch(longest_dur, duration_known=not has_unknown)
            if n <= limit:
                break
            n -= 1
        return sorted_candidates[:n]

    def _select_batch(self) -> List[PendingRequest]:
        """Prefer live work, admitting one aged backfill after four live batches.

        The backfill turn is a single item while live is waiting, so a long
        historical recording cannot expand into a large mixed GPU batch.
        The existing VRAM selection still sizes every normal lane batch.
        """
        live = [r for r in self._pending if r.lane == 'live']
        if not live:
            self._live_batches_since_backfill = 0
            return self._form_vram_safe_batch(self._pending)
        backfill = [r for r in self._pending if r.lane == 'backfill']
        if backfill and self._live_batches_since_backfill >= 4:
            oldest = min(backfill, key=lambda r: r.submitted_at)
            if time.monotonic() - oldest.submitted_at >= self._starvation_timeout:
                self._live_batches_since_backfill = 0
                return [oldest]
        self._live_batches_since_backfill += 1
        return self._form_vram_safe_batch(live)

    def pressure_snapshot(self) -> Dict[str, float | int]:
        """One event-loop snapshot of waiting requests, excluding in-flight work."""
        now = time.monotonic()
        self._prune_pending(now)
        live = [r for r in self._pending if r.lane == 'live']
        return {
            'pending_requests': len(self._pending),
            'oldest_pending_seconds': max((now - r.submitted_at for r in self._pending), default=0.0),
            'live_pending_requests': len(live),
            'live_oldest_pending_seconds': max((now - r.submitted_at for r in live), default=0.0),
            'backfill_pending_requests': len(self._pending) - len(live),
        }

    async def _flush_batch(self) -> None:
        sem = cast(asyncio.Semaphore, self._inflight_sem)
        await sem.acquire()
        self._batches_inflight += 1
        try:
            self._try_init_vram()
            async with self._lock:
                self._prune_pending()
                if not self._pending:
                    return
                batch = self._select_batch()
                batch_set = set(id(r) for r in batch)
                self._pending = [r for r in self._pending if id(r) not in batch_set]
                for req in batch:
                    self._cancel_expire(req)
            self._flush_pending = False

            if not batch:
                return

            if len(batch) < self._max_batch_size and self._vram_enabled:
                self._metrics["vram_limited_batches"] += 1

            self._metrics["total_batches"] += 1
            self._metrics["total_files"] += len(batch)

            durations = [self._effective_duration(r) for r in batch]
            max_dur = max(durations) if durations else 0
            logger.info(
                f"Flushing batch: {len(batch)} files "
                f"(max_dur={max_dur:.1f}s, limit={self._estimate_max_batch(max_dur)})"
            )

            batch_start = time.monotonic()
            queue_durations = [batch_start - req.submitted_at for req in batch]
            if self._on_queue_wait:
                for req, wait in zip(batch, queue_durations):
                    self._on_queue_wait(req.lane, wait)

            audio_paths = [r.audio_path for r in batch]
            timestamps = batch[0].timestamps if batch else True
            is_oom = False
            try:
                gpu_future, work_item = self._gpu_worker.submit(
                    {
                        "audio_paths": audio_paths,
                        "timestamps": timestamps,
                        "batch_size": len(batch),
                        "durations": durations,
                    },
                    cast(asyncio.AbstractEventLoop, self._loop),
                )
                results: Any = await gpu_future
                inference_seconds = work_item.inference_seconds if work_item else 0.0

                if self._on_batch_complete:
                    self._on_batch_complete(queue_durations, inference_seconds, len(batch))

                if isinstance(results, list) and len(cast(List[Any], results)) == len(batch):
                    for req, result in zip(batch, cast(List[Any], results)):
                        if not req.future.done():
                            req.future.set_result(result)
                else:
                    items: List[Any] = cast(List[Any], results if isinstance(results, list) else [results])
                    for i, req in enumerate(batch):
                        if not req.future.done():
                            result = items[i] if i < len(items) else {"text": ""}
                            req.future.set_result(result)

            except asyncio.CancelledError:
                err = RuntimeError("Batch cancelled during shutdown")
                for req in batch:
                    if not req.future.done():
                        req.future.set_exception(err)
            except RuntimeError as exc:
                if "CUDA out of memory" in str(exc) or "OutOfMemoryError" in type(exc).__name__:
                    is_oom = True
                err: Exception = QueueFullError(str(exc)) if "GPU queue full" in str(exc) else exc
                logger.error(f"Batch transcription failed: {exc}")
                for req in batch:
                    if not req.future.done():
                        req.future.set_exception(err)
            except Exception as exc:
                if "CUDA out of memory" in str(exc) or "OutOfMemoryError" in type(exc).__name__:
                    is_oom = True
                logger.error(f"Batch transcription failed: {exc}")
                for req in batch:
                    if not req.future.done():
                        req.future.set_exception(exc)
            finally:
                if is_oom and self._on_gpu_oom:
                    self._on_gpu_oom()
                for req in batch:
                    if req.owns_file:
                        _unlink_safe(req.audio_path)
        finally:
            self._batches_inflight -= 1
            sem.release()

    @property
    def metrics(self) -> Dict[str, Any]:
        self._prune_pending()
        return {
            **self._metrics,
            "pending_requests": len(self._pending),
        }


def _unlink_safe(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
