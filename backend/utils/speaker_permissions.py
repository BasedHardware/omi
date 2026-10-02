"""Plan entitlements for speaker labeling, kept light for routes and services."""

from database import users as users_db
from utils import subscription


def named_speaker_prompts_allowed(uid: str) -> bool:
    """Naming other people follows the named speaker-ID entitlement (paid plans).

    "Is this you?" never calls this: the owner check is free for everyone.
    """
    plan = users_db.get_user_valid_subscription(uid, provision=False)
    return bool(plan and subscription.is_paid_plan(plan.plan))
