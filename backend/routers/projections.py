"""Projections API — one generated image carrying one future-tense imperative.

Split out of `routers/users.py`: the projection surface is its own product, not part of the
user-profile router, and its routes were pushing that file past the product line-count ratchet.
The response models live here too, so the app-client contract has one owner.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from database import projections as projections_db
from utils.other import endpoints as auth
from utils.projections import generate_projection, local_projection_image_path

router = APIRouter()


class ProjectionGeneration(BaseModel):
    model_config = ConfigDict(extra='allow')

    model: Optional[str] = None
    size: Optional[str] = None
    quality: Optional[str] = None
    prompt: Optional[str] = None


class ProjectionResponse(BaseModel):
    model_config = ConfigDict(extra='allow')

    id: Optional[str] = None
    created_at: Optional[datetime] = None
    imperative: Optional[str] = None
    image_url: Optional[str] = None
    generation: Optional[ProjectionGeneration] = None


class ProjectionsResponse(BaseModel):
    projections: List[ProjectionResponse] = Field(default_factory=list)


@router.post('/v1/users/projections/test', tags=['v1'], response_model=ProjectionResponse)
def test_projection(uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """
    Generate a projection for the authenticated user immediately.

    This is the manual trigger for a surface that will otherwise be produced on a schedule;
    it exists so the result can be demonstrated without waiting for a scheduled run.
    """
    projection = generate_projection(uid)
    projections_db.create_projection(uid, projection)
    return projection


@router.get('/v1/users/projections', tags=['v1'], response_model=ProjectionsResponse)
def get_projections_endpoint(
    limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), uid: str = Depends(auth.get_current_user_uid)
) -> Dict[str, Any]:
    """List the authenticated user's projections, newest first."""
    return {'projections': projections_db.get_projections(uid, limit=limit, offset=offset)}


@router.get('/v1/users/projections/{projection_id}', tags=['v1'], response_model=ProjectionResponse)
def get_projection_endpoint(projection_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """Get a single projection by id."""
    projection = projections_db.get_projection(uid, projection_id)
    if not projection:
        raise HTTPException(status_code=404, detail='Projection not found')
    return projection


@router.get('/v1/projection-images/{projection_id}.png', tags=['v1'], include_in_schema=False)
def get_projection_image(projection_id: str) -> FileResponse:
    """Serve a locally stored projection image.

    Only reachable when no `BUCKET_PROJECTION_IMAGES` is configured; with a bucket, images
    are public GCS objects and this backend never serves the bytes. Like those objects, the
    URL is unauthenticated and unguessable rather than uid-scoped.
    """
    try:
        uuid.UUID(projection_id)
    except ValueError:
        raise HTTPException(status_code=404, detail='Projection image not found')
    path = local_projection_image_path(projection_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail='Projection image not found')
    return FileResponse(path, media_type='image/png')
