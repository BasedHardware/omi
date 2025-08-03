from datetime import datetime

import database.users as users_db
import database.user_usage as user_usage_db
from models.users import PlanType, SubscriptionStatus

BASIC_TIER_MINUTES_LIMIT_PER_MONTH = 1200
BASIC_TIER_MONTHLY_SECONDS_LIMIT = BASIC_TIER_MINUTES_LIMIT_PER_MONTH * 60


def is_allowed_to_transcribe(uid: str) -> bool:
    """Checks if a user has transcribing credits."""
    subscription = users_db.get_user_subscription(uid)

    if subscription.status != SubscriptionStatus.active:
        return False

    # For unlimited plans, the limit will be None
    if subscription.limits.transcription_seconds is None:
        return True

    # For plans with a limit, check usage
    usage = user_usage_db.get_monthly_usage_stats(uid, datetime.utcnow())
    transcription_seconds_used = usage.get('transcription_seconds', 0)
    return transcription_seconds_used < subscription.limits.transcription_seconds
