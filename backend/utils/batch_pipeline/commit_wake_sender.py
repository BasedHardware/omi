"""Worker side of the reliability experiment ``commit_wake`` (see ``utils.batch_pipeline.commit_wake``).

The GPU pump's ``on_committed`` hook: it hands the owner id of each commit to ``CommitWakeSender``, which
posts it to ``/v2/batch-pipeline/commit-wake`` on the serving backend. Stdlib and the compute client only,
and nothing of the serving role is imported here, so the worker image and the worker's settings stay as
they are.
"""

import logging
import os
import threading
from typing import Callable

from config import reliability_experiments

logger = logging.getLogger(__name__)

EXPERIMENT = 'commit_wake'
# Owner ids in one request, and owners waiting to be sent. Past the bound a wake is dropped.
MAX_OWNERS_PER_CALL = 32
MAX_PENDING_OWNERS = 1024
# Consecutive failures between warnings, so an unreachable backend does not flood the worker log.
FAILURE_LOG_EVERY = 100


def enabled(owner_id: str | None) -> bool:
    return reliability_experiments.enabled(EXPERIMENT, owner_id)


class CommitWakeSender:
    """The pump's ``on_committed`` hook. Never blocks and never raises into the commit loop.

    Owners wait in arrival order, each at most once, and one daemon thread sends them in calls of up
    to ``MAX_OWNERS_PER_CALL``. A burst of commits for one owner while a call is in flight costs one
    further call, not one per unit.
    """

    def __init__(self, send: Callable[[list[str]], int], *, start_thread: bool = True):
        self._send = send
        self._pending: dict[str, None] = {}
        self._ready = threading.Condition()
        self._failures = 0
        # Started with the first admitted owner, so a worker where the experiment is on for nobody
        # runs no extra thread.
        self._thread = None
        self._start_thread = start_thread

    def __call__(self, entry: dict) -> None:
        owner_id = entry.get('owner_id') if isinstance(entry, dict) else None
        if not isinstance(owner_id, str) or not 0 < len(owner_id) <= 128:
            return
        if not enabled(owner_id):
            return  # Not switched on for this owner: the sweep finds the row, as it always has.
        with self._ready:
            if self._thread is None and self._start_thread:
                self._thread = threading.Thread(target=self._run, name='batch_commit_wake', daemon=True)
                self._thread.start()
            if owner_id in self._pending:
                return
            if len(self._pending) >= MAX_PENDING_OWNERS:
                return  # The sweep finds this row, as it does without the experiment.
            self._pending[owner_id] = None
            self._ready.notify()

    def _take(self) -> list[str]:
        owners = list(self._pending)[:MAX_OWNERS_PER_CALL]
        for owner_id in owners:
            del self._pending[owner_id]
        return owners

    def flush(self) -> int:
        """Send what is waiting now, in bounded calls. Returns the owners handed to the backend."""
        sent = 0
        while True:
            with self._ready:
                owners = self._take()
            if not owners:
                return sent
            try:
                self._send(owners)
            except Exception as error:
                self._failures += 1
                if self._failures % FAILURE_LOG_EVERY == 1:
                    logger.warning(
                        'event=batch_commit_wake outcome=send_failed exception_type=%s failures=%d',
                        type(error).__name__,
                        self._failures,
                    )
                continue
            self._failures = 0
            sent += len(owners)

    def _run(self) -> None:
        while True:
            with self._ready:
                while not self._pending:
                    self._ready.wait()
            self.flush()


def sender_from_env() -> CommitWakeSender | None:
    """The hook for the GPU pump, or None when its target is not configured.

    The hook decides per owner (``enabled(owner_id)``), so it is installed wherever a target exists and
    sends nothing for an owner the experiment is off for. Its client and its thread are created with the
    first admitted owner: a worker where the experiment is on for nobody constructs neither.

    The target is the serving backend the worker already reaches for shadow recovery
    (``BATCH_PIPELINE_SHADOW_RECOVERY_API_URL``), not the admission service: the walk needs the
    serving role's projector.
    """
    if not os.getenv('BATCH_PIPELINE_SHADOW_RECOVERY_API_URL', '').strip():
        return None
    client: list = []

    def send(owner_ids: list[str]) -> int:
        if not client:
            from utils.batch_pipeline.compute_client import shadow_from_env

            client.append(shadow_from_env())
        return client[0].commit_wake(owner_ids)

    return CommitWakeSender(send)
