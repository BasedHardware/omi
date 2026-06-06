import asyncio
import os
import uuid
import logging

from fastapi import FastAPI, Form, UploadFile, File, Header, HTTPException, WebSocket, WebSocketDisconnect, Query

from transcribe import transcribe_file, transcribe_file_v2
from stream_handler import StreamSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

os.makedirs("_temp", exist_ok=True)

# Shared-secret auth so the (publicly-reachable) endpoint isn't open to abuse. The backend sends
# Authorization: Bearer <ENCRYPTION_SECRET>, the same secret both services already have. When unset
# (e.g. local dev) auth is skipped. /health stays open for load-balancer health checks.
_AUTH_TOKEN = os.getenv("ENCRYPTION_SECRET")


def _require_auth(authorization):
    if _AUTH_TOKEN and authorization != f"Bearer {_AUTH_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/v1/transcribe")
def transcribe(file: UploadFile = File(...), authorization: str = Header(None)):
    _require_auth(authorization)
    """Batch-transcribe an audio chunk (16 kHz mono) with on-GPU Parakeet.

    The backend chunks live audio (e.g. ~10 s windows, mirroring the desktop) and posts each chunk
    here; speaker diarization is handled separately by the existing diarizer/speaker-id services.
    """
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())
        return transcribe_file(file_path)
    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass


@app.post("/v2/transcribe")
def transcribe_v2(
    file: UploadFile = File(...),
    diarize: bool = Form(True),
    authorization: str = Header(None),
):
    _require_auth(authorization)
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())
        return transcribe_file_v2(file_path, diarize=diarize)
    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass


_WS_RECEIVE_TIMEOUT = 30.0


@app.websocket("/v3/stream")
async def stream_transcribe(
    websocket: WebSocket,
    sample_rate: int = Query(16000),
):
    await websocket.accept()

    auth = websocket.headers.get("authorization", "")
    if _AUTH_TOKEN and auth != _AUTH_TOKEN:
        await websocket.close(code=1008, reason="unauthorized")
        return
    session = StreamSession(sample_rate=sample_rate)

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
        session.cleanup()


@app.get("/health")
def health_check():
    return {"status": "healthy"}
