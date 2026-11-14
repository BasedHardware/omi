"""A declined yearly renewal moves to the same plan's monthly price (see utils.monthly_switch).

The offer rides GET /v1/users/me/subscription as ``payment_issue.monthly_switch``.
"""

import logging
import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import database.users as users_db
from config.stt_cap_dispatch import any_execution_admission_enabled as funded_processing_enabled
from database import action_items as action_items_db, conversations as conversations_db, memories as memories_db
from database import redis_db
from database.fsr_read_cache import fresh_reader
from routers.payment import PaymentStatusMessageResponse
from utils import monthly_switch
from utils.fair_use import clear_fair_use_on_upgrade
from utils.other import endpoints as auth
from utils.subscription import get_plan_limits, get_plan_type_from_price_id, is_paid_plan
from utils.subscription_state_machine import project_subscription

logger = logging.getLogger(__name__)
router = APIRouter()

UNAVAILABLE = "Switching to monthly is not available for this subscription."
# Outlives Stripe's request timeout, so a slow charge still holds the lock.
LOCK_TTL_SECONDS = 120


class MonthlySwitchRequest(BaseModel):
    price_id: str = Field(..., min_length=1, max_length=255)
    # The monthly amount the reader saw (payment_issue.monthly_switch.amount, minor units).
    expected_amount: int = Field(..., ge=1)


def _lock_key(uid: str) -> str:
    return f'users:{uid}:monthly_switch_lock'


def try_acquire_lock(uid: str, token: str) -> bool:
    """One switch per user at a time: two taps never charge twice. Redis errors propagate (no lock, no charge)."""
    return redis_db.r.set(_lock_key(uid), token, ex=LOCK_TTL_SECONDS, nx=True) is not None


def release_lock(uid: str, token: str) -> None:
    try:
        redis_db.release_token_lock(_lock_key(uid), token)
    except Exception:
        pass  # The TTL releases it; never delete a successor's lock.


def _store(uid: str, price_id: str, previous, updated: dict) -> None:
    """Store the switched plan now and restore paid access, as the upgrade path does; the webhook converges later."""
    # switch() returns only an active subscription on the plan's monthly price.
    plan = get_plan_type_from_price_id(updated['items']['data'][0]['price']['id'])
    new_subscription = project_subscription(updated, plan, get_plan_limits(plan))
    if not new_subscription:
        return
    users_db.update_user_subscription(uid, new_subscription.model_dump())
    redis_db.set_credits_invalidation_signal(uid)
    if is_paid_plan(new_subscription.plan):
        conversations_db.unlock_all_conversations(uid)
        memories_db.unlock_all_memories(uid)
        action_items_db.unlock_all_action_items(uid)
        clear_fair_use_on_upgrade(uid)
        if funded_processing_enabled(uid):
            from utils.processing_backlog_worker import plan_changed

            plan_changed(uid, price_id, previous, new_subscription, updated.get('status'))


@router.post('/v1/payments/payment-issue/monthly-switch', response_model=PaymentStatusMessageResponse)
@fresh_reader
def payment_issue_monthly_switch_endpoint(request: MonthlySwitchRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Move a declined yearly renewal to the same plan's monthly price (utils/monthly_switch.py).

    Charges the monthly price now, then voids the unpaid yearly invoice. 402: declined, nothing
    changed. 409: not offered for this subscription, or a switch is already running. 503: billing
    unreachable; a repeat replays the finished switch or refuses, it never charges twice.
    """
    stored = users_db.get_user_subscription(uid)
    subscription_id = stored.stripe_subscription_id if stored else None
    if not subscription_id or not subscription_id.startswith('sub_'):
        raise HTTPException(status_code=409, detail=UNAVAILABLE)
    token = uuid.uuid4().hex
    try:
        acquired = try_acquire_lock(uid, token)
    except Exception as error:
        logger.error('Monthly switch lock unavailable (%s)', type(error).__name__)
        raise HTTPException(status_code=503, detail="Billing is unavailable. Please try again.")
    if not acquired:
        raise HTTPException(status_code=409, detail="A plan change is already in progress.")
    try:
        updated = monthly_switch.switch(uid, subscription_id, request.price_id, request.expected_amount, token)
        _store(uid, request.price_id, stored, updated)
    except monthly_switch.Refused as refused:
        logger.info(f"Monthly switch refused for user {uid}: {refused.reason}")
        raise HTTPException(status_code=409, detail=UNAVAILABLE)
    except stripe.CardError as e:
        logger.warning(f"Stripe declined the monthly switch for user {uid}: {type(e).__name__}")
        # Stripe's user_message is written for end users; nothing else from the error reaches the response.
        raise HTTPException(
            status_code=402, detail=e.user_message or "Your card was declined. Your plan did not change."
        )
    except (monthly_switch.Incomplete, stripe.StripeError) as error:
        logger.error(f"Monthly switch unconfirmed for user {uid}: {type(error).__name__}")
        raise HTTPException(status_code=503, detail="We couldn't confirm the change. Please try again.")
    finally:
        release_lock(uid, token)
    logger.info(f"Declined yearly renewal moved to monthly for user {uid}")
    return {"status": "switched", "message": "You're on monthly now."}
