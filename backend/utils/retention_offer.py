"""Cancel-flow retention offer: 50% off the next 3 monthly invoices, once per Stripe customer.

Offered on the last step of the in-app cancel flow. Accepting applies the coupon to the
live subscription and clears any scheduled cancellation, so the reader stays subscribed.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import stripe

logger = logging.getLogger(__name__)

COUPON_ID = 'omi-retention-50off-3mo'
PERCENT_OFF = 50
DURATION_MONTHS = 3
USED_METADATA_KEY = 'omi_retention_offer_subscription'  # the subscription that claimed it
APPLIED_METADATA_KEY = 'omi_retention_offer_applied'  # on the subscription, written with the discount
LOCK_TTL_SECONDS = 120

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
    if _get(_get(sub, 'metadata') or {}, APPLIED_METADATA_KEY):
        return _ineligible('already_used')
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
    except stripe.InvalidRequestError:
        stripe.Coupon.create(
            id=COUPON_ID,
            percent_off=PERCENT_OFF,
            duration='repeating',
            duration_in_months=DURATION_MONTHS,
            name=f'Stay offer: {PERCENT_OFF}% off {DURATION_MONTHS} months',
        )


_RELEASE_IF_OWNER = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


_RENEW_IF_OWNER = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
)


def _hold_lock(customer_id: str, token: str) -> None:
    """Renews the lease right before a Stripe write; a worker that lost it stops without writing."""
    from database.redis_db import r

    if not r.eval(_RENEW_IF_OWNER, 1, f'retention_offer:{customer_id}', token, LOCK_TTL_SECONDS):
        raise ValueError('lease_lost')


def _acquire_lock(customer_id: str) -> Optional[str]:
    """Per-customer lease; returns the owner token, or None when another worker holds it."""
    from database.redis_db import r

    token = uuid.uuid4().hex
    return token if r.set(f'retention_offer:{customer_id}', token, ex=LOCK_TTL_SECONDS, nx=True) else None


def _release_lock(customer_id: str, token: str) -> None:
    """Deletes the lease only if this worker still owns it."""
    from database.redis_db import r

    r.eval(_RELEASE_IF_OWNER, 1, f'retention_offer:{customer_id}', token)


def accept(subscription_id: str) -> RetentionOffer:
    """Claim the offer for this customer, then discount the subscription and keep it renewing.

    One redemption per Stripe customer, ever:
    - a per-customer lease serializes workers in the normal case;
    - the claim (customer metadata naming this subscription) uses a per-customer Stripe
      idempotency key, so even a worker that outlived its lease cannot claim for a second
      subscription (Stripe rejects the same key with different parameters);
    - the discount write uses a fixed per-subscription idempotency key, so a worker that
      resumes after its lease replays the earlier result instead of writing again (and cannot
      undo a cancellation made since); it also stamps the subscription as applied, so the
      offer never returns after the 3 discounted months end.
    A retry after any partial failure finishes the same redemption. Raises ValueError(reason).
    """
    sub, _ = _retrieve(subscription_id)
    customer_id = _get(sub, 'customer')
    if not customer_id:
        raise ValueError('no_customer')
    token = _acquire_lock(customer_id)
    if not token:
        raise ValueError('in_progress')
    try:
        # Decide only on state read under the lease: a request that read before another worker
        # redeemed must see that redemption, not its stale copy.
        sub = stripe.Subscription.retrieve(subscription_id, expand=['items.data.price', 'discounts'])
        customer = stripe.Customer.retrieve(customer_id)
        claimed_by = _get(_get(customer, 'metadata') or {}, USED_METADATA_KEY)
        if claimed_by and claimed_by != subscription_id:
            raise ValueError('already_used')
        applied = bool(_get(_get(sub, 'metadata') or {}, APPLIED_METADATA_KEY))
        if applied or _has_retention_coupon(sub):
            if not _has_retention_coupon(sub):
                raise ValueError('already_used')  # redeemed earlier and the discount has ended
            # Retry after a lost response: finish the bookkeeping, never reapply.
            if not claimed_by:
                _hold_lock(customer_id, token)
                _claim(customer_id, subscription_id)
            # Never touch cancel_at_period_end here: a cancellation made after the redemption
            # belongs to the reader, and a late or repeated request must not undo it.
            if not applied:
                _hold_lock(customer_id, token)
                stripe.Subscription.modify(subscription_id, metadata={APPLIED_METADATA_KEY: '1'})
            return RetentionOffer(eligible=True, reason='already_applied')
        offer = evaluate(sub, customer)
        if not offer.eligible:
            raise ValueError(offer.reason)
        if not claimed_by:
            _hold_lock(customer_id, token)
            _claim(customer_id, subscription_id)
        _ensure_coupon()
        _hold_lock(customer_id, token)
        _apply(subscription_id)
        return offer
    finally:
        _release_lock(customer_id, token)


def _apply(subscription_id: str) -> None:
    """Discount the subscription and keep it renewing, at most once per subscription.

    The key is fixed per subscription, so a worker that resumes after its lease expired sends
    the same key and parameters as the request that already redeemed: Stripe replays that
    result instead of executing again, and a cancellation made since then stays intact. A
    failure is never retried blind: the subscription is re-read, and a discount that landed
    counts as success. A cached failure leaves nothing applied; the reader can retry later.
    """
    try:
        stripe.Subscription.modify(
            subscription_id,
            discounts=[{'coupon': COUPON_ID}],
            cancel_at_period_end=False,
            metadata={APPLIED_METADATA_KEY: '1'},
            idempotency_key=f'retention-apply-{subscription_id}',
        )
        return
    except stripe.StripeError:
        sub = stripe.Subscription.retrieve(subscription_id, expand=['discounts'])
    if _has_retention_coupon(sub):
        return  # the write landed even though the response failed
    raise ValueError('unavailable')


def _claim(customer_id: str, subscription_id: str) -> None:
    """Record this subscription as the customer's one redemption.

    The per-customer idempotency key blocks a stale worker from claiming for a second
    subscription. Stripe also caches a 5xx under that key for 24h, so a failure is never retried
    blind: the customer is re-read and the saved claim decides.
    """
    try:
        stripe.Customer.modify(
            customer_id,
            metadata={USED_METADATA_KEY: subscription_id},
            idempotency_key=f'retention-claim-{customer_id}',
        )
        return
    except stripe.IdempotencyError:
        raise ValueError('already_used')
    except stripe.StripeError:
        claimed_by = _get(_get(stripe.Customer.retrieve(customer_id), 'metadata') or {}, USED_METADATA_KEY)
    if claimed_by == subscription_id:
        return  # the write landed even though the response failed
    if claimed_by:
        raise ValueError('already_used')
    # Nothing claimed and the key holds a cached failure: no claim, no discount; retry after it expires.
    raise ValueError('unavailable')
