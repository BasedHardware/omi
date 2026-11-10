"""Redeem a promotion code onto the caller's existing subscription.

Stripe checks a promotion code's minimum amount against what is due today, which is
zero during a free trial, so a code with a minimum can never be entered at a trial
checkout. Stripe also refuses such codes on subscription updates. Omi checks the
code's restrictions against the plan price itself and attaches the code's coupon to
the subscription, so the discount lands on the first invoice after the trial.
"""

import hashlib
import logging
import time
from typing import Optional

import stripe

from database import promotion_redemptions as redemptions_db
from database import users as users_db
from utils import stripe as stripe_utils
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

REDEEMABLE_STATUSES = ('trialing', 'active')


class RedemptionError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _invalid() -> RedemptionError:
    return RedemptionError(400, 'Invalid or expired code.')


def _find_promotion_code(code: str) -> dict:
    promos = stripe.PromotionCode.list(code=code, active=True, limit=1, expand=['data.coupon']).data
    if not promos:
        raise _invalid()
    promo = promos[0].to_dict()
    max_redemptions = promo.get('max_redemptions')
    if max_redemptions is not None and promo.get('times_redeemed', 0) >= max_redemptions:
        raise _invalid()
    expires_at = promo.get('expires_at')
    if expires_at and expires_at <= time.time():
        raise _invalid()
    return promo


def _coupon_id(promo: dict) -> str:
    coupon = promo.get('coupon') or (promo.get('promotion') or {}).get('coupon')
    coupon_id = coupon.get('id') if isinstance(coupon, dict) else coupon
    if not isinstance(coupon_id, str):
        raise _invalid()
    return coupon_id


def _check_eligible(promo: dict, coupon: dict, subscription: dict) -> None:
    items = subscription['items']['data']
    if len(items) != 1:
        raise RedemptionError(400, 'This code cannot be applied to your plan.')
    price = items[0]['price']
    product = price['product'] if isinstance(price['product'], str) else price['product']['id']

    if not coupon.get('valid'):
        raise _invalid()
    applies_to = (coupon.get('applies_to') or {}).get('products')
    if applies_to and product not in applies_to:
        raise RedemptionError(400, 'This code is for a different plan.')

    restrictions = promo.get('restrictions') or {}
    minimum = restrictions.get('minimum_amount')
    if minimum:
        if (
            restrictions.get('minimum_amount_currency') != price['currency']
            or (price.get('unit_amount') or 0) < minimum
        ):
            raise RedemptionError(400, 'This code is for a different plan.')
    if promo.get('customer') and promo['customer'] != subscription['customer']:
        raise _invalid()
    if restrictions.get('first_time_transaction') and subscription['status'] != 'trialing':
        raise RedemptionError(400, 'This code is only for new subscriptions.')


def redeem_promotion_code(uid: str, code: str) -> dict:
    code = code.strip()
    if not code:
        raise _invalid()

    current = users_db.get_user_subscription(uid)
    subscription_id: Optional[str] = current.stripe_subscription_id if current else None
    if not subscription_id:
        raise RedemptionError(400, 'Start your plan first, then redeem your code.')

    subscription = stripe.Subscription.retrieve(subscription_id).to_dict()
    if subscription.get('status') not in REDEEMABLE_STATUSES or subscription.get('cancel_at_period_end'):
        raise RedemptionError(400, 'Start your plan first, then redeem your code.')
    if (subscription.get('metadata') or {}).get('uid') not in (None, uid):
        raise RedemptionError(400, 'Start your plan first, then redeem your code.')
    if subscription.get('discounts') or subscription.get('discount'):
        raise RedemptionError(409, 'A discount is already applied to your plan.')

    promo = _find_promotion_code(code)
    coupon = stripe.Coupon.retrieve(_coupon_id(promo), expand=['applies_to']).to_dict()
    _check_eligible(promo, coupon, subscription)

    attribution = stripe_utils.promotion_code_attribution(promo)
    if not redemptions_db.claim(
        promo['id'],
        uid=uid,
        subscription_id=subscription_id,
        coupon_id=coupon['id'],
        attribution=attribution,
    ):
        raise RedemptionError(409, 'This code has already been used.')

    previous_attempt = (promo.get('metadata') or {}).get('redemption_attempt', 0)
    if (
        isinstance(previous_attempt, bool)
        or not isinstance(previous_attempt, (int, str))
        or (isinstance(previous_attempt, int) and previous_attempt < 0)
        or (isinstance(previous_attempt, str) and (not previous_attempt.isdigit() or len(previous_attempt) > 9))
    ):
        previous_attempt = 0
    redemption_attempt = int(previous_attempt) + 1
    # A deliberate rollback reactivates the code; Stripe would replay an older
    # deactivation response if its key were reused. The persisted attempt makes
    # each logical attempt deterministic without becoming immortal after rollback.
    operation_id = hashlib.sha256(f"{promo['id']}:{redemption_attempt}".encode()).hexdigest()
    promotion_metadata = {
        **attribution,
        'redeemed_by_uid': uid,
        'redeemed_subscription_id': subscription_id,
        'redemption_attempt': str(redemption_attempt),
    }
    try:
        # Stripe merges these redemption keys into the original PromotionCode
        # metadata; repeating valid issuance values also guards that invariant.
        stripe.PromotionCode.modify(
            promo['id'],
            active=False,
            metadata=promotion_metadata,
            idempotency_key=f'omi-redeem-{operation_id}-promotion',
        )
    except Exception as e:
        committed = _committed_promotion_deactivation(promo['id'], uid, subscription_id, redemption_attempt)
        if committed is not True:
            logger.error(f"Promotion code deactivation failed: {sanitize(str(e))}")
            # Release only a verified still-active code. An inactive code with
            # another redemption marker, or an unreadable ambiguous result, must
            # retain the claim and must never be reactivated for somebody else.
            if committed is False:
                _undo_claim(promo['id'], redemption_attempt)
            if isinstance(e, stripe.StripeError):
                raise RedemptionError(400, 'Could not apply this code. Please try again.') from e
            raise
        logger.warning('Reconciled a committed promotion deactivation after an ambiguous Stripe response')

    try:
        subscription_metadata = stripe_utils.merge_promotion_attribution(
            subscription.get('metadata') or {}, attribution
        )
        subscription_metadata['redeemed_promotion_code_id'] = promo['id']
        updated = stripe.Subscription.modify(
            subscription_id,
            discounts=[{'coupon': coupon['id']}],
            metadata=subscription_metadata,
            idempotency_key=f'omi-redeem-{operation_id}-subscription',
        ).to_dict()
    except Exception as e:
        try:
            updated = _committed_redemption(subscription_id, promo['id'])
        except Exception as reconciliation_error:
            logger.error(f'Promotion redemption reconciliation unavailable: {sanitize(str(reconciliation_error))}')
            raise RedemptionError(400, 'Could not apply this code. Please try again.') from e
        if updated is None:
            logger.error(f"Promotion code redemption failed for {uid}: {sanitize(str(e))}")
            # The deactivation commit is not uncertain at this point. Reactivating
            # after a Subscription pre-commit failure preserves the legacy rollback.
            _undo_claim(promo['id'], redemption_attempt)
            if isinstance(e, stripe.StripeError):
                raise RedemptionError(400, 'Could not apply this code. Please try again.') from e
            raise
        logger.warning('Reconciled a committed promotion redemption after an ambiguous Stripe response')

    logger.info(f"Redeemed promotion code {promo['id']} onto {subscription_id} for {uid}")
    if updated.get('status') == 'trialing':
        applies_at = updated.get('trial_end')
    else:
        applies_at = updated.get('current_period_end') or updated['items']['data'][0].get('current_period_end')
    return {
        'status': 'applied',
        'percent_off': coupon.get('percent_off'),
        'amount_off': coupon.get('amount_off'),
        'currency': coupon.get('currency'),
        'applies_at': applies_at,
    }


def _committed_promotion_deactivation(
    promotion_code_id: str, uid: str, subscription_id: str, redemption_attempt: int
) -> Optional[bool]:
    """True only for my committed deactivation; False only for a verified active code."""
    try:
        promo = stripe.PromotionCode.retrieve(promotion_code_id).to_dict()
    except Exception:
        return None
    if promo.get('active') is True:
        return False
    metadata = promo.get('metadata') or {}
    committed = (
        promo.get('active') is False
        and metadata.get('redeemed_by_uid') == uid
        and metadata.get('redeemed_subscription_id') == subscription_id
        and metadata.get('redemption_attempt') == str(redemption_attempt)
    )
    return True if committed else None


def _committed_redemption(subscription_id: str, promotion_code_id: str) -> Optional[dict]:
    """Recognize a timeout-after-commit without releasing an already consumed code."""
    subscription = stripe.Subscription.retrieve(subscription_id).to_dict()
    if (subscription.get('metadata') or {}).get('redeemed_promotion_code_id') != promotion_code_id:
        return None
    return subscription


def _undo_claim(promotion_code_id: str, redemption_attempt: int) -> None:
    try:
        stripe.PromotionCode.modify(
            promotion_code_id, active=True, metadata={'redemption_attempt': str(redemption_attempt)}
        )
    except Exception as e:
        logger.error(f"Could not reactivate promotion code {promotion_code_id}: {sanitize(str(e))}")
        return
    redemptions_db.release(promotion_code_id)
