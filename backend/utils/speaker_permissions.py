"""Plan entitlements for speaker labeling, kept light for routes and services."""

from config.plan_catalog import PAID_PLAN_TYPES
from database import users as users_db


def named_speaker_prompts_allowed(uid: str) -> bool:
    """Naming other people follows the named speaker-ID entitlement (paid plans).

    "Is this you?" never calls this: the owner check is free for everyone.
    """
    plan = users_db.get_user_valid_subscription(uid, provision=False)
    # The plan set comes from the catalog, not utils.subscription: that module pulls the
    # billing SDK into every importer, and live and sync matching import this one.
    return bool(plan and plan.plan in PAID_PLAN_TYPES)
