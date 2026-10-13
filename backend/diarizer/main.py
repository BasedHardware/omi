from typing import Any, Dict, List

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from admission import GPU_LOCK
from api_v2 import create_router
from final_pass import decode_audio, infer

from diarization import diarization_endpoint
from embedding import embedding_endpoint, embedding_endpoint_v2
import logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.post('/v1/diarization')
def diarization(file: UploadFile = File(...)) -> List[Dict[str, Any]]:
    logger.info('diarization')
    with GPU_LOCK:
        return diarization_endpoint(file)


@app.post('/v1/embedding')
def embedding(file: UploadFile = File(...)) -> List[float]:
    logger.info('embedding')
    with GPU_LOCK:
        return embedding_endpoint(file)


@app.post('/v2/embedding')
def embedding_v2(file: UploadFile = File(...)) -> List[float]:
    logger.info('embedding v2')
    with GPU_LOCK:
        return embedding_endpoint_v2(file)


@app.get('/health')
def health_check() -> Dict[str, str]:
    return {"status": "healthy"}


def run_v2(body, content_type, min_speakers, max_speakers):
    waveform = decode_audio(body, content_type)
    body.clear()
    return infer(waveform, min_speakers, max_speakers)


app.include_router(create_router(run_v2))


@app.get('/metrics')
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
