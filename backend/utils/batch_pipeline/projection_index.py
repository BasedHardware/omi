"""Search and people-stats convergence owed by owner-chain assignments.

The step is fail-open and converges to durable state, so it need not run inside
the ordered chain. Walks record each committed canonical and its donor lineage;
one flush converges each touched conversation once, so a heavy owner pays the
lineage deletes (which retry any earlier failed delete) once per flush, not once
per row. Pending
work is in memory only: a lost flush degrades search freshness exactly like a
Typesense outage does today.
"""

from __future__ import annotations

import logging
import threading
import time

from database import conversations as conversations_db

logger = logging.getLogger(__name__)


class ProjectionIndex:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.flushing = threading.Lock()
        # owner -> (conversation ids, donor ids, first deferral time)
        self.pending: dict[str, tuple[dict[str, None], dict[str, None], float]] = {}

    @property
    def owed(self) -> bool:
        return bool(self.pending)

    def defer(self, uid: str, conversation_id: str, donors: list[str]) -> None:
        with self.lock:
            conversations, absorbed, _ = self.pending.setdefault(uid, ({}, {}, self.clock()))
            conversations[conversation_id] = None
            absorbed.update(dict.fromkeys(donors))

    def flush(self) -> int:
        """Converge every owed owner; returns owners flushed. One flusher at a time.

        A single flusher keeps an older read of a conversation from landing after
        a newer one. A deferral that arrives while another flush finishes is
        picked up by the next drain step or serving tick.
        """
        if not self.flushing.acquire(blocking=False):
            return 0
        flushed = 0
        try:
            while True:
                with self.lock:
                    batch, self.pending = self.pending, {}
                if not batch:
                    return flushed
                lag = 0.0
                conversations = donors = 0
                for uid, (ids, absorbed, since) in batch.items():
                    conversations_db.index_sync_assignment(uid, list(ids), list(absorbed))
                    lag = max(lag, self.clock() - since)
                    conversations += len(ids)
                    donors += len(absorbed)
                    flushed += 1
                logger.info(
                    'event=batch_projection_index outcome=flushed owners=%d conversations=%d donors=%d lag_ms=%d',
                    len(batch),
                    conversations,
                    donors,
                    int(lag * 1000),
                )
        except Exception as error:
            logger.error('event=batch_projection_index outcome=error exception_type=%s', type(error).__name__)
            return flushed
        finally:
            self.flushing.release()
