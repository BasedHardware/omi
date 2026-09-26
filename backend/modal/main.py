from typing import Any, Dict

from fastapi import FastAPI, UploadFile, File

from vad_modal import vad_endpoint
import logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.post('/v1/vad')
def vad(file: UploadFile = File) -> Any:  # pyright: ignore[reportArgumentType]  # FastAPI bare File default
    logger.info('vad')
    logger.info(vad_endpoint)
    return vad_endpoint(file)


@app.get('/health')
def health_check() -> Dict[str, str]:
    return {"status": "healthy"}
