import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
import firebase_admin.auth
from pydantic import BaseModel, Field

from database.referrals import claim_referral_trial
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
from utils.integration_telemetry import emit_posthog_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=['referrals'])


class ReferralLinkResponse(BaseModel):
    referral_url: str


class ReferralClaimRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=256)


class ReferralClaimResponse(BaseModel):
    claimed: bool
    trial_days: int


@router.get('/v1/users/me/referral', response_model=ReferralLinkResponse)
def get_referral_link(uid: str = Depends(auth.get_current_user_uid)) -> ReferralLinkResponse:
    try:
        response = ReferralLinkResponse(referral_url=referral_link(uid))
    except ReferralCodeError as error:
        raise HTTPException(status_code=503, detail='Referral links are temporarily unavailable') from error
    except Exception as error:
        logger.error(f'Failed to generate referral link for uid {uid}: {error}', exc_info=True)
        raise HTTPException(status_code=500, detail='Failed to generate referral link') from error
    emit_posthog_event(uid, 'Referral Link Issued', {'program': REFERRAL_PROGRAM})
    return response


@router.get('/r/{code}', response_class=RedirectResponse)
def capture_referral(code: str) -> RedirectResponse:
    clean_code = (code or '').strip()
    if not clean_code or len(clean_code) > 256:
        raise HTTPException(status_code=404, detail='Referral link not found')
    try:
        referrer_uid = referrer_uid_from_code(clean_code)
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='Referral link not found') from error

    response = RedirectResponse(referral_signup_url(clean_code), status_code=302)
    response.set_cookie(
        REFERRAL_COOKIE_NAME,
        clean_code,
        max_age=REFERRAL_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite='lax',
        path='/',
    )
    emit_posthog_event(referrer_uid, 'Referral Link Captured', {'program': REFERRAL_PROGRAM})
    return response


@router.post('/v1/users/me/referral/claim', response_model=ReferralClaimResponse)
def claim_referral(
    body: ReferralClaimRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> ReferralClaimResponse:
    clean_code = body.code.strip()
    try:
        referrer_uid = referrer_uid_from_code(clean_code)
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='Referral link not found') from error

    try:
        user = firebase_admin.auth.get_user(uid)
    except Exception as error:
        logger.error(f'Failed to load user auth metadata for referral claim uid {uid}: {error}', exc_info=True)
        raise HTTPException(status_code=500, detail='Failed to verify account metadata') from error

    creation_timestamp = getattr(getattr(user, 'user_metadata', None), 'creation_timestamp', None)
    try:
        claimed, reason = claim_referral_trial(
            uid,
            referrer_uid,
            is_new_user=is_new_referral_account(creation_timestamp),
        )
    except Exception as error:
        logger.error(f'Failed to execute claim_referral_trial for uid {uid}: {error}', exc_info=True)
        raise HTTPException(status_code=500, detail='Failed to process referral claim') from error

    emit_posthog_event(
        uid,
        'Referral Claimed',
        {'program': REFERRAL_PROGRAM, 'claimed': claimed, 'reason': reason},
    )
    return ReferralClaimResponse(claimed=claimed, trial_days=REFERRAL_TRIAL_DAYS)
