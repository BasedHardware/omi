"""Test-only synchronization at real FSR BEGIN or Firestore Commit boundaries."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from contextvars import copy_context
import threading
from unittest.mock import patch


class CommitBarrier:
    """Pause each participating writer's first nonempty SDK Commit, before sending it.

    The saved method still executes the installed product privacy-token fence and
    the real emulator RPC. Reader commits and subsequent writer commits pass through.
    """

    def __init__(self, client):
        self.api = client._firestore_api
        self.original = self.api.commit
        self.condition = threading.Condition()
        self.release = threading.Event()
        self.arrivals = set()
        self.local = threading.local()

    def commit(self, *args, **kwargs):
        request = kwargs.get('request', args[0] if args else None)
        writes = request.get('writes', ()) if isinstance(request, dict) else getattr(request, 'writes', ())
        if getattr(self.local, 'writer', False) and writes:
            with self.condition:
                self.arrivals.add(threading.get_ident())
                self.condition.notify_all()
            if not self.release.wait(15):
                raise TimeoutError('privacy Commit overlap deadline')
        return self.original(*args, **kwargs)

    def write(self, function):
        self.local.writer = True
        try:
            return function()
        finally:
            self.local.writer = False


def finish_writers(futures, write):
    """Join every concurrent attempt before one bounded retry of SDK Aborted.

    Firestore's transactional decorator wraps exhausted Aborted attempts in
    ValueError. Other exceptions remain failures. A recovery is an explicit
    real-writer retry, never an extra verified transition or a swallowed error.
    """
    from google.api_core.exceptions import Aborted

    outcomes = []
    for future in futures:
        try:
            future.result(timeout=30)
            outcomes.append('committed')
        except Exception as error:
            if not (
                isinstance(error, Aborted) or (isinstance(error, ValueError) and isinstance(error.__cause__, Aborted))
            ):
                raise
            outcomes.append('aborted')
    for index, outcome in enumerate(outcomes):
        if outcome == 'aborted':
            write()
            outcomes[index] = 'aborted_then_committed'
    return outcomes


def overlapping_writes(redis, client, write, read, *, writers, fenced):
    """Read only after every participating writer has reached its real boundary."""
    barrier = redis if fenced else CommitBarrier(client)
    observations = []
    context = patch.object(barrier.api, 'commit', barrier.commit) if not fenced else nullcontext()
    with context, ThreadPoolExecutor(max_workers=writers) as pool:
        function = write if fenced else lambda: barrier.write(write)
        futures = [pool.submit(copy_context().run, function) for _ in range(writers)]
        try:
            with barrier.condition:
                arrived = (lambda: redis.begins >= writers) if fenced else (lambda: len(barrier.arrivals) >= writers)
                if not barrier.condition.wait_for(arrived, timeout=15):
                    raise TimeoutError('privacy writers did not reach overlap boundary')
            observations.append(read())
        finally:
            barrier.release.set()
        outcomes = finish_writers(futures, write)
    return observations, {
        'synchronized_writers': writers,
        'overlap_reads': len(observations),
        'writer_outcomes': outcomes,
        'writer_retry_count': outcomes.count('aborted_then_committed'),
        'synchronization_seam': 'fsr_begin' if fenced else 'firestore_commit',
    }
