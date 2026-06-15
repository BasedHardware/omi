import asyncio
import functools
import gc
import os
import time
import uuid
import logging
import io as _io
import wave as _wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional

gc.disable()

from fastapi import FastAPI, Form, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

from gpu_worker import GPUWorker
from batch_engine import BatchEngine, QueueFullError
from transcribe import (
    transcribe_file,
    transcribe_file_v2,
    set_gpu_worker,
    INFERENCE_MODE,
    _transcribe_from_gpu_result,
)
from stream_handler import StreamSession, warmup_rnnt_decoder

logging.basicConfig(level=logging.INFO)
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
REQUESTS_TOTAL = Counter('parakeet_requests_total', 'Total requests by status', ['endpoint', 'status'])

gpu_worker: Optional[GPUWorker] = None
batch_engine: Optional[BatchEngine] = None
start_time: float = 0
_diarize_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="diarize")
_io_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file-io")


def _get_audio_duration_from_bytes(data: bytes) -> float:
    try:
        with _wave.open(_io.BytesIO(data), 'rb') as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def _on_batch_complete(queue_durations, inference_seconds, batch_size):
    for qd in queue_durations:
        QUEUE_DURATION.observe(qd)
    INFERENCE_DURATION.observe(inference_seconds)
    BATCH_SIZE_HIST.observe(batch_size)


def _on_gpu_oom():
    GPU_OOM_TOTAL.inc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global gpu_worker, batch_engine, start_time
    start_time = time.monotonic()

    os.makedirs("_temp", exist_ok=True)

    if INFERENCE_MODE != "nim":
        gpu_worker = GPUWorker()
        gpu_worker.start()
        set_gpu_worker(gpu_worker)

        batch_engine = BatchEngine(
            gpu_worker=gpu_worker,
            max_batch_size=int(os.getenv("PARAKEET_MAX_BATCH_SIZE", "32")),
            max_wait_seconds=float(os.getenv("PARAKEET_BATCH_WAIT_SECONDS", "0.002")),
            max_queue_depth=int(os.getenv("PARAKEET_MAX_QUEUE_DEPTH", "4096")),
            on_batch_complete=_on_batch_complete,
            on_gpu_oom=_on_gpu_oom,
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
app.mount("/metrics", make_asgi_app())


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@app.post("/v1/transcribe")
async def transcribe(file: UploadFile = File(...)):
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
        if audio_dur > 0:
            AUDIO_DURATION.observe(audio_dur)
        await loop.run_in_executor(_io_pool, _write_file, file_path, data)

        if batch_engine is not None:
            PENDING_REQUESTS.set(len(batch_engine._pending))
            result = await batch_engine.submit(file_path, timestamps=True, owns_file=True)
            PENDING_REQUESTS.set(len(batch_engine._pending))
            return JSONResponse(content=_transcribe_from_gpu_result(result))
        else:
            result = await loop.run_in_executor(_diarize_pool, transcribe_file, file_path)
            return result
    except QueueFullError:
        status = "error"
        return JSONResponse(status_code=503, content={"detail": "Server overloaded — try again later"})
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


@app.post("/v2/transcribe")
async def transcribe_v2(
    file: UploadFile = File(...),
    diarize: bool = Form(True),
):
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
        if audio_dur > 0:
            AUDIO_DURATION.observe(audio_dur)
        await loop.run_in_executor(_io_pool, _write_file, file_path, data)

        if batch_engine is not None:
            PENDING_REQUESTS.set(len(batch_engine._pending))
            gpu_result = await batch_engine.submit(file_path, timestamps=True, owns_file=False)
            PENDING_REQUESTS.set(len(batch_engine._pending))
            result = await loop.run_in_executor(
                _diarize_pool, functools.partial(transcribe_file_v2, file_path, gpu_result=gpu_result, diarize=diarize)
            )
        else:
            result = await loop.run_in_executor(
                _diarize_pool, functools.partial(transcribe_file_v2, file_path, diarize=diarize)
            )
        return result
    except QueueFullError:
        status = "error"
        return JSONResponse(status_code=503, content={"detail": "Server overloaded — try again later"})
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
    session = StreamSession(sample_rate=sample_rate, vad_threshold=vad_threshold, hangover_s=hangover_s)

    ACTIVE_STREAMS.inc()
    t0 = time.monotonic()
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=_WS_RECEIVE_TIMEOUT)
            except asyncio.TimeoutError:
                continue

            if "bytes" in msg:
                segments = await session.feed(msg["bytes"])
                for seg in segments:
                    await websocket.send_json(seg)
            elif "text" in msg:
                if msg["text"] == "finalize":
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"v3/stream error: {e}")
    finally:
        try:
            final_segments = await session.flush()
            for seg in final_segments:
                try:
                    await websocket.send_json(seg)
                except Exception:
                    break
        except Exception as e:
            logger.error(f"v3/stream flush error: {e}")
        ACTIVE_STREAMS.dec()
        STREAM_DURATION.observe(time.monotonic() - t0)
        session.cleanup()


@app.get("/health")
async def health_check():
    if gpu_worker is not None:
        ready = gpu_worker.is_ready
        body = {
            "status": "healthy" if ready else "loading",
            "ready": ready,
            "uptime_seconds": round(time.monotonic() - start_time, 1),
        }
        if not ready:
            return JSONResponse(status_code=503, content=body)
        return body
    return {"status": "healthy"}


@app.get("/batch/metrics")
async def batch_metrics():
    if batch_engine is not None:
        PENDING_REQUESTS.set(len(batch_engine._pending))
        return batch_engine.metrics
    return {}
