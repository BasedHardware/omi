"""Two-pump harness: each simulated GPU replica gets its own thread and loop.

Shared by the in-memory throughput test and the Firestore-emulator safety
tests. Only the CUDA chain is faked; spend admission is the backend RPC's
fenced lease seal without its Redis spend policy.
"""

from __future__ import annotations

import asyncio
from collections import Counter
import random
import threading
import time

from utils.batch_pipeline.contracts import PoolCapacity, Priority, RecoveryWork, WorkItem, WorkResult
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler, owns_lease


class FakeGpu:
    """Timed stand-in for the CUDA chain; records every item it computes."""

    def __init__(self, name, ledger, *, seconds=0.0, jitter=0.0, recovery=(), slow=None):
        self.name, self.ledger = name, ledger
        self.seconds, self.jitter = seconds, jitter
        self.recovery, self.slow = set(recovery), slow or {}
        self.lock = threading.Lock()

    def process_batch(self, items, **kwargs):
        with self.lock:
            self.ledger.extend((self.name, v.segment_id) for v in items)
        delay = self.seconds + random.uniform(0, self.jitter)
        delay = max([delay, *(self.slow.get(v.segment_id, 0) for v in items)])
        time.sleep(delay)
        results = []
        for v in items:
            if v.segment_id in self.recovery:
                results.append(RecoveryWork(v.segment_id, padded_retry_empty=True))
            else:
                results.append(WorkResult(v.segment_id, f'gs://synthetic/{self.name}/{v.segment_id}'))
        random.shuffle(results)  # Completion order inside a batch is not capture order.
        return results


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.accepted: Counter[str] = Counter()
        self.failed: Counter[str] = Counter()
        self.committed: list[tuple[str, str]] = []
        self.gpu: list[tuple[str, str]] = []

    def wrap(self, name, queue: Scheduler):
        complete, fail = queue.complete, queue.fail

        def counted_complete(result, token, now):
            accepted = complete(result, token, now)
            if accepted:
                with self.lock:
                    self.accepted[result.segment_id] += 1
            return accepted

        def counted_fail(segment_id, token, now, **kwargs):
            failed = fail(segment_id, token, now, **kwargs)
            if failed:
                with self.lock:
                    self.failed[segment_id] += 1
            return failed

        queue.complete, queue.fail = counted_complete, counted_fail

        def on_committed(entry):
            with self.lock:
                self.committed.append((name, entry['segment_id']))

        return on_committed


def seal_for(store):
    """The backend spend RPC's fenced seal, without the Redis spend policy."""

    def authorize(leases):
        allowed = []
        for lease in leases:

            def seal(tx, lease=lease):
                job = tx.get('jobs', lease.item.segment_id)
                if not owns_lease(job, lease.token, time.time()):
                    return False
                job['compute_admission_token'] = lease.token
                tx.put('jobs', lease.item.segment_id, job)
                return True

            if store.run(seal):
                allowed.append(lease.item.segment_id)
        return {'allowed': allowed, 'retry_after': {}}

    return authorize


def build_pump(name, store, recorder, gpu, batch_size, *, slots=None):
    queue = Scheduler(store)
    on_committed = recorder.wrap(name, queue)
    return Pump(
        queue,
        gpu,
        batch_size=batch_size,
        poll_seconds=0.05,
        on_committed=on_committed,
        capacity=lambda: PoolCapacity(time.time(), slots() if slots else batch_size),
        authorize_compute=seal_for(store),
    )


def run_pumps(pumps, done, *, timeout, starts=None, describe=None):
    """Each pump gets its own thread and loop, like separate pods."""
    finished = threading.Event()
    errors: list[BaseException] = []

    def host(pump, start_after):
        async def main():
            if start_after is not None:
                while not start_after():
                    await asyncio.sleep(0.05)
            stop = asyncio.Event()
            task = asyncio.create_task(pump.run(stop))
            while not finished.is_set():
                await asyncio.sleep(0.05)
            stop.set()
            await task

        try:
            asyncio.run(main())
        except BaseException as error:  # noqa: BLE001 - surfaced below
            errors.append(error)

    threads = [
        threading.Thread(target=host, args=(pump, (starts or {}).get(i)), daemon=True) for i, pump in enumerate(pumps)
    ]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    try:
        while not done():
            if errors:
                raise errors[0]
            if time.monotonic() - started > timeout:
                detail = describe() if describe else ''
                raise AssertionError(f'two-worker drain did not finish in time {detail}')
            time.sleep(0.05)
        return time.monotonic() - started
    finally:
        finished.set()
        for thread in threads:
            thread.join(30)
        assert not errors, errors


def item(segment, owner, capture, *, seconds=30):
    return WorkItem(
        segment,
        owner,
        capture,
        f'gs://synthetic/{segment}',
        seconds,
        Priority.FRESH,
        requires_compute_admission=True,
    )
