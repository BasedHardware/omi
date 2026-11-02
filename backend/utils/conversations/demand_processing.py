"""Redis scheduling index over durable finalization / sync outbox obligations.

Cloud Tasks remains the wakeup owner; Redis contains IDs and scheduling metadata
only. Losing Redis fails eager, leaving durable retries and reconciliation intact.
No Firestore read is performed by admission, promotion or queue-age publication.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from prometheus_client import Counter, Gauge
from config.demand_processing import (
    enabled,
    surface_reporting_enabled,
    OPEN_LEASE_SECONDS,
    RECENT_SECONDS,
    CEILING_HEADROOM_SECONDS,
    BLOCKED_WAIT_SECONDS,
    OPEN_PROMOTE_LIMIT,
)

logger = logging.getLogger(__name__)
AGE = Gauge('omi_demand_processing_queue_age_seconds', 'Oldest waiting obligation by tier', ['tier'])
EVENTS = Counter('omi_demand_processing_total', 'Demand scheduling outcomes', ['outcome'])
PREFIX = 'demand-processing:v1:'
TTL = 2 * 86400


def prefix() -> str:
    stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    if not stage:
        # Desktop workers already carry this explicit deployment identity.
        channel = os.getenv('OMI_DESKTOP_BACKEND_RELEASE_CHANNEL', '').strip().lower()
        stage = {'production': 'prod', 'development': 'dev'}.get(channel, '')
    if stage not in {'prod', 'dev', 'local', 'offline'}:
        raise ValueError('demand scheduling requires an explicit runtime stage')
    return stage + ':' + PREFIX


def client():
    from database.redis_db import create_bounded_redis_client

    return create_bounded_redis_client(0.5)


def owner_key(uid: str) -> str:
    return prefix() + hashlib.sha256(uid.encode()).hexdigest()


def tier(last_open: float | None, open_until: float, now: float) -> int:
    if open_until > now:
        return 0
    return 1 if last_open is not None and now - last_open <= RECENT_SECONDS else 2


def user_tier(uid: str, *, now: float | None = None, redis=None) -> int:
    now = time.time() if now is None else now
    r = redis or client()
    last = r.get(owner_key(uid) + ':last_surface_open_at')
    return tier(
        float(last) if last else None, now + 1 if r.zcount(owner_key(uid) + ':surfaces', now, '+inf') else 0, now
    )


def _fallback() -> None:
    from utils.observability.fallback import record_fallback

    EVENTS.labels('dependency_unavailable').inc()
    record_fallback(
        component='demand_processing',
        from_mode='scheduled',
        to_mode='eager',
        reason='other',
        outcome='degraded',
        log=logger,
    )


def _wake(row: dict, *, immediate: bool = False, now: float | None = None) -> None:
    from utils.cloud_tasks import enqueue_named_task

    now = time.time() if now is None else now
    binding = row['binding']
    # Promotion gets a separate name; the durable generation/token still fences execution.
    name = row['name'] + (f'-open-{int(now // 30)}' if immediate else '')
    enqueue_named_task(
        binding['queue'],
        binding['handler'],
        name,
        row['payload'],
        audience=binding['audience'],
        invoker_sa=binding['invoker_sa'],
        schedule_at=int(max(now, row['due_at']) if immediate else row['due_at']),
    )


def schedule(
    uid: str,
    obligation: str,
    payload: dict,
    binding: dict,
    name: str,
    *,
    now: float | None = None,
    not_before: float | None = None,
    effects_only: bool = False,
    immediate: bool = False,
) -> bool:
    """Index after durable acceptance, then enqueue. False means use the eager path."""
    if not enabled(uid):
        return False
    now = time.time() if now is None else now
    try:
        r = client()
        old = r.get(prefix() + obligation)
        previous = json.loads(old) if old else {}
        started = previous.get('started_at', now)
        priority = user_tier(uid, now=now, redis=r)
        if immediate:
            priority = 0
        # Sync's trailing-edge settle is a content boundary, not an idle-capacity
        # delay. Only invisible effects may bypass it on explicit demand.
        settle_at = max(now, not_before or now)
        due = now if effects_only and priority == 0 else settle_at
        if effects_only:
            due = min(started + CEILING_HEADROOM_SECONDS, due)
        row = dict(
            obligation=obligation,
            owner=owner_key(uid),
            started_at=started,
            tier=priority,
            due_at=due,
            not_before=now if effects_only else settle_at,
            payload=payload,
            binding=binding,
            name=name,
        )
        p = r.pipeline()
        p.set(prefix() + obligation, json.dumps(row), ex=TTL)
        p.zadd(owner_key(uid) + ':pending', {obligation: started})
        p.expire(owner_key(uid) + ':pending', TTL)
        for t in range(3):
            p.zrem(prefix() + f'queue:{t}', obligation)
            p.zrem(prefix() + f'ready:{t}', obligation)
        p.zadd(prefix() + f'queue:{priority}', {obligation: started})
        p.expire(prefix() + f'queue:{priority}', TTL)
        p.zadd(prefix() + f'ready:{priority}', {obligation: due})
        p.expire(prefix() + f'ready:{priority}', TTL)
        p.execute()
        _wake(row)
        EVENTS.labels('scheduled').inc()
        return True
    except Exception:
        _fallback()
        return False


def promote(uid: str, *, hours: int = 6, limit: int | None = 100, now: float | None = None) -> dict:
    """Wake only this authenticated owner's indexed debt, newest first, without database scans."""
    now = time.time() if now is None else now
    r = client()
    query = {} if limit is None else {'start': 0, 'num': limit + 1}
    pending = r.zrevrangebyscore(owner_key(uid) + ':pending', now, now - hours * 3600, **query)
    count = 0
    for raw in pending if limit is None else pending[:limit]:
        obligation = raw.decode() if isinstance(raw, bytes) else raw
        if _promote_member(uid, obligation, r, now):
            count += 1
    EVENTS.labels('promoted').inc(count)
    return {
        'status': 'processing' if count else 'no_indexed_pending_work',
        'promoted': count,
        'has_more': limit is not None and len(pending) > limit,
        'ready': False,
    }


def _promote_member(uid: str, obligation: str, r: Any, now: float) -> bool:
    value = r.get(prefix() + obligation)
    if not value:
        r.zrem(owner_key(uid) + ':pending', obligation)
        return False
    row = json.loads(value)
    if row['owner'] != owner_key(uid):
        return False
    due = max(now, row.get('not_before', now))
    row.update(tier=0, due_at=due)
    p = r.pipeline()
    p.set(prefix() + obligation, json.dumps(row), ex=TTL)
    for priority in range(3):
        p.zrem(prefix() + f'queue:{priority}', obligation)
        p.zrem(prefix() + f'ready:{priority}', obligation)
    p.zadd(prefix() + 'queue:0', {obligation: row['started_at']})
    p.expire(prefix() + 'queue:0', TTL)
    p.zadd(prefix() + 'ready:0', {obligation: due})
    p.expire(prefix() + 'ready:0', TTL)
    p.execute()
    _wake(row, immediate=True, now=now)
    return True


def promote_conversation_effects(uid: str, conversation_id: str) -> None:
    if not enabled(uid):
        return
    from utils.sync.reprocess import key

    try:
        _promote_member(uid, key(uid, conversation_id + '\0effects'), client(), time.time())
    except Exception:
        _fallback()


def observe_surface(uid: str, session: str, payload: dict, *, now: float | None = None) -> None:
    if not enabled(uid) or not surface_reporting_enabled():
        return
    foreground = payload.get('surface_open')
    if not isinstance(foreground, bool) or not isinstance(payload.get('transcript_visible'), bool):
        return
    now = time.time() if now is None else now
    try:
        r = client()
        base = owner_key(uid)
        was_open = bool(r.zcount(base + ':surfaces', now, '+inf'))
        p = r.pipeline()
        p.zremrangebyscore(base + ':surfaces', '-inf', now)
        if foreground:
            p.zadd(base + ':surfaces', {session: now + OPEN_LEASE_SECONDS})
            p.set(base + ':last_surface_open_at', now, ex=RECENT_SECONDS + 1)
        else:
            p.zrem(base + ':surfaces', session)
        p.expire(base + ':surfaces', OPEN_LEASE_SECONDS * 2)
        p.execute()
        if foreground and not was_open:
            # Newest indexed work, including older debt, bounded per open edge: an
            # unbounded wake is a Cloud Task per obligation and a tier-0 backlog.
            promote(uid, hours=48, limit=OPEN_PROMOTE_LIMIT, now=now)
    except Exception:
        _fallback()


def admit(obligation: str, *, now: float | None = None, token: str | int | None = None) -> bool:
    """Ready 0 -> 1 -> 2. Overdue debt escapes starvation with one minute headroom.

    Scheduling waits happen before any durable claim, so they spend no processing
    retry budget. Remove admitted rows from the waiting index; durable leases own
    execution and the existing reconciler repairs crashes.
    """
    if not enabled():
        return True
    now = time.time() if now is None else now
    try:
        r = client()
        raw = r.get(prefix() + obligation)
        if not raw:
            return True
        row = json.loads(raw)
        payload = row['payload']
        if token is not None and token != payload.get('dispatch_generation', payload.get('task_token')):
            return True  # Let the durable worker acknowledge the stale delivery.

        def postpone(blocked=False):
            from utils.cloud_tasks import enqueue_named_task

            binding = row['binding']
            wake_at = max(now + 5, row['due_at'])
            if blocked:
                # Each wait is a new named task: back off, clamped to the escape.
                escape = row['started_at'] + CEILING_HEADROOM_SECONDS
                wake_at = max(wake_at, min(now + BLOCKED_WAIT_SECONDS, escape))
            enqueue_named_task(
                binding['queue'],
                binding['handler'],
                row['name'] + f'-wait-{int(wake_at)}',
                row['payload'],
                audience=binding['audience'],
                invoker_sa=binding['invoker_sa'],
                schedule_at=int(wake_at),
            )
            return False

        if row['due_at'] > now:
            return postpone()
        overdue = now - row['started_at'] >= CEILING_HEADROOM_SECONDS
        for priority in range(3):
            queue = prefix() + f'queue:{priority}'
            # Prune expired rows without allowing stale index entries to block drain.
            r.zremrangebyscore(queue, '-inf', now - TTL)
            oldest = r.zrange(queue, 0, 0, withscores=True)
            AGE.labels(str(priority)).set(max(0, now - oldest[0][1]) if oldest else 0)
            ready = prefix() + f'ready:{priority}'
            r.zremrangebyscore(ready, '-inf', now - TTL)
            if priority < row['tier'] and r.zcount(ready, '-inf', now) and not overdue:
                return postpone(blocked=True)
        p = r.pipeline()
        for priority in range(3):
            p.zrem(prefix() + f'queue:{priority}', obligation)
            p.zrem(prefix() + f'ready:{priority}', obligation)
        p.zrem(row['owner'] + ':pending', obligation)
        p.delete(prefix() + obligation)
        p.execute()
        EVENTS.labels('admitted').inc()
        return True
    except Exception:
        _fallback()
        return True


def process_recent(uid: str, *, hours: int = 6, limit: int = 20) -> dict:
    from config.demand_processing import tool_enabled

    if not uid:
        raise PermissionError('authenticated owner required')
    if type(hours) is not int or not 1 <= hours <= 6 or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('hours must be 1..6 and limit 1..20')
    if not tool_enabled(uid):
        return {'status': 'disabled', 'ready': False}
    r = client()
    if not r.set(owner_key(uid) + ':process_recent_rate', '1', ex=30, nx=True):
        return {'status': 'rate_limited', 'retry_after_seconds': 30, 'ready': False}
    return promote(uid, hours=hours, limit=limit)


def queue_age(priority: int) -> float:
    if not enabled():
        return 0
    try:
        now = time.time()
        r = client()
        queue = prefix() + f'queue:{priority}'
        r.zremrangebyscore(queue, '-inf', now - TTL)
        oldest = r.zrange(queue, 0, 0, withscores=True)
        return max(0.0, now - oldest[0][1]) if oldest else 0.0
    except Exception:
        return float('nan')  # Missing dependency must not advertise a healthy empty queue.


for _tier in range(3):
    AGE.labels(str(_tier)).set_function(lambda priority=_tier: queue_age(priority))


def lazy_enrichment_enabled(uid: str) -> bool:
    from config.demand_processing import lazy_enabled

    if not lazy_enabled(uid):
        return False
    # Request-scoped credentials cannot enter a durable task. Preserve the live
    # BYOK path rather than silently substituting platform credentials later.
    from utils.byok import has_byok_keys

    return not has_byok_keys()
