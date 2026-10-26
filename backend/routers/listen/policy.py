"""Session-start Redis boundary. Never called by the audio/frame path."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import logging

from config.policy.listen import ListenSessionPolicy, resolve_listen_policy
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
POLICY_TTL_SECONDS = 24 * 60 * 60  # Six times the clients' four-hour recording rotation.
REDIS_TIMEOUT_SECONDS = 0.075  # Total get/CAS/read deadline, not a per-command budget.
MAX_POLICY_BYTES = 64 * 1024


def policy_key(uid: str, identity: str) -> str:
    digest = hashlib.sha256(json.dumps([uid, identity], separators=(',', ':')).encode()).hexdigest()
    return f'listen:session-policy:v1:{digest}'


@lru_cache(maxsize=1)
def _source_counter():
    from prometheus_client import Counter

    return Counter('omi_listen_session_policy_total', 'Listen policy at session start', ['policy_source'])


def record_source(source, policy):
    try:
        _source_counter().labels(policy_source=source).inc()
        if source == 'fallback':
            record_fallback(
                component='stt_live_session', from_mode='none', to_mode='none', reason='other', outcome='recovered'
            )
        logger.info(
            'event=listen_session_policy policy_source=%s policy_id=%s arm=%s window_arm=%s count=1',
            source,
            policy.policy_id,
            policy.routing_arm,
            'window' if policy.window_allocated else 'control',
        )
    except Exception:
        pass  # Observability never holds up the socket.


@asynccontextmanager
async def _client(injected=None):
    if injected is not None:
        yield injected
    else:
        from database.redis_db import get_async_redis_client

        # The process-owned async client pools connections across sessions.
        # Do not enter/close it here: lifecycle and shutdown belong to its owner.
        yield await get_async_redis_client()


def _decode(raw):
    if not isinstance(raw, (str, bytes)) or len(raw) > MAX_POLICY_BYTES:
        raise ValueError('invalid listen policy payload')
    return ListenSessionPolicy.from_dict(json.loads(raw))


async def load_listen_policy(uid, identity, *, resolver, redis_client=None):
    """First writer wins; a restart loads without consulting current env.

    A healthy first write is resolved; invalid state or Redis faults are fallback.
    One total timeout covers pool acquisition and I/O. No worker thread is used.
    """
    candidate = None
    loaded = None
    try:
        async with asyncio.timeout(REDIS_TIMEOUT_SECONDS):
            async with _client(redis_client) as client:
                key = policy_key(uid, identity)
                raw = await client.get(key)
                if raw is not None:
                    policy = loaded = _decode(raw)
                    await client.expire(key, POLICY_TTL_SECONDS)
                    return policy, 'redis'
                candidate = resolver()
                payload = json.dumps(candidate.to_dict(), sort_keys=True, separators=(',', ':'))
                if len(payload) > MAX_POLICY_BYTES:
                    raise ValueError('listen policy exceeds bounded payload')
                if not await client.set(key, payload, nx=True, ex=POLICY_TTL_SECONDS):
                    policy = loaded = _decode(await client.get(key))
                    return policy, 'redis'
                return candidate, 'resolved'
    except Exception:
        # A failed TTL refresh/connection close must not discard a valid stamp.
        if loaded is not None:
            return loaded, 'redis'
        # Do not log exception text, keys, UID, endpoints, or config contents.
        return candidate if candidate is not None else resolver(), 'fallback'


async def persist_conversation_policy(host, conversation_id):
    """Additive alias at conversation lifecycle boundaries, never per frame."""
    policy = getattr(host.state, 'listen_policy', None)
    if policy is None:
        return
    try:
        async with asyncio.timeout(REDIS_TIMEOUT_SECONDS):
            payload = json.dumps(policy.to_dict(), sort_keys=True, separators=(',', ':'))
            # A rollover creates distinct recording and conversation UUIDs.
            # Clients may reconnect using either ID; both must name the stamp.
            identities = dict.fromkeys((conversation_id, getattr(host, 'recording_session_id', None)))
            async with _client() as client:
                for identity in identities:
                    if identity:
                        await client.set(
                            policy_key(host.request.uid, identity), payload, nx=True, ex=POLICY_TTL_SECONDS
                        )
    except Exception:
        record_fallback(
            component='stt_live_session', from_mode='none', to_mode='none', reason='other', outcome='degraded'
        )


async def initialize_session_policy(host):
    from utils.stt import streaming
    from utils.stt.provider_resilience import STT_FALLBACK_LIVENESS_GRACE_SECONDS

    identity = host.client_conversation_id or host.recording_session_id
    # Legacy clients lack a recording ID. Reuse prepare()'s authoritative row,
    # including its ownership/continuation checks, before any STT selection.
    # prepare consumes this read instead of issuing a second Firestore lookup.
    if (
        not host.client_conversation_id
        and not host.is_multi_channel
        and not (host.request.onboarding_mode and host.onboarding_admitted)
    ):
        from utils.conversations.process_conversation import retrieve_in_progress_conversation
        from database.listen_continuations import calendar_continuity_row
        from models.conversation_continuity import calendar_continuity_identity, continuation_timeout, gap_splits
        from utils.transcribe_decisions import effective_conversation_timeout
        from utils.transcribe_decisions import should_attach_to_existing_in_progress

        existing = await host.persistence.call(retrieve_in_progress_conversation, host.request.uid)
        if existing and calendar_continuity_identity(existing) is not None:
            existing = dict(await host.persistence.call(calendar_continuity_row, host.request.uid, existing))
        host._policy_resume_candidate = existing
        if existing:
            source = getattr(existing.get('source'), 'value', existing.get('source'))
            finished = existing.get('finished_at')
            if (
                not any(existing.get(key) for key in ('deleted', 'discarded', 'is_locked'))
                and existing.get('client_device_id') == host.client_device_context.client_device_id
                and should_attach_to_existing_in_progress(existing_source=source, request_source=host.request.source)
                and finished is not None
                and not gap_splits(
                    (datetime.now(timezone.utc) - finished).total_seconds(),
                    continuation_timeout(
                        existing, effective_conversation_timeout(host.request.conversation_timeout, False)
                    ),
                )
            ):
                identity = existing['id']
    policy, source = await load_listen_policy(
        host.request.uid,
        identity,
        resolver=lambda: resolve_listen_policy(
            host.request.uid,
            models=streaming.stt_service_models,
            liveness_grace_seconds=STT_FALLBACK_LIVENESS_GRACE_SECONDS,
        ),
    )
    host.state.listen_policy = policy
    host.state.policy_source = source
    host.recovery_enabled = policy.failover_recovery_enabled
    record_source(source, policy)
    return policy
