"""Bounded record scheduling hints; Firestore claim and custody proof are authority."""

import json
import time
import asyncio
from typing import Any
from dataclasses import dataclass
from collections.abc import Mapping

from config import pipeline_attention as policy
from config.record_audio import record_identity
from database.batch_pipeline_store import FirestoreStore
from database.redis_db import get_async_redis_client
from database import conversations
from utils.conversations import pipeline_attention as attention
from utils.conversations import pipeline_metrics as metrics
from utils.sync.stage import current_stage

TTL = 2 * 86400


@dataclass(frozen=True)
class RecordReceipt:
    admitted: bool | None = None
    projected: bool | None = None
    capture_end: float | None = None


def _capture_end(intake):
    """Complete admitted audio extent, never a per-unit/preview speech clock."""
    ranges = intake.get('record_ranges')
    ids = intake.get('segment_ids')
    if (
        not isinstance(ranges, list)
        or not ranges
        or not isinstance(ids, list)
        or len(ids) != len(ranges)
        or not all(isinstance(sid, str) and sid for sid in ids)
        or len(set(ids)) != len(ids)
    ):
        return None
    ends = []
    for span in ranges:
        if not isinstance(span, Mapping):
            return None
        start, end = policy.seconds(span.get('start')), policy.seconds(span.get('end'))
        if start is None or end is None or end <= start:
            return None
        ends.append(end)
    return max(ends)


def receipt(uid, conversation_id, row, *, require_projection=True, store=None, firestore_client=None):
    """Read the pinned native intake and its all-sibling completion receipt.

    None admission denotes pre-policy debt. The intake's immutable record ranges
    own the physical clock even before all text units have projected.
    """
    content, _ = record_identity(uid, conversation_id)
    job_id = 'bp_' + content
    try:
        store = store or FirestoreStore('batch_pipeline_' + current_stage(), firestore_client=firestore_client)

        def read(tx):
            intake = tx.get('intakes', job_id) or {}
            barrier = intake.get('pipeline_record_barrier')
            if not barrier:
                return RecordReceipt()
            proof = policy.seal_snapshot(row, require_content_revision=False)
            if (
                proof is None
                or intake.get('owner_id') != uid
                or intake.get('conversation_id') != conversation_id
                or intake.get('content_id') != content
                or barrier.get('record_lane_owner') != proof['owner']
                or type(barrier.get('record_upload_revision')) is not int
                or barrier['record_upload_revision'] != proof['upload_revision']
                or barrier.get('status') != 'completed'
                or barrier.get('record_audio_partial')
            ):
                return RecordReceipt(False, False)
            captured = _capture_end(intake)
            if not require_projection:
                return RecordReceipt(True, None, captured)
            revision = row.get('record_projection_revision')
            if type(revision) is not int or revision < 1:
                return RecordReceipt(True, False, captured)
            ledger = tx.get('content', f'{uid}/{content}') or {}
            binding = ledger.get('batch_pipeline') or {}
            ids = intake.get('segment_ids')
            completed = (
                isinstance(ids, list)
                and bool(ids)
                and binding.get('namespace') == store.namespace
                and binding.get('segment_ids') == ids
                and ledger.get('status') == 'completed'
                and ledger.get('job_id') == job_id
                and ledger.get('dispatch_protocol') == 'batch_v1'
            )
            return RecordReceipt(True, completed, captured)

        return store.run(read)
    except Exception:
        attention.unavailable()
        return RecordReceipt(False, False)


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
    if stop.is_set():
        return
    try:
        redis = await get_async_redis_client()
        wake = asyncio.create_task(redis.blpop(base() + 'wakes', timeout=20))
        stopped = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait({wake, stopped}, timeout=21, return_when=asyncio.FIRST_COMPLETED)
            if stopped in done:
                return
            if wake not in done:
                raise asyncio.TimeoutError
            if wake.result():
                # Coalesce a seal burst into one drain pass; durable polling
                # covers hints arriving concurrently with this deletion.
                await redis.delete(base() + 'wakes')
        finally:
            wake.cancel()
            stopped.cancel()
            await asyncio.gather(wake, stopped, return_exceptions=True)
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
