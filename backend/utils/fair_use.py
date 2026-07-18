"""
Fair-use engine for Omi.

Tracks per-user rolling speech hours via Redis minute buckets,
detects soft-cap violations, triggers LLM classification,
and manages graduated enforcement (warning → throttle → restrict).
"""

import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import database.fair_use as fair_use_db
import database.users as users_db
from database.redis_db import r as redis_client
from models.fair_use import SoftCapTrigger
from models.users import PlanType
from utils.subscription import get_plan_limits, has_transcription_credits, is_paid_plan
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.llm.fair_use_classifier import classify_user_purpose
from utils.notifications import send_notification

# Patchable lazy-held callables keep tests at a production seam without using
# in-function imports. Both imported modules are import-pure and construct their
# provider clients only when the callable is invoked.
_classify_user_purpose: Callable[..., Any] = classify_user_purpose
_send_notification: Callable[..., Any] = send_notification


def _get_classify_user_purpose() -> Callable[..., Any]:
    return _classify_user_purpose


def _get_send_notification() -> Callable[..., Any]:
    return _send_notification


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Env-var driven config
# ---------------------------------------------------------------------------

FAIR_USE_ENABLED = os.getenv('FAIR_USE_ENABLED', 'false').lower() == 'true'
FAIR_USE_KILL_SWITCH = os.getenv('FAIR_USE_KILL_SWITCH', 'false').lower() == 'true'

# Soft cap thresholds (milliseconds of real speech) — default tier (Free, Plus, and any
# plan with a bounded monthly transcription allowance).
FAIR_USE_DAILY_SPEECH_MS = int(os.getenv('FAIR_USE_DAILY_SPEECH_MS', '7200000'))  # 2h
FAIR_USE_3DAY_SPEECH_MS = int(os.getenv('FAIR_USE_3DAY_SPEECH_MS', '28800000'))  # 8h
FAIR_USE_WEEKLY_SPEECH_MS = int(os.getenv('FAIR_USE_WEEKLY_SPEECH_MS', '36000000'))  # 10h

# Raised triggers for unlimited-transcription tiers (Unlimited/unlimited_v2, legacy Neo,
# Operator, Architect). They pay for unlimited use, so scrutiny starts later. Kept in the
# same burst-vs-sustained ratio as the default tier (~4x daily for 3-day, ~5x for weekly).
FAIR_USE_DAILY_SPEECH_MS_UNLIMITED = int(os.getenv('FAIR_USE_DAILY_SPEECH_MS_UNLIMITED', '14400000'))  # 4h
FAIR_USE_3DAY_SPEECH_MS_UNLIMITED = int(os.getenv('FAIR_USE_3DAY_SPEECH_MS_UNLIMITED', '57600000'))  # 16h
FAIR_USE_WEEKLY_SPEECH_MS_UNLIMITED = int(os.getenv('FAIR_USE_WEEKLY_SPEECH_MS_UNLIMITED', '72000000'))  # 20h

# Redis bucket granularity
FAIR_USE_BUCKET_SECONDS = int(os.getenv('FAIR_USE_BUCKET_SECONDS', '60'))  # 1-min buckets
FAIR_USE_REDIS_RETENTION_SECONDS = int(os.getenv('FAIR_USE_REDIS_RETENTION_SECONDS', '691200'))  # 8 days

# Classifier config
FAIR_USE_CLASSIFIER_MISUSE_THRESHOLD = float(os.getenv('FAIR_USE_CLASSIFIER_ABUSE_SCORE_THRESHOLD', '0.7'))
FAIR_USE_CLASSIFIER_COOLDOWN_SECONDS = int(os.getenv('FAIR_USE_CLASSIFIER_COOLDOWN_SECONDS', '43200'))  # 12 hours

# Exempt UIDs (comma-separated)
FAIR_USE_EXEMPT_UIDS = set(filter(None, os.getenv('FAIR_USE_EXEMPT_UIDS', '').split(',')))

# Check interval — how often the usage loop checks caps (seconds)
FAIR_USE_CHECK_INTERVAL_SECONDS = int(os.getenv('FAIR_USE_CHECK_INTERVAL_SECONDS', '300'))  # 5 min

# Restrict-stage daily Deepgram budget (milliseconds of audio forwarded to DG per day)
# 0 = no budget cap (disabled). Only enforced when stage == 'restrict'.
FAIR_USE_RESTRICT_DAILY_DG_MS = int(os.getenv('FAIR_USE_RESTRICT_DAILY_DG_MS', '1800000'))  # 30 min

# Hard anti-abuse ceiling: max total audio processed per rolling 24h, ALL plans. Set high
# enough that no legitimate single human hits it (a real person cannot generate this much
# audio in a day) — it exists to stop bulk-sync dumps / reselling, not to cap usage.
# Metered against the live rolling meter (realtime + sync_fresh); sync_backfill is separately
# paced by reserve_backfill_speech. 0 = disabled.
MAX_DAILY_AUDIO_HOURS = int(os.getenv('MAX_DAILY_AUDIO_HOURS', '30'))
MAX_DAILY_AUDIO_MS = MAX_DAILY_AUDIO_HOURS * 3600 * 1000


LIVE_SPEECH_SOURCES = ('realtime', 'sync_fresh')
_VALID_SPEECH_SOURCES = frozenset((*LIVE_SPEECH_SOURCES, 'sync_backfill'))


def _normalize_speech_source(source: str) -> str:
    # Compatibility for deprecated callers while keeping new Redis keys lane-specific.
    normalized = 'sync_fresh' if source == 'sync' else source
    return normalized if normalized in _VALID_SPEECH_SOURCES else 'realtime'


def _redis_key(uid: str, source: str) -> str:
    """Redis sorted set key for a user's speech minute buckets."""
    return f'fair_use:v2:speech:{source}:{uid}'


def _bucket_key(uid: str, source: str) -> str:
    return f'fair_use:v2:bucket:{source}:{uid}'


def _classifier_lock_key(uid: str) -> str:
    """Redis key to deduplicate concurrent classifier runs."""
    return f'fair_use:classifier_lock:{uid}'


# Lua script for atomic compare-and-delete (prevents deleting a lock owned by another worker)
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def _release_lock(key: str, token: str) -> None:
    """Release a Redis lock only if we still own it (compare-and-delete)."""
    redis_client.eval(_RELEASE_LOCK_SCRIPT, 1, key, token)


# ---------------------------------------------------------------------------
# Speech tracking (Redis sorted set of minute buckets)
# ---------------------------------------------------------------------------


_RECORD_SPEECH_ONCE_SCRIPT = """
if redis.call('set', KEYS[1], '1', 'EX', ARGV[4], 'NX') then
    redis.call('hincrby', KEYS[2], ARGV[1], ARGV[2])
    redis.call('expire', KEYS[2], ARGV[4])
    redis.call('zadd', KEYS[3], ARGV[3], ARGV[1])
    redis.call('expire', KEYS[3], ARGV[4])
    return 1
end
return 0
"""


def record_speech_ms(
    uid: str,
    speech_ms: int,
    source: str = 'realtime',
    idempotency_key: Optional[str] = None,
    raise_on_error: bool = False,
) -> None:
    """Record speech milliseconds into the current minute bucket.

    Uses a Redis sorted set where:
      - member = Unix minute timestamp (as string)
      - score = Unix minute timestamp (for range queries)
    The speech_ms is stored in a separate hash keyed by minute.
    Source is part of the Redis key. Live enforcement reads only realtime and
    sync_fresh; sync_backfill is deliberately isolated from live hard caps.
    """
    if not FAIR_USE_ENABLED or speech_ms <= 0:
        return

    try:
        normalized_source = _normalize_speech_source(source)
        now = int(time.time())
        bucket_minute = now // FAIR_USE_BUCKET_SECONDS
        logger.info(f'fair_use: record_speech_ms uid={uid} ms={speech_ms} source={normalized_source}')

        pipe = redis_client.pipeline(transaction=False)
        # Increment speech_ms for this minute bucket
        bucket_key = _bucket_key(uid, normalized_source)
        zset_key = _redis_key(uid, normalized_source)
        if idempotency_key:
            once_key = f'fair_use:v2:once:speech:{normalized_source}:{uid}:{idempotency_key}'
            redis_client.eval(
                _RECORD_SPEECH_ONCE_SCRIPT,
                3,
                once_key,
                bucket_key,
                zset_key,
                str(bucket_minute),
                speech_ms,
                bucket_minute * FAIR_USE_BUCKET_SECONDS,
                FAIR_USE_REDIS_RETENTION_SECONDS,
            )
            return
        pipe.hincrby(bucket_key, str(bucket_minute), speech_ms)
        pipe.expire(bucket_key, FAIR_USE_REDIS_RETENTION_SECONDS)

        # Add minute to sorted set (score = timestamp for range queries)
        pipe.zadd(zset_key, {str(bucket_minute): bucket_minute * FAIR_USE_BUCKET_SECONDS})
        pipe.expire(zset_key, FAIR_USE_REDIS_RETENTION_SECONDS)

        # Prune old zset members older than retention window
        cutoff_ts = now - FAIR_USE_REDIS_RETENTION_SECONDS
        # First, get stale members so we can also prune the hash (#5748 reviewer fix)
        stale_members = redis_client.zrangebyscore(zset_key, 0, cutoff_ts)
        pipe.zremrangebyscore(zset_key, 0, cutoff_ts)
        # Prune matching hash fields to prevent unbounded growth
        if stale_members:
            stale_fields = [m.decode() if isinstance(m, bytes) else m for m in stale_members]
            pipe.hdel(bucket_key, *stale_fields)

        pipe.execute()
    except Exception as e:
        logger.error(f'fair_use: Redis error recording speech for {uid}: {e}')
        if raise_on_error:
            raise


def get_rolling_speech_ms(uid: str, sources: Optional[tuple[str, ...]] = None) -> Dict[str, Any]:
    """Get speech totals for rolling windows: daily (24h), 3-day (72h), weekly (168h).

    Returns dict with keys: daily_ms, three_day_ms, weekly_ms.
    """
    result: Dict[str, Any] = {'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    if not FAIR_USE_ENABLED:
        return result

    try:
        now = int(time.time())
        cutoff_weekly = now - (7 * 24 * 3600)
        cutoff_daily = now - (24 * 3600)
        cutoff_3day = now - (3 * 24 * 3600)

        selected_sources = sources or LIVE_SPEECH_SOURCES
        source_keys = [
            (_bucket_key(uid, _normalize_speech_source(source)), _redis_key(uid, _normalize_speech_source(source)))
            for source in selected_sources
        ]
        if sources is None:
            # Transitional compatibility: retain the previous combined meter
            # in live enforcement until its seven-day TTL naturally expires.
            # New backfill is written only to the isolated v2 key.
            source_keys.append((f'fair_use:bucket:{uid}', f'fair_use:speech:{uid}'))
        for bucket_key, zset_key in source_keys:
            members = redis_client.zrangebyscore(zset_key, cutoff_weekly, '+inf')
            if not members:
                continue
            fields = [m.decode() if isinstance(m, bytes) else m for m in members]
            bucket_values = redis_client.hmget(bucket_key, fields)
            for member, value in zip(members, bucket_values):
                if value is None:
                    continue
                ms = int(value)
                member_str = member.decode() if isinstance(member, bytes) else member
                bucket_ts = int(member_str) * FAIR_USE_BUCKET_SECONDS

                result['weekly_ms'] += ms
                if bucket_ts >= cutoff_3day:
                    result['three_day_ms'] += ms
                if bucket_ts >= cutoff_daily:
                    result['daily_ms'] += ms

        return result
    except Exception as e:
        logger.error(f'fair_use: Redis error reading speech for {uid}: {e}')
        return result


def get_rolling_backfill_speech_ms(uid: str) -> Dict[str, Any]:
    """Return historical recovery usage without including it in live enforcement."""
    return get_rolling_speech_ms(uid, sources=('sync_backfill',))


# ---------------------------------------------------------------------------
# Soft cap detection
# ---------------------------------------------------------------------------


def _is_unlimited_tier(plan: Optional[PlanType]) -> bool:
    """True for paid unlimited-transcription plans (Unlimited/unlimited_v2, legacy Neo,
    Operator, Architect) — the tiers whose monthly transcription allowance is unbounded.

    Keyed off plan limits rather than a hardcoded set so it stays self-consistent as the
    catalog changes. Requires a *paid* plan AND ``transcription_seconds is None`` (paid
    unlimited plans use None): this excludes Free — whose configured cap can be 0 ("no cap
    configured") in some environments — and Plus, which carries a positive monthly cap.
    """
    if plan is None:
        return False
    try:
        return is_paid_plan(plan) and get_plan_limits(plan).transcription_seconds is None
    except Exception:
        return False


def fair_use_caps_for_plan(plan: Optional[PlanType] = None) -> tuple[int, int, int]:
    """Return the (daily_ms, three_day_ms, weekly_ms) soft-cap triggers for a plan.

    Unlimited-tier plans get the raised triggers; everyone else gets the default tier.
    plan=None yields the default tier (backwards-compatible for callers without plan context).
    """
    if _is_unlimited_tier(plan):
        return (
            FAIR_USE_DAILY_SPEECH_MS_UNLIMITED,
            FAIR_USE_3DAY_SPEECH_MS_UNLIMITED,
            FAIR_USE_WEEKLY_SPEECH_MS_UNLIMITED,
        )
    return (FAIR_USE_DAILY_SPEECH_MS, FAIR_USE_3DAY_SPEECH_MS, FAIR_USE_WEEKLY_SPEECH_MS)


def is_daily_audio_ceiling_exceeded(uid: str, speech_totals: Optional[Dict[str, Any]] = None) -> bool:
    """Hard anti-abuse ceiling on total daily audio, applied to ALL plans.

    Reuses the live rolling daily meter (realtime + sync_fresh). Returns False when the
    feature is disabled (MAX_DAILY_AUDIO_MS <= 0), fair-use is off, or the kill switch is on.
    Exempt UIDs bypass the ceiling.
    """
    if not FAIR_USE_ENABLED or FAIR_USE_KILL_SWITCH or MAX_DAILY_AUDIO_MS <= 0:
        return False
    if uid in FAIR_USE_EXEMPT_UIDS:
        return False
    totals = speech_totals if speech_totals is not None else get_rolling_speech_ms(uid)
    return totals.get('daily_ms', 0) >= MAX_DAILY_AUDIO_MS


def check_soft_caps(
    uid: str, speech_totals: Optional[Dict[str, Any]] = None, plan: Optional[PlanType] = None
) -> List[Dict[str, Any]]:
    """Check if user exceeds any rolling speech cap.

    Args:
        uid: User ID.
        speech_totals: Optional precomputed result from get_rolling_speech_ms().
            If None, fetches fresh from Redis.
        plan: Optional plan; selects the per-tier trigger thresholds. Unlimited-tier plans
            get raised triggers. plan=None uses the default tier (backwards-compatible).

    Returns list of triggered caps, e.g.:
      [{'trigger': 'daily', 'speech_ms': 7500000, 'threshold_ms': 7200000}]
    """
    if not FAIR_USE_ENABLED or FAIR_USE_KILL_SWITCH:
        return []

    if uid in FAIR_USE_EXEMPT_UIDS:
        return []

    speech = speech_totals if speech_totals is not None else get_rolling_speech_ms(uid)
    daily_cap, three_day_cap, weekly_cap = fair_use_caps_for_plan(plan)
    triggered: List[Dict[str, Any]] = []

    if speech['daily_ms'] > daily_cap:
        triggered.append(
            {
                'trigger': SoftCapTrigger.DAILY,
                'speech_ms': speech['daily_ms'],
                'threshold_ms': daily_cap,
            }
        )
    if speech['three_day_ms'] > three_day_cap:
        triggered.append(
            {
                'trigger': SoftCapTrigger.THREE_DAY,
                'speech_ms': speech['three_day_ms'],
                'threshold_ms': three_day_cap,
            }
        )
    if speech['weekly_ms'] > weekly_cap:
        triggered.append(
            {
                'trigger': SoftCapTrigger.WEEKLY,
                'speech_ms': speech['weekly_ms'],
                'threshold_ms': weekly_cap,
            }
        )

    return triggered


# ---------------------------------------------------------------------------
# Enforcement state machine
# ---------------------------------------------------------------------------


def get_enforcement_stage(uid: str) -> str:
    """Get current enforcement stage from Firestore (cached in Redis for hot path)."""
    cache_key = f'fair_use:stage:{uid}'
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return cached.decode() if isinstance(cached, bytes) else cached
    except Exception:
        pass

    state = fair_use_db.get_fair_use_state(uid)
    stage = state.get('stage', 'none')

    # Cache for 60s
    try:
        redis_client.setex(cache_key, 60, stage)
    except Exception:
        pass

    return stage


def invalidate_enforcement_cache(uid: str) -> None:
    """Clear cached enforcement state after an update."""
    try:
        redis_client.delete(f'fair_use:stage:{uid}')
    except Exception:
        pass


def is_free_credits_exhausted(uid: str) -> bool:
    """Check if a user is on a free (basic) plan with exhausted transcription credits.

    Returns True only for non-paid users who have used all monthly credits.
    Paid users and users with remaining credits return False.
    """
    try:
        subscription = users_db.get_user_valid_subscription(uid)
        if subscription and is_paid_plan(subscription.plan):
            return False
        return not has_transcription_credits(uid)
    except Exception as e:
        logger.error(f'fair_use: error checking free credits for {uid}: {e}')
        return False


def escalate_enforcement(
    uid: str, triggered_caps: List[Dict[str, Any]], classifier_result: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Escalate enforcement based on violations and classifier result.

    Used for both abuse detection (LLM classifier) and free-exhausted users (#6083).
    Free-exhausted users get a synthetic score > 0.7 instead of LLM classification,
    so they follow the same graduated escalation: none → warning → throttle → restrict.

    Returns dict describing the action taken.
    """
    state = fair_use_db.get_fair_use_state(uid)
    current_stage = state.get('stage', 'none')
    counts = fair_use_db.get_violation_counts(uid)

    misuse_score = 0.0
    usage_type = 'none'
    if classifier_result:
        misuse_score = classifier_result.get('misuse_score', 0.0)
        usage_type = classifier_result.get('usage_type', 'none')

    passes_score_gate = misuse_score >= FAIR_USE_CLASSIFIER_MISUSE_THRESHOLD

    # Determine new stage based on current + violation history
    new_stage = current_stage
    action = 'none'

    if current_stage == 'none':
        if passes_score_gate:
            new_stage = 'warning'
            action = 'warning'
    elif current_stage == 'warning':
        if counts['violation_count_7d'] >= 2 and passes_score_gate:
            new_stage = 'throttle'
            action = 'throttle'
    elif current_stage == 'throttle':
        if counts['violation_count_7d'] >= 3 and passes_score_gate:
            new_stage = 'restrict'
            action = 'restrict'

    # Apply stage changes
    if new_stage != current_stage:
        update: Dict[str, Any] = {
            'stage': new_stage,
            'last_violation_at': datetime.now(timezone.utc),
            'last_classifier_score': misuse_score,
            'last_classifier_type': usage_type,
            'violation_count_7d': counts['violation_count_7d'],
            'violation_count_30d': counts['violation_count_30d'],
        }

        if new_stage == 'throttle':
            update['throttle_until'] = datetime.now(timezone.utc) + timedelta(days=7)
        elif new_stage == 'restrict':
            update['restrict_until'] = datetime.now(timezone.utc) + timedelta(days=30)

        fair_use_db.update_fair_use_state(uid, update)
        invalidate_enforcement_cache(uid)

    # Record the event (create_fair_use_event auto-generates a case_ref)
    speech = get_rolling_speech_ms(uid)
    event_data: Dict[str, Any] = {
        'session_id': '',
        'trigger': triggered_caps[0]['trigger'].value if triggered_caps else 'daily',
        'window_speech_ms': speech,
        'thresholds_ms': {
            'daily': FAIR_USE_DAILY_SPEECH_MS,
            'three_day': FAIR_USE_3DAY_SPEECH_MS,
            'weekly': FAIR_USE_WEEKLY_SPEECH_MS,
        },
        'classifier': classifier_result,
        'enforcement_action': action,
        'previous_stage': current_stage,
        'new_stage': new_stage,
    }
    event_id = fair_use_db.create_fair_use_event(uid, event_data)

    # Store latest case_ref on user state for quick lookup by user/support
    if action != 'none':
        events = fair_use_db.get_fair_use_events(uid, limit=1)
        if events and events[0].get('case_ref'):
            fair_use_db.update_fair_use_state(uid, {'last_case_ref': events[0]['case_ref']})

    return {
        'action': action,
        'previous_stage': current_stage,
        'new_stage': new_stage,
        'event_id': event_id,
    }


def clear_fair_use_on_upgrade(uid: str) -> bool:
    """Clear free-tier-derived fair-use enforcement when a user upgrades to a paid plan.

    Only clears enforcement that originated from free-tier credit exhaustion
    (last_classifier_type == 'free_exhausted'). Abuse-derived enforcement is preserved.

    Returns True if enforcement was cleared, False otherwise.
    """
    subscription = users_db.get_user_valid_subscription(uid)
    if not subscription or not is_paid_plan(subscription.plan):
        return False

    state = fair_use_db.get_fair_use_state(uid)
    stage = state.get('stage', 'none')
    if stage == 'none':
        return False

    if state.get('last_classifier_type') != 'free_exhausted':
        logger.info(
            'fair_use: upgrade clear skipped uid=%s stage=%s classifier_type=%s (not free_exhausted)',
            uid,
            stage,
            state.get('last_classifier_type'),
        )
        return False

    fair_use_db.update_fair_use_state(
        uid,
        {
            'stage': 'none',
            'violation_count_7d': 0,
            'violation_count_30d': 0,
            'throttle_until': None,
            'restrict_until': None,
            'cleared_by': 'subscription_upgrade',
            'cleared_at': datetime.now(timezone.utc),
        },
    )
    invalidate_enforcement_cache(uid)
    logger.info('fair_use: cleared free-exhausted enforcement on upgrade uid=%s previous_stage=%s', uid, stage)
    return True


def _as_utc(dt: datetime) -> datetime:
    """Normalize a datetime to aware UTC for comparisons with datetime.now(timezone.utc)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _retry_after_seconds_from_restrict_until(restrict_until: Any) -> int | None:
    if not isinstance(restrict_until, datetime):
        return None
    restrict_until = _as_utc(restrict_until)
    seconds = int((restrict_until - datetime.now(timezone.utc)).total_seconds())
    return max(seconds, 1) if seconds > 0 else None


def normalize_expired_restriction_state(
    uid: str, state: Dict[str, Any], *, now: datetime | None = None
) -> Dict[str, Any]:
    """Return effective state, persisting the existing restrict→throttle expiry transition."""
    normalized_state = dict(state)
    if normalized_state.get('stage', 'none') != 'restrict':
        return normalized_state

    restrict_until_raw = normalized_state.get('restrict_until')
    if not isinstance(restrict_until_raw, datetime):
        return normalized_state

    restrict_until = _as_utc(restrict_until_raw)
    effective_now = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    if effective_now <= restrict_until:
        return normalized_state

    fair_use_db.update_fair_use_state(uid, {'stage': 'throttle', 'restrict_until': None})
    invalidate_enforcement_cache(uid)
    normalized_state.update({'stage': 'throttle', 'restrict_until': None})
    return normalized_state


def get_hard_restriction_status(uid: str) -> tuple[bool, int | None]:
    """Return whether the user is hard-restricted and, when known, the retry window in seconds."""
    if not FAIR_USE_ENABLED or FAIR_USE_KILL_SWITCH:
        return False, None
    if uid in FAIR_USE_EXEMPT_UIDS:
        return False, None

    # Single Firestore read — get_enforcement_stage uses cache, but we need
    # restrict_until too, so read the full state once and check stage from it.
    state = normalize_expired_restriction_state(uid, fair_use_db.get_fair_use_state(uid))
    stage = state.get('stage', 'none')
    if stage != 'restrict':
        return False, None

    restrict_until = state.get('restrict_until')

    # Check if speech is over hard cap
    speech = get_rolling_speech_ms(uid)
    # In restrict mode, enforce the soft caps as hard caps
    restricted: bool = bool(
        speech['daily_ms'] > FAIR_USE_DAILY_SPEECH_MS
        or speech['three_day_ms'] > FAIR_USE_3DAY_SPEECH_MS
        or speech['weekly_ms'] > FAIR_USE_WEEKLY_SPEECH_MS
    )
    return restricted, _retry_after_seconds_from_restrict_until(restrict_until) if restricted else None


def is_hard_restricted(uid: str) -> bool:
    """Check if a user is hard-restricted (speech cap enforced as hard block)."""
    return get_hard_restriction_status(uid)[0]


def get_hard_restriction_retry_after_seconds(uid: str) -> int | None:
    """Return seconds until the active hard restriction expires, if known."""
    try:
        return get_hard_restriction_status(uid)[1]
    except Exception as e:
        logger.error(f'fair_use: error checking hard restriction retry-after for {uid}: {e}')
        return None


# ---------------------------------------------------------------------------
# Restrict-stage daily Deepgram budget
# ---------------------------------------------------------------------------


def _dg_budget_key(uid: str) -> str:
    """Redis key for daily DG budget counter. Auto-expires at end of UTC day."""
    day = datetime.now(timezone.utc).strftime('%Y%m%d')
    return f'fair_use:dg_budget:{uid}:{day}'


_RECORD_COUNTER_ONCE_SCRIPT = """
if redis.call('set', KEYS[1], '1', 'EX', ARGV[2], 'NX') then
    redis.call('incrby', KEYS[2], ARGV[1])
    redis.call('expire', KEYS[2], ARGV[2])
    return 1
end
return 0
"""


def record_dg_usage_ms(uid: str, ms: int, idempotency_key: Optional[str] = None, raise_on_error: bool = False) -> None:
    """Atomically increment today's DG usage counter."""
    if not FAIR_USE_ENABLED or FAIR_USE_RESTRICT_DAILY_DG_MS <= 0 or ms <= 0:
        return
    try:
        key = _dg_budget_key(uid)
        pipe = redis_client.pipeline(transaction=False)
        pipe.incrby(key, ms)
        # TTL = seconds until next midnight UTC + 1h buffer
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_midnight = int((tomorrow - now).total_seconds())
        if idempotency_key:
            ttl = seconds_until_midnight + 3600
            redis_client.eval(
                _RECORD_COUNTER_ONCE_SCRIPT,
                2,
                f'fair_use:v2:once:dg:{uid}:{idempotency_key}',
                key,
                ms,
                ttl,
            )
            return
        pipe.expire(key, seconds_until_midnight + 3600)
        pipe.execute()
    except Exception as e:
        logger.error(f'fair_use: Redis error recording DG usage for {uid}: {e}')
        if raise_on_error:
            raise


def get_dg_budget_status(uid: str) -> Dict[str, Any]:
    """Get the DG budget status for a user.

    Returns dict with: daily_limit_ms, used_ms, remaining_ms, exhausted, resets_at.
    """
    limit = FAIR_USE_RESTRICT_DAILY_DG_MS
    result: Dict[str, Any] = {
        'daily_limit_ms': limit,
        'used_ms': 0,
        'remaining_ms': limit,
        'exhausted': False,
        'resets_at': None,
    }
    if not FAIR_USE_ENABLED or limit <= 0:
        return result

    try:
        key = _dg_budget_key(uid)
        used = redis_client.get(key)
        used_ms = int(used) if used else 0
        remaining = max(0, limit - used_ms)
        # Next midnight UTC
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        result['used_ms'] = used_ms
        result['remaining_ms'] = remaining
        result['exhausted'] = remaining <= 0
        result['resets_at'] = tomorrow.isoformat() + 'Z'
    except Exception as e:
        logger.error(f'fair_use: Redis error reading DG budget for {uid}: {e}')

    return result


def is_dg_budget_exhausted(uid: str) -> bool:
    """Fast check: is the user's daily DG budget used up?

    Returns False on Redis errors (fail-open).
    """
    if not FAIR_USE_ENABLED or FAIR_USE_RESTRICT_DAILY_DG_MS <= 0:
        return False
    try:
        key = _dg_budget_key(uid)
        used = redis_client.get(key)
        if used is None:
            return False
        return int(used) >= FAIR_USE_RESTRICT_DAILY_DG_MS
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Classifier trigger (async, deduplicated)
# ---------------------------------------------------------------------------


async def trigger_classifier_if_needed(uid: str, triggered_caps: List[Dict[str, Any]], session_id: str = '') -> None:
    """Check if we should run the LLM classifier and handle enforcement.

    Uses a Redis lock to prevent concurrent runs for the same user.
    Runs asynchronously — does not block the WebSocket path.

    Free-exhausted users (#6083) get a synthetic score of 1.0 instead of
    the LLM classifier, then follow the same graduated escalation pipeline.
    """
    # Already at terminal stage — no escalation possible, skip LLM + lock (#6316)
    try:
        current_stage = await run_blocking(db_executor, get_enforcement_stage, uid)
        if current_stage == 'restrict':
            logger.info(f'fair_use: uid={uid} already at restrict stage, skipping classifier')
            return
    except Exception:
        pass  # fail-open: proceed with classifier if stage check fails

    lock_key = _classifier_lock_key(uid)
    lock_token = str(uuid.uuid4())

    try:
        acquired = await run_blocking(
            db_executor,
            redis_client.set,
            lock_key,
            lock_token,
            nx=True,
            ex=FAIR_USE_CLASSIFIER_COOLDOWN_SECONDS,
        )
        if not acquired:
            logger.info(f'fair_use: classifier already running/recent for {uid}')
            return
    except Exception as e:
        logger.error(f'fair_use: Redis lock error for {uid}: {e}')
        return

    try:
        # Free-exhausted users: synthetic score > 0.7, skip LLM classifier (#6083)
        if await run_blocking(db_executor, is_free_credits_exhausted, uid):
            classifier_result = {'misuse_score': 1.0, 'usage_type': 'free_exhausted'}
            logger.info(f'fair_use: free-exhausted uid={uid}, using synthetic score 1.0')
        else:
            classifier_result = await _get_classify_user_purpose()(uid)
        escalation = await run_blocking(db_executor, escalate_enforcement, uid, triggered_caps, classifier_result)

        logger.info(
            'fair_use: uid=%s action=%s score=%.2f type=%s stage=%s->%s',
            uid,
            escalation['action'],
            classifier_result.get('misuse_score', 0),
            classifier_result.get('usage_type', 'none'),
            escalation['previous_stage'],
            escalation['new_stage'],
        )

        # Send notification if action was taken
        if escalation['action'] != 'none':
            # Offloaded: the Firestore read is sync and blocks the event loop in this async path.
            latest_events = await run_blocking(db_executor, fair_use_db.get_fair_use_events, uid, limit=1)
            case_ref = latest_events[0].get('case_ref', '') if latest_events else ''
            await _send_fair_use_notification(uid, escalation['action'], case_ref=case_ref)

    except Exception as e:
        logger.error(f'fair_use: classifier/escalation error for {uid}: {e}')
        try:
            await run_blocking(db_executor, _release_lock, lock_key, lock_token)
        except Exception:
            pass


async def _send_fair_use_notification(uid: str, action: str, case_ref: str = '') -> None:
    """Send in-app push notification about fair-use enforcement."""
    titles = {
        'warning': 'Fair Use Notice',
        'throttle': 'Transcription Quality Reduced',
        'restrict': 'Transcription Limit Reached',
    }

    ref_suffix = f' Reference: {case_ref}' if case_ref else ''

    bodies = {
        'warning': (
            'Your speech usage is unusually high. Omi is designed for personal conversations. '
            'If this continues, transcription quality may be reduced. '
            f'Check Settings > Plan & Usage for details.{ref_suffix}'
        ),
        'throttle': (
            'Due to high non-conversational usage, your transcription quality has been temporarily reduced. '
            'This will reset automatically. Contact team@basedhardware.com if you believe this is an error. '
            f'Quote your case reference when contacting support.{ref_suffix}'
        ),
        'restrict': (
            'Your cloud transcription has been temporarily limited due to repeated fair-use violations. '
            'On-device transcription continues normally. Contact team@basedhardware.com to resolve. '
            f'Quote your case reference when contacting support.{ref_suffix}'
        ),
    }

    title = titles.get(action, 'Fair Use Notice')
    body = bodies.get(action, '')
    if body:
        data = {'type': 'fair_use', 'action': action}
        if case_ref:
            data['case_ref'] = case_ref
        await run_blocking(postprocess_executor, _get_send_notification(), uid, title, body, data=data)
