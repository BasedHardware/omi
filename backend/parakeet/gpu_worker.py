import asyncio
import gc
import logging
import os
import queue
import threading
import time
import wave as _wave
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, cast

import soundfile as sf
import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv

try:
    import nemo.collections.asr as _nemo_asr  # type: ignore[reportMissingImports]  # nemo_toolkit not installed in dev venv
except ImportError:
    _nemo_asr = None

try:
    import pyannote.audio.core.model as _pam  # type: ignore[reportMissingImports]  # pyannote.audio not installed in dev venv
    from pyannote.audio import Inference as _PyannoteInference  # type: ignore[reportMissingImports]  # pyannote.audio not installed in dev venv
    from pyannote.audio import Model as _PyannoteModel  # type: ignore[reportMissingImports]  # pyannote.audio not installed in dev venv
except ImportError:
    _pam = None
    _PyannoteModel = None
    _PyannoteInference = None

# These native/ML libraries ship without type stubs; alias as Any so member
# access does not cascade into hundreds of reportUnknownMemberType warnings.
_torch: Any = cast(Any, torch)
_sf: Any = cast(Any, sf)
nemo_asr: Any = _nemo_asr
pam: Any = _pam
PyannoteModel: Any = cast(Any, _PyannoteModel)
PyannoteInference: Any = cast(Any, _PyannoteInference)

logger = logging.getLogger(__name__)

_MAX_GPU_QUEUE = 512

_VALID_ATTN_MODES = ("full", "local", "auto")


class AudioDurationExceededError(Exception):
    pass


class WorkType(Enum):
    BATCH_TRANSCRIBE = "batch_transcribe"
    EMBEDDING = "embedding"
    SHUTDOWN = "shutdown"


@dataclass
class WorkItem:
    work_type: WorkType
    payload: Any
    future: Optional[asyncio.Future[Any]] = None
    loop: Optional[asyncio.AbstractEventLoop] = None
    sync_event: Optional[threading.Event] = None
    sync_result: Any = None
    sync_error: Optional[Exception] = None
    created_at: float = field(default_factory=time.monotonic)
    inference_seconds: float = 0.0


class GPUWorker:
    def __init__(self) -> None:
        self._queue: queue.Queue[WorkItem] = queue.Queue(maxsize=_MAX_GPU_QUEUE)
        self._thread: Optional[threading.Thread] = None
        self._model: Any = None
        self._embedding_model: Any = None
        self._poll_timeout: float = float(os.getenv("PARAKEET_GPU_POLL_TIMEOUT", "0.05"))
        self._gc_interval: int = int(os.getenv("PARAKEET_GC_INTERVAL", "50"))
        self._gc_counter: int = 0
        self._ready: threading.Event = threading.Event()
        self._load_error: Optional[Exception] = None
        self._running: bool = False
        self._submit_lock: threading.Lock = threading.Lock()
        self._attn_mode: str = os.getenv("PARAKEET_ATTENTION_MODE", "full").lower()
        if self._attn_mode not in _VALID_ATTN_MODES:
            raise ValueError(f"PARAKEET_ATTENTION_MODE must be one of {_VALID_ATTN_MODES}, got '{self._attn_mode}'")
        self._attn_auto_threshold_sec: float = float(os.getenv("PARAKEET_AUTO_ATTN_THRESHOLD", "300"))
        ctx_raw: str = os.getenv("PARAKEET_LOCAL_ATTN_CONTEXT", "128,128")
        self._attn_local_context: List[int] = [int(x.strip()) for x in ctx_raw.split(",")]
        self._attn_is_local: bool = False
        self._model_dtype: Optional[Any] = None
        self._max_file_duration_sec: float = float(os.getenv("PARAKEET_MAX_FILE_DURATION", "0"))
        self._vram_total_mb: float = 0.0
        self._vram_baseline_mb: float = 0.0

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set() and self._load_error is None

    @property
    def vram_info(self) -> Dict[str, Any]:
        return {
            "total_mb": self._vram_total_mb,
            "baseline_mb": self._vram_baseline_mb,
            "attention_mode": self._attn_mode,
            "auto_threshold_sec": self._attn_auto_threshold_sec,
        }

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
        with self._submit_lock:
            if not self._running:
                return
            self._running = False
        evt = threading.Event()
        try:
            self._queue.put(WorkItem(WorkType.SHUTDOWN, None, sync_event=evt), timeout=5)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=30)

    def submit(
        self, payload: Dict[str, Any], loop: asyncio.AbstractEventLoop
    ) -> Tuple[asyncio.Future[Any], Optional[WorkItem]]:
        if not self.is_ready:
            fut: asyncio.Future[Any] = loop.create_future()
            fut.set_exception(RuntimeError("GPU worker not ready"))
            return fut, None
        with self._submit_lock:
            if not self._running:
                fut = loop.create_future()
                fut.set_exception(RuntimeError("GPU worker shutting down"))
                return fut, None
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                fut.set_exception(RuntimeError("GPU queue full"))
            return fut, item

    def submit_sync(self, payload: Dict[str, Any], timeout: float = 120.0) -> List[Dict[str, Any]]:
        if not self.is_ready:
            raise RuntimeError("GPU worker not ready")
        with self._submit_lock:
            if not self._running:
                raise RuntimeError("GPU worker shutting down")
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
        return cast(List[Dict[str, Any]], item.sync_result)

    def submit_embedding_sync(self, payload: Dict[str, Any], timeout: float = 30.0) -> Any:
        if not self.is_ready:
            raise RuntimeError("GPU worker not ready")
        with self._submit_lock:
            if not self._running:
                raise RuntimeError("GPU worker shutting down")
            evt = threading.Event()
            item = WorkItem(WorkType.EMBEDDING, payload, sync_event=evt)
            try:
                self._queue.put(item, timeout=5)
            except queue.Full:
                raise RuntimeError("GPU queue full")
        if not evt.wait(timeout=timeout):
            raise TimeoutError("GPU embedding timed out")
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
                t_infer = time.monotonic()
                if item.work_type == WorkType.EMBEDDING:
                    result: Any = self._compute_embedding(item.payload)
                else:
                    result = self._batch_transcribe(item.payload)
                item.inference_seconds = time.monotonic() - t_infer
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
        model_name = os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
        device = os.getenv("PARAKEET_DEVICE", "cuda:0")
        do_compile = os.getenv("PARAKEET_TORCH_COMPILE", "false").lower() in ("true", "1", "yes")
        disable_cuda_graphs = os.getenv("PARAKEET_CUDA_GRAPHS", "false").lower() not in ("true", "1", "yes")

        _torch.backends.cudnn.benchmark = True
        if hasattr(_torch, 'set_float32_matmul_precision'):
            _torch.set_float32_matmul_precision('high')
        logger.info("Torch optimizations: cudnn.benchmark=True, matmul_precision=high")

        use_bf16 = (
            os.getenv("PARAKEET_BF16", "1") == "1" and _torch.cuda.is_available() and _torch.cuda.is_bf16_supported()
        )

        logger.info(f"Loading batch model: {model_name}")
        model: Any = nemo_asr.models.ASRModel.from_pretrained(model_name, map_location=device)
        if use_bf16:
            logger.info(f"Converting {model_name} to BF16 (halves GPU memory)")
            model = model.to(_torch.bfloat16)
            self._model_dtype = _torch.bfloat16
        model.eval()

        if disable_cuda_graphs:
            if hasattr(model, 'decoding') and hasattr(model.decoding, 'decoding'):
                disabled = model.decoding.decoding.disable_cuda_graphs()
                logger.info(f"CUDA graph decoding disabled (was active: {disabled})")

        if self._attn_mode == "local":
            model.change_attention_model("rel_pos_local_attn", self._attn_local_context)
            model.change_subsampling_conv_chunking_factor(1)
            if self._model_dtype is not None:
                model.to(self._model_dtype)
            self._attn_is_local = True
            logger.info(f"Attention mode: local (context={self._attn_local_context}) — linear VRAM scaling")
        elif self._attn_mode == "auto":
            logger.info(
                f"Attention mode: auto — full for <{self._attn_auto_threshold_sec}s, "
                f"local for >={self._attn_auto_threshold_sec}s (torch.compile disabled for auto mode)"
            )
        else:
            logger.info("Attention mode: full (default)")

        if self._max_file_duration_sec > 0:
            logger.info(f"Max file duration guard: {self._max_file_duration_sec}s")

        if do_compile and self._attn_mode != "auto":
            logger.info("Compiling batch model with torch.compile")
            model = _torch.compile(model)
        elif do_compile and self._attn_mode == "auto":
            logger.info("Skipping torch.compile — incompatible with auto attention switching")

        self._model = model
        _torch.cuda.empty_cache()

        self._load_embedding_model()

        if _torch.cuda.is_available():
            device = os.getenv("PARAKEET_DEVICE", "cuda:0")
            dev_idx = int(device.split(":")[-1]) if ":" in device else 0
            free_bytes, total_bytes = _torch.cuda.mem_get_info(dev_idx)
            self._vram_total_mb = total_bytes / (1024 * 1024)
            self._vram_baseline_mb = (total_bytes - free_bytes) / (1024 * 1024)
            logger.info(
                f"VRAM after model load: {self._vram_baseline_mb:.0f}MiB used / "
                f"{self._vram_total_mb:.0f}MiB total ({free_bytes / (1024 * 1024):.0f}MiB free)"
            )
        logger.info("Batch model loaded and ready")

    def _load_embedding_model(self) -> None:
        if PyannoteModel is None:
            logger.warning("pyannote.audio not installed, built-in embedding unavailable")
            return

        try:
            orig_load: Any = _torch.load
            orig_check: Any = pam.check_version

            def _patched_load(*args: Any, **kwargs: Any) -> Any:
                return orig_load(*args, **{**kwargs, "weights_only": False})

            def _patched_check(*args: Any, **kwargs: Any) -> bool:
                return True

            try:
                _torch.load = _patched_load
                pam.check_version = _patched_check
                model: Any = PyannoteModel.from_pretrained(
                    "pyannote/wespeaker-voxceleb-resnet34-LM",
                    token=os.getenv("HUGGINGFACE_TOKEN"),
                )
            finally:
                _torch.load = orig_load
                pam.check_version = orig_check

            inference: Any = PyannoteInference(model, window="whole")
            if _torch.cuda.is_available():
                inference.to(_torch.device("cuda"))
            self._embedding_model = inference
            logger.info("Built-in speaker embedding model loaded (wespeaker-voxceleb-resnet34-LM)")
        except Exception as e:
            logger.warning(f"Could not load built-in embedding model: {e}")

    @_torch.inference_mode()
    def _compute_embedding(self, payload: Dict[str, Any]) -> Any:
        if self._embedding_model is None:
            return None
        waveform: Any = payload["waveform"]
        sample_rate: Any = payload["sample_rate"]
        return self._embedding_model({"waveform": waveform, "sample_rate": sample_rate})

    def _get_audio_duration_sec(self, path: str) -> float:
        try:
            info: Any = _sf.info(path)
            return float(info.duration)
        except Exception:
            pass
        try:
            with _wave.open(path) as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception as exc:
            logger.warning(f"Cannot determine audio duration for {path}: {exc}")
            if self._max_file_duration_sec > 0:
                return float('inf')
            return 0.0

    def _switch_attention(self, to_local: bool) -> None:
        if to_local == self._attn_is_local:
            return
        if to_local:
            self._model.change_attention_model("rel_pos_local_attn", self._attn_local_context)
            self._model.change_subsampling_conv_chunking_factor(1)
            self._attn_is_local = True
        else:
            self._model.change_attention_model("rel_pos")
            self._attn_is_local = False
        if self._model_dtype is not None:
            self._model.to(self._model_dtype)

    @_torch.inference_mode()
    def _batch_transcribe(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        audio_paths: List[str] = payload["audio_paths"]
        timestamps: bool = payload.get("timestamps", True)
        batch_size: int = payload.get("batch_size", len(audio_paths))

        if self._max_file_duration_sec > 0:
            for path in audio_paths:
                dur = self._get_audio_duration_sec(path)
                if dur > self._max_file_duration_sec:
                    raise AudioDurationExceededError(
                        f"Audio file {dur:.0f}s exceeds max duration "
                        f"({self._max_file_duration_sec:.0f}s). Use shorter files or "
                        f"set PARAKEET_ATTENTION_MODE=local/auto for longer audio."
                    )

        if self._attn_mode == "auto":
            durations_from_batcher: Optional[List[float]] = payload.get("durations")
            if durations_from_batcher:
                max_dur = max(durations_from_batcher)
            else:
                max_dur = max((self._get_audio_duration_sec(p) for p in audio_paths), default=0.0)
            need_local = max_dur >= self._attn_auto_threshold_sec
            if need_local != self._attn_is_local:
                mode_name = "local" if need_local else "full"
                logger.info(f"Auto-switching attention to {mode_name} (longest file: {max_dur:.0f}s)")
                self._switch_attention(need_local)

        results: Any = self._model.transcribe(
            audio_paths,
            batch_size=batch_size,
            timestamps=timestamps,
            return_hypotheses=timestamps,
            num_workers=0,
            verbose=False,
        )

        serialized: List[Dict[str, Any]] = self._extract_results(results, timestamps)
        del results
        return serialized

    @staticmethod
    def _extract_results(results: Any, timestamps: bool) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        items: List[Any] = cast(List[Any], results if isinstance(results, list) else [results])
        for r in items:
            if timestamps and hasattr(r, 'text') and hasattr(r, 'timestamp'):
                ts: Dict[str, Any] = {}
                r_timestamp: Any = r.timestamp
                if isinstance(r_timestamp, dict):
                    for k, entries in cast(Dict[Any, Any], r_timestamp).items():
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


def _safe_set_result(future: asyncio.Future[Any], result: Any) -> None:
    if not future.done():
        future.set_result(result)


def _safe_set_exception(future: asyncio.Future[Any], exc: Exception) -> None:
    if not future.done():
        future.set_exception(exc)
