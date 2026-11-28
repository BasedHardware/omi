"""Support transcription credit: balance arithmetic over stored grants.

A grant (``users/{uid}.support_transcription_credit.<action_id>``) is
``{seconds, granted_at, expires_at, baseline_seconds, allowance_seconds}``:
managed transcription seconds spent only after the plan's monthly allowance,
written by the support operator CLI (``utils/support/transcription_credit.py``)
and nowhere else. ``baseline_seconds`` is the month's ``transcription_seconds``
when the grant was made, so usage before the grant never consumes it;
``allowance_seconds`` is the plan allowance then, used for months whose plan
is no longer known.

Nothing is written at usage time. The balance is derived from the existing
monthly usage totals: in each UTC month a grant was live, usage over the
month's base (the plan allowance, or the grant baseline in the month a grant
started with no earlier grant carrying in) is allocated to live grants in
grant order. A month boundary therefore never re-grants spent seconds.

Usage is metered after admission, so concurrent admissions can overrun a
grant by one meter lag, the same property the plan cap has today.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from config.support_credit import FIELD, MAX_EXPIRES_DAYS, enabled


class CreditUnreadable(ValueError):
    """A stored grant is malformed; callers treat the lookup as transient."""


@dataclass(frozen=True)
class Grant:
    action_id: str
    seconds: int
    granted_at: int
    expires_at: int
    baseline_seconds: int
    allowance_seconds: int


def _int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CreditUnreadable(f'{name} must be an integer >= {minimum}')
    return value


def parse_grants(raw: Any) -> list[Grant]:
    """Validated grants in grant order. ``None`` or empty is no credit."""
    if raw is None:
        return []
    if not isinstance(raw, Mapping):
        raise CreditUnreadable('credit is not a map')
    grants = []
    for action_id, entry in raw.items():
        if not isinstance(action_id, str) or not action_id or not isinstance(entry, Mapping):
            raise CreditUnreadable('credit entry is malformed')
        grant = Grant(
            action_id=action_id,
            seconds=_int(entry.get('seconds'), 'seconds', minimum=1),
            granted_at=_int(entry.get('granted_at'), 'granted_at', minimum=1),
            expires_at=_int(entry.get('expires_at'), 'expires_at', minimum=1),
            baseline_seconds=_int(entry.get('baseline_seconds', 0), 'baseline_seconds'),
            allowance_seconds=_int(entry.get('allowance_seconds', 0), 'allowance_seconds'),
        )
        if grant.expires_at <= grant.granted_at or grant.expires_at - grant.granted_at > MAX_EXPIRES_DAYS * 86400:
            raise CreditUnreadable('credit window is invalid')
        grants.append(grant)
    return sorted(grants, key=lambda grant: (grant.granted_at, grant.action_id))


def month_of(timestamp: float) -> tuple[int, int]:
    moment = datetime.fromtimestamp(timestamp, timezone.utc)
    return moment.year, moment.month


def month_bounds(month: tuple[int, int]) -> tuple[int, int]:
    year, number = month
    start = datetime(year, number, 1, tzinfo=timezone.utc)
    end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp()), int(end.timestamp())


def _months(first: tuple[int, int], last: tuple[int, int]) -> list[tuple[int, int]]:
    months, current = [], first
    while current <= last:
        months.append(current)
        current = (current[0] + (current[1] == 12), current[1] % 12 + 1)
    return months


def remaining_by_grant(
    grants: list[Grant],
    *,
    now: float,
    current_used: int,
    current_allowance: int,
    month_used: Callable[[tuple[int, int]], int],
) -> dict[str, int]:
    """Unspent seconds per grant, including expired ones (whose balance is no longer usable).

    ``month_used`` returns a past month's ``transcription_seconds`` and raises
    when it cannot be read; it is called at most once per past month.
    """
    remaining = {grant.action_id: grant.seconds for grant in grants}
    if not grants:
        return remaining
    current = month_of(now)
    for month in _months(month_of(grants[0].granted_at), current):
        start, end = month_bounds(month)
        live = [grant for grant in grants if grant.granted_at < end and grant.expires_at > start]
        if not live or month > current:
            continue
        if month == current:
            used, allowance = current_used, current_allowance
        else:
            used, allowance = month_used(month), live[0].allowance_seconds
        if any(grant.granted_at < start for grant in live):
            base = allowance
        else:
            base = max(allowance, min(grant.baseline_seconds for grant in live))
        over = max(0, used - base)
        for grant in live:
            if over <= 0:
                break
            take = min(over, remaining[grant.action_id])
            remaining[grant.action_id] -= take
            over -= take
    return remaining


def usable_seconds(grants: list[Grant], remaining: Mapping[str, int], now: float) -> int:
    return sum(remaining[grant.action_id] for grant in grants if grant.granted_at <= now < grant.expires_at)


def retained(grants: list[Grant], now: float) -> list[Grant]:
    """Grants the balance still needs: every live grant and expired ones overlapping their months."""
    live = [grant for grant in grants if grant.expires_at > now]
    if not live:
        return []
    floor = month_bounds(month_of(min(grant.granted_at for grant in live)))[0]
    return [grant for grant in grants if grant.expires_at > now or grant.expires_at > floor]


def serialize(grant: Grant) -> dict[str, int]:
    return {
        'seconds': grant.seconds,
        'granted_at': grant.granted_at,
        'expires_at': grant.expires_at,
        'baseline_seconds': grant.baseline_seconds,
        'allowance_seconds': grant.allowance_seconds,
    }


# --- admission ------------------------------------------------------------------------------

REASON = 'support_credit'
# The caller did not read the credit; ``None`` is a real answer (no credit stored).
UNREAD: Any = object()
logger = logging.getLogger(__name__)


def read_credit(uid: str, *, firestore_client: Any = None) -> Any:
    """The raw credit map (``None`` when absent): one users-root point read."""
    from database._client import db

    snapshot = (firestore_client or db).collection('users').document(uid).get([FIELD])
    return (snapshot.to_dict() or {}).get(FIELD) if snapshot.exists else None


def past_month_used(uid: str, month: tuple[int, int]) -> int:
    """``transcription_seconds`` for an earlier UTC month, from the existing monthly totals."""
    import database.user_usage as user_usage_db

    year, number = month
    usage = user_usage_db.get_monthly_usage_stats(uid, datetime(year, number, 15, tzinfo=timezone.utc))
    value = usage.get('transcription_seconds', 0) if isinstance(usage, dict) else None
    value = 0 if value is None else value
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CreditUnreadable('past month usage is untrusted')
    return value


def after_plan(uid: str, raw: Any = UNREAD, *, used: int, allowance: int, now: float | None = None):
    """The managed answer a live credit funds once a finite plan is spent, or ``None`` (no usable credit).

    ``raw`` is the stored map when the caller already read it (the hold
    controller does). ``limit_seconds`` stays the plan's: batch capacity and
    usage displays are plan-only. A read failure is no credit, so a blip keeps
    today's parking answer for the whole exhausted cohort. A credit that exists
    but cannot be evaluated is transient (``allowance_unavailable``): the user
    was already on the local path, and the hold controller retries instead of
    acknowledging a generation.
    """
    from utils.transcription_allowance import TranscriptionAllowance

    if not enabled():
        return None
    if raw is UNREAD:
        try:
            raw = read_credit(uid)
        except Exception as exc:
            logger.warning('support credit read failed for uid=%s: %s', uid, type(exc).__name__)
            return None
    try:
        grants = parse_grants(raw)
        if not grants:
            return None
        at = time.time() if now is None else now
        left = remaining_by_grant(
            grants,
            now=at,
            current_used=used,
            current_allowance=allowance,
            month_used=lambda month: past_month_used(uid, month),
        )
        usable = usable_seconds(grants, left, at)
    except Exception as exc:
        logger.warning('support credit unavailable for uid=%s: %s', uid, type(exc).__name__)
        return TranscriptionAllowance('on_device', 0, 'allowance_unavailable', limit_seconds=allowance)
    if usable <= 0:
        return None
    return TranscriptionAllowance('managed', usable, REASON, limit_seconds=allowance)
