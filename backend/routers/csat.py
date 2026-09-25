import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import csat
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=['csat'])


class CsatConfigResponse(BaseModel):
    enabled: bool
    title: str
    body: str
    thank_you_text: str
    refer_cta_text: str
    question_threshold: int
    comment_max_score: int
    revision: int


class CsatRatingReceipt(BaseModel):
    id: str
    created: bool


class CsatRatingRequest(BaseModel):
    platform: str
    app_version: str = ''
    score: int
    comment: Optional[str] = None
    revision: int = 0


@router.get('/v1/csat/config', response_model=CsatConfigResponse)
def get_csat_config(
    platform: str = 'macos',
    uid: str = Depends(auth.get_current_user_uid),
) -> CsatConfigResponse:
    # `platform` is accepted and reserved so Windows/iOS/Android callers can
    # attach later without a contract change; v1 serves the same product-wide
    # singleton for every platform. A missing doc returns defaults — never 404.
    try:
        config = csat.get_product_config()
    except Exception as exc:
        logger.warning('csat: failed to retrieve product config: %s', exc)
        config = dict(csat.DEFAULT_CONFIG)

    return CsatConfigResponse(**config)


@router.post('/v1/csat/ratings', response_model=CsatRatingReceipt, status_code=201)
def submit_csat_rating(
    payload: CsatRatingRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    platform = (payload.platform or '').strip().lower()
    if platform not in csat.PLATFORMS:
        raise HTTPException(status_code=400, detail=f'platform must be one of {sorted(csat.PLATFORMS)}')
    if not isinstance(payload.score, int) or not (1 <= payload.score <= 5):
        raise HTTPException(status_code=400, detail='score must be between 1 and 5')
    if not isinstance(payload.revision, int) or payload.revision < 0 or payload.revision > 1_000_000_000:
        raise HTTPException(status_code=400, detail='revision must be >= 0')

    app_version = payload.app_version.strip()[: csat.MAX_APP_VERSION_LENGTH]
    comment = (payload.comment or '').strip()[: csat.MAX_COMMENT_LENGTH]

    # The comment is never logged; only the clamped fields above travel on.
    try:
        doc_id, created = csat.submit_rating(
            uid=uid,
            platform=platform,
            app_version=app_version,
            score=payload.score,
            comment=comment,
            revision=payload.revision,
        )
    except Exception as exc:
        logger.warning('csat: failed to submit rating for uid %s on %s: %s', uid, platform, exc)
        raise HTTPException(status_code=503, detail='CSAT service temporarily unavailable') from exc

    if not created:
        # One rating per user per platform; the existing answer stands.
        return JSONResponse(status_code=409, content={'id': doc_id, 'created': False})
    return CsatRatingReceipt(id=doc_id, created=True)
