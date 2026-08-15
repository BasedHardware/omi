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

import tiktoken

# Below this, the provider never serves a read, so a breakpoint is pure noise.
EXPLICIT_CACHE_MINIMUM_TOKENS = 1024

EXPLICIT_CACHE_OPTIONS = {'mode': 'explicit', 'ttl': '30m'}
EXPLICIT_CACHE_BREAKPOINT = {'mode': 'explicit'}


def has_cacheable_prefix(content: str) -> bool:
    """Use the model-family tokenizer as a conservative preflight for a cache write."""
    if not content:
        return False
    try:
        return len(tiktoken.get_encoding('o200k_base').encode(content)) >= EXPLICIT_CACHE_MINIMUM_TOKENS
    except AttributeError:
        # Do not make a cache write merely because an optional tokenizer dependency is unavailable.
        return len(content) >= EXPLICIT_CACHE_MINIMUM_TOKENS * 4
