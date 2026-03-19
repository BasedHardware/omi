"""
Fair-use engine for Omi.

Tracks per-user rolling speech hours via Redis minute buckets,
detects soft-cap violations, triggers LLM classification,
and manages graduated enforcement (warning → throttle → restrict).
"""

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta

import database.fair_use as fair_use_db
import database.users as users_db
from database.redis_db import r as redis_client
from models.fair_use import UsageType, FairUseStage, SoftCapTrigger

# Lazy imports — NOT circular deps, but import-time side-effect avoidance.
# classify_user_purpose → database.conversations → utils.encryption
#   encryption.py raises ValueError at import if ENCRYPTION_SECRET env var is missing/short.
# send_notification → firebase_admin.messaging
#   Requires Firebase app to be initialized before import.
# Both are only called in async runtime paths, never at import time.
# Moving to top-level would break any context where this module loads before env/Firebase init.
_classify_user_purpose = None
_send_notification = None


def _get_classify_user_purpose():
    global _classify_user_purpose
    if _classify_user_purpose is None:
        from utils.llm.fair_use_classifier import classify_user_purpose

        _classify_user_purpose = classify_user_purpose
    return _classify_user_purpose


def _get_send_notification():
    global _send_notification
    if _send_notification is None:
        from utils.notifications import send_notification

        _send_notification = send_notification
    return _send_notification


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Env-var driven config
# ---------------------------------------------------------------------------

FAIR_USE_ENABLED = os.getenv('FAIR_USE_ENABLED', 'false').lower() == 'true'
FAIR_USE_KILL_SWITCH = os.getenv('FAIR_USE_KILL_SWITCH', 'false').lower() == 'true'

# Soft cap thresholds (milliseconds of real speech)
FAIR_USE_DAILY_SPEECH_MS = int(os.getenv('FAIR_USE_DAILY_SPEECH_MS', '7200000'))  # 2h
FAIR_USE_3DAY_SPEECH_MS = int(os.getenv('FAIR_USE_3DAY_SPEECH_MS', '28800000'))  # 8h
FAIR_USE_WEEKLY_SPEECH_MS = int(os.getenv('FAIR_USE_WEEKLY_SPEECH_MS', '36000000'))  # 10h

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


def _redis_key(uid: str) -> str:
    """Redis sorted set key for a user's speech minute buckets."""
    return f'fair_use:speech:{uid}'


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


def record_speech_ms(uid: str, speech_ms: int) -> None:
    """Record speech milliseconds into the current minute bucket.

    Uses a Redis sorted set where:
      - member = Unix minute timestamp (as string)
      - score = Unix minute timestamp (for range queries)
    The speech_ms is stored in a separate hash keyed by minute.
    """
    if not FAIR_USE_ENABLED or speech_ms <= 0:
        return

    try:
        now = int(time.time())
        bucket_minute = now // FAIR_USE_BUCKET_SECONDS

        pipe = redis_client.pipeline(transaction=False)
        # Increment speech_ms for this minute bucket
        bucket_key = f'fair_use:bucket:{uid}'
        pipe.hincrby(bucket_key, str(bucket_minute), speech_ms)
        pipe.expire(bucket_key, FAIR_USE_REDIS_RETENTION_SECONDS)

        # Add minute to sorted set (score = timestamp for range queries)
        zset_key = _redis_key(uid)
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


def get_rolling_speech_ms(uid: str) -> dict:
    """Get speech totals for rolling windows: daily (24h), 3-day (72h), weekly (168h).

    Returns dict with keys: daily_ms, three_day_ms, weekly_ms.
    """
    result = {'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    if not FAIR_USE_ENABLED:
        return result

    try:
        now = int(time.time())
        bucket_key = f'fair_use:bucket:{uid}'
        zset_key = _redis_key(uid)

        # Get all minutes in the last 7 days from sorted set
        cutoff_weekly = now - (7 * 24 * 3600)
        members = redis_client.zrangebyscore(zset_key, cutoff_weekly, '+inf')

        if not members:
            return result

        # Fetch all bucket values in one HMGET
        bucket_values = redis_client.hmget(bucket_key, [m.decode() if isinstance(m, bytes) else m for m in members])

        cutoff_daily = now - (24 * 3600)
        cutoff_3day = now - (3 * 24 * 3600)

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


# ---------------------------------------------------------------------------
# Soft cap detection
# ---------------------------------------------------------------------------


def check_soft_caps(uid: str) -> list:
    """Check if user exceeds any rolling speech cap.

    Returns list of triggered caps, e.g.:
      [{'trigger': 'daily', 'speech_ms': 7500000, 'threshold_ms': 7200000}]
    """
    if not FAIR_USE_ENABLED or FAIR_USE_KILL_SWITCH:
        return []

    if uid in FAIR_USE_EXEMPT_UIDS:
        return []

    speech = get_rolling_speech_ms(uid)
    triggered = []

    if speech['daily_ms'] > FAIR_USE_DAILY_SPEECH_MS:
        triggered.append(
            {
                'trigger': SoftCapTrigger.DAILY,
                'speech_ms': speech['daily_ms'],
                'threshold_ms': FAIR_USE_DAILY_SPEECH_MS,
            }
        )
    if speech['three_day_ms'] > FAIR_USE_3DAY_SPEECH_MS:
        triggered.append(
            {
                'trigger': SoftCapTrigger.THREE_DAY,
                'speech_ms': speech['three_day_ms'],
                'threshold_ms': FAIR_USE_3DAY_SPEECH_MS,
            }
        )
    if speech['weekly_ms'] > FAIR_USE_WEEKLY_SPEECH_MS:
        triggered.append(
            {
                'trigger': SoftCapTrigger.WEEKLY,
                'speech_ms': speech['weekly_ms'],
                'threshold_ms': FAIR_USE_WEEKLY_SPEECH_MS,
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


def escalate_enforcement(uid: str, triggered_caps: list, classifier_result: dict = None) -> dict:
    """Escalate enforcement based on violations and classifier result.

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

    # Determine new stage based on current + violation history
    new_stage = current_stage
    action = 'none'

    if current_stage == 'none':
        if misuse_score >= FAIR_USE_CLASSIFIER_MISUSE_THRESHOLD:
            new_stage = 'warning'
            action = 'warning'
    elif current_stage == 'warning':
        if counts['violation_count_7d'] >= 2 and misuse_score >= FAIR_USE_CLASSIFIER_MISUSE_THRESHOLD:
            new_stage = 'throttle'
            action = 'throttle'
    elif current_stage == 'throttle':
        if counts['violation_count_7d'] >= 3 and misuse_score >= FAIR_USE_CLASSIFIER_MISUSE_THRESHOLD:
            new_stage = 'restrict'
            action = 'restrict'

    # Apply stage changes
    if new_stage != current_stage:
        update = {
            'stage': new_stage,
            'last_violation_at': datetime.utcnow(),
            'last_classifier_score': misuse_score,
            'last_classifier_type': usage_type,
            'violation_count_7d': counts['violation_count_7d'],
            'violation_count_30d': counts['violation_count_30d'],
        }

        if new_stage == 'throttle':
            update['throttle_until'] = datetime.utcnow() + timedelta(days=7)
        elif new_stage == 'restrict':
            update['restrict_until'] = datetime.utcnow() + timedelta(days=30)

        fair_use_db.update_fair_use_state(uid, update)
        invalidate_enforcement_cache(uid)

    # Record the event (create_fair_use_event auto-generates a case_ref)
    speech = get_rolling_speech_ms(uid)
    event_data = {
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


def is_hard_restricted(uid: str) -> bool:
    """Check if a user is hard-restricted (speech cap enforced as hard block)."""
    if not FAIR_USE_ENABLED or FAIR_USE_KILL_SWITCH:
        return False
    if uid in FAIR_USE_EXEMPT_UIDS:
        return False

    # Single Firestore read — get_enforcement_stage uses cache, but we need
    # restrict_until too, so read the full state once and check stage from it.
    state = fair_use_db.get_fair_use_state(uid)
    stage = state.get('stage', 'none')
    if stage != 'restrict':
        return False

    # Check if restriction has expired
    restrict_until = state.get('restrict_until')
    if restrict_until and isinstance(restrict_until, datetime):
        # Normalize to naive UTC for comparison (Firestore may return aware datetimes)
        if restrict_until.tzinfo is not None:
            restrict_until = restrict_until.replace(tzinfo=None)
        if datetime.utcnow() > restrict_until:
            # Restriction expired, reset to throttle
            fair_use_db.update_fair_use_state(uid, {'stage': 'throttle', 'restrict_until': None})
            invalidate_enforcement_cache(uid)
            return False

    # Check if speech is over hard cap
    speech = get_rolling_speech_ms(uid)
    # In restrict mode, enforce the soft caps as hard caps
    return (
        speech['daily_ms'] > FAIR_USE_DAILY_SPEECH_MS
        or speech['three_day_ms'] > FAIR_USE_3DAY_SPEECH_MS
        or speech['weekly_ms'] > FAIR_USE_WEEKLY_SPEECH_MS
    )


# ---------------------------------------------------------------------------
# Classifier trigger (async, deduplicated)
# ---------------------------------------------------------------------------


async def trigger_classifier_if_needed(uid: str, triggered_caps: list, session_id: str = '') -> None:
    """Check if we should run the LLM classifier and handle enforcement.

    Uses a Redis lock to prevent concurrent runs for the same user.
    Runs asynchronously — does not block the WebSocket path.
    """
    lock_key = _classifier_lock_key(uid)
    lock_token = str(uuid.uuid4())

    try:
        # Acquire lock with cooldown TTL (default 12h — classifier looks at 7d of convos,
        # so re-running every few minutes adds no value; 12h gives ~7% new data per run)
        acquired = redis_client.set(lock_key, lock_token, nx=True, ex=FAIR_USE_CLASSIFIER_COOLDOWN_SECONDS)
        if not acquired:
            logger.info(f'fair_use: classifier already running/recent for {uid}')
            return
    except Exception as e:
        logger.error(f'fair_use: Redis lock error for {uid}: {e}')
        return

    try:
        classifier_result = await _get_classify_user_purpose()(uid)
        escalation = escalate_enforcement(uid, triggered_caps, classifier_result)

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
            # Fetch the case_ref from the just-created event
            latest_events = fair_use_db.get_fair_use_events(uid, limit=1)
            case_ref = latest_events[0].get('case_ref', '') if latest_events else ''
            await _send_fair_use_notification(uid, escalation['action'], case_ref=case_ref)

    except Exception as e:
        logger.error(f'fair_use: classifier/escalation error for {uid}: {e}')
        # Only release lock on error so we can retry sooner;
        # on success, let the 5-minute TTL act as a cooldown to prevent repeated LLM calls
        try:
            _release_lock(lock_key, lock_token)
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
        _get_send_notification()(uid, title, body, data=data)
