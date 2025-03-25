from typing import List

from fastapi import FastAPI, UploadFile, File, Form

from speech_profile_modal import ResponseItem, endpoint as speaker_identification_endpoint
from vad_modal import vad_endpoint

app = FastAPI()

@app.post('/v1/speaker-identification')
def speaker_identification(
        uid: str, audio_file: UploadFile = File, segments: str = Form(...)
) -> List[ResponseItem]:
    print('speaker_identification')
    return speaker_identification_endpoint(uid, audio_file, segments)

@app.post('/v1/vad')
def vad(file: UploadFile = File):
    print('vad')
    print(vad_endpoint)
    return vad_endpoint(file)

@app.get('/health')
def health_check():
    return {"status": "healthy"}
