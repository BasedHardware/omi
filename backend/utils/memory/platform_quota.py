"""Plan entitlement + metering for the Memory Platform API.

The cap is expressed as a ``PlanLimits`` field like every other plan cap, read
through ``get_plan_limits``, and metered with a Redis monthly counter. Two rules
shape the contract:

- ``None`` means uncapped. Every paid plan is uncapped, so shipping this gate
  cannot regress a paying subscriber.
- The Free tier gets a real, usable allowance rather than zero, so an existing
  Free user keeps being served by an API that was previously ungated.

Over-quota is a bounded 429 naming the plan, the limit, and the reset instant —
never a 500 and never a silently truncated result.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException

import database.memory_platform_usage as platform_usage_db
import database.users as users_db
from models.users import PlanType
from utils.subscription import get_plan_display_name, get_plan_limits

logger = logging.getLogger(__name__)


def _user_plan(uid: str) -> PlanType:
    subscription = users_db.get_user_valid_subscription(uid)
    return subscription.plan if subscription else PlanType.basic


def get_platform_quota_snapshot(uid: str) -> Dict[str, Any]:
    """Return the plan, cap, usage, and remaining allowance for this month."""
    plan = _user_plan(uid)
    limit: Optional[int] = get_plan_limits(plan).platform_api_requests_per_month
    used, reset_at = platform_usage_db.get_current_month_usage(uid)
    remaining = None if limit is None else max(limit - used, 0)
    return {
        'plan': get_plan_display_name(plan),
        'plan_type': plan.value,
        'limit': limit,
        'used': used,
        'remaining': remaining,
        'allowed': limit is None or used < limit,
        'reset_at': reset_at,
    }


def enforce_platform_quota(uid: str) -> None:
    """Consume one request of the caller's monthly allowance, or raise 429."""
    plan = _user_plan(uid)
    limit: Optional[int] = get_plan_limits(plan).platform_api_requests_per_month
    if limit is None:
        return

    reserved, used, reset_at = platform_usage_db.reserve_current_month_request(uid, limit)
    if reserved:
        return

    raise HTTPException(
        status_code=429,
        detail={
            'error': 'platform_quota_exceeded',
            'plan': get_plan_display_name(plan),
            'plan_type': plan.value,
            'unit': 'requests',
            'used': used,
            'limit': limit,
            'reset_at': reset_at,
        },
    )


__all__ = ['enforce_platform_quota', 'get_platform_quota_snapshot']
