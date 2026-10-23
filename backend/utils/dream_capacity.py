"""Fail-closed Dream reservation admission and bounded concurrency slots."""

import asyncio
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from functools import lru_cache
from uuid import uuid4

from config.vertex_reservations import PROBE_TIMEOUT_SECONDS, RESERVATIONS, State
from llm_gateway.gateway.providers import VertexAccessTokenSupplier
from utils.http_client import get_desktop_gemini_client, get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.gateway_client import get_llm_gateway_base_url, llm_gateway_headers
from utils.llm.vertex_reservation_probe import probe_reservation
from utils.llm.vertex_reservation_state import reservation_state
from llm_gateway.gateway.dream_lanes import DREAM_MODEL
from utils.observability.fallback import record_fallback

SLOT_SECONDS = 240
COOLDOWN_SECONDS = RESERVATIONS[DREAM_MODEL].saturation_seconds
RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
logger = logging.getLogger(__name__)


@dataclass
class LocalCapacity:
    cooldowns: dict[str, float] = field(default_factory=dict)
    slots: dict[int, tuple[str, float]] = field(default_factory=dict)


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
    return None if waiting else model


def log_wait(model, *, source):
    _decision(model, 'saturated', waiting=True, source=source)


@lru_cache(maxsize=1)
def _vertex_tokens():
    return VertexAccessTokenSupplier()


def gateway_probe_enabled():
    """Kill switch for the gateway reservation probe; on unless 0/false/off/no."""
    return os.getenv('DREAM_GATEWAY_PROBE_ENABLED', 'true').strip().lower() not in {'0', 'false', 'off', 'no'}


async def _probe(model, location):
    try:
        if model == DREAM_MODEL and not gateway_probe_enabled():
            # Off: no probe call; admission relies on fresh evidence from real turns.
            outcome = 'inconclusive'
        elif model == DREAM_MODEL:
            # Use the real Dream route/identity. The gateway publishes strict PT
            # evidence itself; a gateway HTTP 200 alone must never teach success.
            headers = llm_gateway_headers(feature='dream_reservation_probe')
            headers.pop('X-Omi-User-Uid', None)
            headers['X-Omi-LLM-Feature'] = 'dream_reservation_probe'
            async with get_llm_gateway_semaphore():
                response = await get_llm_gateway_client().post(
                    get_llm_gateway_base_url() + '/v1/chat/completions',
                    headers=headers,
                    json={
                        'model': 'omi:auto:dream-verify',
                        'messages': [{'role': 'user', 'content': 'Reply OK.'}],
                        'stream': False,
                        'max_completion_tokens': 16,
                        'reasoning_effort': 'none',
                        'google': {'dream_capacity_mode': 'reserved', 'dream_reserved_only': True},
                    },
                    timeout=PROBE_TIMEOUT_SECONDS,
                )
            logger.info('dream_capacity_probe source=gateway model=%s status=%d', model, response.status_code)
            failure = None
            if response.is_error:
                try:
                    failure = response.json().get('error', {}).get('failure_class')
                except (ValueError, AttributeError):
                    pass
            outcome = (
                'capacity_error'
                if response.status_code == 429 or failure in {'reserved_capacity_unavailable', 'provider_429_omi_paid'}
                else 'inconclusive'
            )
        else:
            outcome = await probe_reservation(
                get_desktop_gemini_client(), _vertex_tokens().get_access_token, model, location
            )
    except Exception as exc:
        logger.info('dream_capacity_probe error=%s model=%s', type(exc).__name__, model)
        outcome = 'inconclusive'
    if outcome == 'capacity_error':
        await mark_saturated(model)
    elif outcome == 'inconclusive':
        # Auth/transport failures are not saturation. Admission still requires
        # fresh shared evidence, readable headroom and shared concurrency slots.
        logger.info('dream_capacity_probe outcome=inconclusive model=%s', model)
    return outcome


def on_demand_allowed(owner_allowlisted):
    return owner_allowlisted is True and os.getenv('DREAM_ON_DEMAND_ENABLED', '').strip().lower() in {
        '1',
        'true',
        'yes',
    }


async def available_model(*, mode='reserved', owner_allowlisted=False):
    if mode == 'on_demand':
        if on_demand_allowed(owner_allowlisted):
            return _decision(DREAM_MODEL, 'allowlisted_on_demand', source='policy')
        return _decision(DREAM_MODEL, 'on_demand_disabled', waiting=True, source='policy')
    if mode != 'reserved':
        return _decision(DREAM_MODEL, 'invalid_mode', waiting=True, source='policy')
    local = _local()
    if local.cooldowns.get(DREAM_MODEL, 0) > time.monotonic():
        return _decision(DREAM_MODEL, 'saturated', waiting=True, source='local_cooldown')
    stage = 'client'
    try:
        if reservation_state.client() is None:
            return _decision(DREAM_MODEL, 'no_client', waiting=True)
        fresh_seconds = float(os.getenv('DREAM_RESERVATION_FRESH_SECONDS', '900'))
        utilization_limit = float(os.getenv('DREAM_DEDICATED_UTILIZATION_LIMIT', '0.7'))
        if not 0 < fresh_seconds <= 900 or not 0 < utilization_limit <= 1:
            return _decision(DREAM_MODEL, 'invalid_headroom_policy', waiting=True)
        stage = 'refresh'
        states = await reservation_state.refresh(
            _probe if gateway_probe_enabled() else None,
            apply_overrides=False,
            probe_model=DREAM_MODEL,
            fresh_seconds=fresh_seconds,
        )
        if states.get(DREAM_MODEL) != State.ACTIVE:
            return _decision(DREAM_MODEL, 'no_states' if not states else 'no_active_model', waiting=True)
        stage = 'headroom'
        reason = await reservation_state.dream_headroom(
            DREAM_MODEL, fresh_seconds=fresh_seconds, utilization_limit=utilization_limit
        )
    except Exception as exc:
        # The probe callable cannot raise into this frame: _probe converts its
        # own failures to 'inconclusive' and refresh runs it as a background
        # task, so every exception here is a shared-state read/transaction
        # error. Payload-free class/stage only; messages can embed private bodies.
        reason = 'state_error'
        logger.warning('dream_capacity_state_error model=%s stage=%s exc=%s', DREAM_MODEL, stage, type(exc).__name__)
    return _decision(DREAM_MODEL, reason or 'fresh_reservation_saturation_clear', waiting=reason is not None)


async def mark_saturated(model):
    if model in RESERVATIONS:
        _local().cooldowns[model] = time.monotonic() + RESERVATIONS[model].saturation_seconds
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


async def wait_for_capacity(deadline, required_seconds, *, clock=None, mode='reserved', owner_allowlisted=False):
    """Recheck with capped exponential jitter, keeping the caller's session and deadline."""
    clock = asyncio.get_running_loop().time if clock is None else clock
    for attempt in range(6):
        ceiling = min(30, COOLDOWN_SECONDS * 2**attempt)
        pause = random.uniform(ceiling / 2, ceiling)
        if deadline - clock() < pause + required_seconds:
            return False
        await asyncio.sleep(pause)
        if deadline - clock() < required_seconds:
            return False
        if await available_model(mode=mode, owner_allowlisted=owner_allowlisted) is not None:
            return True
    return False


def _release_local(token):
    slots = _local().slots
    for index, (own, _) in list(slots.items()):
        if own == token:
            del slots[index]


async def claim(limit, *, slot_seconds=SLOT_SECONDS, mode='reserved', owner_allowlisted=False):
    model = await available_model(mode=mode, owner_allowlisted=owner_allowlisted)
    if model is None:
        return None
    limit = max(1, min(limit, 512))
    token = str(uuid4())
    local = _local()
    index = next((i for i in range(limit) if local.slots.get(i, ('', 0))[1] <= time.monotonic()), None)
    if index is None:
        return _decision(model, 'saturated', waiting=True, source='local_slots')
    local.slots[index] = token, time.monotonic() + slot_seconds
    fallback = ('dream-local:' + str(index), token)
    try:
        client = reservation_state.client()
        if client is None:
            if mode == 'on_demand':
                return fallback
            _release_local(token)
            return _decision(model, 'no_client', waiting=True, source='shared_slots')
        async with asyncio.timeout(0.5):
            for index in range(limit):
                key = reservation_state.key() + ':dream-slot:' + str(index)
                if await client.set(key, token, nx=True, ex=slot_seconds):
                    return key, token
    except Exception:
        if mode == 'on_demand':
            record_fallback(
                component='vertex_reservations',
                from_mode='shared_slots',
                to_mode='local_slots',
                reason='connection_lost',
                outcome='degraded',
            )
            return fallback
        _release_local(token)
        return _decision(model, 'probe_failed', waiting=True, source='shared_slots')
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
