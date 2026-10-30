from typing import Any, Dict

from fastapi import FastAPI, UploadFile, File

from vad_modal import vad_endpoint
import logging

from utils.logging_config import configure_split_stream_logging

# The internal HTTP LB already logs every request. Uvicorn access lines duplicated it.
configure_split_stream_logging(level=logging.INFO)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.post('/v1/vad')
def vad(file: UploadFile = File) -> Any:  # pyright: ignore[reportArgumentType]  # FastAPI bare File default
    logger.debug('vad')
    return vad_endpoint(file)


@app.get('/health')
def health_check() -> Dict[str, str]:
    return {"status": "healthy"}
