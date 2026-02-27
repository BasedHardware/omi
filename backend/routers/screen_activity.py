import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import database.screen_activity as screen_activity_db
import database.vector_db as vector_db
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


class ScreenActivityRow(BaseModel):
    id: int
    timestamp: str
    appName: Optional[str] = ''
    windowTitle: Optional[str] = ''
    ocrText: Optional[str] = ''
    embedding: Optional[List[float]] = None


class ScreenActivitySyncRequest(BaseModel):
    rows: List[ScreenActivityRow]


class ScreenActivitySyncResponse(BaseModel):
    synced: int
    last_id: int


@router.post(
    '/v1/screen-activity/sync',
    tags=['screen_activity'],
    response_model=ScreenActivitySyncResponse,
)
def sync_screen_activity(
    request: ScreenActivitySyncRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if len(request.rows) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 rows per batch")

    if not request.rows:
        return ScreenActivitySyncResponse(synced=0, last_id=0)

    rows_dicts = [row.model_dump() for row in request.rows]

    # Write metadata to Firestore
    written = screen_activity_db.upsert_screen_activity(uid, rows_dicts)

    # Upsert embeddings to Pinecone ns3 (only rows that have embeddings)
    rows_with_embeddings = [r for r in rows_dicts if r.get('embedding')]
    if rows_with_embeddings:
        vector_db.upsert_screen_activity_vectors(uid, rows_with_embeddings)

    last_id = max(row.id for row in request.rows)
    logger.info(f"screen_activity sync uid={uid} synced={written} last_id={last_id}")

    return ScreenActivitySyncResponse(synced=written, last_id=last_id)
