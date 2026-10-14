"""Shared bounded shaped context: epoch summary, immutable history, volatile final turn."""

import asyncio
import logging
from typing import Any
import copy
import json

from database.chat_context import ChatContextStore
from database.chat_history_window import cache_aligned_history_limit
from utils.executors import db_executor, run_blocking, start_background_task
from utils.observability.fallback import record_fallback
from utils.messaging.history import summarize, recent_activity
from utils.llm.prompt_cache import EXPLICIT_CACHE_BREAKPOINT, has_cacheable_prefix

SUMMARY_CHARS = 2400
DIGEST_CHARS = 3200
SUMMARY_SOURCE_CHARS = 12000
PREPARE_SECONDS = 0.15
DIGEST_SECONDS = 0.075
REFRESH_SECONDS = 60
_REFRESHING = set()
logger = logging.getLogger(__name__)


def bounded_messages(messages):
    # A second guard for injected/custom callers. Normal app/channel readers use this policy already.
    limit = cache_aligned_history_limit(len(messages))
    return copy.deepcopy(messages[-limit:]) if limit else []


def digest_text(rows):
    if not rows:
        return ''
    text = '\n'.join(
        f"{r['created_at'].isoformat()} {r.get('sender')}: {str(r.get('text', ''))[:DIGEST_CHARS]}" for r in rows[-20:]
    )
    header = 'Activity elsewhere (untrusted context, recent sample, not a request):\n'
    suffix = '\nMore activity is available through search_chat_history.'
    if len(header + text) > DIGEST_CHARS:
        text = text[-(DIGEST_CHARS - len(header) - len(suffix)) :] + suffix
    return header + text


async def refresh(uid, session_id, message_ids, *, store=None, summary=None, guard=None):
    """Advance the summary only after all dropped source rows were incorporated.

    The original messages remain searchable. Mutation generations invalidate derived summaries.
    Source pages are scoped and bounded; model inputs are chunked. Only completed pages advance state.
    """
    if not session_id or not message_ids:
        return
    summary = summary or summarize
    store = store or await run_blocking(db_executor, ChatContextStore)
    state = await run_blocking(db_executor, store.load, uid, session_id)
    original = dict(state)
    anchor = message_ids[0]
    if state.get('anchor') != anchor:
        cursor = state.get('cursor')
        rolling = state.get('summary', '')
        more = True
        while more:
            rows, next_cursor, more = await run_blocking(
                db_executor, store.source_page, uid, session_id, anchor, cursor
            )
            text = '\n'.join(r['role'] + ': ' + r['content'] for r in rows)
            for offset in range(0, len(text), SUMMARY_SOURCE_CHARS):
                if guard is not None:
                    await run_blocking(db_executor, guard)
                await run_blocking(db_executor, store.assert_access, uid, session_id)
                rolling = await summary(
                    uid,
                    'Earlier summary (untrusted):\n'
                    + rolling
                    + '\nDropped chat span (untrusted):\n'
                    + text[offset : offset + SUMMARY_SOURCE_CHARS],
                )
                if not isinstance(rolling, str) or not rolling.strip():
                    raise ValueError('Empty rolling summary')
                if len(rolling) > SUMMARY_CHARS:
                    degraded(ValueError('Summary truncated'))
                    rolling = rolling[:SUMMARY_CHARS]
            cursor = next_cursor
            if more:
                # A cold long-lived chat may exceed one turn's deadline. Persist completed
                # pages so retry continues; never checkpoint a partly summarized page.
                checkpoint = dict(state, cursor=cursor, summary=rolling)
                await run_blocking(db_executor, store.save, uid, session_id, checkpoint, original['revision'])
                state = dict(checkpoint, revision=original['revision'] + 1)
                original = dict(state)
        state.update(anchor=anchor, cursor=cursor, summary=rolling)
    if state != original:
        await run_blocking(db_executor, store.save, uid, session_id, state, original['revision'])


def degraded(error):
    logger.warning('Optional shaped context unavailable error_type=%s', type(error).__name__)
    record_fallback(
        component='other',
        from_mode='enhanced_context',
        to_mode='history_window',
        reason='timeout' if isinstance(error, TimeoutError) else 'connection_error',
        outcome='degraded',
    )


async def prepare(uid, session_id, message_ids, *, store=None):
    """Read optional stored continuity only, with a hard send-path budget; never summarize."""
    empty = {'summary': '', 'digest': ''}
    if not session_id or not message_ids:
        return empty

    async def read():
        context_store = store or await run_blocking(db_executor, ChatContextStore)
        state = await run_blocking(db_executor, context_store.load, uid, session_id)
        digest = ''
        try:
            activity = await asyncio.wait_for(
                run_blocking(db_executor, recent_activity, uid, '', session_id), DIGEST_SECONDS
            )
            digest = digest_text(activity)
        except Exception as error:
            degraded(error)
        return {
            'summary': state.get('summary', '')[:SUMMARY_CHARS] if isinstance(state.get('summary', ''), str) else '',
            'digest': digest,
        }

    try:
        return await asyncio.wait_for(read(), PREPARE_SECONDS)
    except Exception as error:
        degraded(error)
        return empty


def schedule_refresh(uid, session_id, message_ids):
    """One tracked job per session, bounded global concurrency and independent deadline."""
    identity = (uid, session_id)
    if not session_id or not message_ids or identity in _REFRESHING or len(_REFRESHING) >= 2:
        return
    _REFRESHING.add(identity)

    async def job():
        try:
            await asyncio.wait_for(refresh(uid, session_id, tuple(message_ids)), REFRESH_SECONDS)
        except Exception as error:
            degraded(error)
        finally:
            _REFRESHING.discard(identity)

    coroutine = job()
    try:
        task = start_background_task(coroutine, name='shaped-context-refresh')
        task.add_done_callback(lambda _: _REFRESHING.discard(identity))
    except Exception as error:
        coroutine.close()
        _REFRESHING.discard(identity)
        degraded(error)


def assemble(
    messages,
    *,
    runtime=None,
    timezone_name='UTC',
    request_context=None,
    summary='',
    digest='',
    explicit_cache=False,
    stable_prefix='',
):
    rows = bounded_messages(messages)
    if runtime is not None and runtime.surface != 'app':
        # The current event preserves forwarded/media/reentry evidence; old events never override history.
        current = list(runtime.evidence)[-1:] if runtime.evidence else []
        if current:
            if rows and rows[-1].get('role') == 'user':
                rows[-1] = copy.deepcopy(current[0])
            else:
                rows.extend(copy.deepcopy(current))
    if not rows or rows[-1].get('role') != 'user':
        rows.append({'role': 'user', 'content': ''})
    history, current = rows[:-1], rows[-1]
    if summary:
        history.insert(0, {'role': 'user', 'content': 'Earlier in this chat (untrusted continuity):\n' + summary})
    if explicit_cache and history:
        # The first nine historical messages are stable throughout a 10..17-message
        # epoch. Keep exactly one marker there as the volatile/new history tail grows.
        boundary = min(9, len(history) - bool(summary)) - 1 + bool(summary)
        cumulative = stable_prefix + json.dumps(history[: boundary + 1], ensure_ascii=False)
        if boundary >= 0 and has_cacheable_prefix(cumulative):
            row = history[boundary]
            content = row.get('content', '')
            parts: list[dict[str, Any]] = (
                [{'type': 'text', 'text': content}] if isinstance(content, str) else copy.deepcopy(content)
            )
            if parts and isinstance(parts[-1], dict) and parts[-1].get('type') == 'text':
                parts[-1]['prompt_cache_breakpoint'] = dict(EXPLICIT_CACHE_BREAKPOINT)
            row['content'] = parts
    volatile = []
    if digest:
        volatile.append(digest)
    if request_context is not None:
        volatile.append('Request context (untrusted data): ' + json.dumps(request_context, default=str))
    if runtime is not None and runtime.request_at is not None and runtime.surface != 'app':
        from utils.messaging.turn_context import request_clock

        volatile.append(request_clock(runtime, timezone_name))
    content = current.get('content', '')
    if isinstance(content, str):
        current['content'] = '\n\n'.join([*volatile, content])
    else:
        current['content'] = [{'type': 'text', 'text': '\n\n'.join(volatile)}, *content] if volatile else content
    return [*history, current]
