"""One bounded Flex attempt after capture; Dream owns deferred attempts.

The shared processor owns revision leases, admission receipts, retry backoff,
source/privacy fences and idempotency. Capture must never roll back on failure.
"""

import asyncio
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Callable

from config import required_memory_intake as policy
from database._client import get_firestore_client
from database import dream_scheduler, required_intake_cursors
from database.memory_collections import MemoryCollections
from database.required_intake_fence import source_scope, assert_account_active, RequiredIntakeSourceChanged
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItem
from utils.executors import db_executor, llm_executor, run_blocking, ExecutorSaturatedError, after_db_call, in_db_worker
from utils.memory import canonical_required_processing as required
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
_capture_deadline = ContextVar[float | None]('required_intake_capture_deadline', default=None)
_capture_views = ContextVar[dict[tuple[str, str], list[tuple[Any, Callable[[str], None]]]] | None](
    'required_intake_views', default=None
)


def source_revisions(uid, item, *, db_client):
    # Canonical readers import this hook too; source/model work is write-only.
    from utils.memory.required_source_admission import source_revisions as admit

    return admit(uid, item, db_client=db_client)


@contextmanager
def capture_budget():
    """A batch shares one inline deadline; stragglers remain durable."""
    prior = _capture_deadline.get()
    token = _capture_deadline.set(prior or time.monotonic() + policy.INLINE_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        _capture_deadline.reset(token)


def normalize(item, *, request_timeout=policy.INLINE_TIMEOUT_SECONDS):
    # Explicit Flex route: one attempt, no Standard/on-demand fallback.
    try:
        from utils.llm.clients import feature_auto_lane_id, get_or_create_omi_gateway_llm
        from utils.llm.usage_tracker import track_usage

        llm = get_or_create_omi_gateway_llm(
            feature_auto_lane_id('memory_l2_flex'),
            options={'request_timeout': request_timeout, 'max_retries': 0},
            feature='memory_l2_flex',
        ).bind(service_tier='flex')
    except Exception as error:
        raise required.RequiredProcessingDeferred('required_intake_model_unavailable') from error
    try:
        with track_usage(item.uid, 'memory_l2_flex'):
            return required.invoke_required_memory_processor(item, llm)
    except Exception as error:
        # Availability never spends the processor's quality retry budget.
        if (
            isinstance(error, (TimeoutError, ConnectionError))
            or type(error).__name__
            in {'APITimeoutError', 'APIConnectionError', 'RateLimitError', 'InternalServerError'}
            or getattr(error, 'status_code', None) in {408, 409, 429, 500, 502, 503, 504}
        ):
            raise required.RequiredProcessingDeferred(type(error).__name__) from error
        raise


def result_guard(deadline):
    if not policy.enabled() or time.monotonic() >= deadline:
        raise required.RequiredProcessingDeferred('required_intake_disabled_or_deadline')


def _assert_dispatch_current(item, *, db_client, deadline):
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item

    result_guard(deadline)
    if item.captured_at < policy.BACKLOG_CUTOFF and not policy.backlog_enabled(item.uid):
        raise required.RequiredProcessingDeferred('required_intake_backlog_disabled')
    assert_account_active(item.uid, None, db_client)
    current = read_canonical_memory_item(item.uid, item.memory_id, db_client=db_client, include_inactive=True)
    if (
        current is None
        or not required.is_pending_required_processing(current)
        or current.item_revision != item.item_revision
        or current.content != item.content
        or current.source_state.value != 'active'
        or source_revisions(item.uid, current, db_client=db_client) is None
    ):
        raise RequiredIntakeSourceChanged('required_intake_dispatch_source_changed')
    control = MemoryControlState.model_validate(
        db_client.document(MemoryCollections(uid=item.uid).memory_apply_control_state).get().to_dict()
    )
    if control.account_generation != item.account_generation:
        raise RequiredIntakeSourceChanged('required_intake_dispatch_generation_changed')
    assert_account_active(item.uid, None, db_client)
    result_guard(deadline)


def normalize_at_dispatch(item, *, db_client, deadline, request_timeout=None):
    """Re-admit in the actual model worker, after any executor queue wait."""
    try:
        _assert_dispatch_current(item, db_client=db_client, deadline=deadline)
    except (required.RequiredProcessingDeferred, RequiredIntakeSourceChanged):
        raise
    except Exception as error:
        # Metadata availability is not a model quality failure.
        raise required.RequiredProcessingDeferred('required_intake_dispatch_unavailable') from error
    if request_timeout is None:
        return normalize(item)
    return normalize(item, request_timeout=min(request_timeout, max(1, int(deadline - time.monotonic()))))


def bounded_normalize(item, *, deadline, db_client):
    remaining = deadline - time.monotonic()
    if remaining < 1:
        raise required.RequiredProcessingDeferred('required_intake_deadline')
    # Quantized timeouts keep the shared model cache bounded to twelve clients.
    try:
        future = llm_executor.submit(
            normalize_at_dispatch, item, db_client=db_client, deadline=deadline, request_timeout=int(remaining)
        )
    except ExecutorSaturatedError as error:
        raise required.RequiredProcessingDeferred('required_intake_executor_busy') from error
    try:
        return future.result(timeout=remaining)
    except TimeoutError as error:
        # A running provider call may finish late, but it has no write authority.
        future.cancel()
        raise required.RequiredProcessingDeferred('required_intake_timeout') from error


# Closed set for the required_intake_inline reason token. Skip reasons mirror
# the literal skipped_reason values constructed in canonical_required_processing;
# attempted failures collapse to flex_deferred/failed (their error_code already
# reaches required_intake_deferred).
INLINE_SKIP_REASONS = frozenset(
    {
        'memory_not_found',
        'not_pending_required_processing',
        'account_generation_changed',
        'writer_mode_owned',
        'newer_revision_pending',
        'retry_backoff',
        'attempt_leased',
        'retry_exhausted',
        'processor_not_configured',
    }
)
INLINE_REASON_TOKENS = INLINE_SKIP_REASONS | {'processed', 'flex_deferred', 'failed', 'unclassified'}


def inline_reason(result) -> str:
    if result.processed:
        return 'processed'
    if result.skipped_reason is not None:
        return result.skipped_reason if result.skipped_reason in INLINE_SKIP_REASONS else 'unclassified'
    if result.error_code == 'flex_deferred':
        return 'flex_deferred'
    if result.error_code is not None:
        return 'failed'
    return 'unclassified'


def record_deferred(error=None):
    record_fallback(
        component='agent_tools',
        from_mode='required_inline',
        to_mode='dream_retry',
        reason='unavailable',
        outcome='degraded',
        log=logger,
    )
    logger.warning('required_intake_deferred error_type=%s', type(error).__name__ if error else 'processor_result')


def after_capture(uid, item: MemoryItem, *, db_client):
    """Call only after canonical apply commits. Historical replays stay gated."""
    if (
        not policy.enabled()
        or item.captured_at < policy.BACKLOG_CUTOFF
        or not required.is_pending_required_processing(item)
    ):
        return None
    deadline = _capture_deadline.get() or time.monotonic() + policy.INLINE_TIMEOUT_SECONDS
    views = (_capture_views.get() or {}).get((uid, item.memory_id), [])
    if after_db_call(partial(after_capture_async, uid, item, db_client=db_client, deadline=deadline, views=views)):
        pending_views = _capture_views.get()
        if pending_views is None:
            pending_views = {}
            _capture_views.set(pending_views)
        pending_views[(uid, item.memory_id)] = views
        return None
    if in_db_worker():
        # A raw synchronous submission has no async caller to await model IO.
        # Preserve the capture for Dream rather than occupying a shared DB worker.
        record_deferred(required.RequiredProcessingDeferred('required_intake_async_boundary_unavailable'))
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        revisions = source_revisions(uid, item, db_client=db_client)
        if revisions is None:
            return None
        with source_scope(uid, revisions, processing_id=item.memory_id):
            result = required.process_required_memory_item(
                uid,
                item.memory_id,
                db_client=db_client,
                processor=partial(bounded_normalize, deadline=deadline, db_client=db_client),
                result_guard=partial(result_guard, deadline),
            )
        logger.info(
            'required_intake_inline processed=%s attempted=%s reason=%s',
            result.processed,
            result.attempted,
            inline_reason(result),
        )
        if result.error_code:
            record_deferred()
        return result
    except Exception as error:
        record_deferred(error)
        return None


def register_capture_view(uid, item, view, invalidate):
    """Keep the returned single/batch API view current after deferred DB IO."""
    views = (_capture_views.get() or {}).get((uid, item.memory_id))
    if views is not None:
        views.append((view, invalidate))


def _refresh_views(uid, memory_id, views, client):
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item, memory_item_to_memorydb

    item = read_canonical_memory_item(uid, memory_id, db_client=client)
    if item is None:
        return
    current = memory_item_to_memorydb(item)
    for view, invalidate in views:
        for name in type(current).model_fields:
            setattr(view, name, getattr(current, name))
        invalidate(uid)


async def after_capture_async(uid, item, *, db_client, deadline, views=None):
    """DB claim, pure model wait and DB settlement use distinct executor leaves."""
    if not policy.enabled() or deadline <= time.monotonic():
        return None
    try:
        revisions = await run_blocking(db_executor, source_revisions, uid, item, db_client=db_client)
        if revisions is None or deadline <= time.monotonic():
            return None
        with source_scope(uid, revisions, processing_id=item.memory_id):
            result = await required.process_required_memory_item_async(
                uid,
                item.memory_id,
                db_client=db_client,
                processor=partial(normalize_at_dispatch, db_client=db_client, deadline=deadline),
                timeout_seconds=max(0, deadline - time.monotonic()),
                result_guard=partial(result_guard, deadline),
            )
        logger.info(
            'required_intake_inline processed=%s attempted=%s reason=%s',
            result.processed,
            result.attempted,
            inline_reason(result),
        )
        if views and (result.processed or result.skipped_reason == 'not_pending_required_processing'):
            await run_blocking(db_executor, _refresh_views, uid, item.memory_id, views, db_client)
        if result.error_code:
            record_deferred()
        return result
    except Exception as error:
        record_deferred(error)
        return None


async def retry_owner(uid, *, db_client=None, now=None):
    """Retry fresh stragglers; never let an old backlog consume the page."""
    if not policy.enabled():
        return 0
    client = db_client if db_client is not None else await run_blocking(db_executor, get_firestore_client)
    current = now or datetime.now(timezone.utc)
    before, cursor, generation = await run_blocking(
        db_executor, required_intake_cursors.load, uid, 'retry', db_client=client
    )
    items = await run_blocking(
        db_executor,
        required.list_pending_required_processing_items,
        uid,
        db_client=client,
        limit=required.MAX_REQUIRED_PROCESSING_QUERY_SCAN,
        captured_after=policy.BACKLOG_CUTOFF,
        captured_before=current - timedelta(minutes=policy.RETRY_MIN_AGE_MINUTES),
        cursor=cursor,
    )
    if not items and cursor:
        items = await run_blocking(
            db_executor,
            required.list_pending_required_processing_items,
            uid,
            db_client=client,
            limit=required.MAX_REQUIRED_PROCESSING_QUERY_SCAN,
            captured_after=policy.BACKLOG_CUTOFF,
            captured_before=current - timedelta(minutes=policy.RETRY_MIN_AGE_MINUTES),
        )
    processed = 0
    attempted = 0
    visited = None
    for item in items:
        if not policy.enabled() or attempted >= policy.RETRY_ITEMS_PER_OWNER:
            break
        visited = {'captured_at': item.captured_at, 'memory_id': item.memory_id}
        try:
            revisions = await run_blocking(db_executor, source_revisions, uid, item, db_client=client)
        except Exception as error:
            record_deferred(error)
            continue
        if revisions is None:
            continue
        try:
            deadline = time.monotonic() + policy.INLINE_TIMEOUT_SECONDS
            with source_scope(uid, revisions, processing_id=item.memory_id):
                result = await required.process_required_memory_item_async(
                    uid,
                    item.memory_id,
                    db_client=client,
                    processor=partial(normalize_at_dispatch, db_client=client, deadline=deadline),
                    timeout_seconds=policy.INLINE_TIMEOUT_SECONDS,
                    result_guard=partial(result_guard, deadline),
                )
        except Exception as error:
            attempted += 1  # Conservatively charge an unknown provider/settlement outcome.
            record_deferred(error)
            continue
        attempted += int(result.attempted)
        processed += int(result.processed)
    if policy.enabled() and (visited is not None or cursor):
        await run_blocking(
            db_executor, required_intake_cursors.finish, uid, 'retry', before, visited, generation, db_client=client
        )
    logger.info('required_intake_retry scanned=%d processed=%d', len(items), processed)
    return processed


async def retry_due_owners(owners, *, complete_owner=None):
    """Bound the sweep, keep DB threads free during model waits, retain due rows."""
    if not policy.enabled():
        return 0
    queue = iter(enumerate(owners))
    completed = set()

    async def worker():
        for index, uid in queue:
            if not policy.enabled():
                return
            try:
                await retry_owner(uid)
                if complete_owner is not None and policy.enabled():
                    client = await run_blocking(db_executor, get_firestore_client)
                    completion = await run_blocking(
                        db_executor,
                        complete_owner,
                        uid,
                        db_client=client,
                        now=datetime.now(timezone.utc),
                        run_id='dream-required-intake',
                        limit=5,
                    )
                    logger.info(
                        'required_intake_completion promoted=%d failed=%d',
                        len(completion.promoted_memory_ids),
                        len(completion.failed_memory_ids),
                    )
            except Exception as error:
                record_deferred(error)
            completed.add(index)

    try:
        async with asyncio.timeout(120):
            async with asyncio.TaskGroup() as group:
                for _ in range(4):
                    group.create_task(worker())
    except TimeoutError:
        logger.info('required_intake_retry outcome=sweep_budget')
    prefix = 0
    while prefix in completed:
        prefix += 1
    return prefix


async def retry_sweep(*, limit=4990, complete_owner=None):
    if not policy.enabled() or limit <= 0:
        return
    try:
        owners, before = await run_blocking(db_executor, dream_scheduler.required_retry_page, limit=limit)
        completed = await retry_due_owners(owners, complete_owner=complete_owner)
        if not owners or completed:
            await run_blocking(
                db_executor,
                dream_scheduler.finish_required_retry_page,
                before,
                owners[completed - 1] if completed else None,
            )
    except Exception as error:
        record_deferred(error)
