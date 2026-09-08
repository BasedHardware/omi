"""Executor-backed synchronous storage boundary for live listen sessions."""

from __future__ import annotations

from typing import Any, Callable

from utils.executors import db_executor, run_blocking


class ListenPersistence:
    """Run Firestore/Redis-backed operations without blocking the WS event loop.

    Database modules in this repository expose synchronous functions.  Session
    components receive this small boundary instead of importing those modules,
    making the async/offload contract both explicit and easy to fake in tests.
    """

    async def call(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await run_blocking(db_executor, function, *args, **kwargs)
