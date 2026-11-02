"""Promotion code redemption onto an existing subscription (see utils.promotion_redemption)."""

import logging
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
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
