"""Promotion code redemption: onto an existing subscription (utils.promotion_redemption), or a fully
prepaid code with no card (utils.prepaid_code_redemption)."""

import logging
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import prepaid_code_redeem as prepaid_code_config
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.prepaid_code_redemption import TRY_AGAIN, PrepaidCodeError, redeem_prepaid_code
from utils.promotion_redemption import RedemptionError, redeem_promotion_code

logger = logging.getLogger(__name__)

router = APIRouter()


class RedeemCodeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)


class RedeemCodeResponse(BaseModel):
    status: str
    percent_off: Optional[float] = None
    amount_off: Optional[int] = None
    currency: Optional[str] = None
    applies_at: Optional[int] = None


@router.post('/v1/payments/redeem-code', response_model=RedeemCodeResponse)
def redeem_code_endpoint(
    request: RedeemCodeRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'payments:redeem_code')),
):
    try:
        return redeem_promotion_code(uid, request.code)
    except RedemptionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except stripe.StripeError as e:
        logger.error(f"Stripe error redeeming code for {uid}: {sanitize(str(e))}")
        raise HTTPException(status_code=502, detail="Could not apply this code. Please try again.")


class RedeemPrepaidCodeResponse(BaseModel):
    status: str
    plan: str
    ends_at: int
    months: int


@router.post('/v1/payments/prepaid-code/redeem', response_model=RedeemPrepaidCodeResponse)
def redeem_prepaid_code_endpoint(
    body: RedeemCodeRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Redeem a fully prepaid Omi Pro code with no card. Errors carry a reason code as ``detail``."""
    if not prepaid_code_config.enabled_for(uid):
        raise HTTPException(status_code=404, detail='Not Found')
    auth.check_rate_limit_inline(uid, 'payments:prepaid_code')
    try:
        return redeem_prepaid_code(uid, body.code)
    except PrepaidCodeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.reason)
    except stripe.StripeError as e:
        logger.error(f"Stripe error redeeming prepaid code for {uid}: {sanitize(str(e))}")
        raise HTTPException(status_code=503, detail=TRY_AGAIN)
