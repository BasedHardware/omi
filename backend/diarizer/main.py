from typing import List

from fastapi import FastAPI, UploadFile, File, Form

from diarization import diarization_endpoint
from embedding import embedding_endpoint

app = FastAPI()


@app.post('/v1/diarization')
def diarization(file: UploadFile = File(...)):
    print('diarization')
    return diarization_endpoint(file)


@app.post('/v1/embedding')
def embedding(file: UploadFile = File(...)):
    print('embedding')
    return embedding_endpoint(file)


@app.get('/health')
def health_check():
    return {"status": "healthy"}
