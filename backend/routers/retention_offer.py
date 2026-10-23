"""Cancel-flow stay offer endpoints (see utils.retention_offer)."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import database.users as users_db
from utils import retention_offer
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


class RetentionOfferResponse(BaseModel):
    eligible: bool
    percent_off: int
    duration_months: int
    regular_amount: Optional[int] = None
    discounted_amount: Optional[int] = None
    currency: Optional[str] = None


def _response(offer: retention_offer.RetentionOffer) -> RetentionOfferResponse:
    return RetentionOfferResponse(
        eligible=offer.eligible,
        percent_off=offer.percent_off,
        duration_months=offer.duration_months,
        regular_amount=offer.regular_amount,
        discounted_amount=offer.discounted_amount,
        currency=offer.currency,
    )


@router.get('/v1/payments/retention-offer', response_model=RetentionOfferResponse)
def get_retention_offer_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """The stay offer shown on the last cancel step; ineligible readers get eligible=false."""
    subscription = users_db.get_user_subscription(uid)
    return _response(retention_offer.get_offer(subscription.stripe_subscription_id if subscription else None))


@router.post('/v1/payments/retention-offer', response_model=RetentionOfferResponse)
def accept_retention_offer_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """Apply the stay offer and keep the subscription renewing."""
    subscription = users_db.get_user_subscription(uid)
    if not subscription or not subscription.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription found.")
    try:
        offer = retention_offer.accept(subscription.stripe_subscription_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Offer not available: {exc}")
    except Exception as e:
        logger.error(f"Error applying retention offer: {sanitize(str(e))}")
        raise HTTPException(status_code=500, detail="Could not apply the offer. Please try again.")
    # Firestore's cancel_at_period_end is written only by Stripe's customer.subscription.updated
    # webhook, which fires for this write too. Writing it here could race a later cancellation.
    logger.info(f"Retention offer accepted uid={uid}")
    return _response(offer)
