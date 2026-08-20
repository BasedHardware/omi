from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from utils.other import endpoints as auth
from utils.referrals import (
    REFERRAL_COOKIE_MAX_AGE_SECONDS,
    REFERRAL_COOKIE_NAME,
    REFERRAL_DOWNLOAD_URL,
    ReferralCodeError,
    referral_link,
    referrer_uid_from_code,
)

router = APIRouter(tags=['referrals'])


class ReferralLinkResponse(BaseModel):
    referral_url: str


@router.get('/v1/users/me/referral', response_model=ReferralLinkResponse)
def get_referral_link(request: Request, uid: str = Depends(auth.get_current_user_uid)) -> ReferralLinkResponse:
    return ReferralLinkResponse(referral_url=referral_link(uid, public_base_url=str(request.base_url)))


@router.get('/r/{code}', response_class=RedirectResponse)
def capture_referral(code: str) -> RedirectResponse:
    try:
        referrer_uid_from_code(code)
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='Referral link not found') from error

    response = RedirectResponse(REFERRAL_DOWNLOAD_URL, status_code=302)
    response.set_cookie(
        REFERRAL_COOKIE_NAME,
        code,
        max_age=REFERRAL_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite='lax',
        path='/',
    )
    return response
