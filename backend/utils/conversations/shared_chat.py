from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import database.conversations as conversations_db
import database.redis_db as redis_db

_TRANSCRIPT_TRUNCATION_MARKER = '[... transcript truncated at segment boundaries ...]'
_PER_IP_LIMIT = 8
_GLOBAL_LIMIT = 120
_RATE_LIMIT_WINDOW_SECONDS = 60


class SharedConversationUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__('shared conversation not found')


class PublicSharedChatRateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__('public shared conversation chat rate limit exceeded')


class PublicSharedChatRateLimiterUnavailable(Exception):
    pass


@dataclass(frozen=True)
class ResolvedSharedConversation:
    uid: str
    conversation: dict[str, Any]


def check_public_shared_chat_rate_limits(
    opaque_subject: str,
    *,
    rate_limit_check: Callable[[str, str, int, int], tuple[bool, int, int]] | None = None,
) -> None:
    check = rate_limit_check or redis_db.check_rate_limit
    try:
        per_ip_allowed, _, per_ip_retry_after = check(
            opaque_subject,
            'public_shared_conversation_chat:per_ip',
            _PER_IP_LIMIT,
            _RATE_LIMIT_WINDOW_SECONDS,
        )
        if not per_ip_allowed:
            raise PublicSharedChatRateLimited(per_ip_retry_after)

        global_allowed, _, global_retry_after = check(
            'all',
            'public_shared_conversation_chat:global',
            _GLOBAL_LIMIT,
            _RATE_LIMIT_WINDOW_SECONDS,
        )
        if not global_allowed:
            raise PublicSharedChatRateLimited(global_retry_after)
    except PublicSharedChatRateLimited:
        raise
    except Exception as exc:
        raise PublicSharedChatRateLimiterUnavailable() from exc


def resolve_shared_public_conversation(
    conversation_id: str,
    *,
    owner_lookup: Callable[[str], str] | None = None,
    conversation_lookup: Callable[[str, str], dict[str, Any] | None] | None = None,
) -> ResolvedSharedConversation:
    lookup_owner = owner_lookup or redis_db.get_conversation_uid
    lookup_conversation = conversation_lookup or conversations_db.get_public_shared_conversation_bounded

    uid = lookup_owner(conversation_id)
    if not uid:
        raise SharedConversationUnavailable()

    conversation = lookup_conversation(uid, conversation_id)
    if conversation is None:
        raise SharedConversationUnavailable()

    visibility = conversation.get('visibility')
    if (
        not isinstance(visibility, str)
        or visibility not in {'shared', 'public'}
        or conversation.get('is_locked', False)
    ):
        raise SharedConversationUnavailable()

    return ResolvedSharedConversation(uid=uid, conversation=conversation)


def build_bounded_transcript(segments: Sequence[object], *, max_chars: int) -> str:
    if max_chars <= 0:
        return ''

    marker = _TRANSCRIPT_TRUNCATION_MARKER[:max_chars]
    separator_budget = 2 if len(marker) < max_chars else 0
    available = max(0, max_chars - len(marker) - separator_budget)
    head_budget = int(available * 0.6)
    tail_budget = available - head_budget

    full_blocks: list[str] = []
    full_used = 0
    full_fits = True
    head_blocks: list[tuple[int, str]] = []
    head_used = 0
    head_closed = False
    tail_blocks: deque[tuple[int, str]] = deque()
    tail_used = 0
    truncated = False

    for ordinal, segment in enumerate(segments):
        block, oversized = _render_segment_bounded(segment, max_chars=max_chars)
        if oversized:
            truncated = True
            full_fits = False
            full_blocks.clear()
            head_closed = True
            tail_blocks.clear()
            tail_used = 0
            continue
        if not block:
            continue

        if full_fits:
            full_cost = len(block) + (1 if full_blocks else 0)
            if full_used + full_cost <= max_chars:
                full_blocks.append(block)
                full_used += full_cost
            else:
                full_fits = False
                truncated = True
                full_blocks.clear()

        if not head_closed:
            head_cost = len(block) + (1 if head_blocks else 0)
            if head_used + head_cost <= head_budget:
                head_blocks.append((ordinal, block))
                head_used += head_cost
            else:
                head_closed = True

        if len(block) > tail_budget:
            tail_blocks.clear()
            tail_used = 0
        else:
            tail_cost = len(block) + (1 if tail_blocks else 0)
            tail_blocks.append((ordinal, block))
            tail_used += tail_cost
            while tail_blocks and tail_used > tail_budget:
                _, removed = tail_blocks.popleft()
                tail_used -= len(removed)
                if tail_blocks:
                    tail_used -= 1

    if full_fits and not truncated:
        return '\n'.join(full_blocks)

    last_head_ordinal = head_blocks[-1][0] if head_blocks else -1
    selected = [block for _, block in head_blocks]
    selected.append(marker)
    selected.extend(block for ordinal, block in tail_blocks if ordinal > last_head_ordinal)
    return '\n'.join(selected)[:max_chars]


def _render_segment_bounded(segment: object, *, max_chars: int) -> tuple[str, bool]:
    if isinstance(segment, Mapping):
        data: Mapping[str, Any] = segment
    else:
        model_dump = getattr(segment, 'model_dump', None)
        rendered = model_dump() if callable(model_dump) else vars(segment)
        if not isinstance(rendered, Mapping):
            return '', False
        data = rendered

    text = data.get('text')
    if not isinstance(text, str):
        return '', False
    if data.get('is_user') is True:
        speaker = 'Owner'
    else:
        speaker_id = data.get('speaker_id')
        speaker = f'Speaker {speaker_id}' if isinstance(speaker_id, int) else 'Speaker'
    start = 0
    end = len(text)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start == end:
        return '', False

    prefix = f'{speaker}: '
    if len(prefix) + (end - start) > max_chars:
        return '', True
    return prefix + text[start:end], False
