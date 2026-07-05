from typing import Any, Dict

from fastapi import FastAPI, UploadFile, File, Form

from speech_profile_modal import endpoint as speaker_identification_endpoint
from vad_modal import vad_endpoint
import logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.post('/v1/speaker-identification')
def speaker_identification(
    uid: str, audio_file: UploadFile = File, segments: str = Form(...)
) -> Any:  # pyright: ignore[reportArgumentType]  # FastAPI File default
    logger.info('speaker_identification')
    return speaker_identification_endpoint(uid, audio_file, segments)


@app.post('/v1/vad')
def vad(file: UploadFile = File) -> Any:  # pyright: ignore[reportArgumentType]  # FastAPI File default
    logger.info('vad')
    logger.info(vad_endpoint)
    return vad_endpoint(file)


@app.get('/health')
def health_check() -> Dict[str, str]:
    return {"status": "healthy"}
