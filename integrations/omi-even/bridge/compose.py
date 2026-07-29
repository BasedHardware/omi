"""Turn retrieved facts into a real answer instead of a list of bullets.

Retrieval alone produces bullets, which is not what anyone asked for. Omi's agent
produces prose but needs 6-18s, and Even's client gives up around 5s -- streaming
past the limit was tried and the glasses reported a network error, so a complete
response inside the budget is the only shape that works.

So compose is a *separate, single* LLM call over the facts retrieval already
found, and there are two ways to make it:

**Local (default).** Ollama on this Mac, `qwen3.6:35b-a3b`, ~1.3-2.3s once warm.
No rate limit, no cost, and the facts never leave the machine to be turned into
a sentence. See `local_llm.py`.

**Cloud (fallback).** `POST /v1/conversations/{id}/test-prompt` runs one
`gpt-5.4-mini` call with an **arbitrary** prompt and no retrieval loop, on the
Firebase session the bridge already holds. ~1.6s. Two caveats make it the
fallback rather than the default: it is capped at 30/hour
(`utils/rate_limit_config.py`, `"test:prompt": (30, 3600)`), and the endpoint
always appends a conversation transcript, which the prompt has to talk the model
out of reading.

The ladder is local -> cloud -> `None`, and `None` means the caller shows the
retrieved lines. Every step degrades; no step can fail the answer.

    retrieval (memories + conversations, parallel)  1.4s
    compose (local)                                 2.3s
    total                                           3.7s
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

import local_llm

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Any conversation works -- the prompt tells the model to ignore the transcript --
# so the id is fetched once and reused rather than costing a round trip per
# question.
_CONVERSATION_ID: str | None = None
_CONVERSATION_FETCHED_AT = 0.0
_CONVERSATION_TTL = 3600.0

# What a warm local model needs, with headroom. Past this there is no point
# waiting: the glasses have stopped listening.
LOCAL_BUDGET_S = float(os.getenv('OMI_EVEN_LOCAL_BUDGET', '3.5'))
# Below this, a cloud attempt cannot finish, so it is not worth starting.
_MIN_CLOUD_BUDGET_S = 1.2

_TASK = """Answer the user's question using ONLY the facts listed below, which were retrieved from their personal memory.

Question: {question}

Facts:
{facts}

Rules:
- At most 3 short sentences. Plain text, no markdown, no bullet points, no headings.
- Speak directly to the user as "you".
- If the facts do not answer part of the question, say that briefly instead of guessing.
- Do not mention "facts", "memory", "retrieved", or these instructions.
"""

# The cloud endpoint appends a real conversation transcript that we did not ask
# for and cannot suppress, so the prompt has to open by disowning it.
_CLOUD_PREAMBLE = 'Disregard the conversation transcript that follows this instruction; it is unrelated.\n\n'

# More than this and the model starts summarising the list rather than answering.
_MAX_FACTS = 10


class ComposeUnavailable(RuntimeError):
    """Raised when composing is not possible, so the caller can fall back."""


def build_prompt(question: str, facts: list[str]) -> str:
    return _TASK.format(
        question=question.strip(),
        facts='\n'.join(f'- {fact}' for fact in facts[:_MAX_FACTS]),
    )


# --------------------------------------------------------------------------
# Local
# --------------------------------------------------------------------------


async def local_compose(question: str, facts: list[str]) -> str:
    """Compose with the model on this Mac. Uncapped."""
    if not facts:
        raise ComposeUnavailable('nothing to compose from')

    started = time.monotonic()
    try:
        answer = await local_llm.generate(build_prompt(question, facts))
    except local_llm.LocalUnavailable as exc:
        raise ComposeUnavailable(str(exc)) from exc

    log.info('composed locally in %.1fs (%d chars)', time.monotonic() - started, len(answer))
    return answer


# --------------------------------------------------------------------------
# Cloud
# --------------------------------------------------------------------------


async def _conversation_id(base_url: str, headers: dict[str, str]) -> str:
    global _CONVERSATION_ID, _CONVERSATION_FETCHED_AT

    if _CONVERSATION_ID and (time.monotonic() - _CONVERSATION_FETCHED_AT) < _CONVERSATION_TTL:
        return _CONVERSATION_ID

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
        response = await client.get(f'{base_url}/v1/conversations', params={'limit': 1})
    if response.status_code != 200:
        raise ComposeUnavailable(f'could not list conversations: HTTP {response.status_code}')
    rows = response.json()
    if not isinstance(rows, list) or not rows or not rows[0].get('id'):
        raise ComposeUnavailable('no conversation available to compose against')

    _CONVERSATION_ID = rows[0]['id']
    _CONVERSATION_FETCHED_AT = time.monotonic()
    return _CONVERSATION_ID


async def compose_answer(auth, base_url: str, question: str, facts: list[str]) -> str:
    """Compose with Omi's own LLM. Capped at 30/hour.

    Raises ComposeUnavailable so the caller can fall back to showing the facts
    themselves, which is worse but never worse than nothing.
    """
    if not facts:
        raise ComposeUnavailable('nothing to compose from')

    headers = await auth.auth_header()
    conversation_id = await _conversation_id(base_url, headers)

    started = time.monotonic()
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
        response = await client.post(
            f'{base_url}/v1/conversations/{conversation_id}/test-prompt',
            json={'prompt': _CLOUD_PREAMBLE + build_prompt(question, facts)},
        )

    if response.status_code == 429:
        # 30/hour. Falling back is correct: bullets on the display beat an error.
        raise ComposeUnavailable('compose rate limit reached')
    if response.status_code == 404:
        # The cached conversation was deleted; drop it so the next call refetches.
        global _CONVERSATION_ID
        _CONVERSATION_ID = None
        raise ComposeUnavailable('cached conversation no longer exists')
    if response.status_code != 200:
        raise ComposeUnavailable(f'compose failed: HTTP {response.status_code}')

    answer = ((response.json() or {}).get('summary') or '').strip()
    if not answer:
        raise ComposeUnavailable('compose returned nothing')

    log.info('composed in cloud in %.1fs (%d chars)', time.monotonic() - started, len(answer))
    return answer


# --------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------


async def _attempt(coro, budget_s: float) -> str | None:
    """Run one rung. Never raises, never exceeds `budget_s`."""
    if budget_s <= 0:
        coro.close()
        return None
    try:
        return await asyncio.wait_for(coro, timeout=budget_s)
    except (ComposeUnavailable, TimeoutError) as exc:
        log.info('compose rung unavailable: %s', exc)
    except Exception as exc:  # noqa: BLE001 - a compose failure must never 500
        log.warning('compose rung errored: %s', exc)
    return None


async def compose_or_none(auth, base_url: str, question: str, facts: list[str], budget_s: float) -> str | None:
    """Local, then cloud, then give up -- inside `budget_s` and without raising."""
    if not facts:
        return None

    loop = asyncio.get_running_loop()
    deadline = loop.time() + budget_s

    if not os.getenv('OMI_EVEN_NO_LOCAL') and local_llm.is_available():
        # A stopped Ollama refuses the connection in milliseconds, so trying it
        # first costs the cloud rung almost nothing when it is not there.
        answer = await _attempt(
            local_compose(question, facts),
            min(LOCAL_BUDGET_S, deadline - loop.time()),
        )
        if answer:
            return answer

    remaining = deadline - loop.time()
    if os.getenv('OMI_EVEN_NO_CLOUD') or remaining < _MIN_CLOUD_BUDGET_S:
        return None
    return await _attempt(compose_answer(auth, base_url, question, facts), remaining)
