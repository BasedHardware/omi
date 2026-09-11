"""Shared explicit prompt-cache primitives for the GPT-5.6 family.

The provider only serves a cache READ from a prefix that ends on a message
boundary or on an explicit ``prompt_cache_breakpoint``. A prompt whose stable
text is packed into the same message as volatile text (a per-frame timestamp,
a screenshot) therefore has no readable boundary at all: every call is charged
a full cache WRITE and no call can ever hit. Cache writes are billed at a
premium over fresh input, so an unreadable write is strictly worse than not
caching, and the breakpoint is what makes the write worth paying for.

The provider also ignores any cached prefix shorter than
``EXPLICIT_CACHE_MINIMUM_TOKENS``. Marking a block under that floor buys
nothing, so callers preflight with :func:`has_cacheable_prefix` first.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from typing import Any

# Below this, the provider never serves a read, so a breakpoint is pure noise.
EXPLICIT_CACHE_MINIMUM_TOKENS = 1024

# Deliberately a character heuristic rather than a real tokenizer. This runs on
# the request path, and `tiktoken.get_encoding` fetches its vocabulary from a
# remote blob on first use: a network failure there would surface as a 500 on a
# call that only needed to answer "is this block big enough to be worth
# caching?". Four characters per token is the usual English ratio, and the
# decision degrades gracefully either way — slightly under-counting skips a
# marginal cache write, slightly over-counting pays for one.
EXPLICIT_CACHE_MINIMUM_CHARACTERS = EXPLICIT_CACHE_MINIMUM_TOKENS * 4

EXPLICIT_CACHE_OPTIONS = {'mode': 'explicit', 'ttl': '30m'}
EXPLICIT_CACHE_BREAKPOINT = {'mode': 'explicit'}


# One kill switch for every explicit-cache caller. Unset means enabled.
GPT56_EXPLICIT_CACHE_ENABLED_ENV = 'OMI_LLM_GPT56_EXPLICIT_CACHE_ENABLED'


def has_cacheable_prefix(content: str) -> bool:
    """Conservative preflight: is this block worth marking for a cache write?"""
    return len(content) >= EXPLICIT_CACHE_MINIMUM_CHARACTERS


def explicit_cache_switch_enabled() -> bool:
    """The operator kill switch shared by every explicit-cache caller.

    Callers still add their own route condition (the explicit contract is
    GPT-5.6-only); this owns just the env semantics so a rollback is one
    variable everywhere rather than one per feature.
    """
    value = os.getenv(GPT56_EXPLICIT_CACHE_ENABLED_ENV)
    if value is None:
        return True
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


def gpt56_explicit_cache_enabled() -> bool:
    """May this process put ``prompt_cache_options`` on a request at all?

    True when the gateway lanes (which pin the GPT-5.6 family) are the route and
    the kill switch is not off. Whether a given prefix earns a breakpoint is a
    separate, per-caller question.

    Sending :data:`EXPLICIT_CACHE_OPTIONS` with *no* breakpoint is not a no-op:
    it is how a request whose prompt has no reusable prefix opts out of the
    provider's automatic caching, which otherwise bills much of the prompt at
    the cache-write premium for a write nothing can ever read back.
    """
    try:
        from utils.llm.gateway_client import should_route_features_through_gateway
    except ImportError:  # pragma: no cover - isolated suites import this module alone
        return False
    return should_route_features_through_gateway() and explicit_cache_switch_enabled()


def cache_write_opt_out_options() -> dict[str, str] | None:
    """Options for a prompt with no reusable prefix: explicit mode, no breakpoint.

    Not a no-op and not the same as sending nothing. A GPT-5.6 request that
    carries no ``prompt_cache_options`` gets the provider's automatic caching,
    which writes a long prompt on every call and bills those tokens at the
    write premium — and when the prompt's stable head is under
    ``EXPLICIT_CACHE_MINIMUM_TOKENS`` no later call can ever read that write
    back. Explicit mode without a breakpoint declares "cache nothing here" and
    returns the request to the plain input rate. It adds no field to the
    messages and changes no prompt bytes.

    None under BYOK: a BYOK key can route a feature off GPT-5.6 entirely, where
    this is not a field the provider accepts.
    """
    if not gpt56_explicit_cache_enabled() or _byok_request():
        return None
    return dict(EXPLICIT_CACHE_OPTIONS)


def _byok_request() -> bool:
    try:
        from utils.byok import has_byok_keys
    except ImportError:  # pragma: no cover - isolated suites import this module alone
        return False
    return has_byok_keys()


def with_cache_write_opt_out(runnable: Any) -> Any:
    """Bind the opt-out to an already-structured runnable, which is the only order that works.

    ``BaseChatModel.bind`` returns a ``RunnableBinding``, and ``RunnableBinding``
    defines no ``with_structured_output`` of its own: the attribute lookup
    forwards to the unbound model and every bound kwarg is silently dropped.
    Binding first therefore produces a request with no cache options at all, and
    nothing raises — measured against langchain_openai, ``_generate`` receives
    ``{'response_format': ...}`` and no ``extra_body``. Bind last and it arrives.
    Callers that invoke the model directly, or pipe it into a chain, keep the
    binding either way and do not need this.
    """
    options = cache_write_opt_out_options()
    if options is None:
        return runnable
    return runnable.bind(extra_body={'prompt_cache_options': options})


def prefix_cache_key(namespace: str, stable_text: str) -> str:
    """Routing key derived from the prefix bytes themselves.

    Same bytes -> same key, so two callers that build an identical prefix land
    on the same cache entry, and an edit to the prefix can never route onto the
    entry its previous wording wrote. Carries no prompt content.
    """
    return f'{namespace}-{hashlib.sha256(stable_text.encode("utf-8")).hexdigest()[:32]}'


def content_parts_with_breakpoint(stable_text: str, volatile_text: str) -> list[dict[str, Any]]:
    """One message's text as two parts, with the readable break between them.

    The concatenation is the caller's original prompt byte-for-byte; only where
    the cache boundary sits is new. A breakpoint on the volatile part could
    never be read, so there is deliberately only one.
    """
    return [
        {'type': 'text', 'text': stable_text, 'prompt_cache_breakpoint': EXPLICIT_CACHE_BREAKPOINT},
        {'type': 'text', 'text': volatile_text},
    ]


def has_explicit_breakpoint(messages: object) -> bool:
    """Has some caller already marked its own prefix in these messages?"""
    if not isinstance(messages, list):
        return False
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get('content')
        if not isinstance(content, list):
            continue
        if any(isinstance(part, Mapping) and 'prompt_cache_breakpoint' in part for part in content):
            return True
    return False


def apply_cache_write_opt_out(body: dict[str, Any], *, marked_messages: object = None) -> None:
    """Default an outbound request body to the opt-out, without overriding a caller.

    Three ways a caller can have made a deliberate choice, all of which win:
    its own ``prompt_cache_options``; a ``prompt_cache_key``, which is how a
    pre-5.6 caller asks for implicit caching (adding explicit-mode options on
    top would silently turn that request into a non-cache one — see
    ``accounting.cache_requested_for_openai_request``); or a breakpoint in its
    messages.

    ``marked_messages`` is the message list to scan for that breakpoint. Pass the
    caller's ORIGINAL messages when ``body`` holds a translated copy: a
    translation that normalizes content parts drops the breakpoint, and scanning
    the copy would then miss a marking the caller really made.
    """
    if body.get('prompt_cache_options') is not None or body.get('prompt_cache_key') is not None:
        return
    if has_explicit_breakpoint(marked_messages if marked_messages is not None else body.get('messages')):
        return
    options = cache_write_opt_out_options()
    if options is not None:
        body['prompt_cache_options'] = options


def marked_prefix_request(namespace: str, stable_text: str, volatile_text: str) -> tuple[str | None, list[Any] | None]:
    """``(cache_key, messages)`` for a two-part prompt, or ``(None, None)``.

    ``(None, None)`` whenever the stable head is under the provider's floor: a
    breakpoint there buys a write no later call can read, which costs more than
    not caching at all. The returned messages are one user turn whose parts
    concatenate to ``stable_text + volatile_text`` — the caller's original
    prompt, unchanged.
    """
    if not has_cacheable_prefix(stable_text):
        return None, None
    parts = content_parts_with_breakpoint(stable_text, volatile_text)
    return prefix_cache_key(namespace, stable_text), [{'role': 'user', 'content': parts}]
