"""Redeem a fully prepaid Omi Pro code with no card and no checkout page.

In scope: a single-use Stripe promotion code whose coupon makes the Omi Pro monthly price exactly
zero for a fixed number of months (100% off or an amount at least the monthly price, duration
``repeating`` N months, or ``once`` for one month when the amount is below the yearly price).
Every other code keeps today's checkout behaviour.

Stripe stays the record: the server creates the customer and a subscription with the code and no
payment method, set to cancel before the first undiscounted renewal. Stripe counts the redemption
and enforces max redemptions, expiry and first-time restrictions. The existing webhook grants Pro.
"""

import calendar
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import stripe

from config import prepaid_code_redeem as prepaid_config
from database import promotion_redemptions as redemptions_db
from database import users as users_db
from models.users import PlanType, SubscriptionStatus
from utils import play_stripe_guard
from utils import stripe as stripe_utils
from utils.log_sanitizer import sanitize
from utils.subscription import (
    find_active_paid_subscription_for_user,
    get_paid_plan_definitions,
    get_plan_display_name,
    is_paid_plan,
)

logger = logging.getLogger(__name__)

PLAN = PlanType.unlimited_v2
MAX_MONTHS = 24
# End an hour before the Nth monthly boundary so no undiscounted renewal can ever be invoiced.
END_MARGIN_SECONDS = 3600

INVALID = 'invalid_code'
USED = 'code_used'
EXPIRED = 'code_expired'
HAS_PLAN = 'has_plan'
NOT_PREPAID = 'not_prepaid'
NOT_ELIGIBLE = 'not_eligible'
TRY_AGAIN = 'try_again'


class PrepaidCodeError(Exception):
    def __init__(self, status_code: int, reason: str):
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


def normalize_code(code: str) -> str:
    # Stripe matches codes case-insensitively; pasted codes often carry spaces.
    return ''.join((code or '').split())


def add_months(ts: int, months: int) -> int:
    t = datetime.fromtimestamp(ts, timezone.utc)
    index = t.month - 1 + months
    year, month = t.year + index // 12, index % 12 + 1
    day = min(t.day, calendar.monthrange(year, month)[1])
    return int(t.replace(year=year, month=month, day=day).timestamp())


def _pro_prices() -> tuple[str, Optional[str]]:
    for definition in get_paid_plan_definitions():
        if definition['plan_type'] == PLAN and definition.get('monthly_price_id'):
            return definition['monthly_price_id'], definition.get('annual_price_id')
    raise PrepaidCodeError(503, TRY_AGAIN)


def prepaid_months(coupon: dict, monthly: dict, annual_amount: Optional[int]) -> Optional[int]:
    """Months the coupon makes Omi Pro monthly exactly zero, or None when it is not fully prepaid."""
    if not coupon.get('valid'):
        return None
    applies_to = (coupon.get('applies_to') or {}).get('products')
    product = monthly['product'] if isinstance(monthly['product'], str) else monthly['product']['id']
    if applies_to and product not in applies_to:
        return None
    unit_amount = monthly.get('unit_amount') or 0
    percent_off = coupon.get('percent_off')
    amount_off = coupon.get('amount_off')
    if percent_off is not None and float(percent_off) >= 100:
        covers_year = True
    elif amount_off and coupon.get('currency') == monthly.get('currency') and unit_amount and amount_off >= unit_amount:
        covers_year = annual_amount is not None and amount_off >= annual_amount
    else:
        return None
    duration = coupon.get('duration')
    if duration == 'repeating':
        months = coupon.get('duration_in_months') or 0
        return months if 1 <= months <= MAX_MONTHS else None
    if duration == 'once' and not covers_year:
        # A one-off code that would also zero a yearly price has no knowable term: leave it to checkout.
        return 1
    return None


def _promotion(code: str) -> dict:
    promos = stripe.PromotionCode.list(code=code, limit=1, expand=['data.coupon']).data
    if not promos:
        raise PrepaidCodeError(400, INVALID)
    return promos[0].to_dict()


def _classify(promo: dict, uid: str, now: int) -> tuple[dict, int]:
    coupon = promo.get('coupon') or {}
    if isinstance(coupon, str):
        coupon = stripe.Coupon.retrieve(coupon).to_dict()
    expires_at = promo.get('expires_at')
    redeem_by = coupon.get('redeem_by')
    if (expires_at and expires_at <= now) or (redeem_by and redeem_by <= now):
        raise PrepaidCodeError(400, EXPIRED)
    max_redemptions = promo.get('max_redemptions')
    if max_redemptions is not None and promo.get('times_redeemed', 0) >= max_redemptions:
        raise PrepaidCodeError(409, USED)
    if not promo.get('active'):
        raise PrepaidCodeError(409, USED) if promo.get('times_redeemed') else PrepaidCodeError(400, INVALID)
    if not coupon.get('valid'):
        raise PrepaidCodeError(400, EXPIRED)
    # A shared code is a discount, not something one person prepaid: keep it on checkout.
    if max_redemptions != 1:
        raise PrepaidCodeError(400, NOT_PREPAID)
    restricted_customer = promo.get('customer')
    if restricted_customer and restricted_customer != users_db.get_stripe_customer_id(uid):
        raise PrepaidCodeError(400, INVALID)
    monthly_price_id, annual_price_id = _pro_prices()
    monthly = stripe.Price.retrieve(monthly_price_id).to_dict()
    annual_amount = stripe.Price.retrieve(annual_price_id).get('unit_amount') if annual_price_id else None
    months = prepaid_months(coupon, monthly, annual_amount)
    if months is None:
        raise PrepaidCodeError(400, NOT_PREPAID)
    return monthly, months


def _has_live_plan(uid: str, now: int) -> bool:
    current = users_db.get_existing_user_subscription(uid)
    if play_stripe_guard.live_play_row(current):
        return True
    if (
        current is not None
        and is_paid_plan(current.plan)
        and current.status == SubscriptionStatus.active
        and (current.current_period_end or 0) >= now
    ):
        return True
    return find_active_paid_subscription_for_user(uid) is not None


def _customer_id(uid: str) -> str:
    customer_id = users_db.get_stripe_customer_id(uid)
    if customer_id:
        return customer_id
    customer = stripe.Customer.create(metadata={'uid': uid}, idempotency_key=f'prepaid-code-customer-{uid}')
    users_db.set_stripe_customer_id(uid, customer.id)
    return customer.id


def _create_subscription(uid: str, promo: dict, price_id: str, ends_at: int) -> dict:
    metadata = {
        **stripe_utils.promotion_code_attribution(promo),
        'uid': uid,
        'sub_type': 'unlimited',
        'redeemed_promotion_code_id': promo['id'],
        prepaid_config.SUBSCRIPTION_MARKER: '1',
    }
    return stripe.Subscription.create(
        customer=_customer_id(uid),
        items=[{'price': price_id}],
        discounts=[{'promotion_code': promo['id']}],
        cancel_at=ends_at,
        proration_behavior='none',
        # Never leave an incomplete subscription or an invoice to chase: the code must zero it.
        payment_behavior='error_if_incomplete',
        metadata=metadata,
        idempotency_key=f'prepaid-code-{promo["id"]}-{uid}',
    ).to_dict()


def _stripe_reason(error: stripe.StripeError) -> str:
    message = str(getattr(error, 'user_message', None) or error).lower()
    if 'used up' in message:
        return USED
    if 'expired' in message:
        return EXPIRED
    if 'prior transactions' in message or 'first-time' in message:
        return NOT_ELIGIBLE
    return INVALID


def _result(ends_at: int, months: int) -> dict:
    return {'status': 'redeemed', 'plan': get_plan_display_name(PLAN), 'ends_at': ends_at, 'months': months}


def _resume(uid: str, promo: dict, claim: dict) -> dict:
    """Same user, same code again: return the first redemption, never a second subscription."""
    ends_at, months = claim.get('ends_at'), claim.get('months')
    if not ends_at or not months:
        raise PrepaidCodeError(503, TRY_AGAIN)
    try:
        monthly_price_id, _ = _pro_prices()
        _create_subscription(uid, promo, monthly_price_id, ends_at)
    except stripe.StripeError:
        current = users_db.get_existing_user_subscription(uid)
        if not (current and is_paid_plan(current.plan) and current.status == SubscriptionStatus.active):
            raise PrepaidCodeError(503, TRY_AGAIN)
    return _result(ends_at, months)


def redeem_prepaid_code(uid: str, raw_code: str) -> dict:
    code = normalize_code(raw_code)
    if not code:
        raise PrepaidCodeError(400, INVALID)
    now = int(time.time())
    promo = _promotion(code)

    claim = redemptions_db.get(promo['id'])
    if claim is not None:
        if claim.get('uid') == uid:
            return _resume(uid, promo, claim)
        raise PrepaidCodeError(409, USED)

    monthly, months = _classify(promo, uid, now)
    if _has_live_plan(uid, now):
        raise PrepaidCodeError(409, HAS_PLAN)

    ends_at = add_months(now, months) - END_MARGIN_SECONDS
    coupon = promo.get('coupon') or {}
    if not redemptions_db.claim(
        promo['id'],
        uid=uid,
        subscription_id='',
        coupon_id=str((coupon.get('id') if isinstance(coupon, dict) else coupon) or ''),
        attribution=stripe_utils.promotion_code_attribution(promo),
        extra={'ends_at': ends_at, 'months': months, 'kind': 'prepaid_no_card'},
    ):
        claim = redemptions_db.get(promo['id']) or {}
        if claim.get('uid') == uid:
            return _resume(uid, promo, claim)
        raise PrepaidCodeError(409, USED)

    try:
        subscription = _create_subscription(uid, promo, monthly['id'], ends_at)
    except stripe.InvalidRequestError as error:
        # Stripe refused the code itself: nothing was created, so the claim is released.
        logger.warning(f"Prepaid code refused by Stripe for {uid}: {sanitize(str(error))}")
        redemptions_db.release(promo['id'])
        raise PrepaidCodeError(400, _stripe_reason(error)) from error
    except stripe.StripeError as error:
        # Unknown outcome: keep the claim so a retry replays the same idempotent create.
        logger.error(f"Prepaid code redemption failed for {uid}: {sanitize(str(error))}")
        raise PrepaidCodeError(503, TRY_AGAIN) from error

    redemptions_db.set_subscription(promo['id'], subscription['id'])
    logger.info(f"Redeemed prepaid code {promo['id']} as {subscription['id']} for {uid} ({months} months)")
    return _result(ends_at, months)
