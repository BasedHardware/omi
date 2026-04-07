"""Dedicated ThreadPoolExecutors for Lane 2 of the 3-lane async architecture (issue #6369).

Provides two shared executors with strict separation:
- critical_executor: process_conversation, memory extraction, action items, trends,
  goal progress, persona updates, webhook delivery, vector operations.
  Never shared with best-effort work.
- storage_executor: audio file precaching, GCS operations.

These replace ad-hoc ThreadPoolExecutor creation throughout the codebase,
preventing thread proliferation and providing bounded concurrency.
"""

import atexit
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

critical_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="critical")
storage_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="storage")


def shutdown_executors():
    """Shut down all shared executors. Called at app shutdown."""
    for name, executor in [('critical', critical_executor), ('storage', storage_executor)]:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.warning(f"Error shutting down {name} executor: {e}")


atexit.register(shutdown_executors)
