"""Shared bounded shaped context: epoch summary, immutable history, volatile final turn."""

import asyncio
import logging
from typing import Any
import copy
import json
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar

from database.chat_context import ChatContextStore
from database.chat_history_window import cache_aligned_history_limit
from utils.executors import (
    db_executor,
    get_context_executor,
    ExecutorSaturatedError,
    run_blocking,
    start_background_task,
)
from utils.observability.fallback import record_fallback
from utils.messaging.history import summarize, recent_activity
from utils.llm.prompt_cache import EXPLICIT_CACHE_BREAKPOINT, has_cacheable_prefix
from utils.messaging.metrics import CONTEXT_TURNS, CONTEXT_READS, CONTEXT_SETUP_OVERLAP
from utils.messaging.projection import surface_runtime

SUMMARY_CHARS = 2400
DIGEST_CHARS = 3200
SUMMARY_SOURCE_CHARS = 12000
PREPARE_SECONDS = 0.15
# Guarded refresh_load is the uncensored equivalent of the foreground load:
# observed p95 0.86s. This window overlaps setup; consumption never waits for it.
PREFETCH_SECONDS = 1.0
FENCE_SECONDS = 0.15
REFRESH_SECONDS = 60
_REFRESHING = set()
logger = logging.getLogger(__name__)
_preparation: ContextVar[Any] = ContextVar('shaped_context_preparation', default=None)


def context_surface():
    runtime = surface_runtime.get()
    channel = runtime.channel if runtime is not None else None
    return channel if channel in ('telegram', 'imessage') else 'app'


async def measured(phase, operation, *, timeout=None):
    start = time.monotonic()
    try:
        return await asyncio.wait_for(operation, timeout) if timeout is not None else await operation
    except Exception as error:
        # Metadata only: never stringify exceptions or log their locals/payloads.
        setattr(error, 'shaped_context_phase', phase)
        raise
    finally:
        CONTEXT_READS.labels(context_surface(), phase).observe(time.monotonic() - start)


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
    state = await measured('refresh_load', run_blocking(db_executor, store.load, uid, session_id))
    original: dict[str, Any] = dict(state)
    anchor = message_ids[0]
    if state.get('anchor') != anchor:
        cursor = state.get('cursor')
        rolling = state.get('summary', '')
        more = True
        while more:
            rows, next_cursor, more = await measured(
                'source_page', run_blocking(db_executor, store.source_page, uid, session_id, anchor, cursor)
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
                    # Model length instructions are soft. The persisted contract
                    # is enforced here; bounded clipping is not a context outage.
                    logger.info('Shaped context summary capped surface=%s limit=%d', context_surface(), SUMMARY_CHARS)
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


def degraded(error, *, phase='refresh'):
    phase = getattr(error, 'shaped_context_phase', phase)
    site = 'deadline' if isinstance(error, TimeoutError) else 'unknown'
    trace = error.__traceback__
    while trace is not None:
        filename = trace.tb_frame.f_code.co_filename
        if '/database/' in filename or '/utils/' in filename:
            site = '/'.join(filename.split('/')[-2:]) + ':' + trace.tb_frame.f_code.co_name + ':' + str(trace.tb_lineno)
        trace = trace.tb_next
    reason = 'timeout' if isinstance(error, TimeoutError) else 'connection_error'
    if isinstance(error, PermissionError):
        reason = 'auth_error'
    logger.warning(
        'Optional shaped context unavailable surface=%s phase=%s error_type=%s code_site=%s',
        context_surface(),
        phase,
        type(error).__name__,
        site,
    )
    record_fallback(
        component='other',
        from_mode='enhanced_context',
        to_mode='history_window',
        reason=reason,
        outcome='degraded',
    )


def _prepared_result(state, digest, *, pending=False):
    for result in (state, digest):
        if isinstance(result, Exception):
            degraded(result)
    readable = isinstance(state, dict)
    summary = state.get('summary', '') if readable else ''
    outcome = (
        ('summary_pending' if pending else 'degraded')
        if not readable
        else (
            ('digest_degraded' if summary else 'empty_digest_degraded')
            if not isinstance(digest, str)
            else 'summary' if summary else 'empty'
        )
    )
    CONTEXT_TURNS.labels(context_surface(), outcome).inc()
    return {
        'summary': summary[:SUMMARY_CHARS] if isinstance(summary, str) else '',
        # A failed owner/link/generation guard also discards the independent digest.
        'digest': digest if readable and isinstance(digest, str) else '',
    }


class ContextPreparation:
    """Request-owned reads, started before setup and sampled independently at the mount."""

    def __init__(self, uid, session_id, message_ids, *, store=None, timeout=PREFETCH_SECONDS):
        self.identity = (uid, session_id)
        self.scoped = bool(session_id and message_ids)
        self.started = time.monotonic()
        self.result = None
        self.tasks = []
        self.store = store
        if not self.scoped:
            return

        async def continuity():
            self.store = store or await run_blocking(get_context_executor(), ChatContextStore)
            return await run_blocking(get_context_executor(), self.store.load_for_turn, uid, session_id)

        async def activity_digest():
            activity = await run_blocking(get_context_executor(), recent_activity, uid, '', session_id)
            return digest_text(activity)

        async def read(phase, operation):
            try:
                return await measured(phase, operation, timeout=timeout)
            except Exception as error:
                # Return errors to the consumer: tracked-task logging must never
                # stringify Firestore/provider exceptions or double-count them.
                return error

        for phase, operation in (('summary_load', continuity()), ('digest', activity_digest())):
            self.tasks.append(start_background_task(read(phase, operation), name='shaped-context-' + phase))

    def take(self, *, guard_error=None):
        """Sample completed data; the fresh mount guard is checked separately."""
        if self.result is not None:
            if guard_error is not None:
                degraded(guard_error)
                return {'summary': '', 'digest': ''}
            return self.result
        if not self.scoped:
            CONTEXT_TURNS.labels(context_surface(), 'unscoped').inc()
            self.result = {'summary': '', 'digest': ''}
            return self.result
        results = []
        for phase, task in zip(('summary', 'digest'), self.tasks):
            if task.done() and not task.cancelled():
                results.append(task.result())
            else:
                error = TimeoutError()
                setattr(error, 'shaped_context_phase', phase + '_not_ready')
                results.append(error)
        if guard_error is not None:
            results[0] = guard_error
        self.result = _prepared_result(
            *results,
            pending=not self.tasks[0].done()
            or isinstance(results[0], ExecutorSaturatedError)
            or isinstance(guard_error, TimeoutError),
        )
        return self.result

    async def checked_take(self):
        # Re-read projected access and invalidation fences at injection, not at
        # the beginning of potentially long setup. One BatchGet, no queue.
        if self.scoped and self.tasks[0].done() and not self.tasks[0].cancelled():
            state = self.tasks[0].result()
            if isinstance(state, dict):
                try:
                    assert self.store is not None
                    started = time.monotonic()
                    await measured(
                        'fence_check',
                        run_blocking(
                            get_context_executor(), self.store.validate_for_turn, *self.identity, state, FENCE_SECONDS
                        ),
                        timeout=FENCE_SECONDS,
                    )
                    if time.monotonic() - started > FENCE_SECONDS:
                        error = TimeoutError()
                        setattr(error, 'shaped_context_phase', 'fence_check')
                        raise error
                except Exception as error:
                    return self.take(guard_error=error)
        return self.take()

    async def close(self):
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


@asynccontextmanager
async def preparation_scope(uid, session_id, message_ids):
    pending = ContextPreparation(uid, session_id, message_ids)
    token = _preparation.set(pending)
    try:
        yield pending
    finally:
        _preparation.reset(token)
        await pending.close()


async def take_prepared(uid, session_id):
    pending = _preparation.get()
    if pending is None or pending.identity != (uid, session_id):
        return None
    if pending.scoped and pending.result is None:
        CONTEXT_SETUP_OVERLAP.labels(context_surface()).observe(time.monotonic() - pending.started)
    return await pending.checked_take()


async def prepare(uid, session_id, message_ids, *, store=None):
    """Bounded direct-call seam; streaming callers prefetch through preparation_scope."""
    pending = ContextPreparation(uid, session_id, message_ids, store=store, timeout=PREPARE_SECONDS)
    try:
        await asyncio.gather(*pending.tasks)
        return pending.take()
    finally:
        await pending.close()


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
