"""Dedicated ThreadPoolExecutors for Lane 2 of the 3-lane async architecture (issue #6369).

Provides shared executors with strict separation (bulkhead pattern):
- critical_executor: process_conversation, memory extraction, action items, trends,
  goal progress, persona updates, webhook delivery, vector operations.
- sync_executor: sync pipeline VAD/STT/segment processing. Isolated from critical
  to prevent sync load from starving real-time conversation processing.
- postprocess_executor: best-effort post-processing (memories, trends, vectors,
  action items, goals). Separated so slow LLM retries cannot block sync or
  conversation processing.
- storage_executor: audio file precaching, GCS operations.

These replace ad-hoc ThreadPoolExecutor creation throughout the codebase,
preventing thread proliferation and providing bounded concurrency.
"""

import atexit
import contextvars
import logging
from concurrent.futures import Future, ThreadPoolExecutor

logger = logging.getLogger(__name__)

critical_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="critical")
sync_executor = ThreadPoolExecutor(max_workers=12, thread_name_prefix="sync")
postprocess_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="postproc")
storage_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="storage")


def submit_with_context(executor: ThreadPoolExecutor, fn, *args, **kwargs) -> Future:
    """Submit *fn* to *executor*, propagating the current contextvars (BYOK keys, etc.)."""
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)


def shutdown_executors():
    """Shut down all shared executors. Called at app shutdown."""
    for name, executor in [
        ('critical', critical_executor),
        ('sync', sync_executor),
        ('postprocess', postprocess_executor),
        ('storage', storage_executor),
    ]:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.warning(f"Error shutting down {name} executor: {e}")


atexit.register(shutdown_executors)
