"""Fail-closed Dream reservation admission and bounded concurrency slots."""

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
from llm_gateway.gateway.dream_lanes import DREAM_MODEL
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
    return None if waiting else model


def log_wait(model, *, source):
    _decision(model, 'saturated', waiting=True, source=source)


@lru_cache(maxsize=1)
def _vertex_tokens():
    return VertexAccessTokenSupplier()


async def _probe(model, location):
    local = _local()
    if model == DREAM_MODEL:
        location = 'us'
    try:
        outcome = await probe_reservation(
            get_desktop_gemini_client(), _vertex_tokens().get_access_token, model, location
        )
    except Exception:
        outcome = 'inconclusive'
    if outcome == 'capacity_error':
        await mark_saturated(model)
    elif outcome == 'dedicated_success':
        if model == DREAM_MODEL:
            local.probe_failed_until = 0
    else:
        if model == DREAM_MODEL:
            local.probe_failed_until = time.monotonic() + PROBE_SECONDS
        logger.warning('dream_capacity_probe outcome=probe_failed model=%s', model)
    if model == DREAM_MODEL:
        try:
            client = reservation_state.client()
            if client is not None:
                async with asyncio.timeout(0.3):
                    key = reservation_state.key() + ':dream-probe-failed:' + model
                    if outcome == 'dedicated_success':
                        await client.delete(key)
                    elif outcome != 'capacity_error':
                        await client.set(key, '1', ex=PROBE_SECONDS)
        except Exception:
            # Admission independently requires a readable shared store.
            local.probe_failed_until = time.monotonic() + PROBE_SECONDS
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
    try:
        if reservation_state.client() is None:
            return _decision(DREAM_MODEL, 'no_client', waiting=True)
        states = await reservation_state.refresh(_probe, apply_overrides=False)
        if states.get(DREAM_MODEL) != State.ACTIVE:
            return _decision(DREAM_MODEL, 'no_states' if not states else 'no_active_model', waiting=True)
        if local.probe_failed_until > time.monotonic():
            return _decision(DREAM_MODEL, 'probe_failed', waiting=True)
        fresh_seconds = float(os.getenv('DREAM_RESERVATION_FRESH_SECONDS', '900'))
        utilization_limit = float(os.getenv('DREAM_DEDICATED_UTILIZATION_LIMIT', '0.7'))
        if not 0 < fresh_seconds <= 900 or not 0 < utilization_limit <= 1:
            return _decision(DREAM_MODEL, 'invalid_headroom_policy', waiting=True)
        reason = await reservation_state.dream_headroom(
            DREAM_MODEL, fresh_seconds=fresh_seconds, utilization_limit=utilization_limit
        )
    except Exception:
        reason = 'probe_failed'
    return _decision(DREAM_MODEL, reason or 'fresh_reservation_saturation_clear', waiting=reason is not None)


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


async def wait_for_capacity(deadline, required_seconds, *, clock=None, mode='reserved', owner_allowlisted=False):
    """One cooldown, then recheck shared/local saturation; never outlive the pass."""
    clock = asyncio.get_running_loop().time if clock is None else clock
    if deadline - clock() < COOLDOWN_SECONDS + required_seconds:
        return False
    await asyncio.sleep(COOLDOWN_SECONDS)
    return (
        deadline - clock() >= required_seconds
        and await available_model(mode=mode, owner_allowlisted=owner_allowlisted) is not None
    )


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
