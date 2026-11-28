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
monthly usage totals. Within a UTC month, each grant's baseline is a known
point (usage at ``granted_at``), so usage above it happened after that grant
started. Usage over the plan allowance is split at those points, and each
segment is charged only to grants already granted and not yet expired when it
began, grants still usable now first. Where a grant expired inside a segment
the split is unknown, so the usable grant pays: the balance can understate a
credit, never overstate it. A month boundary never re-grants spent seconds.

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
    """A stored grant is malformed, or a usage total the balance needs is untrusted."""


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
    when it cannot be read; it is called at most once per past month. A past
    month's plan is unknown, so it uses the smallest allowance recorded by a
    grant live that month (more overage, never less).
    """
    remaining = {grant.action_id: grant.seconds for grant in grants}
    if not grants:
        return remaining
    current = month_of(now)
    for month in _months(month_of(grants[0].granted_at), current):
        start, end = month_bounds(month)
        live = [grant for grant in grants if grant.granted_at < end and grant.expires_at > start]
        if not live:
            continue
        if month == current:
            used, allowance = current_used, current_allowance
        else:
            used, allowance = month_used(month), min(grant.allowance_seconds for grant in live)
        _charge(live, remaining, used=used, allowance=allowance, month_start=start, now=now)
    return remaining


def _charge(
    live: list[Grant], remaining: dict[str, int], *, used: int, allowance: int, month_start: int, now: float
) -> None:
    # Known (usage level, time) points in the month, in time order: the month start for
    # grants carried in, each in-month grant's baseline at its grant time.
    points: list[tuple[int, int]] = []
    for grant in sorted(live, key=lambda item: (max(item.granted_at, month_start), item.action_id)):
        when = max(grant.granted_at, month_start)
        level = 0 if grant.granted_at < month_start else grant.baseline_seconds
        points.append((max(level, points[-1][0]) if points else level, when))
    for index, (level, when) in enumerate(points):
        low = max(allowance, level)
        high = points[index + 1][0] if index + 1 < len(points) else used
        over = max(0, min(high, used) - low)
        eligible = [grant for grant in live if grant.granted_at <= when < grant.expires_at]
        eligible.sort(key=lambda grant: (not grant.granted_at <= now < grant.expires_at, grant.granted_at))
        for grant in eligible:
            if over <= 0:
                break
            take = min(over, remaining[grant.action_id])
            remaining[grant.action_id] -= take
            over -= take


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
    value = usage_seconds(usage)
    if value is None:
        raise CreditUnreadable('past month usage is untrusted')
    return value


def usage_seconds(usage: Any) -> int | None:
    """``transcription_seconds`` of a monthly usage record, or ``None`` when it is not trustworthy."""
    if not isinstance(usage, Mapping):
        return None
    value = usage.get('transcription_seconds', 0)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def after_plan(uid: str, raw: Any = UNREAD, *, used: int, allowance: int, now: float | None = None):
    """The managed answer a live credit funds once a finite plan is spent, or ``None`` (no usable credit).

    ``raw`` is the stored map when the caller already read it (the hold
    controller does). ``limit_seconds`` stays the plan's: batch capacity and
    usage displays are plan-only. A read failure is no credit, so a blip keeps
    today's parking answer for the whole exhausted cohort, and so does a
    malformed map (logged as an error). A well-formed credit whose usage cannot
    be read is transient (``allowance_unavailable``): the user was already on
    the local path, and the hold controller retries instead of acknowledging a
    generation.
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
        parsed = parse_grants(raw)
    except CreditUnreadable as exc:
        # A data defect, not a blip: no credit, so today's answer stands and the hold
        # controller acknowledges it; repairing the map changes the generation.
        logger.error('support credit malformed for uid=%s: %s', uid, exc)
        return None
    at = time.time() if now is None else now
    grants = retained(parsed, at)
    if not grants:
        return None
    try:
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
