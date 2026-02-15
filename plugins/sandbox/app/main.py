from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app import buffer, omi_client
from app.models import WebhookRequest
from app.processor import process_and_decide


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await buffer.close()
    await omi_client.close()


app = FastAPI(title='Omi Sandbox Plugin', lifespan=lifespan)


@app.get('/health')
async def health():
    return {'status': 'ok'}


@app.post('/webhook/transcript')
async def handle_transcript(payload: WebhookRequest):
    if not payload.segments:
        return {}

    segments_raw = [s.model_dump() for s in payload.segments]
    ready, accumulated = await buffer.add_segments(payload.session_id, segments_raw)

    if not ready:
        return {}

    result = await process_and_decide(accumulated, payload.session_id)
    return result or {}
