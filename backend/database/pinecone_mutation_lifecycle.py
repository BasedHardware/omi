"""Bounded, process-local shutdown bookkeeping; Firestore remains authoritative.

Reservations close the race between admission and shutdown without holding a
process-wide lock over Firestore IO. A late admission settles before returning
to its provider caller. No provider work is retried by this registry.
"""

from collections.abc import Callable
import logging
from threading import Lock
from typing import Any

from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)
PENDING = Gauge('omi_pinecone_mutations_inflight', 'Process-local admitted or admitting Pinecone mutations')
UNCERTAIN = Counter('omi_pinecone_mutation_uncertain_marks_total', 'Successful uncertain settlement calls')
DRAIN_ERRORS = Counter('omi_pinecone_mutation_drain_errors_total', 'Failed shutdown settlement calls')


class MutationRegistry:
    def __init__(self, limit: int = 4096):
        self._lock = Lock()
        self._entries: dict[tuple, Callable[[], Any] | None] = {}
        self._draining = False
        self._limit = limit

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

    def activate(self, identity: tuple, settle: Callable[[], Any]) -> bool:
        with self._lock:
            self._entries[identity] = settle
            return self._draining

    def discard(self, identity: tuple) -> None:
        with self._lock:
            if identity in self._entries:
                del self._entries[identity]
                PENDING.dec()

    def drain(self) -> int:
        """Close admission and mark live tickets uncertain, never completed.

        Failed writes remain registered for a subsequent drain attempt. Already
        admitting transactions settle in their own thread before provider IO.
        SIGKILL/OOM and unavailable Firestore cannot be repaired in process.
        """
        with self._lock:
            self._draining = True
            callbacks = [callback for callback in self._entries.values() if callback is not None]
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
