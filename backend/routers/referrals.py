import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
import firebase_admin.auth
from pydantic import BaseModel

from database.referrals import claim_referral_trial
from utils.integration_telemetry import emit_posthog_event
from utils.other import endpoints as auth
from utils.referrals import (
    REFERRAL_COOKIE_MAX_AGE_SECONDS,
    REFERRAL_COOKIE_NAME,
    REFERRAL_PROGRAM,
    REFERRAL_TRIAL_DAYS,
    ReferralCodeError,
    is_new_referral_account,
    referral_link,
    referral_signup_url,
    referrer_uid_from_code,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=['referrals'])


class ReferralLinkResponse(BaseModel):
    referral_url: str


class ReferralClaimRequest(BaseModel):
    code: str


class ReferralClaimResponse(BaseModel):
    claimed: bool
    trial_days: int


def _safe_emit_posthog_event(distinct_id: Optional[str], event: str, properties: dict) -> None:
    try:
        emit_posthog_event(distinct_id, event, properties)
    except Exception:
        logger.warning('Failed to emit referral telemetry event: %s', event, exc_info=True)


@router.get('/v1/users/me/referral', response_model=ReferralLinkResponse)
def get_referral_link(uid: str = Depends(auth.get_current_user_uid)) -> ReferralLinkResponse:
    try:
        response = ReferralLinkResponse(referral_url=referral_link(uid))
    except ReferralCodeError as error:
        raise HTTPException(status_code=503, detail='Referral links are temporarily unavailable') from error
    _safe_emit_posthog_event(uid, 'Referral Link Issued', {'program': REFERRAL_PROGRAM})
    return response


@router.get('/r/{code}', response_class=RedirectResponse)
def capture_referral(code: str) -> RedirectResponse:
    try:
        referrer_uid = referrer_uid_from_code(code)
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='Referral link not found') from error

    response = RedirectResponse(referral_signup_url(code), status_code=302)
    response.set_cookie(
        REFERRAL_COOKIE_NAME,
        code,
        max_age=REFERRAL_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite='lax',
        path='/',
    )
    _safe_emit_posthog_event(referrer_uid, 'Referral Link Captured', {'program': REFERRAL_PROGRAM})
    return response


@router.post('/v1/users/me/referral/claim', response_model=ReferralClaimResponse)
def claim_referral(
    body: ReferralClaimRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> ReferralClaimResponse:
    if not body.code or not body.code.strip():
        raise HTTPException(status_code=400, detail='Referral code cannot be blank')

    try:
        referrer_uid = referrer_uid_from_code(body.code.strip())
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='Referral link not found') from error

    try:
        user = firebase_admin.auth.get_user(uid)
    except Exception as exc:
        logger.warning('Failed to fetch user auth metadata for referral claim: %s', type(exc).__name__)
        raise HTTPException(status_code=503, detail='User authentication metadata temporarily unavailable') from exc

    creation_timestamp = getattr(getattr(user, 'user_metadata', None), 'creation_timestamp', None)
    try:
        claimed, reason = claim_referral_trial(
            uid,
            referrer_uid,
            is_new_user=is_new_referral_account(creation_timestamp),
        )
    except Exception as exc:
        logger.warning('Failed to execute claim_referral_trial: %s', type(exc).__name__)
        raise HTTPException(status_code=503, detail='Referral claim service temporarily unavailable') from exc

    _safe_emit_posthog_event(
        uid,
        'Referral Claimed',
        {'program': REFERRAL_PROGRAM, 'claimed': claimed, 'reason': reason},
    )
    return ReferralClaimResponse(claimed=claimed, trial_days=REFERRAL_TRIAL_DAYS)