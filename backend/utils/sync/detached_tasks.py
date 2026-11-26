"""Retrieve detached sync-task outcomes without leaving unobserved exceptions."""

import asyncio


def consume_detached_outcome(task: asyncio.Future) -> None:
    """Retrieve a detached task's eventual outcome once it settles, so a late
    failure of work its handler has stopped waiting on cannot resurface as an
    unretrieved-exception warning."""
    if not task.done():
        task.add_done_callback(consume_detached_outcome)
        return
    if not task.cancelled():
        task.exception()
