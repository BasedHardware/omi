from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from database.referrals import claim_referral_trial
from utils.auth import get_auth_provider
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

router = APIRouter(tags=['referrals'])


class ReferralLinkResponse(BaseModel):
    referral_url: str


class ReferralClaimRequest(BaseModel):
    code: str


class ReferralClaimResponse(BaseModel):
    claimed: bool
    trial_days: int


@router.get('/v1/users/me/referral', response_model=ReferralLinkResponse)
def get_referral_link(uid: str = Depends(auth.get_current_user_uid)) -> ReferralLinkResponse:
    try:
        response = ReferralLinkResponse(referral_url=referral_link(uid))
    except ReferralCodeError as error:
        raise HTTPException(status_code=503, detail='Referral links are temporarily unavailable') from error
    emit_posthog_event(uid, 'Referral Link Issued', {'program': REFERRAL_PROGRAM})
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
    emit_posthog_event(referrer_uid, 'Referral Link Captured', {'program': REFERRAL_PROGRAM})
    return response


@router.post('/v1/users/me/referral/claim', response_model=ReferralClaimResponse)
def claim_referral(
    body: ReferralClaimRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> ReferralClaimResponse:
    try:
        referrer_uid = referrer_uid_from_code(body.code)
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='Referral link not found') from error

    # Through the neutral auth port (ADR-0034), not firebase_admin.auth: the account-creation time is
    # already a neutral scalar on UserProfile (epoch ms, populated from Firebase's
    # user_metadata.creation_timestamp or Keycloak's createdTimestamp), added for the desktop trial
    # paywall. Reading the Firebase UserRecord here would have made the referral trial Firebase-only.
    creation_timestamp = get_auth_provider().get_user_profile(uid).created_at
    claimed, reason = claim_referral_trial(
        uid,
        referrer_uid,
        is_new_user=is_new_referral_account(creation_timestamp),
    )
    emit_posthog_event(
        uid,
        'Referral Claimed',
        {'program': REFERRAL_PROGRAM, 'claimed': claimed, 'reason': reason},
    )
    return ReferralClaimResponse(claimed=claimed, trial_days=REFERRAL_TRIAL_DAYS)
