import os
from datetime import datetime
from typing import List

import database.users as users_db
import database.user_usage as user_usage_db
from models.users import PlanType, SubscriptionStatus, Subscription, PlanLimits

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
            "Unlimited insights gained",
            "Unlimited memories created",
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
            f"{BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH:,} insights gained per month"
            if BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH > 0
            else "Unlimited insights gained"
        ),
        (
            f"{BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH} memories created per month"
            if BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH > 0
            else "Unlimited memories created"
        ),
    ]


def has_transcription_credits(uid: str) -> bool:
    """Checks if a user has transcribing credits."""
    subscription = users_db.get_user_subscription(uid)

    if subscription.status != SubscriptionStatus.active:
        return False

    limits = get_plan_limits(subscription.plan)

    # For unlimited plans, the limit will be None
    if limits.transcription_seconds is None:
        return True

    # For plans with a limit, check usage
    usage = user_usage_db.get_monthly_usage_stats(uid, datetime.utcnow())
    transcription_seconds_used = usage.get('transcription_seconds', 0)
    return transcription_seconds_used < limits.transcription_seconds
