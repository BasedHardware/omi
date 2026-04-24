"""
Phone call quota resolution + gate.

Paid-plan users always pass. Free-plan users are metered against
``phone_call_config``'s ``free_plan`` block and their monthly usage counter
in ``phone_call_usage``.

Setting ``free_plan.monthly_call_limit`` to 0 makes the feature paid-only
again (same behavior as before this module existed); the quota snapshot
returned to the client in that case reports ``has_access = False``.
"""

from typing import FrozenSet, Optional

from fastapi import HTTPException

import database.phone_call_usage as phone_call_usage_db
import database.users as users_db
from database.phone_call_config import get_config_for_plan
from utils.subscription import is_paid_plan

# Minimal E.164 prefix → ISO-2 mapping. Intentionally covers the cheap/common
# destinations; anything not on the list falls through to an empty match and
# is treated as "unknown country" — the allowlist check then rejects it
# (fail-safe against toll-fraud on high-cost international routes).
#
# A prefix maps to one-or-more ISO codes because the NANP pool (+1) is shared
# by US and Canada (plus other territories we intentionally don't allowlist).
# Without a proper libphonenumber parse we can't distinguish US from CA by
# area code here, so the allowlist check treats +1 as matching if *either*
# code is allowed. Ops who want to separate US and CA should run the check
# outside this module.
_E164_PREFIX_TO_ISO2: list[tuple[str, FrozenSet[str]]] = [
    ('+1', frozenset({'US', 'CA'})),  # NANP: US and CA share +1
    ('+44', frozenset({'GB'})),
    ('+61', frozenset({'AU'})),
    ('+64', frozenset({'NZ'})),
    ('+33', frozenset({'FR'})),
    ('+49', frozenset({'DE'})),
    ('+34', frozenset({'ES'})),
    ('+39', frozenset({'IT'})),
    ('+31', frozenset({'NL'})),
    ('+46', frozenset({'SE'})),
    ('+47', frozenset({'NO'})),
    ('+45', frozenset({'DK'})),
    ('+358', frozenset({'FI'})),
    ('+353', frozenset({'IE'})),
    ('+41', frozenset({'CH'})),
    ('+43', frozenset({'AT'})),
    ('+32', frozenset({'BE'})),
    ('+351', frozenset({'PT'})),
    ('+81', frozenset({'JP'})),
    ('+82', frozenset({'KR'})),
]


def countries_from_e164(number: str) -> FrozenSet[str]:
    """Best-effort ISO-2 lookup from an E.164 number.

    Returns the set of ISO-2 codes that share the matched dial prefix. The
    number passes an allowlist check if any element of that set is allowed.
    Empty set means "unknown" — fail-safe, always blocked when an allowlist
    is configured.
    """
    if not number or not number.startswith('+'):
        return frozenset()
    for prefix, iso_codes in _E164_PREFIX_TO_ISO2:
        if number.startswith(prefix):
            return iso_codes
    return frozenset()


def country_from_e164(number: str) -> Optional[str]:
    """Back-compat: return a representative ISO-2 for ``number`` if known.

    Prefer ``countries_from_e164`` when checking allowlists — it returns the
    full set so shared dial prefixes (notably +1 for US + CA) don't silently
    pick one country over another.
    """
    matches = countries_from_e164(number)
    if not matches:
        return None
    return next(iter(matches))


class QuotaSnapshot:
    __slots__ = (
        'plan',
        'is_paid',
        'monthly_limit',
        'monthly_used',
        'max_duration_seconds',
        'allowed_countries',
        'reset_at',
    )

    def __init__(
        self,
        plan,
        is_paid: bool,
        monthly_limit: Optional[int],
        monthly_used: int,
        max_duration_seconds: Optional[int],
        allowed_countries: list,
        reset_at: int,
    ):
        self.plan = plan
        self.is_paid = is_paid
        self.monthly_limit = monthly_limit
        self.monthly_used = monthly_used
        self.max_duration_seconds = max_duration_seconds
        self.allowed_countries = allowed_countries or []
        self.reset_at = reset_at

    @property
    def has_access(self) -> bool:
        """True iff the user can currently place a call under this plan."""
        if self.is_paid:
            return True
        if self.monthly_limit is None:
            return True
        if self.monthly_limit <= 0:
            return False
        return self.monthly_used < self.monthly_limit

    @property
    def remaining(self) -> Optional[int]:
        if self.is_paid or self.monthly_limit is None:
            return None
        return max(0, self.monthly_limit - self.monthly_used)

    def to_client_dict(self) -> dict:
        return {
            'has_access': self.has_access,
            'is_paid': self.is_paid,
            'monthly_limit': self.monthly_limit,
            'monthly_used': self.monthly_used,
            'remaining': self.remaining,
            'max_duration_seconds': self.max_duration_seconds,
            'allowed_countries': self.allowed_countries,
            'reset_at': self.reset_at,
        }


def get_quota_snapshot(uid: str) -> QuotaSnapshot:
    """Resolve the user's plan + config + current usage into a snapshot."""
    subscription = users_db.get_user_valid_subscription(uid)
    plan = subscription.plan if subscription else None
    paid = bool(subscription and is_paid_plan(subscription.plan))
    config = get_config_for_plan(paid)
    used, reset_at = phone_call_usage_db.get_current_month_count(uid)
    return QuotaSnapshot(
        plan=plan,
        is_paid=paid,
        monthly_limit=config.get('monthly_call_limit'),
        monthly_used=used,
        max_duration_seconds=config.get('max_duration_seconds'),
        allowed_countries=config.get('allowed_countries') or [],
        reset_at=reset_at,
    )


def check_call_access(uid: str) -> QuotaSnapshot:
    """Raise 402/403 if the user cannot access the phone call feature.

    Returns the snapshot so callers can reuse it (e.g. for max-duration
    enforcement on the TwiML response).
    """
    snapshot = get_quota_snapshot(uid)
    if snapshot.has_access:
        return snapshot

    if not snapshot.is_paid and (snapshot.monthly_limit or 0) <= 0:
        # Feature disabled for the free tier.
        raise HTTPException(status_code=403, detail="Phone calls require a paid subscription")
    # Free tier enabled but quota exhausted.
    raise HTTPException(
        status_code=402,
        detail={
            'error': 'phone_call_quota_exceeded',
            'monthly_limit': snapshot.monthly_limit,
            'monthly_used': snapshot.monthly_used,
            'reset_at': snapshot.reset_at,
        },
    )


def check_destination_allowed(snapshot: QuotaSnapshot, to_number: str) -> None:
    """Reject destinations outside the allowlist. No-op if allowlist is empty
    or the caller is on a paid plan."""
    if snapshot.is_paid:
        return
    allowed = snapshot.allowed_countries
    if not allowed:
        return
    allowed_set = {c.upper() for c in allowed}
    matches = countries_from_e164(to_number)
    if not matches or matches.isdisjoint(allowed_set):
        raise HTTPException(
            status_code=403,
            detail="This destination is not available on the free plan",
        )
