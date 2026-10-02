"""Plan entitlements for speaker labeling, kept light for routes and services."""

from database import users as users_db
from utils.subscription import is_paid_plan


def named_speaker_prompts_allowed(uid: str) -> bool:
    """Naming other people follows the named speaker-ID entitlement (paid plans).

    "Is this you?" never calls this: the owner check is free for everyone.
    """
    subscription = users_db.get_user_valid_subscription(uid, provision=False)
    return bool(subscription and is_paid_plan(subscription.plan))
