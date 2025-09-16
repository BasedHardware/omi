import os
from datetime import datetime
from typing import List
import os
import stripe

import database.users as users_db
import database.user_usage as user_usage_db
from models.users import PlanType, SubscriptionStatus, Subscription, PlanLimits


def get_plan_type_from_price_id(price_id: str) -> PlanType:
    """Determines the plan type based on the Stripe price ID."""
    unlimited_monthly_price = os.getenv('STRIPE_UNLIMITED_MONTHLY_PRICE_ID')
    unlimited_annual_price = os.getenv('STRIPE_UNLIMITED_ANNUAL_PRICE_ID')

    if price_id in (unlimited_monthly_price, unlimited_annual_price):
        return PlanType.unlimited
    raise ValueError(f"Price ID {price_id} does not correspond to a known plan.")


BASIC_TIER_MINUTES_LIMIT_PER_MONTH = int(os.getenv('BASIC_TIER_MINUTES_LIMIT_PER_MONTH', '0'))
BASIC_TIER_MONTHLY_SECONDS_LIMIT = BASIC_TIER_MINUTES_LIMIT_PER_MONTH * 60
BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH = int(os.getenv('BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH', '0'))
BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH = int(os.getenv('BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH', '0'))
BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH = int(os.getenv('BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH', '0'))


def get_basic_plan_limits() -> PlanLimits:
    """Returns the PlanLimits object for the basic tier."""
    return PlanLimits(
        transcription_seconds=BASIC_TIER_MONTHLY_SECONDS_LIMIT,
        words_transcribed=BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH,
        insights_gained=BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH,
        memories_created=BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH,
    )


def get_default_basic_subscription() -> Subscription:
    """Returns a default Subscription object for the basic plan."""
    return Subscription(limits=get_basic_plan_limits())


def get_plan_limits(plan: PlanType) -> PlanLimits:
    """Returns the PlanLimits object for the given plan."""
    if plan == PlanType.unlimited:
        return PlanLimits(
            transcription_seconds=None,
            words_transcribed=None,
            insights_gained=None,
            memories_created=None,
        )
    return get_basic_plan_limits()


def get_plan_features(plan: PlanType) -> List[str]:
    """Returns the list of feature strings for the given plan."""
    if plan == PlanType.unlimited:
        return [
            "Unlimited listening time",
            "Unlimited words transcribed",
            "Unlimited insights",
            "Unlimited memories",
        ]

    # Basic plan
    return [
        (
            f"{BASIC_TIER_MINUTES_LIMIT_PER_MONTH} minutes of listening per month"
            if BASIC_TIER_MINUTES_LIMIT_PER_MONTH > 0
            else "Unlimited listening time"
        ),
        (
            f"{BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH:,} words transcribed per month"
            if BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH > 0
            else "Unlimited words transcribed"
        ),
        (
            f"{BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH:,} insights per month"
            if BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH > 0
            else "Unlimited insights"
        ),
        (
            f"{BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH} memories per month"
            if BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH > 0
            else "Unlimited memories"
        ),
    ]


def can_user_make_payment(uid: str, target_price_id: str = None) -> tuple[bool, str]:
    """
    Checks if a user can make a new payment based on their current subscription status.
    
    Args:
        uid: User ID
        target_price_id: Optional target price ID to check if this is an upgrade/downgrade
    
    Returns:
        tuple: (can_pay: bool, reason: str)
    """
    subscription = users_db.get_user_valid_subscription(uid)
    
    # If no subscription or basic plan, user can pay
    if not subscription or subscription.plan == PlanType.basic:
        return True, "User can make payment"
    
    # If unlimited plan but inactive, user can pay
    if subscription.plan == PlanType.unlimited and subscription.status == SubscriptionStatus.inactive:
        return True, "User can make payment"
    
    # If unlimited plan and active, check if this is a plan change
    if subscription.plan == PlanType.unlimited and subscription.status == SubscriptionStatus.active:
        if subscription.current_period_end:
            from datetime import datetime, timezone
            period_end_dt = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
            
            # If subscription has expired, user can pay
            if period_end_dt <= datetime.now(timezone.utc):
                return True, "User's subscription has expired, can make new payment"
            
            # If target price is provided, check if it's different from current plan
            if target_price_id:
                current_price_id = None
                # Try to get current price ID from Stripe subscription
                if subscription.stripe_subscription_id:
                    try:
                        stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
                        if stripe_sub:
                            stripe_sub_dict = stripe_sub.to_dict()
                            if stripe_sub_dict['items']['data']:
                                current_price_id = stripe_sub_dict['items']['data'][0]['price']['id']
                    except Exception as e:
                        print(f"Error retrieving current price ID: {e}")
                
                # If different price, allow upgrade/downgrade
                if current_price_id and current_price_id != target_price_id:
                    return True, "User can upgrade/downgrade to different plan"
                elif not current_price_id:
                    return True, "User can make payment (current price unknown)"
            
            # Same plan, active subscription
            return False, "User already has an active subscription for this plan"
    
    return True, "User can make payment"

  
def get_monthly_usage_for_subscription(uid: str) -> dict:
    """
    Gets the current monthly usage for subscription purposes, considering the launch date from env variables.
    The launch date format is expected to be YYYY-MM-DD.
    If the launch date is not set, not valid, or in the future, usage is considered zero.
    """
    subscription_launch_date_str = os.getenv('SUBSCRIPTION_LAUNCH_DATE')
    if not subscription_launch_date_str:
        # Subscription not launched, so no usage is counted against limits.
        return {}

    try:
        # Use strptime to enforce YYYY-MM-DD format
        launch_date = datetime.strptime(subscription_launch_date_str, '%Y-%m-%d')
    except ValueError:
        # Invalid date format, treat as not launched.
        return {}

    now = datetime.utcnow()
    if now < launch_date:
        # Launch date is in the future, so no usage is counted yet.
        return {}

    return user_usage_db.get_monthly_usage_stats_since(uid, now, launch_date)


def has_transcription_credits(uid: str) -> bool:
    """
    Checks if a user has transcribing credits by verifying their valid subscription and usage.
    """
    subscription = users_db.get_user_valid_subscription(uid)
    if not subscription:
        return False

    usage = get_monthly_usage_for_subscription(uid)
    limits = get_plan_limits(subscription.plan)

    # Check transcription seconds (0 means unlimited)
    if limits.transcription_seconds and limits.transcription_seconds > 0:
        if usage.get('transcription_seconds', 0) >= limits.transcription_seconds:
            return False

    return True
