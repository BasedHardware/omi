import asyncio
import os
import time
import uuid
import logging

from fastapi import FastAPI, Form, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from prometheus_client import Gauge, Histogram, make_asgi_app

from transcribe import transcribe_file, transcribe_file_v2
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

app = FastAPI()
app.mount("/metrics", make_asgi_app())

os.makedirs("_temp", exist_ok=True)


@app.on_event("startup")
async def startup_warmup():
    warmup_rnnt_decoder()


@app.post("/v1/transcribe")
def transcribe(file: UploadFile = File(...)):
    """Batch-transcribe an audio chunk (16 kHz mono) with on-GPU Parakeet."""
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    ACTIVE_BATCH.inc()
    t0 = time.monotonic()
    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())
        return transcribe_file(file_path)
    finally:
        REQUEST_DURATION.labels(endpoint="v1_transcribe").observe(time.monotonic() - t0)
        ACTIVE_BATCH.dec()
        try:
            os.remove(file_path)
        except OSError:
            pass


@app.post("/v2/transcribe")
def transcribe_v2(
    file: UploadFile = File(...),
    diarize: bool = Form(True),
):
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    ACTIVE_BATCH.inc()
    t0 = time.monotonic()
    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())
        return transcribe_file_v2(file_path, diarize=diarize)
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
def health_check():
    return {"status": "healthy"}
