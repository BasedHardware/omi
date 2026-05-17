"""Dedicated ThreadPoolExecutors for Lane 2 of the 3-lane async architecture (issue #6369).

Provides shared executors with strict separation (bulkhead pattern):
- critical_executor: auth verification, rate limiting, hard restriction checks,
  small session/code cache reads. Must never starve — gates every request.
- db_executor: Firestore CRUD and Redis data mutations. High volume, moderate latency.
- llm_executor: persona generation, onboarding LLM, slow model-backed work. Bulkhead
  to prevent slow LLM retries from blocking DB or auth operations.
- stripe_executor: Stripe API calls (Subscription.retrieve, etc.). External network I/O
  with unpredictable latency, isolated from everything else.
- sync_executor: sync pipeline VAD/STT/segment processing.
- postprocess_executor: best-effort post-processing (memories, trends, vectors,
  action items, goals, conversation processing, webhook delivery).
- storage_executor: audio file precaching, GCS operations.

These replace ad-hoc ThreadPoolExecutor creation throughout the codebase,
preventing thread proliferation and providing bounded concurrency.
"""

import asyncio
import atexit
import contextvars
import functools
import logging
from concurrent.futures import Future, ThreadPoolExecutor

logger = logging.getLogger(__name__)

critical_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="critical")
db_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="db")
llm_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm")
stripe_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="stripe")
sync_executor = ThreadPoolExecutor(max_workers=12, thread_name_prefix="sync")
postprocess_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="postproc")
storage_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="storage")


async def run_blocking(executor: ThreadPoolExecutor, fn, *args, **kwargs):
    """Offload *fn* to *executor*, propagating ContextVars."""
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    call = functools.partial(ctx.run, functools.partial(fn, *args, **kwargs))
    return await loop.run_in_executor(executor, call)


def submit_with_context(executor: ThreadPoolExecutor, fn, *args, **kwargs) -> Future:
    """Submit *fn* to *executor*, propagating the current contextvars (BYOK keys, etc.)."""
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)


def shutdown_executors():
    """Shut down all shared executors. Called at app shutdown."""
    for name, executor in [
        ('critical', critical_executor),
        ('db', db_executor),
        ('llm', llm_executor),
        ('stripe', stripe_executor),
        ('sync', sync_executor),
        ('postprocess', postprocess_executor),
        ('storage', storage_executor),
    ]:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.warning(f"Error shutting down {name} executor: {e}")


atexit.register(shutdown_executors)
