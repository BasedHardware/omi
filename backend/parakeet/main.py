import asyncio
import functools
import gc
import os
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional

gc.disable()

from fastapi import FastAPI, Form, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from prometheus_client import Gauge, Histogram, make_asgi_app

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

ACTIVE_STREAMS = Gauge('parakeet_active_streams', 'Active /v3/stream WebSocket connections')
ACTIVE_BATCH = Gauge('parakeet_active_batch_requests', 'Active batch transcription requests')
REQUEST_DURATION = Histogram(
    'parakeet_request_duration_seconds',
    'Request latency',
    ['endpoint'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
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

gpu_worker: Optional[GPUWorker] = None
batch_engine: Optional[BatchEngine] = None
start_time: float = 0
_diarize_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="diarize")


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


@app.post("/v1/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if gpu_worker is not None and not gpu_worker.is_ready:
        return JSONResponse(status_code=503, content={"detail": "Model loading, try again shortly"})
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    ACTIVE_BATCH.inc()
    t0 = time.monotonic()
    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())

        if batch_engine is not None:
            result = await batch_engine.submit(file_path, timestamps=True, owns_file=True)
            return JSONResponse(content=_transcribe_from_gpu_result(result))
        else:
            return transcribe_file(file_path)
    except QueueFullError:
        return JSONResponse(status_code=503, content={"detail": "Server overloaded — try again later"})
    finally:
        REQUEST_DURATION.labels(endpoint="v1_transcribe").observe(time.monotonic() - t0)
        ACTIVE_BATCH.dec()
        if batch_engine is None:
            try:
                os.remove(file_path)
            except OSError:
                pass


@app.post("/v2/transcribe")
async def transcribe_v2(
    file: UploadFile = File(...),
    diarize: bool = Form(True),
):
    if gpu_worker is not None and not gpu_worker.is_ready:
        return JSONResponse(status_code=503, content={"detail": "Model loading, try again shortly"})
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    ACTIVE_BATCH.inc()
    t0 = time.monotonic()
    loop = asyncio.get_running_loop()
    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())

        if batch_engine is not None:
            gpu_result = await batch_engine.submit(file_path, timestamps=True, owns_file=False)
            result = await loop.run_in_executor(
                _diarize_pool, functools.partial(transcribe_file_v2, file_path, gpu_result=gpu_result, diarize=diarize)
            )
        else:
            result = await loop.run_in_executor(
                _diarize_pool, functools.partial(transcribe_file_v2, file_path, diarize=diarize)
            )
        return result
    except QueueFullError:
        return JSONResponse(status_code=503, content={"detail": "Server overloaded — try again later"})
    finally:
        REQUEST_DURATION.labels(endpoint="v2_transcribe").observe(time.monotonic() - t0)
        ACTIVE_BATCH.dec()
        try:
            os.remove(file_path)
        except OSError:
            pass


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
        return {
            "status": "healthy" if ready else "loading",
            "ready": ready,
            "uptime_seconds": round(time.monotonic() - start_time, 1),
        }
    return {"status": "healthy"}


@app.get("/batch/metrics")
async def batch_metrics():
    if batch_engine is not None:
        return batch_engine.metrics
    return {}
