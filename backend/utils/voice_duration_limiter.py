"""
Voice-message audio-duration budget enforcement.

Shared rolling 24h budget across all three voice-message STT endpoints
(/v2/voice-message/transcribe, /v2/voice-message/transcribe-stream,
/v2/voice-messages) to prevent unbounded Deepgram cost.

Design:
- Single Redis sorted set per UID with minute-granularity buckets.
- Atomic Lua script: prune stale entries → sum consumed → reject or record.
- Fail-open on Redis errors (consistent with existing rate limiting).
- Separate namespace from fair_use.py DG budget (different purpose/scope).

Constants:
- MAX_SESSION_DURATION_S: 120 seconds per request/session.
- DAILY_BUDGET_MS: 7,200,000 ms (2 hours) per rolling 24h window.
"""

import logging
import time

import av

from database.redis_db import r

logger = logging.getLogger(__name__)

MAX_SESSION_DURATION_S = 120
DAILY_BUDGET_MS = 7_200_000
_WINDOW_S = 86400  # 24 hours in seconds

# ---------------------------------------------------------------------------
# Lua script: atomic consume-or-reject for the rolling-window duration budget.
#
# KEYS[1] = sorted-set key  (voice_duration:{uid})
# ARGV[1] = current timestamp (seconds, float)
# ARGV[2] = window size (seconds)
# ARGV[3] = budget limit (ms)
# ARGV[4] = duration to consume (ms)
#
# Returns: [allowed (0/1), used_ms, remaining_ms]
#
# The sorted set stores (score=timestamp, member=timestamp:random) with value
# encoded in the member as "timestamp_ms:duration_ms".  We use the score for
# range pruning and parse the member for summing.
# ---------------------------------------------------------------------------
_CONSUME_LUA_SRC = """
local key       = KEYS[1]
local now       = tonumber(ARGV[1])
local window    = tonumber(ARGV[2])
local budget    = tonumber(ARGV[3])
local request   = tonumber(ARGV[4])
local force     = tonumber(ARGV[5] or 0)  -- 1 = force-record (skip budget check)

-- 1. Prune entries older than the rolling window
local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

-- 2. Sum consumed ms from remaining entries
local entries = redis.call('ZRANGE', key, 0, -1)
local used = 0
for _, member in ipairs(entries) do
    -- member format: "timestamp_ms:duration_ms:nonce"
    local sep1 = string.find(member, ':', 1, true)
    if sep1 then
        local sep2 = string.find(member, ':', sep1 + 1, true)
        local dur_str
        if sep2 then
            dur_str = string.sub(member, sep1 + 1, sep2 - 1)
        else
            dur_str = string.sub(member, sep1 + 1)
        end
        used = used + tonumber(dur_str)
    end
end

-- 3. Check budget (> so users can consume the full allowance)
-- Skip check when force=1 (post-session recording must always succeed)
if force ~= 1 then
    if used + request > budget and request > 0 then
        return {0, used, math.max(0, budget - used)}
    end
    -- Probe-only (request==0): reject only when already over budget
    if request == 0 and used > budget then
        return {0, used, 0}
    end
end

-- 4. Record consumption (skip if request is zero — probe-only call)
if request > 0 then
    -- Use INCR counter as nonce to guarantee unique members even within
    -- the same millisecond (prevents ZADD overwrite under concurrency).
    local counter = redis.call('INCR', key .. ':seq')
    local member = tostring(math.floor(now * 1000)) .. ':' .. tostring(request) .. ':' .. tostring(counter)
    redis.call('ZADD', key, now, member)
    -- Set TTL = window + 1h buffer so the key self-cleans
    redis.call('EXPIRE', key, window + 3600)
    redis.call('EXPIRE', key .. ':seq', window + 3600)
end

return {1, used + request, math.max(0, budget - used - request)}
"""

try:
    _CONSUME_LUA = r.register_script(_CONSUME_LUA_SRC)
except Exception:
    _CONSUME_LUA = None
    logger.warning('voice_duration_limiter: failed to register Lua script (Redis unavailable?)')


def _budget_key(uid: str) -> str:
    return f'voice_duration:{uid}'


def try_consume_budget(uid: str, duration_ms: int) -> tuple[bool, int, int]:
    """Atomically try to consume duration_ms from the user's rolling 24h budget.

    Args:
        uid: User ID.
        duration_ms: Duration to consume in milliseconds.

    Returns:
        (allowed, used_ms, remaining_ms).
        On Redis error: (True, 0, DAILY_BUDGET_MS) — fail-open.
    """
    if duration_ms < 0:
        return True, 0, DAILY_BUDGET_MS

    if _CONSUME_LUA is None:
        return True, 0, DAILY_BUDGET_MS

    try:
        result = _CONSUME_LUA(
            keys=[_budget_key(uid)],
            args=[time.time(), _WINDOW_S, DAILY_BUDGET_MS, duration_ms],
        )
        allowed = bool(result[0])
        used_ms = int(result[1])
        remaining_ms = int(result[2])
        return allowed, used_ms, remaining_ms
    except Exception as e:
        logger.error(f'voice_duration_limiter: Redis error for uid={uid}: {e}')
        return True, 0, DAILY_BUDGET_MS


def check_budget(uid: str) -> tuple[bool, int, int]:
    """Check remaining budget without consuming.

    Returns:
        (has_budget, used_ms, remaining_ms).
        On Redis error: (True, 0, DAILY_BUDGET_MS) — fail-open.
    """
    return try_consume_budget(uid, 0)


def record_actual_duration(uid: str, duration_ms: int) -> bool:
    """Record actual consumed duration (used by WebSocket on session end).

    For WebSocket sessions where the exact duration isn't known upfront,
    call this after the session ends with the actual duration.
    Uses force-record to always persist the usage even if over budget,
    so the overspend is tracked for subsequent requests.

    Returns True on success, False on error (but still fail-open).
    """
    if duration_ms <= 0:
        return True

    if _CONSUME_LUA is None:
        return True

    try:
        _CONSUME_LUA(
            keys=[_budget_key(uid)],
            args=[time.time(), _WINDOW_S, DAILY_BUDGET_MS, duration_ms, 1],  # force=1
        )
        return True
    except Exception as e:
        logger.error(f'voice_duration_limiter: Redis error recording duration for uid={uid}: {e}')
        return True  # Fail-open


def get_budget_status(uid: str) -> dict:
    """Get the current budget status for a user.

    Returns dict with: daily_limit_ms, used_ms, remaining_ms, exhausted.
    """
    has_budget, used_ms, remaining_ms = check_budget(uid)
    return {
        'daily_limit_ms': DAILY_BUDGET_MS,
        'used_ms': used_ms,
        'remaining_ms': remaining_ms,
        'exhausted': not has_budget,
    }


def compute_pcm_duration_ms(byte_length: int, sample_rate: int, channels: int) -> int:
    """Compute audio duration in milliseconds from PCM byte length.

    PCM 16-bit: bytes = samples * channels * 2
    duration_s = samples / sample_rate = bytes / (sample_rate * channels * 2)
    """
    bytes_per_second = sample_rate * channels * 2
    if bytes_per_second <= 0:
        return 0
    return int((byte_length / bytes_per_second) * 1000)


def compute_max_pcm_bytes(sample_rate: int, channels: int, max_duration_s: int = MAX_SESSION_DURATION_S) -> int:
    """Compute maximum PCM byte size for a given duration.

    Returns the byte limit that corresponds to max_duration_s at the given format.
    """
    return sample_rate * channels * 2 * max_duration_s


def read_wav_duration_ms(file_path: str) -> int | None:
    """Read audio duration using PyAV (FFmpeg).

    Returns duration in milliseconds, or None if the file cannot be read
    or has an invalid/unsupported format.
    """
    try:
        with av.open(file_path) as container:
            if not container.streams.audio:
                return None
            stream = container.streams.audio[0]
            # Prefer container-level duration; fall back to stream-level
            if container.duration is not None:
                duration_s = float(container.duration) / av.time_base
            elif stream.duration is not None and stream.time_base is not None:
                duration_s = float(stream.duration * stream.time_base)
            else:
                return None
            if duration_s <= 0:
                return None
            return int(duration_s * 1000)
    except Exception as e:
        logger.warning(f'voice_duration_limiter: failed to read audio duration from {file_path}: {e}')
        return None
