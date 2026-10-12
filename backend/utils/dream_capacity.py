"""Fail-closed background admission on the shared reservation evidence store."""

import asyncio
import os
from functools import lru_cache
from uuid import uuid4

from llm_gateway.gateway.providers import VertexAccessTokenSupplier
from utils.http_client import get_desktop_gemini_client
from utils.llm.vertex_reservation_probe import probe_reservation
from utils.llm.vertex_reservation_state import reservation_state
from utils.llm.vertex_pt_routing import PT_MODEL_CURRENT, reserved_generation_model

SLOT_SECONDS = 240  # Longer than Dream's bounded 180-second pass.
RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"


@lru_cache(maxsize=1)
def _vertex_tokens():
    return VertexAccessTokenSupplier()


async def _probe(model, location):
    return await probe_reservation(get_desktop_gemini_client(), _vertex_tokens().get_access_token, model, location)


async def available_model():
    states = await reservation_state.refresh(_probe)
    try:
        model = reserved_generation_model(PT_MODEL_CURRENT, states, override=os.getenv('OMI_VERTEX_PT_MODEL', ''))
        client = reservation_state.client()
        if model is None or client is None:
            return None
        async with asyncio.timeout(0.5):
            if await client.get(reservation_state.key() + ':saturated:' + model):
                return None
        return model
    except Exception:
        return None


async def mark_saturated(model):
    # Reuse the shared bounded writer and 120-second TTL; no provider fallback.
    await reservation_state.record(model, 'dedicated', 429, None)


async def claim(limit):
    model = await available_model()
    client = reservation_state.client()
    if model is None or client is None:
        return None
    token = str(uuid4())
    try:
        async with asyncio.timeout(0.5):
            for index in range(max(1, min(limit, 8))):
                key = reservation_state.key() + ':dream-slot:' + str(index)
                if await client.set(key, token, nx=True, ex=SLOT_SECONDS):
                    return key, token
    except Exception:
        return None
    return None


async def release(slot):
    try:
        client = reservation_state.client()
        if client is not None:
            async with asyncio.timeout(0.5):
                await client.eval(RELEASE, 1, slot[0], slot[1])
    except Exception:
        # TTL retains the bound during outage; never erase another worker's token.
        return
