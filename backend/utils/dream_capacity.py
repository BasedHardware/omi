"""Evidence is advisory; explicit cooldowns and bounded slots control admission."""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from uuid import uuid4

from config.vertex_reservations import RESERVATIONS, State, PROBE_SECONDS
from llm_gateway.gateway.providers import VertexAccessTokenSupplier
from utils.http_client import get_desktop_gemini_client
from utils.llm.vertex_reservation_probe import probe_reservation
from utils.llm.vertex_reservation_state import reservation_state
from utils.llm.vertex_pt_routing import PT_MODEL_CURRENT, reserved_generation_model
from utils.observability.fallback import record_fallback

SLOT_SECONDS = 240
COOLDOWN_SECONDS = 120
RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
logger = logging.getLogger(__name__)


@dataclass
class LocalCapacity:
    cooldowns: dict[str, float] = field(default_factory=dict)
    slots: dict[int, tuple[str, float]] = field(default_factory=dict)
    probe_failed_until: float = 0


@lru_cache(maxsize=1)
def _local_state(key):
    # One namespace, at most two models/eight slots, with monotonic expiry.
    return LocalCapacity()


def _local():
    try:
        key = reservation_state.key()
    except Exception:
        key = 'unavailable'
    return _local_state(key)


def _decision(model, reason, *, waiting=False, source='evidence'):
    logger.warning(
        json.dumps(
            {
                'event': 'dream_capacity_decision',
                'decision': 'waiting' if waiting else 'admit',
                'reason': reason,
                'source': source,
                'model': model if model in RESERVATIONS else 'unknown',
            },
            sort_keys=True,
        )
    )
    if not waiting:
        record_fallback(
            component='vertex_reservations',
            from_mode='evidence_gate',
            to_mode='gateway_admission',
            reason=reason,
            outcome='degraded',
        )
    return None if waiting else model


def log_wait(model, *, source):
    _decision(model, 'saturated', waiting=True, source=source)


@lru_cache(maxsize=1)
def _vertex_tokens():
    return VertexAccessTokenSupplier()


async def _probe(model, location):
    local = _local()
    try:
        outcome = await probe_reservation(
            get_desktop_gemini_client(), _vertex_tokens().get_access_token, model, location
        )
    except Exception:
        outcome = 'inconclusive'
    if outcome == 'capacity_error':
        await mark_saturated(model)
    elif outcome == 'dedicated_success':
        local.probe_failed_until = 0
    else:
        local.probe_failed_until = time.monotonic() + PROBE_SECONDS
        logger.warning('dream_capacity_probe outcome=probe_failed model=%s', model)
    return outcome


async def available_model():
    # This hint never authorizes shared/pay-as-you-go Gemini: the reserved-only
    # gateway remains the final provider authority, as before step 5.
    model = os.getenv('OMI_VERTEX_PT_MODEL', '')
    model = model if model in RESERVATIONS else PT_MODEL_CURRENT
    local = _local()
    reason = None
    states = {}
    try:
        client = reservation_state.client()
        states = await reservation_state.refresh(_probe)
        active = reserved_generation_model(PT_MODEL_CURRENT, states, override=os.getenv('OMI_VERTEX_PT_MODEL', ''))
        if active is not None:
            model = active
        if client is None:
            reason = 'no_client'
        elif local.probe_failed_until > time.monotonic():
            reason = 'probe_failed' if active is None else None
        elif not states or all(state == State.UNKNOWN for state in states.values()):
            reason = 'no_states'
        elif active is None:
            reason = 'no_active_model'
    except Exception:
        states = {}
        client = None
        reason = 'probe_failed'
    # Without unique active evidence, honor either exclusive-order alias's cooldown.
    models = [model] if states.get(model) == State.ACTIVE and reason is None else list(RESERVATIONS)
    if any(local.cooldowns.get(candidate, 0) > time.monotonic() for candidate in models):
        return _decision(model, 'saturated', waiting=True, source='local_cooldown')
    if client is not None:
        try:
            async with asyncio.timeout(0.5):
                for candidate in models:
                    if await client.get(reservation_state.key() + ':saturated:' + candidate):
                        return _decision(model, 'saturated', waiting=True, source='redis_cooldown')
        except Exception:
            reason = 'probe_failed'
    return _decision(model, reason) if reason else model


async def mark_saturated(model):
    if model in RESERVATIONS:
        _local().cooldowns[model] = time.monotonic() + COOLDOWN_SECONDS
        try:
            await reservation_state.record(model, 'dedicated', 429, None)
        except Exception:
            record_fallback(
                component='vertex_reservations',
                from_mode='shared_cooldown',
                to_mode='local_cooldown',
                reason='connection_lost',
                outcome='degraded',
            )
        logger.warning('dream_capacity_cooldown reason=saturated model=%s', model)


def _release_local(token):
    slots = _local().slots
    for index, (own, _) in list(slots.items()):
        if own == token:
            del slots[index]


async def claim(limit):
    model = await available_model()
    if model is None:
        return None
    limit = max(1, min(limit, 8))
    token = str(uuid4())
    local = _local()
    index = next((i for i in range(limit) if local.slots.get(i, ('', 0))[1] <= time.monotonic()), None)
    if index is None:
        return _decision(model, 'saturated', waiting=True, source='local_slots')
    local.slots[index] = token, time.monotonic() + SLOT_SECONDS
    fallback = ('dream-local:' + str(index), token)
    try:
        client = reservation_state.client()
        if client is None:
            return fallback
        async with asyncio.timeout(0.5):
            for index in range(limit):
                key = reservation_state.key() + ':dream-slot:' + str(index)
                if await client.set(key, token, nx=True, ex=SLOT_SECONDS):
                    return key, token
    except Exception:
        record_fallback(
            component='vertex_reservations',
            from_mode='shared_slots',
            to_mode='local_slots',
            reason='connection_lost',
            outcome='degraded',
        )
        return fallback
    _release_local(token)
    return _decision(model, 'saturated', waiting=True, source='shared_slots')


async def release(slot):
    _release_local(slot[1])
    if slot[0].startswith('dream-local:'):
        return
    try:
        client = reservation_state.client()
        if client is not None:
            async with asyncio.timeout(0.5):
                await client.eval(RELEASE, 1, slot[0], slot[1])
    except Exception:
        # TTL retains the bound during outage; never erase another worker's token.
        return
