from omi_logging import configure_logging, TraceContextMiddleware

# Gateway and Ingress logging coverage differs; retain general request logs.
configure_logging('diarizer', access_policy='keep')

from typing import Any, Dict, List

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from contextlib import asynccontextmanager

from diarization import diarization_endpoint, initialize_diarization
from embedding import embedding_endpoint, embedding_endpoint_v2, initialize_embeddings
import logging

# Vendor imports may install handlers; reapply the process policy afterward.
configure_logging('diarizer', access_policy='keep')

logger = logging.getLogger(__name__)
logger.info('Diarizer logging configured')


@asynccontextmanager
async def lifespan(_app):
    # Uvicorn completes startup before opening its listening socket. Never
    # acknowledge TCP readiness until the existing models can serve requests.
    initialize_embeddings()
    initialize_diarization()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(TraceContextMiddleware)


@app.post('/v1/diarization')
def diarization(file: UploadFile = File(...)) -> List[Dict[str, Any]]:
    logger.debug('diarization')
    return diarization_endpoint(file)


@app.post('/v1/embedding')
def embedding(file: UploadFile = File(...)) -> List[float]:
    logger.debug('embedding')
    return embedding_endpoint(file)


@app.post('/v2/embedding')
def embedding_v2(file: UploadFile = File(...)) -> List[float]:
    logger.debug('embedding v2')
    return embedding_endpoint_v2(file)


@app.get('/health')
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}


@app.get('/metrics')
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
