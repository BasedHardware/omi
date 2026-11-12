"""Monthly to yearly switch offer (see utils.yearly_switch). The switch itself is
POST /v1/payments/upgrade-subscription with ``switch_now``."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

import database.users as users_db
from utils import yearly_switch, yearly_switch_retention
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


@router.get('/v1/payments/yearly-switch-retention', response_model=YearlySwitchResponse)
def retention_status(uid: str = Depends(auth.get_current_user_uid)):
    """Config only: never enroll or preview a charge. Clients refresh on resume."""
    return YearlySwitchResponse(eligible=yearly_switch_retention.enabled(), reason='retention_status')


@router.post('/v1/payments/yearly-switch-retention', response_model=YearlySwitchResponse)
def admit_retention(placement: Literal['cancel', 'engaged'], uid: str = Depends(auth.get_current_user_uid)):
    """Consume one UID admission, for either placement; never applies a switch."""
    if not yearly_switch_retention.enabled():
        return YearlySwitchResponse(eligible=False, reason='retention_disabled')
    from database.account_deletion_policy import account_deletion_blocks_access
    from database.conversations import get_conversations_count

    def blocked():
        return account_deletion_blocks_access(users_db.get_user_deletion_wipe_status(uid))

    if blocked():
        return YearlySwitchResponse(eligible=False, reason='unavailable')
    subscription = users_db.get_user_subscription(uid)
    offer = yearly_switch.get_offer(subscription.stripe_subscription_id if subscription else None)
    if not offer.eligible:
        return YearlySwitchResponse(**offer.__dict__)
    try:
        admitted = yearly_switch_retention.admit(
            uid,
            placement,
            count_captures=lambda start, end: get_conversations_count(
                uid, statuses=['completed'], start_date=start, end_date=end
            ),
            blocked=blocked,
        )
    except Exception:
        # This optional placement must never block the existing cancel path.
        from utils.observability.fallback import record_fallback

        record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')
        return YearlySwitchResponse(eligible=False, reason='unavailable')
    return (
        YearlySwitchResponse(**offer.__dict__)
        if admitted
        else YearlySwitchResponse(eligible=False, reason='not_admitted')
    )
