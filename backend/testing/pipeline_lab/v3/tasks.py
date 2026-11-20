"""Loopback Cloud Tasks: named tasks are recorded on the virtual clock and run in process.

Production's v3 work is driven by named Cloud Tasks (``utils.cloud_tasks.enqueue_named_task``
from ``utils/conversations/v3/triggers.enqueue``): one coalesced task per owner-minute that
calls ``POST /v1/conversations-v3/reconcile``. The lab replaces the enqueue function wherever
it is bound with :meth:`LoopbackTasks.enqueue` (same signature), which

- keeps Cloud Tasks' named-task dedupe: a second create of a name already used answers like
  ``AlreadyExists`` (logged as ``duplicate``; production logs and skips it the same way);
- keeps ``schedule_at`` (epoch seconds) so the driver runs each task at its virtual time;
- never touches the network.

Every enqueue and every run is a row in ``runs/<id>/v3_tasks.jsonl``.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
import heapq
import itertools
import threading
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

RECONCILE_PATH = '/v1/conversations-v3/reconcile'


@dataclass(order=True)
class Task:
    due: float
    seq: int
    name: str = field(compare=False)
    queue: str = field(compare=False)
    url: str = field(compare=False)
    payload: dict[str, Any] = field(compare=False, default_factory=dict)
    enqueued_at: float = field(compare=False, default=0.0)

    @property
    def path(self) -> str:
        return urlsplit(self.url).path

    def as_row(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'queue': self.queue,
            'path': self.path,
            'due': _iso(self.due),
            'enqueued_at': _iso(self.enqueued_at),
        }


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


class LoopbackTasks:
    def __init__(self, now: Callable[[], datetime], *, log: Optional[Callable[[dict[str, Any]], None]] = None):
        self._now = now
        self._log = log
        self._lock = threading.Lock()
        self._heap: list[Task] = []
        self._names: set[tuple[str, str]] = set()
        self._seq = itertools.count()
        self.created = 0
        self.duplicates = 0

    def enqueue(
        self,
        queue: str,
        url: str,
        task_id: str,
        payload: dict[str, Any],
        *,
        audience: Optional[str] = None,
        invoker_sa: Optional[str] = None,
        schedule_at: Optional[int] = None,
    ) -> None:
        """Drop-in for ``utils.cloud_tasks.enqueue_named_task``."""
        now = self._now().timestamp()
        due = float(schedule_at) if schedule_at is not None else now
        with self._lock:
            if (queue, task_id) in self._names:
                self.duplicates += 1
                outcome = 'duplicate'
                task = None
            else:
                self._names.add((queue, task_id))
                task = Task(due, next(self._seq), task_id, queue, url, dict(payload or {}), now)
                heapq.heappush(self._heap, task)
                self.created += 1
                outcome = 'created'
        if self._log is not None:
            row = {'event': 'enqueue', 'outcome': outcome, 'name': task_id, 'queue': queue, 'path': urlsplit(url).path}
            row.update({'due': _iso(due), 'enqueued_at': _iso(now)})
            self._log(row)

    def next_due(self) -> Optional[float]:
        with self._lock:
            return self._heap[0].due if self._heap else None

    def pop_due(self, now: float) -> Optional[Task]:
        with self._lock:
            if self._heap and self._heap[0].due <= now:
                return heapq.heappop(self._heap)
            return None

    def pending(self) -> int:
        with self._lock:
            return len(self._heap)

    def install(self, stack: ExitStack) -> int:
        """Bind :meth:`enqueue` wherever the product bound ``enqueue_named_task``."""
        from testing.pipeline_lab.stack.patching import replace_everywhere
        from utils import cloud_tasks

        return replace_everywhere(stack, cloud_tasks.enqueue_named_task, self.enqueue)
