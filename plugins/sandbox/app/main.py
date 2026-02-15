from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

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
async def handle_transcript(payload: WebhookRequest, uid: str = Query(default='')):
    if not payload.segments:
        return {}

    # Omi backend sends uid as query param; body session_id is the same value
    session_id = uid or payload.session_id
    if not session_id:
        return {}

    segments_raw = [s.model_dump() for s in payload.segments]
    ready, accumulated = await buffer.add_segments(session_id, segments_raw)

    if not ready:
        return {}

    result = await process_and_decide(accumulated, session_id)
    return result or {}
