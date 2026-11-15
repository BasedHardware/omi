"""Monthly to yearly switch offer (see utils.yearly_switch). The switch itself is
POST /v1/payments/upgrade-subscription with ``switch_now``."""

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

import database.users as users_db
from database.account_deletion_policy import account_deletion_blocks_access
from database.conversations import get_conversations_count
from utils import yearly_switch, yearly_switch_retention
from utils.observability.fallback import record_fallback
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

    def blocked():
        return account_deletion_blocks_access(users_db.get_user_deletion_wipe_status(uid))

    if blocked():
        return YearlySwitchResponse(eligible=False, reason='unavailable')
    try:
        # A durable assignment already decided both arms and consumed this UID's
        # single opportunity. Do not repeat Stripe or capture-count reads on Home.
        if yearly_switch_retention.assignment_exists(uid):
            return YearlySwitchResponse(eligible=False, reason='not_admitted')

        subscription = users_db.get_user_subscription(uid)
        subscription_id = subscription.stripe_subscription_id if subscription else None
        current_price_id = getattr(subscription, 'current_price_id', None) if subscription else None
        subscription_status = getattr(subscription, 'status', None) if subscription else None
        subscription_status = getattr(subscription_status, 'value', subscription_status)
        known_monthly_price = (
            bool(subscription_id)
            and subscription_status == 'active'
            and not bool(getattr(subscription, 'cancel_at_period_end', True))
            and isinstance(current_price_id, str)
            and yearly_switch.supports_monthly_switch_price(current_price_id)
        )

        # When the stored subscription snapshot identifies a configured monthly
        # price, apply engagement before Stripe. For older snapshots without a
        # price id, retain Stripe as the eligibility authority before reading captures.
        offer = None
        if placement != 'engaged' or not known_monthly_price:
            offer = yearly_switch.get_offer(subscription_id)
            if not offer.eligible:
                return YearlySwitchResponse(**offer.__dict__)

        # Engagement is evaluated only for a plausible monthly subscriber.
        now = None
        capture_count = 0
        if placement == 'engaged':
            now = datetime.now(timezone.utc)
            start = now - timedelta(days=yearly_switch_retention.WINDOW_DAYS)
            capture_count = get_conversations_count(uid, statuses=['completed'], start_date=start, end_date=now)
            if capture_count < yearly_switch_retention.ENGAGED_CAPTURES:
                return YearlySwitchResponse(eligible=False, reason='not_engaged')

        if offer is None:
            offer = yearly_switch.get_offer(subscription_id)
        if not offer.eligible:
            return YearlySwitchResponse(**offer.__dict__)

        admitted = yearly_switch_retention.admit(
            uid,
            placement,
            count_captures=lambda _start, _end: capture_count,
            blocked=blocked,
            now=now,
        )
    except Exception:
        # This optional placement must never block the existing cancel path.
        record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')
        return YearlySwitchResponse(eligible=False, reason='unavailable')
    return (
        YearlySwitchResponse(**offer.__dict__)
        if admitted
        else YearlySwitchResponse(eligible=False, reason='not_admitted')
    )
