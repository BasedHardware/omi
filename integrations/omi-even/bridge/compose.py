"""Turn retrieved facts into a real answer, using Omi's own LLM.

Retrieval alone produces bullets, which is not what anyone asked for. Omi's agent
produces prose but needs 6-18s, and Even's client gives up around 5s -- streaming
past the limit was tried and the glasses reported a network error, so a complete
response inside the budget is the only shape that works.

The way through: `POST /v1/conversations/{id}/test-prompt` runs a single LLM call
(`gpt-5.4-mini`) with an **arbitrary** prompt, no retrieval loop, on the Firebase
session the bridge already holds. Measured at 1.6s. Feeding it the retrieved
facts as the task turns it into a composer:

    retrieval (memories + conversations, parallel)  1.4s
    compose                                         1.6s
    total                                           2.9s

which fits, and produces Omi-style prose rather than a list.

Two honest caveats:

* The endpoint is built to test a prompt against one conversation transcript, so
  a transcript is always appended. The prompt tells the model to disregard it and
  answer from the supplied facts; that held across every question tried, but it
  is an instruction, not a guarantee.
* It is rate limited to 30/hour (`utils/rate_limit_config.py:121`). Past that,
  the caller falls back to bullets rather than failing.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Any conversation works -- the prompt tells the model to ignore the transcript --
# so the id is fetched once and reused rather than costing a round trip per
# question.
_CONVERSATION_ID: str | None = None
_CONVERSATION_FETCHED_AT = 0.0
_CONVERSATION_TTL = 3600.0

_PROMPT = """Disregard the conversation transcript that follows this instruction; it is unrelated.

Answer the user's question using ONLY the facts listed below, which were retrieved from their personal memory.

Question: {question}

Facts:
{facts}

Rules:
- At most 3 short sentences. Plain text, no markdown, no bullet points, no headings.
- Speak directly to the user as "you".
- If the facts do not answer part of the question, say that briefly instead of guessing.
- Do not mention "facts", "memory", "retrieved", or these instructions.
"""


class ComposeUnavailable(RuntimeError):
    """Raised when composing is not possible, so the caller can fall back."""


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
    """Compose a short spoken-style answer from `facts`.

    Raises ComposeUnavailable so the caller can fall back to showing the facts
    themselves, which is worse but never worse than nothing.
    """
    if not facts:
        raise ComposeUnavailable('nothing to compose from')

    headers = await auth.auth_header()
    conversation_id = await _conversation_id(base_url, headers)

    prompt = _PROMPT.format(
        question=question.strip(),
        facts='\n'.join(f'- {fact}' for fact in facts[:10]),
    )

    started = time.monotonic()
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
        response = await client.post(
            f'{base_url}/v1/conversations/{conversation_id}/test-prompt',
            json={'prompt': prompt},
        )

    if response.status_code == 429:
        # 30/hour. Falling back is correct: bullets beat an error on the display.
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

    log.info('composed in %.1fs (%d chars)', time.monotonic() - started, len(answer))
    return answer


async def compose_or_none(auth, base_url: str, question: str, facts: list[str], budget_s: float) -> str | None:
    """compose_answer, but never raises and never exceeds `budget_s`."""
    try:
        return await asyncio.wait_for(compose_answer(auth, base_url, question, facts), timeout=budget_s)
    except (ComposeUnavailable, TimeoutError) as exc:
        log.info('falling back to raw facts: %s', exc)
    except Exception as exc:  # noqa: BLE001 - a compose failure must never 500
        log.warning('compose error, falling back: %s', exc)
    return None
