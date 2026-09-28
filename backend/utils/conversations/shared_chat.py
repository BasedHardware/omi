from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from uuid import uuid4
from typing import Any

import database.conversations as conversations_db
import database.redis_db as redis_db

_TRANSCRIPT_TRUNCATION_MARKER = '[... transcript truncated at segment boundaries ...]'
SUBJECT_MINUTE_LIMIT = 8
ANONYMOUS_FREE_QUESTIONS = 3
CONVERSATION_DAILY_LIMIT = 60
ANONYMOUS_GLOBAL_MINUTE_LIMIT = 20
ANONYMOUS_GLOBAL_DAILY_LIMIT = 3_000
SIGNED_USER_DAILY_LIMIT = 30
SIGNED_GLOBAL_DAILY_LIMIT = 2_000
MINUTE_SECONDS = 60
DAY_SECONDS = 24 * 60 * 60

# One atomic admission across the daily budgets. Redis TIME provides one clock
# for every backend instance; sorted sets enforce a true rolling window.
_ROLLING_LIMIT_LUA = redis_db.r.register_script('''
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) * 1000 + math.floor(tonumber(now_parts[2]) / 1000)
local count = #KEYS
for i = 1, count do
    local limit = tonumber(ARGV[2 * i])
    local window = tonumber(ARGV[2 * i + 1])
    redis.call('ZREMRANGEBYSCORE', KEYS[i], '-inf', now - window)
    if redis.call('ZCARD', KEYS[i]) >= limit then
        local oldest = redis.call('ZRANGE', KEYS[i], 0, 0, 'WITHSCORES')
        local retry = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
        return {i, retry, 0}
    end
end
local remaining = 0
for i = 1, count do
    local window = tonumber(ARGV[2 * i + 1])
    redis.call('ZADD', KEYS[i], now, ARGV[1])
    redis.call('PEXPIRE', KEYS[i], window)
    if i == 1 then remaining = tonumber(ARGV[2]) - redis.call('ZCARD', KEYS[i]) end
end
return {0, 0, remaining}
''')


class SharedConversationUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__('shared conversation not found')


class PublicSharedChatRateLimited(Exception):
    def __init__(self, retry_after: int, reason: str = 'subject_minute') -> None:
        self.retry_after = max(1, retry_after)
        self.reason = reason
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
            SUBJECT_MINUTE_LIMIT,
            MINUTE_SECONDS,
        )
        if not per_ip_allowed:
            raise PublicSharedChatRateLimited(per_ip_retry_after, 'subject_minute')

        global_allowed, _, global_retry_after = check(
            'all',
            'public_shared_conversation_chat:global',
            ANONYMOUS_GLOBAL_MINUTE_LIMIT,
            MINUTE_SECONDS,
        )
        if not global_allowed:
            raise PublicSharedChatRateLimited(global_retry_after, 'global_minute')
    except PublicSharedChatRateLimited:
        raise
    except Exception as exc:
        raise PublicSharedChatRateLimiterUnavailable() from exc


def _reserve_rolling_budgets(budgets: list[tuple[str, int, int, str]]) -> tuple[int, str]:
    keys = [f'public_shared_chat:v2:{key}' for key, _, _, _ in budgets]
    reservation = uuid4().hex
    args: list[str | int] = [reservation]
    for _, limit, window, _ in budgets:
        args.extend((limit, window * 1000))
    try:
        denied, retry_after, remaining = _ROLLING_LIMIT_LUA(keys=keys, args=args)
    except Exception as exc:
        raise PublicSharedChatRateLimiterUnavailable() from exc
    if denied:
        raise PublicSharedChatRateLimited(int(retry_after), budgets[int(denied) - 1][3])
    return int(remaining), reservation


def check_anonymous_shared_chat_daily_limits(opaque_subject: str, conversation_id: str) -> int:
    """Reserve all anonymous daily budgets before any conversation read."""
    remaining, _ = _reserve_rolling_budgets(
        [
            (
                f'free:{opaque_subject}:{conversation_id}',
                ANONYMOUS_FREE_QUESTIONS,
                DAY_SECONDS,
                'free_questions_exhausted',
            ),
            (f'conversation:{conversation_id}', CONVERSATION_DAILY_LIMIT, DAY_SECONDS, 'conversation_daily'),
            ('anonymous_global_daily', ANONYMOUS_GLOBAL_DAILY_LIMIT, DAY_SECONDS, 'global_daily'),
        ]
    )
    return remaining


def check_signed_shared_chat_daily_limits(uid: str) -> str:
    _, reservation = _reserve_rolling_budgets(
        [
            (f'signed:{uid}', SIGNED_USER_DAILY_LIMIT, DAY_SECONDS, 'signed_user_daily'),
            ('signed_global_daily', SIGNED_GLOBAL_DAILY_LIMIT, DAY_SECONDS, 'signed_global_daily'),
        ]
    )
    return reservation


def release_signed_shared_chat_daily_limits(uid: str, reservation: str) -> None:
    """Give a non-Omi identity its provisional signed slots back."""
    try:
        redis_db.r.zrem(f'public_shared_chat:v2:signed:{uid}', reservation)
        redis_db.r.zrem('public_shared_chat:v2:signed_global_daily', reservation)
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
