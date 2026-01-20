from typing import List

from fastapi import FastAPI, UploadFile, File, Form

from diarization import diarization_endpoint
from embedding import embedding_endpoint, embedding_endpoint_v2

app = FastAPI()


@app.post('/v1/diarization')
def diarization(file: UploadFile = File(...)):
    print('diarization')
    return diarization_endpoint(file)


@app.post('/v1/embedding')
def embedding(file: UploadFile = File(...)):
    print('embedding')
    return embedding_endpoint(file)


@app.post('/v2/embedding')
def embedding_v2(file: UploadFile = File(...)):
    print('embedding v2')
    return embedding_endpoint_v2(file)


@app.get('/health')
def health_check():
    return {"status": "healthy"}
