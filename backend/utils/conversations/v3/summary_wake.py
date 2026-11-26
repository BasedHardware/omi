"""Waiting requests for a v3 conversation after End (reliability experiment ``fast_end_feedback``).

Baseline: after End the app learns of each step from its next poll, up to 5 s later.
With the experiment on, the builder publishes the conversation id twice: when it commits the ended
conversation with its outline (title, emoji, one-liner; the row leaves ``live``), and when the summary
is stored (the row shows ``done``). ``GET /v1/conversations/{id}/summary/wait`` returns the conversation
on the wake it was asked to wait for (``until=outline`` or ``until=summary``). The row is the authority:
the waiter also re-reads it every few seconds, so a lost wake only costs that interval.
Off, nothing is published and the path does not exist.
"""

import asyncio
import logging
import time

from config import reliability_experiments
from utils.sync import stage as sync_stage

logger = logging.getLogger(__name__)

EXPERIMENT = 'fast_end_feedback'
WAIT_SECONDS = 20
RECHECK_SECONDS = 5
SETTLED_STATES = frozenset({'done', 'failed'})
SETTLED_STATUSES = frozenset({'completed', 'failed'})
OUTLINED_STATES = frozenset({'transcribing', 'writing'}) | SETTLED_STATES
# Done and failed are published by the summary step itself.
COMMIT_WAKE_STATES = frozenset({'transcribing', 'writing'})


def enabled(uid: str | None) -> bool:
    return reliability_experiments.enabled(EXPERIMENT, uid)


def channel(uid: str) -> str:
    return sync_stage.redis_key(f'v3_summary_ready:{uid}')


def settled(row) -> bool:
    """Whether the app has nothing more to wait for on this row."""
    if row.get('v3_derived'):
        return row.get('tile_state') in SETTLED_STATES
    return getattr(row.get('status'), 'value', row.get('status')) in SETTLED_STATUSES


def advanced(row) -> bool:
    """Whether the builder has committed the ended conversation: it is no longer ``live``."""
    if row.get('v3_derived'):
        return row.get('tile_state') in OUTLINED_STATES
    return settled(row)


STAGES = {'outline': advanced, 'summary': settled}


def state(row) -> str:
    """What the answer carries: ``ready`` (settled), ``outline`` (committed, summary to come) or ``timeout``."""
    return 'ready' if settled(row) else 'outline' if advanced(row) else 'timeout'


def publish_committed(uid: str, rows, existing) -> None:
    """After a builder commit: wake the waiters of each conversation that just left ``live``."""
    if not enabled(uid):
        return
    for row in rows:
        before = (existing.get(row['id']) or {}).get('tile_state')
        if row.get('tile_state') in COMMIT_WAKE_STATES and before != row.get('tile_state'):
            publish(uid, row['id'])


def publish(uid: str, conversation_id: str) -> None:
    """Best-effort: the row is already written, and a waiter re-reads it without this."""
    if not enabled(uid):
        return
    try:
        from database.redis_db import r

        r.publish(channel(uid), conversation_id)
    except Exception as error:
        logger.warning('event=v3_summary_wake outcome=error exception_type=%s', type(error).__name__)


async def wait(
    uid: str,
    conversation_id: str,
    read,
    disconnected,
    *,
    until='summary',
    seconds=WAIT_SECONDS,
    recheck=RECHECK_SECONDS,
):
    """Return ``(row, state)`` as soon as the row reaches ``until``, or the current row after ``seconds``.

    ``until`` is ``outline`` (the builder committed the ended conversation) or ``summary`` (it settled).

    ``read`` is an awaitable that returns the stored row (and raises what a detail read raises).
    Subscribes before the first read so a wake between the read and the wait is not lost. Without
    Redis the waiter still works on the re-read interval.
    """
    from database.redis_db import get_async_redis_client

    reached = STAGES[until]
    deadline = time.monotonic() + seconds

    async def poll(next_message):
        row = await read()
        checked = time.monotonic()
        while not reached(row):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or await disconnected():
                break
            woke = await next_message(min(1, remaining))
            if woke or time.monotonic() - checked >= recheck:
                row = await read()
                checked = time.monotonic()
        return row, state(row)

    subscription = None
    try:
        redis = await get_async_redis_client()
        subscription = redis.pubsub()
        sub = await subscription.__aenter__()
        await sub.subscribe(channel(uid))
        await sub.get_message(timeout=3)
    except Exception as error:
        logger.warning('event=v3_summary_wait outcome=no_wake exception_type=%s', type(error).__name__)
        sub = None

    async def next_message(timeout):
        if sub is None:
            await asyncio.sleep(timeout)
            return False
        try:
            message = await sub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        except Exception:
            await asyncio.sleep(timeout)
            return False
        return bool(message and message.get('data') == conversation_id)

    try:
        return await poll(next_message)
    finally:
        if subscription is not None:
            try:
                await subscription.__aexit__(None, None, None)
            except Exception:
                pass
