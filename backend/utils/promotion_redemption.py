"""Redeem a promotion code onto the caller's existing subscription.

Stripe checks a promotion code's minimum amount against what is due today, which is
zero during a free trial, so a code with a minimum can never be entered at a trial
checkout. Stripe also refuses such codes on subscription updates. Omi checks the
code's restrictions against the plan price itself and attaches the code's coupon to
the subscription, so the discount lands on the first invoice after the trial.
"""

import logging
import time
from typing import Optional

import stripe

from database import promotion_redemptions as redemptions_db
from database import users as users_db
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
    promos = stripe.PromotionCode.list(code=code, active=True, limit=1).data
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

    if not redemptions_db.claim(promo['id'], uid=uid, subscription_id=subscription_id, coupon_id=coupon['id']):
        raise RedemptionError(409, 'This code has already been used.')

    try:
        stripe.PromotionCode.modify(
            promo['id'],
            active=False,
            metadata={'redeemed_by_uid': uid, 'redeemed_subscription_id': subscription_id},
        )
        updated = stripe.Subscription.modify(
            subscription_id,
            discounts=[{'coupon': coupon['id']}],
            metadata={'redeemed_promotion_code_id': promo['id']},
        ).to_dict()
    except Exception as e:
        logger.error(f"Promotion code redemption failed for {uid}: {sanitize(str(e))}")
        _undo_claim(promo['id'])
        if isinstance(e, stripe.StripeError):
            raise RedemptionError(400, 'Could not apply this code. Please try again.') from e
        raise

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


def _undo_claim(promotion_code_id: str) -> None:
    try:
        stripe.PromotionCode.modify(promotion_code_id, active=True)
    except Exception as e:
        logger.error(f"Could not reactivate promotion code {promotion_code_id}: {sanitize(str(e))}")
        return
    redemptions_db.release(promotion_code_id)
