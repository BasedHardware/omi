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

from config import required_memory_intake as policy
from database._client import get_firestore_client
from database import dream_scheduler
from database.required_intake_fence import source_scope
from models.product_memory import MemoryItem
from utils.executors import db_executor, llm_executor, run_blocking, ExecutorSaturatedError
from utils.llm.clients import feature_auto_lane_id, get_or_create_omi_gateway_llm
from utils.llm.usage_tracker import track_usage
from utils.memory import canonical_required_processing as required
from utils.memory.promotion_flex import PromotionFlexDeferred
from utils.memory.required_source_admission import source_revisions
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
_capture_deadline = ContextVar[float | None]('required_intake_capture_deadline', default=None)


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
        llm = get_or_create_omi_gateway_llm(
            feature_auto_lane_id('memory_l2_flex'),
            options={'request_timeout': request_timeout, 'max_retries': 0},
            feature='memory_l2_flex',
        ).bind(service_tier='flex')
    except Exception as error:
        raise PromotionFlexDeferred('required_intake_model_unavailable') from error
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
            raise PromotionFlexDeferred(type(error).__name__) from error
        raise


def result_guard(deadline):
    if not policy.enabled() or time.monotonic() >= deadline:
        raise PromotionFlexDeferred('required_intake_disabled_or_deadline')


def bounded_normalize(item, *, deadline):
    remaining = deadline - time.monotonic()
    if remaining < 1:
        raise PromotionFlexDeferred('required_intake_deadline')
    # Quantized timeouts keep the shared model cache bounded to twelve clients.
    try:
        future = llm_executor.submit(normalize, item, request_timeout=int(remaining))
    except ExecutorSaturatedError as error:
        raise PromotionFlexDeferred('required_intake_executor_busy') from error
    try:
        return future.result(timeout=remaining)
    except TimeoutError as error:
        # A running provider call may finish late, but it has no write authority.
        future.cancel()
        raise PromotionFlexDeferred('required_intake_timeout') from error


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
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        revisions = source_revisions(uid, item, db_client=db_client)
        if revisions is None:
            return None
        with source_scope(uid, revisions):
            result = required.process_required_memory_item(
                uid,
                item.memory_id,
                db_client=db_client,
                processor=partial(bounded_normalize, deadline=deadline),
                result_guard=partial(result_guard, deadline),
            )
        logger.info('required_intake_inline processed=%s attempted=%s', result.processed, result.attempted)
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
    client = db_client if db_client is not None else get_firestore_client()
    current = now or datetime.now(timezone.utc)
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
    for item in items:
        if not policy.enabled() or attempted >= policy.RETRY_ITEMS_PER_OWNER:
            break
        revisions = await run_blocking(db_executor, source_revisions, uid, item, db_client=client)
        if revisions is None:
            continue
        with source_scope(uid, revisions):
            result = await required.process_required_memory_item_async(
                uid,
                item.memory_id,
                db_client=client,
                processor=normalize,
                timeout_seconds=policy.INLINE_TIMEOUT_SECONDS,
                result_guard=partial(result_guard, time.monotonic() + policy.INLINE_TIMEOUT_SECONDS),
            )
        attempted += int(result.attempted)
        processed += int(result.processed)
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
                    completion = await run_blocking(
                        db_executor,
                        complete_owner,
                        uid,
                        db_client=get_firestore_client(),
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
