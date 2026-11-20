"""Executor barrier: wait for fire-and-forget work a conversation started.

``process_conversation`` hands action items, goals, vectors, webhooks and more to
``utils.executors.postprocess_executor`` (and friends) without waiting. Exporting
before that work drains would read a half-finished conversation, and the next
conversation would read stale state (task dedup, memory intake, goal progress).

The barrier wraps ``submit`` (and ``submit_when_available``) on the executor
*instances*, which every importer shares, records each future, and waits until no
tracked future is pending. Work submitted by tracked work is tracked too, so the
wait loops until the set is quiet.
"""

from __future__ import annotations

from concurrent.futures import Future, wait as wait_futures, FIRST_COMPLETED
from contextlib import ExitStack
import threading
import time
from typing import Any, Iterable

DEFAULT_EXECUTORS = (
    'postprocess_executor',
    'llm_executor',
    'db_executor',
    'storage_executor',
    'open_loops_executor',
    'admission_executor',
)


class BarrierTimeout(TimeoutError):
    pass


class ExecutorBarrier:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: set[Future] = set()
        self.submitted = 0
        self.failed = 0
        self.errors: list[str] = []

    def _track(self, future: Future) -> Future:
        with self._lock:
            self._pending.add(future)
            self.submitted += 1

        def done(f: Future) -> None:
            with self._lock:
                self._pending.discard(f)
                if not f.cancelled() and f.exception() is not None:
                    self.failed += 1
                    self.errors.append(type(f.exception()).__name__)

        future.add_done_callback(done)
        return future

    def instrument(self, stack: ExitStack, executor: Any) -> None:
        """Wrap one executor instance's submit methods for the block."""
        barrier = self
        for name in ('submit', 'submit_when_available'):
            original = getattr(executor, name, None)
            if original is None:
                continue

            def wrapped(*args: Any, __original=original, **kwargs: Any) -> Any:
                future = __original(*args, **kwargs)
                if isinstance(future, Future):
                    barrier._track(future)
                return future

            setattr(executor, name, wrapped)

            def restore(__executor=executor, __name=name) -> None:
                try:
                    delattr(__executor, __name)  # drop the instance attribute; class method shows again
                except AttributeError:
                    pass

            stack.callback(restore)

    def instrument_product(self, stack: ExitStack, names: Iterable[str] = DEFAULT_EXECUTORS) -> list[str]:
        from utils import executors

        instrumented = []
        for name in names:
            executor = getattr(executors, name, None)
            if executor is not None:
                self.instrument(stack, executor)
                instrumented.append(name)
        return instrumented

    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    def wait(self, timeout: float = 300.0, *, settle: float = 0.05) -> float:
        """Block until no tracked work is pending (stable for ``settle`` seconds)."""
        started = time.monotonic()
        deadline = started + timeout
        while True:
            with self._lock:
                pending = list(self._pending)
            if not pending:
                time.sleep(settle)
                with self._lock:
                    if not self._pending:
                        return time.monotonic() - started
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BarrierTimeout(f'{len(pending)} background tasks still pending')
            wait_futures(pending, timeout=min(remaining, 1.0), return_when=FIRST_COMPLETED)


async def drain_event_loop(timeout: float = 120.0) -> tuple[int, int]:
    """Await tasks the product left on the running loop (``asyncio.create_task`` work).

    Returns ``(drained, still_pending)``. A long-lived background loop never finishes,
    so running out of time is reported, not raised; the driver records it as a warning.
    """
    import asyncio

    current = asyncio.current_task()
    deadline = time.monotonic() + timeout
    drained = 0
    while True:
        tasks = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
        if not tasks:
            return drained, 0
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return drained, len(tasks)
        done, _ = await asyncio.wait(tasks, timeout=min(remaining, 1.0))
        drained += len(done)
