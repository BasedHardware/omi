from datetime import datetime

import database.users as users_db
import database.user_usage as user_usage_db
from models.users import PlanType, SubscriptionStatus

FREE_TIER_MINUTES_LIMIT_PER_MONTH = 1200
FREE_TIER_MONTHLY_SECONDS_LIMIT = FREE_TIER_MINUTES_LIMIT_PER_MONTH * 60


def is_allowed_to_transcribe(uid: str) -> bool:
    """Checks if a user has transcribing credits."""
    subscription = users_db.get_user_subscription(uid)

    if subscription.plan == PlanType.unlimited and subscription.status == SubscriptionStatus.active:
        return True

    if subscription.plan == PlanType.free:
        usage = user_usage_db.get_monthly_usage_stats(uid, datetime.utcnow())
        transcription_seconds = usage.get('transcription_seconds', 0)
        return transcription_seconds < FREE_TIER_MONTHLY_SECONDS_LIMIT

    return False
