"""Read-ahead of an owner chain's immutable per-row inputs.

Once a row is in the result log its successor link, job binding, result payload
and audio manifest never change, so they can be read while earlier rows commit.
Receipt state is mutable and is never taken from here: the walk reads it fresh,
and the assignment transaction rereads everything it fences on. A miss or a
failed load falls back to the walk's own read; a load still running at the step
deadline ends the step instead. So read-ahead can only make a walk faster,
never change what it persists.
"""

from __future__ import annotations

from concurrent.futures import Future, wait
from dataclasses import dataclass
import logging
import threading
from typing import TYPE_CHECKING, Any

from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from utils.executors import storage_executor

if TYPE_CHECKING:
    from utils.batch_pipeline.projection import Projector

logger = logging.getLogger(__name__)
# Longest single wait on a read-ahead; a load still running stays queued.
PREFETCH_WAIT_SECONDS = 30.0
EMPTY_OUTCOMES = frozenset({'silence', 'no_recoverable_speech'})
# ``take`` result for a row whose read-ahead is still loading at the step deadline.
NOT_READY = object()


@dataclass(frozen=True)
class Prefetched:
    job: dict[str, Any]
    binding: ProjectionBinding
    payload: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None


class ChainPrefetch:
    """Keeps up to ``depth`` successors of the walk's position loading.

    Runs on the storage pool: every task is a leaf read and nothing here waits
    on another pool. The walk thread waits only on these leaf futures.
    """

    def __init__(self, projector: Projector, key: str, depth: int, *, executor=None):
        self.projector, self.key, self.depth = projector, key, depth
        self.executor = executor or storage_executor
        self.lock = threading.Lock()
        self.links: dict[str | None, str] = {}
        self.rows: dict[str, Future] = {}
        self.scouting = False
        self.closed = False

    def successor(self, previous: str | None) -> str | None:
        """A link already read ahead (append-only, so never stale), else None."""
        with self.lock:
            return self.links.get(previous)

    def advance(self, previous: str | None) -> None:
        """The walk is about to take ``previous``'s successor: keep the window full."""
        with self.lock:
            if self.closed or self.scouting:
                return
            cursor, ahead = previous, 0
            while cursor in self.links and ahead < self.depth:
                cursor, ahead = self.links[cursor], ahead + 1
            if ahead >= self.depth:
                return
            self.scouting = True
        try:
            self.executor.submit(self._scout, cursor, self.depth - ahead)
        except Exception:
            with self.lock:
                self.scouting = False

    def take(self, segment_id: str, timeout: float = PREFETCH_WAIT_SECONDS) -> Prefetched | object | None:
        """The row's inputs; None means read inline; NOT_READY means still loading.

        A load still running at ``timeout`` stays queued for the next step: a
        slow read is never repeated inline on the walk's pool slot. Only a
        failed load is read inline. The storage calls carry their own
        timeouts, and a drain turn starts a fresh read-ahead.
        """
        with self.lock:
            future = self.rows.get(segment_id)
        if future is None:
            return None
        try:
            wait([future], timeout=max(0.0, min(timeout, PREFETCH_WAIT_SECONDS)))
            if not future.done():
                return NOT_READY
            with self.lock:
                self.rows.pop(segment_id, None)
            return future.result(timeout=0)
        except Exception as error:
            with self.lock:
                self.rows.pop(segment_id, None)
            logger.info(
                'event=batch_projection_prefetch outcome=miss exception_type=%s',
                type(error).__name__,
            )
            return None

    def close(self) -> None:
        with self.lock:
            self.closed = True
            pending, self.rows = list(self.rows.values()), {}
        for future in pending:
            future.cancel()

    def _scout(self, cursor: str | None, count: int) -> None:
        try:
            for _ in range(count):
                if self.closed:
                    return
                successor = self.projector.store.store.projection_successor(self.key, cursor)
                if successor is None:
                    return
                with self.lock:
                    if self.closed:
                        return
                    self.links[cursor] = successor
                    if successor not in self.rows:
                        self.rows[successor] = self.executor.submit(self._load, successor)
                cursor = successor
        except Exception as error:
            logger.info('event=batch_projection_prefetch outcome=scout_error exception_type=%s', type(error).__name__)
        finally:
            with self.lock:
                self.scouting = False

    def _load(self, segment_id: str) -> Prefetched:
        job, entry, binding = self.projector.store.read(segment_id)
        item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
        outcome = entry['result']['outcome']
        payload = manifest = None
        if outcome != 'silence' and not entry.get('projection'):
            payload = self.projector.load_result(item, entry['result']['result_uri'])
            if outcome not in EMPTY_OUTCOMES and item.requires_compute_admission and self.projector.fetch_audio:
                from utils.batch_pipeline.audio import read_context

                manifest = read_context(self.projector.fetch_audio(item))
        return Prefetched(job, binding, payload, manifest)
