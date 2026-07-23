"""Pre-flight guard for oversized chat input.

An extremely long chat message (or a long conversation history) can exceed the chat model's
context window. When that happens the Anthropic call raises an input-too-long error which the
agent loop swallows into a streamed text chunk without a terminal ``done:`` frame, so the mobile
client never finalizes a reply and the user sees "no response" (or a generic error).

This module keeps the decision logic pure and import-light so it can be unit-tested without the
heavy chat/LLM stack: the token counter is injected by the caller. The caller trims the oldest
turns to fit the budget and, when the newest turn alone is too large, returns a clear message
through the normal streaming contract instead of calling the model with input that cannot fit.
"""

import os
from typing import Any, Callable, List, Sequence, Tuple


def _int_from_env(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back to ``default``."""
    try:
        value = int(os.environ.get(name, ''))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# claude-sonnet-4-6 (the chat_agent model) has a 200k-token context window. Cap the conversation
# input well below it so the system prompt, tool schemas, accumulated tool results and the reply
# tokens all still fit. 120k tokens is ~90k words of conversation — far beyond any legitimate
# mobile chat, so real usage is never rejected, only pathological paste-dumps.
MAX_CHAT_INPUT_TOKENS = _int_from_env('MAX_CHAT_INPUT_TOKENS', 120_000)

# Delivered to the user (and persisted) when the newest message alone is over the budget. Sent
# through the same streaming/done: contract as any normal reply so the client renders it in-line.
INPUT_TOO_LONG_MESSAGE = (
    "That message is too long for me to process in one go. "
    "Please shorten it or split it into a few smaller messages and send again."
)


def message_text(content: Any) -> str:
    """Best-effort plain text of a message's content.

    Handles a plain string, an Anthropic-style list of content blocks (dicts with a ``text``
    field, e.g. ``{"type": "text", "text": ...}``), or a bare list of strings. Non-text blocks
    (images, tool results) contribute nothing to the text token estimate.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get('text')
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def fit_within_budget(
    items: Sequence[Any],
    text_of: Callable[[Any], str],
    counter: Callable[[str], int],
    limit: int = MAX_CHAT_INPUT_TOKENS,
) -> Tuple[list, bool]:
    """Trim the oldest items so the cumulative token estimate fits within ``limit``.

    Keeps the most recent items and always preserves the final (current) item. ``text_of`` maps
    an item to its text and ``counter`` estimates that text's token count.

    Returns ``(kept_items, newest_exceeds_limit)``. When the newest item alone is over ``limit``
    the input cannot fit the context window, so this returns ``([], True)`` and the caller should
    reject with a clear message rather than call the model. Otherwise ``newest_exceeds_limit`` is
    ``False`` and ``kept_items`` is the trimmed, in-order list to send.
    """
    items = list(items)
    if not items:
        return items, False

    if counter(text_of(items[-1])) > limit:
        return [], True

    kept: list = []
    total = 0
    for item in reversed(items):
        tokens = counter(text_of(item))
        if kept and total + tokens > limit:
            break
        kept.append(item)
        total += tokens
    kept.reverse()
    return kept, False
