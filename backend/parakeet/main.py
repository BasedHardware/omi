import os
import uuid
import logging

from fastapi import FastAPI, UploadFile, File, Header, HTTPException

from transcribe import transcribe_file

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


@app.get("/health")
def health_check():
    return {"status": "healthy"}
