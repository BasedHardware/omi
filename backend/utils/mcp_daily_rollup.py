"""Daily MCP activity rollup: one PostHog snapshot per uid/client/UTC day (SCA-3665).

``MCP Tool Use Succeeded`` sends one PostHog event per successful call
(about 71k a day, 80% from a few always-on streams). The Omi TV MCP
DAU/WAU/MAU only needs, per uid/client/UTC day, the qualifying call count and
the cadence statistics ``web/admin/lib/wall-mcp.ts`` uses to exclude
unattended streams. This module keeps those statistics in Redis and emits a
cumulative ``MCP Daily Activity`` snapshot at most once per
``FLUSH_DELAY_SECONDS`` per key, plus a final one after the day ends, so the
reader stays exact for complete days and at most one flush behind for today.

Writes per successful call: one atomic Lua call on the key's hash, its TTL and
the day's dirty set. Kill switch: ``MCP_DAILY_ROLLUP_ENABLED`` (on unless set
to a false value). Every failure is fail-open; the raw per-call event is
emitted independently and never depends on Redis.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import database.redis_db as redis_db
from utils.product_telemetry import emit_product_event

logger = logging.getLogger(__name__)

MCP_DAILY_ACTIVITY = "MCP Daily Activity"
ROLLUP_SCHEMA_VERSION = 1
KEY_PREFIX = "mcp:roll"
DIRTY_PREFIX = "mcp:roll:dirty"
KEY_TTL_SECONDS = 3 * 86400
FLUSH_DELAY_SECONDS = 1800
SWEEP_INTERVAL_SECONDS = 60
SWEEP_BATCH = 500
QUALIFYING_INITIATORS = frozenset({"user", "unknown"})
ENABLED_ENV = "MCP_DAILY_ROLLUP_ENABLED"

# KEYS[1] stats hash, KEYS[2] dirty zset. ARGV: tool, eligible (0/1), flush delay, ttl,
# and an optional fixed clock in seconds (tests only; production passes '').
# Redis TIME orders calls across instances, so gaps are never negative. Gaps are
# whole seconds, matching dateDiff('second', ...) on the raw stream. Ineligible
# (scheduled_agent) calls count only toward ``raw``, as in the raw reader.
_RECORD = """
local now = tonumber(ARGV[5]) or tonumber(redis.call('TIME')[1])
local key = KEYS[1]
redis.call('HINCRBY', key, 'raw', 1)
if ARGV[2] == '1' then
  local last = tonumber(redis.call('HGET', key, 'last') or '-1')
  if last < 0 then
    redis.call('HSET', key, 'first', now)
  else
    local gap = now - last
    if gap > 0 then
      redis.call('HINCRBY', key, 'pg', 1)
      redis.call('HINCRBY', key, 'sg', gap)
      redis.call('HINCRBY', key, 'sg2', gap * gap)
    end
  end
  redis.call('HSET', key, 'last', now)
  redis.call('HINCRBY', key, 'n', 1)
  local t = redis.call('HINCRBY', key, 't:' .. ARGV[1], 1)
  local dom = tonumber(redis.call('HGET', key, 'dom') or '0')
  if t > dom then redis.call('HSET', key, 'dom', t) end
end
redis.call('EXPIRE', key, tonumber(ARGV[4]))
redis.call('ZADD', KEYS[2], 'NX', now + tonumber(ARGV[3]), key)
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[4]))
return now
"""

_sweeper_lock = threading.Lock()
_sweeper_started = False


def enabled() -> bool:
    raw = os.getenv(ENABLED_ENV)
    return raw is None or raw.strip().lower() not in {"0", "false", "off", "no"}


def _day(now: datetime) -> str:
    return now.strftime("%Y%m%d")


def stats_key(day: str, uid: str, client: str) -> str:
    return f"{KEY_PREFIX}:{day}:{client}:{uid}"


def dirty_key(day: str) -> str:
    return f"{DIRTY_PREFIX}:{day}"


def record_success(
    *,
    uid: str,
    client: str,
    tool: str,
    initiator: str,
    now: Optional[datetime] = None,
    redis: Any = None,
    clock_s: Optional[int] = None,
) -> bool:
    """Accumulate one successful call; returns False when skipped or Redis failed."""
    if not enabled() or not uid:
        return False
    r = redis if redis is not None else redis_db.r
    day = _day(now or datetime.now(timezone.utc))
    eligible = "1" if initiator in QUALIFYING_INITIATORS else "0"
    try:
        r.eval(
            _RECORD,
            2,
            stats_key(day, uid, client),
            dirty_key(day),
            tool,
            eligible,
            FLUSH_DELAY_SECONDS,
            KEY_TTL_SECONDS,
            "" if clock_s is None else str(int(clock_s)),
        )
    except Exception as exc:  # noqa: BLE001 - telemetry must fail open
        logger.warning("mcp daily rollup record failed error=%s", type(exc).__name__)
        return False
    _ensure_sweeper()
    return True


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def snapshot_properties(day: str, client: str, stats: dict) -> dict:
    """Cumulative counters for one uid/client/UTC day; the reader keeps the largest raw count."""
    fields = {_text(k): _text(v) for k, v in stats.items()}
    as_int = lambda name: int(fields.get(name, "0") or 0)  # noqa: E731
    first, last = as_int("first"), as_int("last")
    return {
        "utc_day": f"{day[:4]}-{day[4:6]}-{day[6:]}",
        "client": client,
        "raw_calls": as_int("raw"),
        "calls": as_int("n"),
        "positive_gaps": as_int("pg"),
        "sum_gap_s": as_int("sg"),
        "sum_gap_sq_s": as_int("sg2"),
        "span_s": max(0, last - first) if as_int("n") else 0,
        "dominant_tool_calls": as_int("dom"),
        "last_call_at": datetime.fromtimestamp(last, timezone.utc).isoformat() if as_int("n") else None,
        "last_call_s": last if as_int("n") else 0,
        "schema_version": ROLLUP_SCHEMA_VERSION,
        "source_platform": "mcp",
        "$process_person_profile": False,
    }


def flush_due(
    emit: Callable[..., bool], *, now: Optional[datetime] = None, redis: Any = None, batch: int = SWEEP_BATCH
) -> int:
    """Emit snapshots for today's due keys and every key of earlier days still dirty.

    ZREM is the claim: across instances exactly one sweeper emits a given
    dirty entry. A later call re-adds the key, so the next snapshot follows.
    A snapshot the capture client refuses is re-queued for the next sweep.
    """
    if not enabled():
        return 0
    r = redis if redis is not None else redis_db.r
    now = now or datetime.now(timezone.utc)
    emitted = 0
    for offset, cutoff in ((0, now.timestamp()), (1, "+inf"), (2, "+inf")):
        day = _day(now - timedelta(days=offset))
        dirty = dirty_key(day)
        try:
            members = r.zrangebyscore(dirty, "-inf", cutoff, start=0, num=batch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp daily rollup sweep failed error=%s", type(exc).__name__)
            return emitted
        for member in members:
            key = _text(member)
            try:
                if not r.zrem(dirty, key):
                    continue
                stats = r.hgetall(key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("mcp daily rollup claim failed error=%s", type(exc).__name__)
                continue
            parts = key.split(":", 4)
            if len(parts) != 5 or not stats:
                continue
            _, _, key_day, client, uid = parts
            accepted = emit(
                uid=uid,
                event=MCP_DAILY_ACTIVITY,
                properties=snapshot_properties(key_day, client, stats),
                timestamp=now,
            )
            if accepted is False:
                # Not captured: put the claim back so a later sweep retries (bounded by the key TTL).
                try:
                    r.zadd(dirty, {key: now.timestamp() + SWEEP_INTERVAL_SECONDS}, nx=True)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("mcp daily rollup requeue failed error=%s", type(exc).__name__)
                continue
            emitted += 1
    return emitted


def _sweep_forever() -> None:
    while True:
        time.sleep(SWEEP_INTERVAL_SECONDS)
        try:
            flush_due(emit_product_event)
        except Exception as exc:  # noqa: BLE001 - the sweeper must survive
            logger.warning("mcp daily rollup sweeper error=%s", type(exc).__name__)


def _ensure_sweeper() -> None:
    """Start one daemon sweeper per process that serves MCP traffic."""
    global _sweeper_started
    if _sweeper_started:
        return
    with _sweeper_lock:
        if _sweeper_started:
            return
        threading.Thread(target=_sweep_forever, name="mcp-daily-rollup", daemon=True).start()
        _sweeper_started = True
