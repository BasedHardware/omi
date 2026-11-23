"""Never bill one user through both Stripe and Google Play.

A Stripe subscription that appears for a user Google Play already bills is cancelled at once, its
first charge refunded, both ids logged, and the user told. Called from the Stripe webhook.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import database.play_subscriptions as play_subscriptions_db
from config.plan_catalog import _paid_period_still_open
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
        and _paid_period_still_open(subscription.current_period_end, datetime.now(timezone.utc))
    )


async def refuse_stripe_for_play_subscriber(uid: str, stripe_subscription_id: str) -> dict:
    """A Stripe subscription appeared for a user Google Play already bills: undo it, never keep both."""
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
    return {"status": "success", "message": "Checkout refused: Google Play already bills this user."}
