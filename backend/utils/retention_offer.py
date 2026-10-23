"""Cancel-flow retention offer: 50% off the next 3 monthly invoices, once per Stripe customer.

Offered on the last step of the in-app cancel flow. Accepting applies the coupon to the
live subscription and clears any scheduled cancellation, so the reader stays subscribed.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

import stripe

logger = logging.getLogger(__name__)

COUPON_ID = 'omi-retention-50off-3mo'
PERCENT_OFF = 50
DURATION_MONTHS = 3
USED_METADATA_KEY = 'omi_retention_offer_subscription'  # the subscription that claimed it
LOCK_TTL_SECONDS = 30

_ELIGIBLE_STATUSES = frozenset({'active', 'past_due'})


@dataclass(frozen=True)
class RetentionOffer:
    eligible: bool
    reason: str
    percent_off: int = PERCENT_OFF
    duration_months: int = DURATION_MONTHS
    regular_amount: Optional[int] = None  # minor units
    discounted_amount: Optional[int] = None  # minor units
    currency: Optional[str] = None


def _ineligible(reason: str) -> RetentionOffer:
    return RetentionOffer(eligible=False, reason=reason)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _has_retention_coupon(sub: Any) -> bool:
    """Whether our stay coupon is already on the subscription (needs ``discounts`` expanded)."""
    for discount in _get(sub, 'discounts') or []:
        coupon = _get(_get(discount, 'source'), 'coupon') or _get(discount, 'coupon')
        if _get(coupon, 'id', coupon) == COUPON_ID:
            return True
    legacy = _get(sub, 'discount')
    return bool(legacy) and _get(_get(legacy, 'coupon'), 'id') == COUPON_ID


def _has_discount(sub: Any) -> bool:
    if _get(sub, 'discount'):
        return True
    return bool(_get(sub, 'discounts'))


def evaluate(sub: Any, customer: Any) -> RetentionOffer:
    """Pure eligibility check over a retrieved Stripe subscription (with price) and its customer."""
    if sub is None:
        return _ineligible('no_subscription')
    if _get(sub, 'status') not in _ELIGIBLE_STATUSES:
        return _ineligible('status')
    if _get(sub, 'schedule'):
        return _ineligible('scheduled_change')
    if _has_discount(sub):
        return _ineligible('already_discounted')
    metadata = _get(customer, 'metadata') or {}
    claimed_by = _get(metadata, USED_METADATA_KEY)
    if claimed_by and claimed_by != _get(sub, 'id'):
        return _ineligible('already_used')
    items = _get(_get(sub, 'items'), 'data') or []
    if len(items) != 1:
        return _ineligible('items')
    price = _get(items[0], 'price')
    recurring = _get(price, 'recurring') or {}
    if _get(recurring, 'interval') != 'month' or int(_get(recurring, 'interval_count', 1) or 1) != 1:
        return _ineligible('not_monthly')
    amount = _get(price, 'unit_amount')
    if not amount:
        return _ineligible('free_price')
    quantity = int(_get(items[0], 'quantity', 1) or 1)
    regular = int(amount) * quantity
    return RetentionOffer(
        eligible=True,
        reason='eligible',
        regular_amount=regular,
        discounted_amount=regular * (100 - PERCENT_OFF) // 100,
        currency=_get(price, 'currency'),
    )


def _retrieve(subscription_id: str):
    sub = stripe.Subscription.retrieve(subscription_id, expand=['items.data.price', 'discounts'])
    customer_id = _get(sub, 'customer')
    customer = stripe.Customer.retrieve(customer_id) if customer_id else None
    return sub, customer


def get_offer(subscription_id: Optional[str]) -> RetentionOffer:
    """Never raises: a Stripe failure hides the offer instead of breaking the cancel flow."""
    if not subscription_id:
        return _ineligible('no_subscription')
    try:
        sub, customer = _retrieve(subscription_id)
        return evaluate(sub, customer)
    except Exception as exc:  # noqa: BLE001 - offer is optional
        logger.warning('retention offer lookup failed: %s', type(exc).__name__)
        return _ineligible('unavailable')


def _ensure_coupon() -> None:
    try:
        stripe.Coupon.retrieve(COUPON_ID)
    except stripe.error.InvalidRequestError:
        stripe.Coupon.create(
            id=COUPON_ID,
            percent_off=PERCENT_OFF,
            duration='repeating',
            duration_in_months=DURATION_MONTHS,
            name=f'Stay offer: {PERCENT_OFF}% off {DURATION_MONTHS} months',
        )


def _acquire_lock(customer_id: str) -> bool:
    from database.redis_db import r

    return bool(r.set(f'retention_offer:{customer_id}', '1', ex=LOCK_TTL_SECONDS, nx=True))


def _release_lock(customer_id: str) -> None:
    from database.redis_db import r

    r.delete(f'retention_offer:{customer_id}')


def accept(subscription_id: str) -> RetentionOffer:
    """Claim the offer for this customer, then discount the subscription and keep it renewing.

    One redemption per Stripe customer: a per-customer lock serializes workers, and the claim
    (customer metadata naming this subscription) is written before the discount, so a retry
    after any partial failure finishes the same redemption instead of starting another.
    Raises ValueError(reason) when the offer does not apply.
    """
    sub, _ = _retrieve(subscription_id)
    customer_id = _get(sub, 'customer')
    if not customer_id:
        raise ValueError('no_customer')
    if not _acquire_lock(customer_id):
        raise ValueError('in_progress')
    try:
        customer = stripe.Customer.retrieve(customer_id)
        claimed_by = _get(_get(customer, 'metadata') or {}, USED_METADATA_KEY)
        if claimed_by and claimed_by != subscription_id:
            raise ValueError('already_used')
        if _has_retention_coupon(sub):
            # Retry after a lost response: finish the bookkeeping, never reapply.
            if not claimed_by:
                stripe.Customer.modify(customer_id, metadata={USED_METADATA_KEY: subscription_id})
            if _get(sub, 'cancel_at_period_end'):
                stripe.Subscription.modify(subscription_id, cancel_at_period_end=False)
            return RetentionOffer(eligible=True, reason='already_applied')
        offer = evaluate(sub, customer)
        if not offer.eligible:
            raise ValueError(offer.reason)
        if not claimed_by:
            stripe.Customer.modify(
                customer_id,
                metadata={USED_METADATA_KEY: subscription_id},
                idempotency_key=f'retention-claim-{subscription_id}',
            )
        _ensure_coupon()
        stripe.Subscription.modify(
            subscription_id,
            discounts=[{'coupon': COUPON_ID}],
            cancel_at_period_end=False,
            idempotency_key=f'retention-apply-{subscription_id}',
        )
        return offer
    finally:
        _release_lock(customer_id)
