"""Owner-gated pipeline scheduling over existing durable obligations.

Lifecycle: rollout, default off; owner pipeline-approved; review 2026-11-21.
Redis never proves a seal or completion. Presence only chooses fast scheduling.
"""

from collections.abc import Mapping
from functools import cache
import hashlib
import json
import os
import time

from config import pipeline_attention as policy
from database.redis_db import create_bounded_redis_client
from utils import omi_flags
from utils.conversations import pipeline_metrics as metrics
from utils.observability.fallback import record_fallback


def admitted(uid: str) -> bool:
    if not uid or policy.mode() == 'off':
        return False
    try:
        grant = omi_flags.resolve(policy.COHORT_KEY, uid)
        return grant is not None and grant.enabled
    except Exception:
        return False


def serving(uid: str) -> bool:
    return policy.mode() == 'serve' and admitted(uid)


def notes_serving(uid: str) -> bool:
    return policy.seal_fast_enabled() and serving(uid)


def retry_deadline(obligation) -> float | None:
    """The original obligation owns the one-hour recovery budget, never a retry."""
    since = policy.seconds(obligation.get('first_pending_at')) or policy.seconds(obligation.get('pipeline_capture_end'))
    accepted = policy.seconds(obligation.get('pipeline_dispatch_at'))
    if since is None and accepted is not None:
        since = max(0, accepted - policy.DISPATCH_AFTER_SECONDS)
    return since + policy.MAX_RETRY_SECONDS if since is not None else None


@cache
def client():
    return create_bounded_redis_client(0.5)


def key(uid: str) -> str:
    stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    if stage not in {'prod', 'dev', 'local', 'offline'}:
        raise ValueError('pipeline attention requires explicit runtime stage')
    return stage + ':pipeline-attention:v1:' + hashlib.sha256(uid.encode()).hexdigest()


def unavailable():
    metrics.event('dependency_unavailable')
    record_fallback(
        component='demand_processing',
        from_mode='pipeline_attention',
        to_mode='legacy',
        reason='other',
        outcome='degraded',
    )


def attention(uid: str, *, now=None, redis=None) -> str:
    now = time.time() if now is None else now
    try:
        r = redis or client()
        seen = r.get(key(uid) + ':presence_at')
        if seen is None or now - float(seen) >= policy.LEASE_SECONDS * 2:
            return 'unknown'
        return 'watched' if r.zcount(key(uid) + ':watched', now, '+inf') else 'unwatched'
    except Exception:
        unavailable()
        return 'unknown'


def promoted(uid: str, *, redis=None) -> bool:
    try:
        return bool((redis or client()).get(key(uid) + ':promoted'))
    except Exception:
        unavailable()
        return False


def observe_surface(uid, session, payload, *, now=None, redis=None):
    """#23498 hook: Home is explicit; generic foreground opens only promote."""
    if not serving(uid):
        return
    now = time.time() if now is None else now
    r = redis or client()
    watched = payload.get('foreground') is True and (
        payload.get('home_visible') is True or payload.get('transcript_visible') is True
    )
    p = r.pipeline()
    p.set(key(uid) + ':presence_at', now, ex=policy.LEASE_SECONDS * 2)
    p.zremrangebyscore(key(uid) + ':watched', '-inf', now)
    if watched:
        p.zadd(key(uid) + ':watched', {session: now + policy.LEASE_SECONDS})
    else:
        p.zrem(key(uid) + ':watched', session)
    p.expire(key(uid) + ':watched', policy.LEASE_SECONDS * 2)
    p.execute()


def begin_promotion(uid, *, trigger, now=None, redis=None) -> bool:
    """#24607 hook: bounded epoch; renewals do not buy repeated paid runs."""
    if not serving(uid) or trigger not in {'app_open', 'api_read', 'mcp_read'}:
        return False
    r = redis or client()
    return bool(r.set(key(uid) + ':promoted', trigger, ex=policy.LEASE_SECONDS, nx=True))


def hold_decision(uid, row, obligation, *, projected: bool | None, settled=False, now=None):
    """Ready notes may beat the ceiling; kills and exhausted waits use legacy admission."""
    now = time.time() if now is None else now
    if policy.mode() == 'shadow':
        if admitted(uid):
            metrics.event('shadow')
        return False, None, None
    if not notes_serving(uid):
        return False, None, None
    accepted = policy.seconds(obligation.get('pipeline_dispatch_at'))
    record = bool(obligation.get('pipeline_record'))
    limit = retry_deadline(obligation)
    if limit is not None and now >= limit:
        return False, None, None
    proof = policy.seal_snapshot(row)
    if proof is None:
        metrics.event('seal_denied')
        return False, min(now + 60, limit) if (accepted or record) and limit is not None else None, None
    if projected is not True:
        if projected is None and not accepted and not record:
            return False, None, None  # Untagged old intakes retain their legacy policy.
        metrics.event('projection_pending')
        return False, min(now + 60, limit) if limit is not None else None, None
    if accepted is not None:
        return True, None, proof  # The durable deadline is a ceiling, never a minimum wait.
    state = attention(uid, now=now)
    fast = state == 'watched' or promoted(uid)
    bypass = fast or settled
    if bypass:
        metrics.event('fast' if fast else 'deadline')
    return bypass, None, proof if bypass or record else None


def fast_members(uid, members):
    return (
        serving(uid)
        and policy.seal_fast_enabled()
        and bool(members)
        and all(policy.seal_snapshot(member) is not None for member in members)
        and all(
            (member.get(policy.FIELD) or {}).get('notes_fingerprint') == notes_fingerprint(member) for member in members
        )
        and (attention(uid) == 'watched' or promoted(uid))
    )


def notes_fingerprint(row: Mapping) -> str:
    evidence = {
        'segments': row.get('transcript_segments'),
        'photos': row.get('photos'),
        'content_revision': row.get('sync_content_revision'),
        'upload_revision': row.get('record_upload_revision'),
    }
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()


def prepare_notes_receipt(existing, write, uid, *, now, context=None):
    """Called inside the existing persistence transaction, never emits before commit."""
    context = context or {}
    if not context.get('pipeline_seal') or not write.get('summary_output_present') or write.get('discarded'):
        return None
    if not policy.snapshot_matches(existing, context['pipeline_seal']):
        metrics.event('stale_commit')
        raise ValueError('pipeline seal changed during notes generation')
    old = existing.get(policy.FIELD) or {}
    digest = context['pipeline_fingerprint']
    if old.get('notes_fingerprint') == digest:
        return None
    count = int(old.get('notes_versions', 0)) + 1
    state = old.get('attention', context.get('pipeline_attention', 'unknown'))
    captured = policy.seconds(context.get('pipeline_capture_end'))
    closed = policy.seconds(old.get('sealed_at'))
    write[policy.FIELD] = {
        **old,
        'notes_fingerprint': digest,
        'notes_versions': count,
        'attention': state,
        'first_notes_at': old.get('first_notes_at', now),
        **({'capture_end': captured} if captured is not None else {}),
    }
    return {
        'first': count == 1,
        'attention': state,
        'lane': 'batch',
        'capture_latency': now - captured if captured is not None and captured <= now else None,
        'close_latency': now - closed if closed is not None and closed <= now else None,
        'capture_seal_latency': (
            closed - captured if captured is not None and closed is not None and captured <= closed else None
        ),
        'rewrites': count - 1,
        'reason': 'initial' if count == 1 else 'changed_revision',
    }
