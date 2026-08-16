import asyncio
import functools
import gc
import math
import os
import time
import uuid
import logging
import io as _io
import wave as _wave

import soundfile as sf
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, cast

gc.disable()

from fastapi import FastAPI, Form, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram
from prometheus_client import make_asgi_app  # type: ignore[reportUnknownVariableType]  # prometheus_client partially typed

from gpu_worker import GPUWorker, AudioDurationExceededError
from batch_engine import BatchEngine, QueueFullError
from transcribe import (
    transcribe_file,
    transcribe_file_v2,
    set_gpu_worker,
    INFERENCE_MODE,
    _transcribe_from_gpu_result,  # type: ignore[reportPrivateUsage,reportUnknownVariableType]  # upstream transcribe partially typed
)
from stream_handler import StreamSession, warmup_rnnt_decoder
from admission import StreamAdmissionController

logging.basicConfig(level=logging.INFO)
# httpx logs every outbound request at INFO; the per-segment diarizer embedding
# calls (one per audio segment) flood the log pipeline with 200 OK noise. Keep
# only warnings/errors (4xx/5xx, timeouts) from httpx. See issue #8080.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_ASR_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_AUDIO_LEN_BUCKETS = (1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600, 7200, 18000, 36000)

ACTIVE_STREAMS = Gauge('parakeet_active_streams', 'Active /v3/stream WebSocket connections')
ACTIVE_BATCH = Gauge('parakeet_active_batch_requests', 'Active batch transcription requests')
PENDING_REQUESTS = Gauge('parakeet_batch_pending_requests', 'Pending requests in batch engine queue')
REQUEST_DURATION = Histogram(
    'parakeet_request_duration_seconds',
    'Request latency',
    ['endpoint'],
    buckets=_ASR_BUCKETS,
)
STREAM_DURATION = Histogram(
    'parakeet_stream_duration_seconds',
    'WebSocket stream session duration',
    buckets=[10, 30, 60, 120, 300, 600, 1800, 3600],
)
BATCH_SIZE_HIST = Histogram(
    'parakeet_batch_size',
    'Number of files per GPU batch',
    buckets=[1, 2, 4, 8, 16, 32, 64],
)
RTFX = Gauge('parakeet_rtfx', 'Real-time factor of last request (audio_duration / processing_time)')
AUDIO_DURATION = Histogram(
    'parakeet_audio_duration_seconds',
    'Input audio length distribution',
    buckets=_AUDIO_LEN_BUCKETS,
)
QUEUE_DURATION = Histogram(
    'parakeet_queue_duration_seconds',
    'Time spent waiting in queue before batch assembly',
    buckets=_ASR_BUCKETS,
)
INFERENCE_DURATION = Histogram(
    'parakeet_inference_duration_seconds',
    'Pure GPU inference time excluding queue and post-processing',
    buckets=_ASR_BUCKETS,
)
GPU_OOM_TOTAL = Counter('parakeet_gpu_oom_total', 'CUDA out-of-memory events')
GPU_FATAL_ERRORS_TOTAL = Counter(
    'parakeet_gpu_fatal_errors_total',
    'Fatal CUDA errors that make a Parakeet GPU worker unavailable',
)
REQUESTS_TOTAL = Counter('parakeet_requests_total', 'Total requests by status', ['endpoint', 'status'])

gpu_worker: Optional[GPUWorker] = None
batch_engine: Optional[BatchEngine] = None
stream_admission: Optional[StreamAdmissionController] = None
start_time: float = 0
_diarize_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="diarize")
_io_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file-io")
_max_file_duration_sec = float(os.getenv("PARAKEET_MAX_FILE_DURATION", "0"))


def _get_audio_duration_from_bytes(data: bytes) -> float:
    try:
        info = cast(Any, sf.info(_io.BytesIO(data)))  # type: ignore[reportUnknownMemberType]  # soundfile partially typed
        return info.duration
    except Exception:
        pass
    try:
        with _wave.open(_io.BytesIO(data), 'rb') as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        if _max_file_duration_sec > 0:
            return float('inf')
        return 0.0


def _duration_limit_detail(audio_dur: float) -> str:
    if math.isinf(audio_dur):
        return "Cannot determine audio duration"
    return f"Audio duration {audio_dur:.0f}s exceeds limit ({_max_file_duration_sec:.0f}s)"


def _on_batch_complete(queue_durations: List[float], inference_seconds: float, batch_size: int) -> None:
    for qd in queue_durations:
        QUEUE_DURATION.observe(qd)
    INFERENCE_DURATION.observe(inference_seconds)
    BATCH_SIZE_HIST.observe(batch_size)


def _on_gpu_oom() -> None:
    GPU_OOM_TOTAL.inc()


def _on_fatal_cuda_error(_reason: str) -> None:
    GPU_FATAL_ERRORS_TOTAL.inc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global gpu_worker, batch_engine, stream_admission, start_time
    start_time = time.monotonic()
    stream_admission = StreamAdmissionController.from_env(os.environ)

    os.makedirs("_temp", exist_ok=True)

    if INFERENCE_MODE != "nim":
        gpu_worker = GPUWorker(on_fatal_cuda_error=_on_fatal_cuda_error)
        gpu_worker.start()
        set_gpu_worker(gpu_worker)

        batch_engine = BatchEngine(
            gpu_worker=gpu_worker,
            max_batch_size=int(os.getenv("PARAKEET_MAX_BATCH_SIZE", "32")),
            max_wait_seconds=float(os.getenv("PARAKEET_BATCH_WAIT_SECONDS", "0.002")),
            max_queue_depth=int(os.getenv("PARAKEET_MAX_QUEUE_DEPTH", "4096")),
            on_batch_complete=_on_batch_complete,
            on_gpu_oom=_on_gpu_oom,
            vram_safety_factor=float(os.getenv("PARAKEET_VRAM_SAFETY_FACTOR", "0.8")),
            vram_bytes_per_t2=float(os.getenv("PARAKEET_VRAM_BYTES_PER_T2", "136.6")),
            starvation_timeout_sec=float(os.getenv("PARAKEET_STARVATION_TIMEOUT", "5.0")),
            max_inflight=int(os.getenv("PARAKEET_MAX_INFLIGHT", "2")),
        )
        await batch_engine.start()
        logger.info("Server started, GPU model loading in background...")
    else:
        logger.info("Parakeet ASR server ready (NIM mode)")

    warmup_rnnt_decoder()
    yield

    logger.info("Shutting down...")
    if batch_engine:
        await batch_engine.stop()
    if gpu_worker:
        gpu_worker.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/metrics", cast(Any, make_asgi_app()))


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@app.post("/v1/transcribe", response_model=None)
async def transcribe(file: UploadFile = File(...)) -> JSONResponse | Dict[str, Any]:
    if gpu_worker is not None and not gpu_worker.is_ready:
        REQUESTS_TOTAL.labels(endpoint="v1_transcribe", status="error").inc()
        return JSONResponse(status_code=503, content={"detail": "Model loading, try again shortly"})
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    ACTIVE_BATCH.inc()
    t0 = time.monotonic()
    audio_dur = 0.0
    status = "success"
    loop = asyncio.get_running_loop()
    try:
        data = await file.read()
        audio_dur = _get_audio_duration_from_bytes(data)
        if _max_file_duration_sec > 0 and audio_dur > _max_file_duration_sec:
            status = "rejected"
            return JSONResponse(
                status_code=413,
                content={"detail": _duration_limit_detail(audio_dur)},
            )
        if audio_dur > 0 and math.isfinite(audio_dur):
            AUDIO_DURATION.observe(audio_dur)
        await loop.run_in_executor(_io_pool, _write_file, file_path, data)

        if batch_engine is not None:
            PENDING_REQUESTS.set(len(batch_engine._pending))  # type: ignore[reportPrivateUsage]  # batch_engine internal queue
            result = cast(Dict[str, Any], await batch_engine.submit(file_path, timestamps=True, owns_file=True))  # type: ignore[reportUnknownMemberType]  # batch_engine.submit partially typed
            PENDING_REQUESTS.set(len(batch_engine._pending))  # type: ignore[reportPrivateUsage]  # batch_engine internal queue
            return JSONResponse(content=_transcribe_from_gpu_result(result))
        else:
            result = await loop.run_in_executor(_diarize_pool, transcribe_file, file_path)
            return result
    except QueueFullError:
        status = "error"
        return JSONResponse(status_code=503, content={"detail": "Server overloaded — try again later"})
    except AudioDurationExceededError as e:
        status = "rejected"
        return JSONResponse(status_code=413, content={"detail": str(e)})
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.monotonic() - t0
        REQUEST_DURATION.labels(endpoint="v1_transcribe").observe(elapsed)
        REQUESTS_TOTAL.labels(endpoint="v1_transcribe", status=status).inc()
        if status == "success" and audio_dur > 0 and elapsed > 0:
            RTFX.set(audio_dur / elapsed)
        ACTIVE_BATCH.dec()
        if batch_engine is None:
            await loop.run_in_executor(_io_pool, _remove_file, file_path)


@app.post("/v2/transcribe", response_model=None)
async def transcribe_v2(
    file: UploadFile = File(...),
    diarize: bool = Form(True),
) -> JSONResponse | Dict[str, Any]:
    if gpu_worker is not None and not gpu_worker.is_ready:
        REQUESTS_TOTAL.labels(endpoint="v2_transcribe", status="error").inc()
        return JSONResponse(status_code=503, content={"detail": "Model loading, try again shortly"})
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    ACTIVE_BATCH.inc()
    t0 = time.monotonic()
    audio_dur = 0.0
    status = "success"
    loop = asyncio.get_running_loop()
    try:
        data = await file.read()
        audio_dur = _get_audio_duration_from_bytes(data)
        if _max_file_duration_sec > 0 and audio_dur > _max_file_duration_sec:
            status = "rejected"
            return JSONResponse(
                status_code=413,
                content={"detail": _duration_limit_detail(audio_dur)},
            )
        if audio_dur > 0 and math.isfinite(audio_dur):
            AUDIO_DURATION.observe(audio_dur)
        await loop.run_in_executor(_io_pool, _write_file, file_path, data)

        if batch_engine is not None:
            PENDING_REQUESTS.set(len(batch_engine._pending))  # type: ignore[reportPrivateUsage]  # batch_engine internal queue
            gpu_result = cast(Dict[str, Any], await batch_engine.submit(file_path, timestamps=True, owns_file=False))  # type: ignore[reportUnknownMemberType]  # batch_engine.submit partially typed
            PENDING_REQUESTS.set(len(batch_engine._pending))  # type: ignore[reportPrivateUsage]  # batch_engine internal queue
            result = cast(
                Dict[str, Any],
                await loop.run_in_executor(
                    _diarize_pool,
                    cast(Any, functools.partial(transcribe_file_v2, file_path, gpu_result=gpu_result, diarize=diarize)),
                ),
            )
        else:
            result = cast(
                Dict[str, Any],
                await loop.run_in_executor(
                    _diarize_pool, cast(Any, functools.partial(transcribe_file_v2, file_path, diarize=diarize))
                ),
            )
        return result
    except QueueFullError:
        status = "error"
        return JSONResponse(status_code=503, content={"detail": "Server overloaded — try again later"})
    except AudioDurationExceededError as e:
        status = "rejected"
        return JSONResponse(status_code=413, content={"detail": str(e)})
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.monotonic() - t0
        REQUEST_DURATION.labels(endpoint="v2_transcribe").observe(elapsed)
        REQUESTS_TOTAL.labels(endpoint="v2_transcribe", status=status).inc()
        if status == "success" and audio_dur > 0 and elapsed > 0:
            RTFX.set(audio_dur / elapsed)
        ACTIVE_BATCH.dec()
        await loop.run_in_executor(_io_pool, _remove_file, file_path)


_WS_RECEIVE_TIMEOUT = 30.0


@app.websocket("/v3/stream")
async def stream_transcribe(
    websocket: WebSocket,
    sample_rate: int = Query(16000),
    vad_threshold: float = Query(None),
    hangover_s: float = Query(None),
):
    await websocket.accept()
    if gpu_worker is not None and not gpu_worker.is_ready:
        REQUESTS_TOTAL.labels(endpoint='v3_stream', status='error').inc()
        await websocket.close(code=1013, reason='service_not_ready')
        return
    if stream_admission is None:
        logger.error('v3/stream admission unavailable')
        await websocket.close(code=1011, reason='service_not_ready')
        return
    decision = stream_admission.try_acquire()
    if decision.lease is None:
        REQUESTS_TOTAL.labels(endpoint='v3_stream', status=decision.reason).inc()
        await websocket.close(code=1013, reason=decision.reason)
        return

    session: Optional[StreamSession] = None
    active_gauge_owned = False
    t0 = time.monotonic()
    try:
        session = StreamSession(sample_rate=sample_rate, vad_threshold=vad_threshold, hangover_s=hangover_s)
        ACTIVE_STREAMS.inc()
        active_gauge_owned = True
        await websocket.send_json({'type': 'ready'})
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=_WS_RECEIVE_TIMEOUT)
            except asyncio.TimeoutError:
                continue

            if "bytes" in msg:
                segments = cast(List[Any], await session.feed(msg["bytes"]))
                for seg in segments:
                    await websocket.send_json(seg)
            elif "text" in msg:
                if msg["text"] == "finalize":
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"v3/stream error: {e}")
        try:
            await websocket.close(code=1011, reason='stream_initialization_failed')
        except Exception:
            pass
    finally:
        try:
            if session is not None:
                final_segments = cast(List[Any], await session.flush())
                for seg in final_segments:
                    try:
                        await websocket.send_json(seg)
                    except Exception:
                        break
        except Exception as e:
            logger.error(f"v3/stream flush error: {e}")
        finally:
            try:
                if session is not None:
                    session.cleanup()
            except Exception as e:
                logger.error(f"v3/stream cleanup error: {e}")
            finally:
                if active_gauge_owned:
                    ACTIVE_STREAMS.dec()
                    STREAM_DURATION.observe(time.monotonic() - t0)
                decision.lease.release()


@app.get("/health", response_model=None)
async def health_check() -> JSONResponse | Dict[str, Any]:
    if gpu_worker is not None:
        ready = gpu_worker.is_ready
        fatal_cuda_reason = gpu_worker.fatal_cuda_reason
        body = {
            "status": "healthy" if ready else "unhealthy" if fatal_cuda_reason is not None else "loading",
            "ready": ready,
            "uptime_seconds": round(time.monotonic() - start_time, 1),
        }
        if fatal_cuda_reason is not None:
            body["reason"] = fatal_cuda_reason
        if not ready:
            return JSONResponse(status_code=503, content=body)
        return body
    return {"status": "healthy"}


@app.get("/batch/metrics")
async def batch_metrics() -> Dict[str, Any]:
    if batch_engine is not None:
        PENDING_REQUESTS.set(len(batch_engine._pending))  # type: ignore[reportPrivateUsage]  # batch_engine internal queue
        return cast(Dict[str, Any], batch_engine.metrics)  # type: ignore[reportUnknownMemberType]  # batch_engine.metrics partially typed
    return {}
