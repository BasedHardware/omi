"""Monthly to yearly switch on the same plan, at the plan's existing yearly price.

Offered to monthly payers in Plans & Billing and on Home. The switch applies now: Stripe credits
the unused part of the current month against the first yearly invoice, charges it today, and the
yearly period starts today. POST /v1/payments/upgrade-subscription applies it (``switch_now``)
with ``payment_behavior='error_if_incomplete'``, so a declined charge changes nothing and the
reader stays on monthly (#23301).

Only an active, renewing, undiscounted monthly subscription qualifies: no trial (#23298), no
past_due, no scheduled cancellation or plan change, no discount (a coupon would carry onto the
yearly invoice). No new prices, coupons or discounts.
"""

import logging
import time
from dataclasses import dataclass, replace
from typing import Any, Optional

import stripe

logger = logging.getLogger(__name__)

# The plans the phone sells (plan-catalog.md). Desktop plans stay manage-only on mobile, legacy Neo
# is not offered a new term.
SWITCH_PLAN_IDS = frozenset({'plus', 'unlimited_v2'})
# A reader inside this long of their first paid period is in their first billing month.
FIRST_PERIOD_SECONDS = 7 * 86400
# A preview's proration date the switch still honors.
PRORATION_DATE_MAX_AGE_SECONDS = 3600


@dataclass(frozen=True)
class YearlySwitch:
    eligible: bool
    reason: str
    plan_id: Optional[str] = None
    price_id: Optional[str] = None  # the yearly price to switch to
    currency: Optional[str] = None
    monthly_amount: Optional[int] = None  # minor units
    yearly_amount: Optional[int] = None  # minor units
    savings_amount: Optional[int] = None  # 12 x monthly - yearly, minor units
    first_billing_period: Optional[bool] = None
    # Preview only (Stripe's invoice preview for the switch):
    amount_due_today: Optional[int] = None
    renews_at: Optional[int] = None
    proration_date: Optional[int] = None


def _ineligible(reason: str) -> YearlySwitch:
    return YearlySwitch(eligible=False, reason=reason)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _plan_definitions() -> list[dict]:
    from utils.subscription import get_paid_plan_definitions

    return get_paid_plan_definitions()


def _monthly_target(price_id: Optional[str]) -> Optional[tuple[str, str]]:
    """(plan_id, yearly price id) when price_id is a switchable plan's configured monthly price."""
    for definition in _plan_definitions():
        plan = definition['plan_type']
        plan_id = getattr(plan, 'value', plan)
        if plan_id not in SWITCH_PLAN_IDS or definition.get('legacy'):
            continue
        if price_id and price_id == definition.get('monthly_price_id') and definition.get('annual_price_id'):
            return plan_id, definition['annual_price_id']
    return None


def refusal(sub: Any, now: Optional[int] = None) -> Optional[str]:
    """Why this subscription cannot switch to yearly now; None when it can."""
    now = int(now if now is not None else time.time())
    if sub is None:
        return 'no_subscription'
    if _get(sub, 'status') != 'active':
        return 'status'
    trial_end = _get(sub, 'trial_end')
    if trial_end and int(trial_end) > now:
        return 'trial'
    if _get(sub, 'cancel_at_period_end') or _get(sub, 'cancel_at'):
        return 'cancel_scheduled'
    if _get(sub, 'schedule'):
        return 'scheduled_change'
    if _get(sub, 'pending_update'):
        return 'pending_update'
    if _get(sub, 'discount') or _get(sub, 'discounts'):
        return 'discounted'
    items = _get(_get(sub, 'items'), 'data') or []
    if len(items) != 1 or int(_get(items[0], 'quantity', 1) or 1) != 1:
        return 'items'
    price = _get(items[0], 'price') or {}
    recurring = _get(price, 'recurring') or {}
    if _get(recurring, 'interval') != 'month' or int(_get(recurring, 'interval_count', 1) or 1) != 1:
        return 'not_monthly'
    if not _get(price, 'unit_amount'):
        return 'free_price'
    if _monthly_target(_get(price, 'id')) is None:
        return 'not_offered'
    return None


def evaluate(sub: Any, yearly_price: Any, now: Optional[int] = None) -> YearlySwitch:
    """Pure eligibility and savings over a retrieved subscription and the plan's yearly price."""
    now = int(now if now is not None else time.time())
    reason = refusal(sub, now)
    if reason:
        return _ineligible(reason)
    price = _get(_get(_get(sub, 'items'), 'data')[0], 'price')
    plan_id, yearly_price_id = _monthly_target(_get(price, 'id'))
    yearly_recurring = _get(yearly_price, 'recurring') or {}
    if (
        yearly_price is None
        or _get(yearly_price, 'id') != yearly_price_id
        or _get(yearly_price, 'active') is False
        or _get(yearly_recurring, 'interval') != 'year'
        or int(_get(yearly_recurring, 'interval_count', 1) or 1) != 1
        or not _get(yearly_price, 'unit_amount')
    ):
        return _ineligible('no_yearly_price')
    currency = _get(price, 'currency')
    if not currency or _get(yearly_price, 'currency') != currency:
        return _ineligible('currency')
    monthly = int(_get(price, 'unit_amount'))
    yearly = int(_get(yearly_price, 'unit_amount'))
    savings = 12 * monthly - yearly
    if savings <= 0:
        return _ineligible('no_savings')
    paid_from = max(int(_get(sub, 'start_date') or 0), int(_get(sub, 'trial_end') or 0))
    period_start = int(_get(sub, 'current_period_start') or 0)
    return YearlySwitch(
        eligible=True,
        reason='eligible',
        plan_id=plan_id,
        price_id=yearly_price_id,
        currency=currency,
        monthly_amount=monthly,
        yearly_amount=yearly,
        savings_amount=savings,
        first_billing_period=period_start - paid_from < FIRST_PERIOD_SECONDS,
    )


def switch_refusal(sub: Any, target_price_id: str, now: Optional[int] = None) -> Optional[str]:
    """The plan-change endpoint's guard for ``switch_now``: the same rules the offer uses."""
    reason = refusal(sub, now)
    if reason:
        return reason
    price = _get(_get(_get(sub, 'items'), 'data')[0], 'price')
    if _monthly_target(_get(price, 'id'))[1] != target_price_id:
        return 'not_yearly_of_plan'
    return None


def proration_date_refusal(sub: Any, proration_date: Optional[int], now: Optional[int] = None) -> Optional[str]:
    """A preview's proration date is honored only inside the current period and for an hour."""
    if proration_date is None:
        return None
    now = int(now if now is not None else time.time())
    period_start = int(_get(sub, 'current_period_start') or 0)
    if proration_date > now or proration_date < period_start or now - proration_date > PRORATION_DATE_MAX_AGE_SECONDS:
        return 'preview_expired'
    return None


def _preview(sub: Any, offer: YearlySwitch, now: int) -> YearlySwitch:
    """Stripe's own invoice for the switch: what is charged today and when the yearly plan renews."""
    item_id = _get(_get(_get(sub, 'items'), 'data')[0], 'id')
    invoice = stripe.Invoice.create_preview(
        customer=_get(sub, 'customer'),
        subscription=_get(sub, 'id'),
        subscription_details={
            'items': [{'id': item_id, 'price': offer.price_id}],
            'proration_behavior': 'always_invoice',
            'proration_date': now,
        },
    )
    if _get(invoice, 'currency') != offer.currency or _get(invoice, 'amount_due') is None:
        raise ValueError('preview_mismatch')
    ends = [
        int(_get(_get(line, 'period'), 'end') or 0)
        for line in (_get(_get(invoice, 'lines'), 'data') or [])
        if not _get(line, 'proration')
    ]
    renews_at = max(ends) if ends and max(ends) > now else None
    if renews_at is None:
        raise ValueError('preview_without_period')
    return replace(offer, amount_due_today=int(_get(invoice, 'amount_due')), renews_at=renews_at, proration_date=now)


def get_offer(subscription_id: Optional[str], preview: bool = False, now: Optional[int] = None) -> YearlySwitch:
    """Never raises: a Stripe failure hides the offer instead of breaking Plans & Billing or Home."""
    if not subscription_id:
        return _ineligible('no_subscription')
    now = int(now if now is not None else time.time())
    try:
        sub = stripe.Subscription.retrieve(subscription_id, expand=['items.data.price'])
        reason = refusal(sub, now)
        if reason:
            return _ineligible(reason)
        price = _get(_get(_get(sub, 'items'), 'data')[0], 'price')
        _, yearly_price_id = _monthly_target(_get(price, 'id'))
        offer = evaluate(sub, stripe.Price.retrieve(yearly_price_id), now)
        if not offer.eligible or not preview:
            return offer
        return _preview(sub, offer, now)
    except Exception as exc:  # noqa: BLE001 - the offer is optional
        logger.warning('yearly switch lookup failed: %s', type(exc).__name__)
        return _ineligible('unavailable')
