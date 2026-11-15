"""Default-off per-user-day backfill/import transcribed-hours cap for ``unlimited_v2``.

The cap counts exactly what the finops meter attributes to a user-day: the
``transcription_seconds`` recorded on ``users/{uid}/hourly_usage`` documents for
the current UTC day (the same basis ``stt_usage_daily.csv`` and
``unit_cost_user_day.tx_sec`` use). Nothing here estimates: an unreadable meter
admits transcription instead of inventing a refusal.

The cap is deliberately narrower than the meter. It only refuses admissions the
caller marks as **backfill/import** work (the sync ``backfill`` lane and the
batch ``backfill`` lane). Live listen and fresh sync/batch capture never pass
that marker, so live capture is untouched even on a user-day already above the
cap. The meter itself cannot separate backfill seconds from live seconds; the
admission lane is the separation, and it is exact for the work being admitted.

Two runtime settings, both read at the admission boundary:

* ``UNLIMITED_V2_BACKFILL_HOURS_CAP_ENABLED`` (bool, default ``false``) — the
  kill switch. ``false`` bypasses every read below and restores current behavior.
* ``UNLIMITED_V2_BACKFILL_HOURS_CAP_HOURS`` (hours, default ``24``) — the daily
  cap level. A blank, unparseable or non-positive value keeps the default level;
  the boolean above is the only on/off authority.

Only the current ``unlimited_v2`` plan is in scope. Every other plan — Free,
Plus, and the deprecated paid tiers — resolves unchanged in both modes; those
plans already have a finite allowance that bounds a backfill day.
"""

import logging
import os
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple

from prometheus_client import Counter

from config.plan_catalog_generated import PlanType
from utils.transcription_allowance import TranscriptionAllowance

# The plan and hourly-usage reads below are imported at their call boundary,
# not at module scope: `utils.stt_cap_dispatch` is imported by every streaming
# provider module (including the GPU images), and this default-off cap must not
# widen that import graph with Firestore/user-database modules while it is off.

logger = logging.getLogger(__name__)

ENABLED_ENV = 'UNLIMITED_V2_BACKFILL_HOURS_CAP_ENABLED'
HOURS_ENV = 'UNLIMITED_V2_BACKFILL_HOURS_CAP_HOURS'
DEFAULT_CAP_HOURS = 24.0
REASON = 'unlimited_v2_backfill_day_tx_hours_cap'

CAP_PLAN = PlanType.unlimited_v2
# Only offline backfill/import admission is in scope; live listen is never capped.
BACKFILL_PLANES = frozenset({'sync', 'batch'})
# Managed allowances that never spend Omi-funded STT are exempt from the cap.
_EXEMPT_REASONS = frozenset({'marketplace_reviewer', 'release_probe', 'byok'})

_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})

# The admission refresh cadence is per-minute per live session and per piece for
# offline work; a short TTL keeps the authoritative day read from turning into a
# Firestore hotspot without letting a capped user run far past the cap. The cache
# holds only one in-flight value per user per day.
_READ_TTL_SECONDS = 30.0
_READ_CACHE: Dict[str, Tuple[date, float, int]] = {}
_READ_CACHE_LIMIT = 4096

BLOCKS = Counter(
    'omi_unlimited_v2_backfill_day_cap_blocks_total',
    'Backfill/import admissions refused by the default-off unlimited_v2 daily transcribed-hours cap',
    ['plane'],
)


def cap_enabled() -> bool:
    """Read the kill switch at the call boundary; absent means off."""
    return os.getenv(ENABLED_ENV, 'false').strip().lower() in _TRUTHY


def cap_hours() -> float:
    """The configured daily cap level in hours; invalid values keep the default."""
    raw = os.getenv(HOURS_ENV, '')
    if not raw.strip():
        return DEFAULT_CAP_HOURS
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning('unlimited_v2 backfill cap: unparseable hours setting; using default')
        return DEFAULT_CAP_HOURS
    if value <= 0:
        logger.warning('unlimited_v2 backfill cap: non-positive hours setting; using default')
        return DEFAULT_CAP_HOURS
    return value


def cap_seconds() -> float:
    return cap_hours() * 3600.0


def is_cap_plan(plan: Any) -> bool:
    """True only for the current ``unlimited_v2`` plan; unknown values are not capped."""
    try:
        return PlanType(plan) == CAP_PLAN
    except (TypeError, ValueError):
        return False


def _utc_day(now: datetime) -> date:
    return now.astimezone(timezone.utc).date()


def transcribed_seconds_for_day(
    uid: str,
    day: date,
    *,
    firestore_client: Any = None,
) -> int:
    """Sum ``transcription_seconds`` over one user-day's hourly documents.

    Raises on an unreadable store; callers decide whether that admits or refuses.
    """
    # Lazy module import: see the import note at the top of this file.
    from database._client import get_firestore_client
    from database.firestore_index_registry import HOURLY_USAGE_UTC_DAY_QUERY

    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection('hourly_usage')
    query = HOURLY_USAGE_UTC_DAY_QUERY.build(
        collection,
        {'year': day.year, 'month': day.month, 'day': day.day},
        field_filter_factory=_field_filter,
    )
    total = 0
    for snapshot in query.stream():
        data = snapshot.to_dict() or {}
        value = data.get('transcription_seconds', 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        total += max(0, int(value))
    return total


def _field_filter(field_path: str, operator: str, value: Any) -> Any:
    # Lazy module import: see the import note at the top of this file.
    from google.cloud.firestore_v1.base_query import FieldFilter

    return FieldFilter(field_path, operator, value)


def _cached_seconds_today(uid: str, day: date, *, now_monotonic: float, firestore_client: Any = None) -> int:
    entry = _READ_CACHE.get(uid)
    if entry is not None and entry[0] == day and now_monotonic - entry[1] <= _READ_TTL_SECONDS:
        return entry[2]
    seconds = transcribed_seconds_for_day(uid, day, firestore_client=firestore_client)
    if len(_READ_CACHE) >= _READ_CACHE_LIMIT:
        _prune_read_cache(day)
    _READ_CACHE[uid] = (day, now_monotonic, seconds)
    return seconds


def _prune_read_cache(day: date) -> None:
    for key in [key for key, value in _READ_CACHE.items() if value[0] != day]:
        _READ_CACHE.pop(key, None)
    if len(_READ_CACHE) >= _READ_CACHE_LIMIT:
        _READ_CACHE.clear()  # Never let a capped rollout grow process memory without bound.


def _plan_for(uid: str) -> Any:
    # Lazy module import: see the import note at the top of this file.
    import database.users as users_db

    subscription = users_db.get_user_subscription(uid, read_only=True)
    return getattr(subscription, 'plan', None)


def exhausted(uid: str, *, now: Optional[datetime] = None, firestore_client: Any = None) -> bool:
    """True when this user-day already reached the cap for an ``unlimited_v2`` account.

    Fails open (admits) on any unreadable dependency: a missing meter is never
    evidence that the cap was reached.
    """
    if not cap_enabled() or not uid:
        return False
    try:
        plan = _plan_for(uid)
    except Exception as error:
        logger.warning('unlimited_v2 backfill cap: plan lookup failed uid=%s error=%s', uid, type(error).__name__)
        return False
    if not is_cap_plan(plan):
        return False
    effective_now = now if now is not None else datetime.now(timezone.utc)
    day = _utc_day(effective_now)
    try:
        seconds = _cached_seconds_today(uid, day, now_monotonic=time.monotonic(), firestore_client=firestore_client)
    except Exception as error:
        logger.warning('unlimited_v2 backfill cap: day meter unavailable uid=%s error=%s', uid, type(error).__name__)
        return False
    return seconds >= cap_seconds()


def refuse(
    uid: str,
    allowance: TranscriptionAllowance,
    *,
    plane: str = 'sync',
    now: Optional[datetime] = None,
) -> TranscriptionAllowance:
    """Close a managed backfill allowance when the plan's user-day is at the cap.

    A capped user-day is answered exactly like the plan running out of managed
    minutes: ``on_device`` with zero remaining, so every existing caller (held
    offline segments, HTTP 402) keeps its own contract. Live planes are never
    closed here, whatever the caller passes.
    """
    if plane not in BACKFILL_PLANES:
        return allowance
    if not allowance.managed or allowance.reason in _EXEMPT_REASONS:
        return allowance
    if not refuses(uid, plane=plane, now=now):
        return allowance
    return TranscriptionAllowance('on_device', 0, REASON, limit_seconds=0)


def refuses(uid: str, *, plane: str = 'sync', now: Optional[datetime] = None) -> bool:
    """Whether this backfill admission is refused by the cap, recording the surface."""
    if plane not in BACKFILL_PLANES:
        return False
    if not exhausted(uid, now=now):
        return False
    BLOCKS.labels(plane).inc()
    logger.info('unlimited_v2 backfill cap: admission refused uid=%s plane=%s cap_hours=%s', uid, plane, cap_hours())
    return True
