"""Never bill one user through both Stripe and Google Play.

A Stripe subscription that appears for a user Google Play already bills is cancelled at once, its
first charge refunded, both ids logged, and the user told. Called from the Stripe webhook.
"""

from __future__ import annotations

import logging
import time
from typing import Mapping, Optional

import database.play_subscriptions as play_subscriptions_db
from config import prepaid_code_redeem as prepaid_config
from models.users import Subscription
from utils import stripe as stripe_utils
from utils.executors import db_executor, run_blocking, stripe_executor
from utils.notification_dispatch import NotificationIntent, NotificationKind, dispatch_notification_async
from utils.subscription import is_paid_plan

logger = logging.getLogger(__name__)

PLAY_MANAGED_DETAIL = (
    'Your Omi Pro subscription is billed through Google Play. '
    'Manage or cancel it in Google Play: https://play.google.com/store/account/subscriptions'
)


def live_play_row(subscription: Subscription | None) -> bool:
    return bool(
        subscription is not None
        and subscription.provider == 'play'
        and is_paid_plan(subscription.plan)
        and bool(subscription.current_period_end)
        and subscription.current_period_end >= int(time.time())
    )


async def refuse_stripe_for_play_subscriber(
    uid: str, stripe_subscription_id: str, subscription: Optional[Mapping] = None
) -> None:
    """A Stripe subscription appeared for a user Google Play already bills: undo it, never keep both.

    A prepaid code's subscription charges nothing, so there is no double charge to stop: it is kept (cancelling
    it would destroy the included term and not return the code) and logged for a person to refund Google.
    """
    if subscription is not None and prepaid_config.is_prepaid_subscription(subscription):
        pointer = await run_blocking(db_executor, play_subscriptions_db.get_user_pointer, uid)
        code = (subscription.get('metadata') or {}).get('redeemed_promotion_code_id')
        logger.error(prepaid_config.PLAY_OVERLAP_LOG, uid, (pointer or '')[:12], code)
        return
    result = await run_blocking(
        stripe_executor, stripe_utils.cancel_and_refund_checkout_subscription, stripe_subscription_id
    )
    pointer = await run_blocking(db_executor, play_subscriptions_db.get_user_pointer, uid)
    logger.error(
        'play_billing double billing refused: uid=%s stripe_subscription=%s refund=%s play_token=%s',
        uid,
        stripe_subscription_id,
        result.get('refund_id'),
        (pointer or '')[:12],
    )
    body = 'Your Omi Pro is billed through Google Play, so we canceled the new card subscription' + (
        ' and refunded it.' if result.get('refund_id') else '. You were not charged.'
    )
    try:
        await dispatch_notification_async(
            NotificationIntent(
                user_id=uid,
                title='You already have Omi Pro',
                body=body,
                source='play_billing_double_billing',
                kind=NotificationKind.BILLING_CONFLICT,
            )
        )
    except Exception:
        logger.warning('play_billing double billing notice not sent for uid=%s', uid)
