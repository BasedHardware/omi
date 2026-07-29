"""Projections API — one generated image carrying one future-tense imperative.

Split out of `routers/users.py`: the projection surface is its own product, not part of the
user-profile router, and its routes were pushing that file past the product line-count ratchet.
The response models live here too, so the app-client contract has one owner.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from google.cloud.exceptions import NotFound as BlobNotFound
from pydantic import BaseModel, ConfigDict, Field

from database import projections as projections_db
from utils.other import endpoints as auth
from utils.projections import NoProjectionSubject, generate_projection, local_projection_image_path
from utils.projections import storage as projection_storage

router = APIRouter()


def _manual_generation_enabled() -> bool:
    """Keep the on-demand route available for local/demo builds, never production."""
    stage = (os.getenv('OMI_ENV_STAGE') or os.getenv('ENVIRONMENT') or os.getenv('APP_ENV') or '').strip().lower()
    if stage in {'prod', 'production'}:
        return False
    return not (os.getenv('K_SERVICE') or os.getenv('KUBERNETES_SERVICE_HOST')) or stage in {
        'dev',
        'development',
        'local',
        'test',
    }


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
    subject: Optional[str] = None
    stage: Optional[str] = None
    generation: Optional[ProjectionGeneration] = None


class ProjectionsResponse(BaseModel):
    projections: List[ProjectionResponse] = Field(default_factory=list)


# Persisted but never served. `selection.prompt` is the whole evidence packet — 7-10k tokens
# of the user's own week — so a page of thirty projections would ship thirty copies of it.
# The response model allows extra keys, so these have to be dropped explicitly rather than
# relied on to be filtered by the schema.
INTERNAL_PROJECTION_FIELDS = (
    'selection',
    'projection',
    'evidence',
    'setting',
    'tone',
    'emotions',
    'image_path',
    'cadence_key',
)


def _served(projection: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in projection.items() if key not in INTERNAL_PROJECTION_FIELDS}


@router.post('/v1/users/projections/test', tags=['v1'], response_model=ProjectionResponse)
def test_projection(uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """
    Generate a projection for the authenticated user immediately.

    This is the manual trigger for a surface that will otherwise be produced on a schedule;
    it exists so the result can be demonstrated without waiting for a scheduled run.

    Answers 409 when there is nothing to project from, or when nothing the selector ranked
    was grounded in the captured evidence. Both are real outcomes rather than errors: an
    invented projection is the evidence-free artifact this surface exists to replace.
    """
    if not _manual_generation_enabled():
        raise HTTPException(status_code=404, detail='Projection generation is not available')

    try:
        projection = generate_projection(uid)
    except NoProjectionSubject as error:
        raise HTTPException(status_code=409, detail=str(error) or 'No projection subject available')
    projections_db.create_projection(uid, projection)
    return _served(projection)


@router.get('/v1/users/projections', tags=['v1'], response_model=ProjectionsResponse)
def get_projections_endpoint(
    limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), uid: str = Depends(auth.get_current_user_uid)
) -> Dict[str, Any]:
    """List the authenticated user's projections, newest first."""
    projections = projections_db.get_projections(uid, limit=limit, offset=offset)
    return {'projections': [_served(projection) for projection in projections]}


@router.get('/v1/users/projections/{projection_id}', tags=['v1'], response_model=ProjectionResponse)
def get_projection_endpoint(projection_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """Get a single projection by id."""
    projection = projections_db.get_projection(uid, projection_id)
    if not projection:
        raise HTTPException(status_code=404, detail='Projection not found')
    return _served(projection)


@router.get('/v1/projection-images/{projection_id}.png', tags=['v1'], include_in_schema=False)
def get_projection_image(projection_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Response:
    """Serve private image bytes only to the projection's authenticated owner."""
    try:
        uuid.UUID(projection_id)
    except ValueError:
        raise HTTPException(status_code=404, detail='Projection image not found')

    projection = projections_db.get_projection(uid, projection_id)
    if not projection:
        raise HTTPException(status_code=404, detail='Projection image not found')

    try:
        if projection_storage.uses_gcs():
            image_bytes = projection_storage.download_projection_image(uid, projection_id)
        else:
            path = local_projection_image_path(uid, projection_id)
            if not path.is_file():
                raise FileNotFoundError
            image_bytes = path.read_bytes()
    except (BlobNotFound, FileNotFoundError):
        raise HTTPException(status_code=404, detail='Projection image not found')

    return Response(
        content=image_bytes,
        media_type='image/png',
        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'},
    )
