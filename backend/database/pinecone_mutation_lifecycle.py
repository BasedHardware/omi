"""Bounded, process-local shutdown bookkeeping; Firestore remains authoritative.

Reservations close the race between admission and shutdown without holding a
process-wide lock over Firestore IO. A late admission settles before returning
to its provider caller. No provider work is retried by this registry.
"""

import asyncio
from collections.abc import Callable
import contextvars
import logging
import signal
from threading import Condition, current_thread, main_thread
from time import monotonic
from typing import Any

from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)
PENDING = Gauge('omi_pinecone_mutations_inflight', 'Process-local admitted or admitting Pinecone mutations')
UNCERTAIN = Counter('omi_pinecone_mutation_uncertain_marks_total', 'Successful uncertain settlement calls')
DRAIN_ERRORS = Counter('omi_pinecone_mutation_drain_errors_total', 'Failed shutdown settlement calls')


def install_shutdown_drain(drain: Callable[[], Any]) -> Callable[[], None]:
    """Schedule settlement on SIGTERM before Uvicorn waits for active requests.

    Only chain an installed server handler. Standalone jobs, default/ignored
    signals and event loops hosted outside the main thread are left alone.
    The signal handler only schedules work; it never locks the registry or
    performs provider/Firestore IO.
    """
    if current_thread() is not main_thread():
        return lambda: None
    previous = signal.getsignal(signal.SIGTERM)
    if not callable(previous):
        return lambda: None
    loop = asyncio.get_running_loop()
    scheduled = False

    def launch() -> None:
        from utils.executors import start_background_task

        start_background_task(drain_on_shutdown(drain), name='pinecone:shutdown-drain')

    def handle(signum: int, frame: Any) -> None:
        nonlocal scheduled
        try:
            if not scheduled:
                scheduled = True
                loop.call_soon_threadsafe(launch)
        except RuntimeError:
            # A closing loop cannot schedule; still deliver the server signal.
            pass
        finally:
            previous(signum, frame)

    signal.signal(signal.SIGTERM, handle)

    def restore() -> None:
        if signal.getsignal(signal.SIGTERM) is handle:
            signal.signal(signal.SIGTERM, previous)

    return restore


async def drain_on_shutdown(drain: Callable[[], Any], *, timeout: float = 5.0) -> None:
    """Reserve grace for audio/client cleanup even when Firestore is unavailable.

    Timeout stops waiting, not the worker: settlement may continue during the
    remaining platform grace. It never asserts that the provider has stopped.
    """
    from utils.executors import get_pinecone_shutdown_executor

    try:
        # Keep the executor-owned Future alive even if timeout or later task
        # cancellation stops awaiting it. Neither default-pool starvation nor
        # background-task cancellation may discard a queued settlement retry.
        future = asyncio.get_running_loop().run_in_executor(
            get_pinecone_shutdown_executor(), contextvars.copy_context().run, drain
        )
        await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
    except TimeoutError:
        logger.warning('event=pinecone_mutation_drain outcome=shutdown_wait_timeout')
    except Exception:
        logger.error('event=pinecone_mutation_drain outcome=shutdown_failed')


class MutationRegistry:
    def __init__(self, limit: int = 4096, *, grace_seconds: float = 3.0):
        self._lock = Condition()
        self._entries: dict[tuple, Callable[[], Any] | None] = {}
        self._draining = False
        self._limit = limit
        # Cloud Run sends SIGKILL ten seconds after SIGTERM. The existing
        # five-second outer wait leaves settlement and other cleanup margin.
        self._grace_seconds = grace_seconds
        self._deadline: float | None = None

    def reserve(self, identity: tuple) -> None:
        with self._lock:
            if self._draining:
                raise RuntimeError('Pinecone mutations are draining')
            if identity in self._entries or len(self._entries) >= self._limit:
                raise RuntimeError('Pinecone mutation registry is full or ticket is already active')
            self._entries[identity] = None
            PENDING.inc()

    def start(self) -> None:
        """Allow a fresh application lifespan only after the previous one drained."""
        with self._lock:
            if self._draining and self._entries:
                raise RuntimeError('Pinecone mutation shutdown has unresolved local tickets')
            self._draining = False
            self._deadline = None

    def activate(self, identity: tuple, settle: Callable[[], Any]) -> bool:
        with self._lock:
            self._entries[identity] = settle
            return self._draining

    def discard(self, identity: tuple) -> None:
        with self._lock:
            if identity in self._entries:
                del self._entries[identity]
                PENDING.dec()
                self._lock.notify_all()

    def drain(self) -> int:
        """Close admission, allow normal completion, then mark stragglers uncertain.

        Failed writes remain registered for a subsequent drain attempt. Already
        admitting transactions settle in their own thread before provider IO.
        SIGKILL/OOM and unavailable Firestore cannot be repaired in process.
        """
        with self._lock:
            self._draining = True
            if self._deadline is None:
                self._deadline = monotonic() + self._grace_seconds
            # Condition.wait releases the lock: provider threads can finish
            # and discard their tickets throughout the grace. Reservations
            # without a callback settle in activate's caller before provider IO.
            while any(callback is not None for callback in self._entries.values()):
                remaining = self._deadline - monotonic()
                if remaining <= 0:
                    break
                self._lock.wait(remaining)
            callbacks = [callback for callback in self._entries.values() if callback is not None]
        if callbacks:
            logger.info('event=pinecone_mutation_drain outcome=grace_deadline attempted=%d', len(callbacks))
        settled = 0
        for callback in callbacks:
            try:
                callback()
                settled += 1
            except Exception:
                DRAIN_ERRORS.inc()
                # Never log owner, operation identity, paths or provider errors.
                logger.error('event=pinecone_mutation_drain outcome=settlement_failed')
        logger.info('event=pinecone_mutation_drain settled=%d attempted=%d', settled, len(callbacks))
        return settled
