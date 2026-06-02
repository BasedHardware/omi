import os
import uuid
import logging

from fastapi import FastAPI, UploadFile, File

from transcribe import transcribe_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

os.makedirs("_temp", exist_ok=True)


@app.post("/v1/transcribe")
def transcribe(file: UploadFile = File(...)):
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
