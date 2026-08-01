"""Projections API — one generated image carrying one future-tense imperative.

Split out of `routers/users.py`: the projection surface is its own product, not part of the
user-profile router, and its routes were pushing that file past the product line-count ratchet.
The response models live here too, so the app-client contract has one owner.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from google.cloud.exceptions import NotFound as BlobNotFound
from pydantic import BaseModel, ConfigDict, Field

from database import projections as projections_db
from utils.other import endpoints as auth
from utils.projections import NoProjectionSubject, generate_projection
from utils.projections import storage as projection_storage

router = APIRouter()


def _manual_generation_enabled() -> bool:
    """Keep the on-demand route on explicit local stages and off every hosted runtime."""
    stage = (os.getenv('OMI_ENV_STAGE') or os.getenv('ENVIRONMENT') or os.getenv('APP_ENV') or '').strip().lower()
    is_hosted = bool(os.getenv('K_SERVICE') or os.getenv('KUBERNETES_SERVICE_HOST'))
    return not is_hosted and stage in {'local', 'offline', 'test'}


class ProjectionGeneration(BaseModel):
    model_config = ConfigDict(extra='forbid')

    model: Optional[str] = None
    size: Optional[str] = None
    quality: Optional[str] = None


class ProjectionEvidenceReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reference: str
    source: Literal['conversation', 'action_item', 'goal']
    label: str
    occurred_at: Optional[datetime] = None


class ProjectionWhyThis(BaseModel):
    model_config = ConfigDict(extra='forbid')

    evidence: List[ProjectionEvidenceReceipt] = Field(default_factory=list)
    evidence_tier: str
    selection_rank: int = Field(ge=1)
    uncertainty: List[str] = Field(default_factory=list)


class ProjectionFeedback(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rating: Literal['up', 'down']
    updated_at: Optional[datetime] = None


class ProjectionFeedbackRequest(BaseModel):
    rating: Literal['up', 'down']


class ProjectionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: Optional[str] = None
    created_at: Optional[datetime] = None
    imperative: Optional[str] = None
    image_url: Optional[str] = None
    subject: Optional[str] = None
    stage: Optional[str] = None
    generation: Optional[ProjectionGeneration] = None
    why_this: Optional[ProjectionWhyThis] = None
    feedback: Optional[ProjectionFeedback] = None


class ProjectionsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    projections: List[ProjectionResponse] = Field(default_factory=list)


# Serve an allowlist rather than trying to enumerate every internal field that generation
# may add later. `selection.prompt` alone can contain 7-10k tokens of the owner's week.
SERVED_PROJECTION_FIELDS = (
    'id',
    'created_at',
    'imperative',
    'image_url',
    'subject',
    'stage',
    'generation',
    'why_this',
    'feedback',
)

SERVED_GENERATION_FIELDS = ('model', 'size', 'quality')
SERVED_WHY_THIS_FIELDS = ('evidence', 'evidence_tier', 'selection_rank', 'uncertainty')
SERVED_EVIDENCE_FIELDS = ('reference', 'source', 'label', 'occurred_at')
SERVED_FEEDBACK_FIELDS = ('rating', 'updated_at')


def _served(projection: Dict[str, Any]) -> Dict[str, Any]:
    served = {key: projection[key] for key in SERVED_PROJECTION_FIELDS if key in projection}
    generation = served.get('generation')
    if isinstance(generation, dict):
        served['generation'] = {key: generation[key] for key in SERVED_GENERATION_FIELDS if key in generation}
    why_this = served.get('why_this')
    if isinstance(why_this, dict):
        served_why_this = {key: why_this[key] for key in SERVED_WHY_THIS_FIELDS if key in why_this}
        evidence = served_why_this.get('evidence')
        if isinstance(evidence, list):
            served_why_this['evidence'] = [
                (
                    {key: receipt[key] for key in SERVED_EVIDENCE_FIELDS if key in receipt}
                    if isinstance(receipt, dict)
                    else receipt
                )
                for receipt in evidence
            ]
        served['why_this'] = served_why_this
    feedback = served.get('feedback')
    if isinstance(feedback, dict):
        served['feedback'] = {key: feedback[key] for key in SERVED_FEEDBACK_FIELDS if key in feedback}
    return served


@router.post(
    '/v1/users/projections/test',
    tags=['v1'],
    response_model=ProjectionResponse,
    include_in_schema=False,
)
def test_projection(uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """
    Generate a projection for the authenticated user immediately.

    This local-development-only trigger exercises a surface that is otherwise produced on
    a schedule.

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


@router.post(
    '/v1/users/projections/{projection_id}/feedback',
    tags=['v1'],
    response_model=ProjectionFeedback,
)
def set_projection_feedback(
    projection_id: str,
    request: ProjectionFeedbackRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> Dict[str, Any]:
    """Record the authenticated owner's latest explicit response signal."""
    try:
        uuid.UUID(projection_id)
    except ValueError:
        raise HTTPException(status_code=404, detail='Projection not found')
    if not projections_db.set_projection_feedback(uid, projection_id, request.rating):
        raise HTTPException(status_code=404, detail='Projection not found')
    return {'rating': request.rating, 'updated_at': datetime.now(timezone.utc)}


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
    persisted_path = projection.get('image_path')

    try:
        validated_path = projection_storage.validate_projection_image_path(uid, projection_id, persisted_path)
        if projection_storage.uses_gcs():
            image_bytes = projection_storage.download_projection_image(uid, projection_id, validated_path)
        else:
            path = projection_storage.local_projection_image_path(
                uid,
                projection_id,
                persisted_path=validated_path,
            )
            if not path.is_file():
                raise FileNotFoundError
            image_bytes = path.read_bytes()
    except (BlobNotFound, FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail='Projection image not found')

    return Response(
        content=image_bytes,
        media_type='image/png',
        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'},
    )
