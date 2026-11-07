"""Bounded record scheduling hints; Firestore claim and custody proof are authority."""

import json
import time
import asyncio
from typing import Any

from config import pipeline_attention as policy
from config.record_audio import record_identity
from database.batch_pipeline_store import FirestoreStore
from database.redis_db import get_async_redis_client
from database import conversations
from utils.conversations import pipeline_attention as attention
from utils.conversations import pipeline_metrics as metrics
from utils.sync.stage import current_stage

TTL = 2 * 86400


def base():
    return current_stage() + ':pipeline-record:v1:'


def register(uid, conversation_id, enqueued_at, *, redis=None):
    if not policy.record_fast_enabled() or not attention.serving(uid):
        return
    try:
        r = redis or attention.client()
        _, segment = record_identity(uid, conversation_id)
        p = r.pipeline()
        p.set(
            base() + segment,
            json.dumps({'uid': uid, 'conversation_id': conversation_id, 'enqueued_at': enqueued_at}),
            ex=TTL,
            nx=True,
        )
        # NX preserves original age on registration retries.
        p.zadd(base() + 'age', {segment: enqueued_at}, nx=True)
        p.zadd(base() + 'fresh', {segment: enqueued_at}, nx=True)
        p.zadd(base() + 'due', {segment: 0}, nx=True)
        p.zadd(attention.key(uid) + ':records', {segment: enqueued_at}, nx=True)
        p.expire(attention.key(uid) + ':records', TTL)
        p.expire(base() + 'age', TTL)
        p.expire(base() + 'fresh', TTL)
        p.expire(base() + 'due', TTL)
        p.execute()
    except Exception:
        attention.unavailable()


def sealed(uid, conversation_id, row, *, store=None, now=None):
    """Wake a parked deterministic obligation only after a committed full seal."""
    if (
        not policy.record_fast_enabled()
        or not attention.serving(uid)
        or policy.seal_snapshot(row, require_content_revision=False) is None
    ):
        return False
    now = time.time() if now is None else now
    _, segment = record_identity(uid, conversation_id)
    store = store or FirestoreStore('batch_pipeline_' + current_stage())

    def wake(tx):
        pending = tx.get('jobs', segment)
        if not pending or pending.get('state') != 'record_pending' or pending.get('owner_id') != uid:
            return None
        pending['pipeline_record_wake_at'] = now
        if pending.get('pipeline_record_lease_until', 0) <= now and (
            pending.get('pipeline_record_deferred') or pending.get('available_at', 0) <= now
        ):
            pending['available_at'] = min(pending.get('available_at', now), now)
        tx.put('jobs', segment, pending)
        return pending.get('enqueued_at'), pending['available_at']

    try:
        result = store.run(wake)
        if result is not None:
            enqueued, available = result
            if enqueued is not None:
                register(uid, conversation_id, enqueued)
            defer(segment, available)
            r = attention.client()
            p = r.pipeline()
            p.lpush(base() + 'wakes', segment)
            p.ltrim(base() + 'wakes', 0, 999)
            p.expire(base() + 'wakes', TTL)
            p.execute()
            metrics.event('record_wake')
            return True
    except Exception:
        attention.unavailable()
    return False


async def wait_for_wake(stop):
    """A bounded interrupt of the existing poll, with no new durable queue."""
    if policy.mode() != 'serve' or not policy.record_fast_enabled():
        try:
            await asyncio.wait_for(stop.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass
        return
    try:
        redis = await get_async_redis_client()
        await asyncio.wait_for(redis.blpop(base() + 'wakes', timeout=20), timeout=21)
    except (Exception, asyncio.TimeoutError):
        attention.unavailable()
        try:
            await asyncio.wait_for(stop.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass


def select(legacy, batch_size, *, redis=None, now=None):
    """One in four oldest slots; fewer slots alternate passes. Per-owner cap one.

    The existing poll is a permanent backstop for missing Redis hints. A stale
    hint is never admission: the Firestore due/lease check still runs.
    """
    if policy.mode() != 'serve' or not policy.record_fast_enabled():
        return legacy
    try:
        r = redis or attention.client()
        now = time.time() if now is None else now
        turn = r.incr(base() + 'turn')
        r.expire(base() + 'turn', TTL)
        reserve = max(1, (batch_size + 3) // 4) if batch_size >= 4 or turn % 2 == 0 else 0
        decode = lambda value: value.decode() if isinstance(value, bytes) else value
        aged = [decode(value) for value in r.zrange(base() + 'age', 0, batch_size * 4 - 1)]
        fresh = [decode(value) for value in r.zrevrange(base() + 'fresh', 0, batch_size * 4 - 1)]
        metadata: dict[str, dict[str, Any]] = {}
        for segment in dict.fromkeys(list(legacy) + aged + fresh):
            raw = r.get(base() + segment)
            meta: dict[str, Any] = json.loads(raw) if raw else {'uid': segment, 'enqueued_at': float('-inf')}
            if segment not in legacy and (
                not raw or not attention.serving(meta['uid']) or (r.zscore(base() + 'due', segment) or 0) > now
            ):
                continue
            metadata[segment] = meta
        oldest = sorted(metadata, key=lambda s: metadata[s]['enqueued_at'])
        newest = sorted(metadata, key=lambda s: metadata[s]['enqueued_at'], reverse=True)
        watched = [
            s
            for s in newest
            if s not in legacy and attention.attention(metadata[s]['uid'], now=now, redis=r) == 'watched'
        ]
        candidates, owners = [], set()
        for segment in oldest if reserve else []:
            owner = metadata[segment]['uid']
            if owner in owners:
                continue
            owners.add(owner)
            candidates.append(segment)
            if len(candidates) >= reserve:
                break
        for segment in watched + newest:
            if segment in candidates:
                continue
            owner = metadata[segment]['uid']
            if owner in owners:
                continue
            owners.add(owner)
            candidates.append(segment)
            if len(candidates) >= batch_size:
                break
        return candidates
    except Exception:
        attention.unavailable()
        return legacy


def defer(segment, due, *, redis=None):
    if policy.mode() != 'serve' or not policy.record_fast_enabled():
        return
    try:
        r = redis or attention.client()
        r.zadd(base() + 'due', {segment: due})
        r.expire(base() + 'due', TTL)
    except Exception:
        attention.unavailable()


def completed(segment, *, redis=None):
    if policy.mode() == 'off':
        return
    try:
        r = redis or attention.client()
        raw = r.get(base() + segment)
        meta = json.loads(raw) if raw else {}
        p = r.pipeline()
        p.zrem(base() + 'age', segment)
        p.zrem(base() + 'fresh', segment)
        p.zrem(base() + 'due', segment)
        p.delete(base() + segment)
        if meta.get('uid'):
            p.zrem(attention.key(meta['uid']) + ':records', segment)
        p.execute()
    except Exception:
        attention.unavailable()


def promote_owner(uid, *, limit=20, now=None):
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('record promotion limit must be 1..20')
    if not policy.record_fast_enabled() or not attention.serving(uid):
        return 0
    r = attention.client()
    count = 0
    for raw in r.zrevrange(attention.key(uid) + ':records', 0, min(20, limit) - 1):
        segment = raw.decode() if isinstance(raw, bytes) else raw
        value = r.get(base() + segment)
        meta = json.loads(value) if value else {}
        if meta.get('uid') != uid:
            r.zrem(attention.key(uid) + ':records', segment)
            continue
        row = conversations.get_conversation_raw_snapshot(uid, meta['conversation_id'])
        if row and sealed(uid, meta['conversation_id'], row, now=now):
            count += 1
    return count
