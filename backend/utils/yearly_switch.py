"""Omi Pro monthly to Omi Pro yearly, at the existing yearly price.

Offered to monthly payers in Plans & Billing and on Home. The switch applies now: Stripe credits
the unused part of the current month against the first yearly invoice, charges it today, and the
yearly period starts today. POST /v1/payments/upgrade-subscription applies it (``switch_now``)
with ``payment_behavior='error_if_incomplete'``, so a declined charge changes nothing and the
reader stays on monthly (#23301).

Only an active, renewing, undiscounted USD monthly subscription on Omi Pro's configured monthly
price qualifies: no trial (#23298), no past_due, no scheduled cancellation or plan change, no
discount (a coupon would carry onto the yearly invoice). No new prices, coupons or discounts.

The charge is the one the reader saw: the switch re-runs the preview at the same proration date
and refuses unless the amount matches, and it carries an idempotency key bound to that preview.
"""

import logging
import time
from dataclasses import dataclass, replace
from typing import Any, Optional

import stripe

logger = logging.getLogger(__name__)

# Omi Pro is the only plan sold (plan-catalog.md, 2026-10-26). A retired plan is not offered a new
# yearly term, and moving its monthly payers onto Omi Pro yearly is a price change, not this offer.
SWITCH_PLAN_IDS = frozenset({'unlimited_v2'})
# Billing currencies the offer supports. A JPY subscription manages through its own prices (#23584).
SWITCH_CURRENCIES = frozenset({'usd'})
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


class _Refused(Exception):
    """A preview that shows the switch must not run (``reason`` is the refusal)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


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


def _target(sub: Any) -> tuple[str, str]:
    """(plan_id, yearly price id) of a subscription that passed refusal()."""
    price = _get(_get(_get(sub, 'items'), 'data')[0], 'price')
    target = _monthly_target(_get(price, 'id'))
    if target is None:
        raise ValueError('not_offered')
    return target


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
    # Paused collection voids the switch invoice; an invoiced (enterprise) subscription is not charged now.
    if _get(sub, 'pause_collection'):
        return 'paused'
    if (_get(sub, 'collection_method') or 'charge_automatically') != 'charge_automatically':
        return 'collection_method'
    items = _get(_get(sub, 'items'), 'data') or []
    if len(items) != 1 or int(_get(items[0], 'quantity', 1) or 1) != 1:
        return 'items'
    price = _get(items[0], 'price') or {}
    recurring = _get(price, 'recurring') or {}
    if _get(recurring, 'interval') != 'month' or int(_get(recurring, 'interval_count', 1) or 1) != 1:
        return 'not_monthly'
    if not _get(price, 'unit_amount'):
        return 'free_price'
    sub_currency = _get(sub, 'currency') or _get(price, 'currency')
    if sub_currency not in SWITCH_CURRENCIES or _get(price, 'currency') not in SWITCH_CURRENCIES:
        return 'currency'
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
    plan_id, yearly_price_id = _target(sub)
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
    if _target(sub)[1] != target_price_id:
        return 'not_yearly_of_plan'
    return None


def request_refusal(
    sub: Any,
    target_price_id: str,
    promotion_code: Optional[str] = None,
    proration_date: Optional[int] = None,
    expected_amount_due: Optional[int] = None,
    now: Optional[int] = None,
) -> Optional[str]:
    """Why POST upgrade-subscription with ``switch_now`` must refuse, before any Stripe write."""
    if promotion_code:
        return 'promotion_code'  # no new discounts
    if proration_date is None or expected_amount_due is None:
        return 'preview_required'  # the switch charges only an amount the reader saw
    return switch_refusal(sub, target_price_id, now) or proration_date_refusal(sub, proration_date, now)


def charge_refusal(
    sub: Any, target_price_id: str, proration_date: Optional[int], expected_amount_due: Optional[int]
) -> Optional[str]:
    """Re-runs the preview at the reader's proration date; refuses unless it charges what they saw."""
    if proration_date is None or expected_amount_due is None:
        return 'preview_required'
    try:
        amount_due, _, _ = preview_invoice(sub, target_price_id, proration_date)
    except _Refused as refused:
        return refused.reason
    except Exception as exc:  # noqa: BLE001 - an unreadable preview never charges
        logger.warning('yearly switch charge preview failed: %s', type(exc).__name__)
        return 'preview_unavailable'
    return None if amount_due == expected_amount_due else 'preview_changed'


def upgrade_refusal(sub: Any, request: Any) -> Optional[str]:
    """POST upgrade-subscription ``switch_now`` guard: the offer's rules, then the re-run preview."""
    price_id, proration_date, expected = request.price_id, request.proration_date, request.expected_amount_due
    return request_refusal(sub, price_id, request.promotion_code, proration_date, expected) or charge_refusal(
        sub, price_id, proration_date, expected
    )


def idempotency_key(subscription_id: str, proration_date: Optional[int]) -> str:
    """One charge per preview: a retried or doubled request replays Stripe's first result."""
    return f'omi-yearly-switch-{subscription_id}-{proration_date}'


def charge_params(subscription_id: str, proration_date: Optional[int]) -> dict[str, Any]:
    """Subscription.modify arguments that pin the switch to the preview upgrade_refusal accepted."""
    return {'proration_date': proration_date, 'idempotency_key': idempotency_key(subscription_id, proration_date)}


def proration_date_refusal(sub: Any, proration_date: Optional[int], now: Optional[int] = None) -> Optional[str]:
    """A preview's proration date is honored only inside the current period and for an hour."""
    if proration_date is None:
        return 'preview_required'
    now = int(now if now is not None else time.time())
    period_start = int(_get(sub, 'current_period_start') or 0)
    if proration_date > now or proration_date < period_start or now - proration_date > PRORATION_DATE_MAX_AGE_SECONDS:
        return 'preview_expired'
    return None


def preview_invoice(sub: Any, price_id: str, proration_date: int) -> tuple[int, int, str]:
    """Stripe's own invoice for the switch at ``proration_date``: (amount due, renewal, currency).

    The same items and proration behavior as the switch itself, so the amount is the charge.
    """
    item_id = _get(_get(_get(sub, 'items'), 'data')[0], 'id')
    params: dict[str, Any] = {
        'customer': _get(sub, 'customer'),
        'subscription': _get(sub, 'id'),
        'subscription_details': {
            'items': [{'id': item_id, 'price': price_id}],
            'proration_behavior': 'always_invoice',
            'proration_date': proration_date,
        },
    }
    invoice = stripe.Invoice.create_preview(**params)
    currency = _get(invoice, 'currency')
    if currency not in SWITCH_CURRENCIES or _get(invoice, 'amount_due') is None:
        raise ValueError('preview_mismatch')
    # A customer-level coupon still discounts the yearly invoice: not an undiscounted switch.
    if _get(invoice, 'discounts') or any(
        int(_get(d, 'amount') or 0) for d in (_get(invoice, 'total_discount_amounts') or [])
    ):
        raise _Refused('discounted')
    ends = [
        int(_get(_get(line, 'period'), 'end') or 0)
        for line in (_get(_get(invoice, 'lines'), 'data') or [])
        if not _get(line, 'proration')
    ]
    renews_at = max(ends) if ends and max(ends) > proration_date else None
    if renews_at is None:
        raise ValueError('preview_without_period')
    return int(_get(invoice, 'amount_due')), renews_at, currency


def _preview(sub: Any, offer: YearlySwitch, now: int) -> YearlySwitch:
    amount_due, renews_at, currency = preview_invoice(sub, offer.price_id or '', now)
    if currency != offer.currency:
        raise ValueError('preview_mismatch')
    return replace(offer, amount_due_today=amount_due, renews_at=renews_at, proration_date=now)


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
        offer = evaluate(sub, stripe.Price.retrieve(_target(sub)[1]), now)
        if not offer.eligible or not preview:
            return offer
        return _preview(sub, offer, now)
    except _Refused as refused:
        return _ineligible(refused.reason)
    except Exception as exc:  # noqa: BLE001 - the offer is optional
        logger.warning('yearly switch lookup failed: %s', type(exc).__name__)
        return _ineligible('unavailable')
