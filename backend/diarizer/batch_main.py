"""Batch-only app: deploy on separate GPUs; never co-serve embeddings."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from api_v2 import create_router
from embedding import initialize_embeddings
from final_pass import decode_audio, infer, pipeline


@asynccontextmanager
async def lifespan(_app):
    if os.getenv('DIARIZATION_V2_ENABLED', '').lower() != 'true':
        raise RuntimeError('batch diarization requires DIARIZATION_V2_ENABLED=true')
    # Startup errors are fatal; the socket opens only after both models load.
    initialize_embeddings(batch_only=True)
    pipeline()
    yield


app = FastAPI(lifespan=lifespan)


def run_v2(body, content_type, min_speakers, max_speakers):
    waveform = decode_audio(body, content_type)
    body.clear()
    return infer(waveform, min_speakers, max_speakers)


app.include_router(create_router(run_v2))


@app.get('/health')
async def health_check():
    return {'status': 'healthy'}


@app.get('/metrics')
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
