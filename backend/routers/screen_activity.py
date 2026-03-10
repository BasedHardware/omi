import logging
import threading
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import database.screen_activity as screen_activity_db
import database.vector_db as vector_db
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


class ScreenActivityRow(BaseModel):
    id: int = Field(description="Screenshot ID (used as Firestore document ID)")
    timestamp: str = Field(description="Timestamp in RFC3339 or 'YYYY-MM-DD HH:MM:SS' format")
    appName: str = Field(default='', description="Application name")
    windowTitle: str = Field(default='', description="Window title")
    ocrText: str = Field(default='', description="OCR text from screenshot (truncated to 1000 chars)")
    embedding: Optional[List[float]] = Field(default=None, description="Optional vector embedding (3072-dim Gemini)")


class ScreenActivitySyncRequest(BaseModel):
    rows: List[ScreenActivityRow]


class ScreenActivitySyncResponse(BaseModel):
    synced: int = Field(description="Number of rows written to Firestore")
    last_id: int = Field(description="Maximum row ID from the batch")


@router.post('/v1/screen-activity/sync', response_model=ScreenActivitySyncResponse, tags=['screen-activity'])
def sync_screen_activity(
    request: ScreenActivitySyncRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if len(request.rows) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 rows per batch")

    if not request.rows:
        return ScreenActivitySyncResponse(synced=0, last_id=0)

    # Convert Pydantic models to dicts for database layer
    rows_data = [row.model_dump() for row in request.rows]

    # Firestore upsert (synchronous — blocks response until written)
    try:
        synced = screen_activity_db.upsert_screen_activity(uid, rows_data)
    except Exception:
        logger.exception('Firestore upsert failed for uid=%s', uid)
        raise HTTPException(status_code=500, detail="Failed to sync screen activity")

    # Pinecone vector upsert (fire-and-forget background thread)
    rows_with_embeddings = [r for r in rows_data if r.get('embedding')]
    if rows_with_embeddings:
        thread = threading.Thread(
            target=_upsert_vectors_background,
            args=(uid, rows_with_embeddings),
            daemon=True,
        )
        thread.start()

    last_id = max(row.id for row in request.rows)
    return ScreenActivitySyncResponse(synced=synced, last_id=last_id)


def _upsert_vectors_background(uid: str, rows: list):
    try:
        vector_db.upsert_screen_activity_vectors(uid, rows)
    except Exception:
        logger.exception('Failed to upsert screen activity vectors for uid=%s', uid)
