"""Monthly to yearly switch offer (see utils.yearly_switch). The switch itself is
POST /v1/payments/upgrade-subscription with ``switch_now``."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

import database.users as users_db
from utils import yearly_switch
from utils.other import endpoints as auth

router = APIRouter()


class YearlySwitchResponse(BaseModel):
    eligible: bool
    reason: str
    plan_id: Optional[str] = None
    price_id: Optional[str] = None
    currency: Optional[str] = None
    monthly_amount: Optional[int] = None
    yearly_amount: Optional[int] = None
    savings_amount: Optional[int] = None
    first_billing_period: Optional[bool] = None
    amount_due_today: Optional[int] = None
    renews_at: Optional[int] = None
    proration_date: Optional[int] = None


@router.get('/v1/payments/yearly-switch', response_model=YearlySwitchResponse)
def get_yearly_switch_endpoint(
    preview: bool = Query(
        False, description="Include Stripe's invoice preview: the charge today and the renewal date."
    ),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Whether this monthly payer can switch to yearly now, and (with preview) exactly what it costs."""
    subscription = users_db.get_user_subscription(uid)
    offer = yearly_switch.get_offer(subscription.stripe_subscription_id if subscription else None, preview=preview)
    return YearlySwitchResponse(**offer.__dict__)
