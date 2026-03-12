from typing import List

from fastapi import FastAPI, UploadFile, File, Form

from diarization import diarization_endpoint
from embedding import embedding_endpoint, embedding_endpoint_v2
import logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.post('/v1/diarization')
def diarization(file: UploadFile = File(...)):
    logger.info('diarization')
    return diarization_endpoint(file)


@app.post('/v1/embedding')
def embedding(file: UploadFile = File(...)):
    logger.info('embedding')
    return embedding_endpoint(file)


@app.post('/v2/embedding')
def embedding_v2(file: UploadFile = File(...)):
    logger.info('embedding v2')
    return embedding_endpoint_v2(file)


@app.get('/health')
def health_check():
    return {"status": "healthy"}
