"""Compose on the Mac, via Ollama, so there is no rate limit at all.

Omi's `test-prompt` endpoint composes well but is capped at 30/hour
(`utils/rate_limit_config.py`, `"test:prompt": (30, 3600)`), which a normal day
of wearing the glasses burns through. The bridge already only works while this
Mac is awake -- it *is* the tunnel endpoint -- so a model running here adds no
new failure mode, costs nothing, and the retrieved facts never leave the
machine to be turned into a sentence.

Measured on this hardware (M-series, 64 GB), composing 2-3 sentences from
retrieved facts:

    llama3.2:latest      0.5-1.2s warm,  5.5s cold   (drops items from a list)
    qwen3.6:35b-a3b      1.3-2.3s warm, 16.5s cold   (keeps them; the default)

`qwen3.6:35b-a3b` is a mixture-of-experts model with ~3B active parameters, so
it answers at small-model speed with large-model recall. The 16.5s cold load is
the one thing that would break the ~5s budget, which is why `warm()` runs at
startup and on a timer: a model that has fallen out of memory mid-day is the
only realistic way this path goes slow.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

BASE_URL = os.getenv('OMI_EVEN_OLLAMA_URL', 'http://127.0.0.1:11434')
MODEL = os.getenv('OMI_EVEN_LOCAL_MODEL', 'qwen3.6:35b-a3b')

# Each request refreshes this TTL, and `warm()` re-pings well inside it, so the
# model stays resident while the bridge runs and is released a while after it
# stops -- rather than holding ~23 GB forever.
KEEP_ALIVE = os.getenv('OMI_EVEN_LOCAL_KEEP_ALIVE', '30m')
WARM_INTERVAL_S = 600.0

# Long enough to cover a cold load; the *caller* enforces the answer deadline,
# and warming deliberately has no deadline at all.
_WARM_TIMEOUT = httpx.Timeout(300.0, connect=2.0)
# A refused connection must be instant, so a stopped Ollama costs no budget.
_ANSWER_TIMEOUT = httpx.Timeout(30.0, connect=1.0)

# Two or three sentences. Left uncapped, a small model will happily narrate the
# whole fact list back, which does not fit the display anyway.
_NUM_PREDICT = 160

# Ollama sizes the KV cache from the model's declared maximum, not from what we
# actually send: `ollama ps` showed qwen3.6 resident at 28 GB for a 262144-token
# context, to serve prompts of roughly 500 tokens. On a machine that is also
# doing the user's real work, that is the difference between a background
# service and a stall. Ten facts plus the instructions fit in 4096 with room to
# spare.
_NUM_CTX = int(os.getenv('OMI_EVEN_LOCAL_NUM_CTX', '4096'))

_available = True


class LocalUnavailable(RuntimeError):
    """Ollama is not running, has no such model, or returned nothing."""


def _payload(prompt: str, *, num_predict: int) -> dict:
    return {
        'model': MODEL,
        'prompt': prompt,
        'stream': False,
        # qwen3.6 is a reasoning model; its thinking tokens would cost more than
        # the whole budget and never reach the display.
        'think': False,
        'keep_alive': KEEP_ALIVE,
        'options': {'temperature': 0.3, 'num_predict': num_predict, 'num_ctx': _NUM_CTX},
    }


async def generate(prompt: str) -> str:
    """One completion. Raises LocalUnavailable rather than returning junk."""
    global _available
    try:
        async with httpx.AsyncClient(timeout=_ANSWER_TIMEOUT) as client:
            response = await client.post(f'{BASE_URL}/api/generate', json=_payload(prompt, num_predict=_NUM_PREDICT))
    except httpx.HTTPError as exc:
        _available = False
        raise LocalUnavailable(f'ollama unreachable: {exc}') from exc

    if response.status_code != 200:
        # A missing model is a config problem, not a blip: stop trying until the
        # next successful warm, so every question does not pay for the discovery.
        _available = False
        raise LocalUnavailable(f'ollama HTTP {response.status_code}: {response.text[:120]}')

    _available = True
    answer = ((response.json() or {}).get('response') or '').strip()
    if not answer:
        raise LocalUnavailable('ollama returned nothing')
    return answer


def is_available() -> bool:
    """False once a call has failed, until a later call or warm succeeds.

    Consulted only to decide whether local is worth *trying first*; it is never
    the reason an answer is missing, because every path falls through.
    """
    return _available


async def warm() -> bool:
    """Load the model into memory. Safe to call repeatedly; never raises."""
    global _available
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_WARM_TIMEOUT) as client:
            response = await client.post(f'{BASE_URL}/api/generate', json=_payload('hi', num_predict=1))
        if response.status_code != 200:
            _available = False
            log.warning('local model %s unavailable: HTTP %s', MODEL, response.status_code)
            return False
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - a warmer must never take the bridge with it
        _available = False
        log.info('local model unavailable (%s); cloud compose will be used', exc)
        return False

    _available = True
    log.info('local model %s warm in %.1fs', MODEL, time.monotonic() - started)
    return True


async def warm_forever() -> None:
    """Keep the model resident for as long as the bridge runs.

    A cold `qwen3.6:35b-a3b` takes 16.5s to answer, which is three times the
    whole budget -- so the model going cold, not the model being slow, is what
    would actually break this path.
    """
    while True:
        await warm()
        await asyncio.sleep(WARM_INTERVAL_S)
