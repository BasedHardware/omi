"""Measure the batch claim chain's lease ceiling on staging Firestore: no GPU, no vendor call.

Seeds pseudo-owners (``lg-<run>-oNNNN``) and their fresh units through the real
``Scheduler.enqueue``, then drives N lanes of the real ``Scheduler.pull`` (multi-lease, shard
spread, privacy fence) until the backlog drains. Each lease settles with a lease-fenced refund
``defer`` parked for a day, never ``complete``: no unit reaches ``result_ready``, so staging's
serving loop never merges or projects bench work. The lanes stand in for the GPU workers' pump
lanes (two per worker), so the rate it reports is the claim path with the GPU taken out;
``--hold`` adds a fixed flight time per lease. Admission, heartbeats and the ordered merge are
not exercised: they run outside the claim lane.

    python -m scripts.staging.claim_bench run --run-id cb1 --owners 64 --units 16 --lanes 32
    python -m scripts.staging.claim_bench cleanup --run-id cb1 --owners 64 --units 16

Runs only inside the staging runtime (staging fence, ``staging`` database). Prints JSON event
lines with counts, rates and latencies only. ``run`` always cleans up its own documents (a parked
unit left behind would come due after a day and become live staging work); ``cleanup`` repeats
that by derived document id, never by query, for a run that died before its own cleanup.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import multiprocessing
import os
import random
import re
import sys
from threading import Event, Lock, Thread
import time
from typing import Callable

from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.scheduler import Scheduler, owner_key

NAMESPACE = 'batch_pipeline_prod'  # staging runs prod code paths against its own database
RUN_ID_RE = re.compile(r'^cb[a-z0-9]{1,20}$')
MAX_OWNERS = 512
MAX_UNITS = 512
EMPTY_PULL_SLEEP_S = 0.05
IDLE_STOP_S = 10.0
SETTLE_PARK_S = 86400  # defer's ceiling: a settled unit is never due again before cleanup
SEED_ATTEMPTS = 8
ERROR_SLEEP_S = 0.2
MAX_ERRORS = 500


class BenchRefused(RuntimeError):
    pass


def owner_id(run_id: str, index: int) -> str:
    return f'lg-{run_id}-o{index:04d}'


def bench_owner(uid: str, run_id: str) -> bool:
    """Seeding and deletion guard: only this run's pseudo-owners, never any other id shape."""
    if not RUN_ID_RE.fullmatch(run_id):
        return False
    head = f'lg-{run_id}-o'
    tail = uid[len(head) :]
    return uid.startswith(head) and len(tail) == 4 and tail.isdigit()


def segment_id(run_id: str, owner: int, unit: int) -> str:
    return f'{run_id}-o{owner:04d}-u{unit:04d}'


def plan(run_id: str, *, owners: int, units: int, duration: float, now: float) -> list[WorkItem]:
    """Fresh units, contiguous in capture time per owner and ending a minute before ``now``."""
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError('run id must match ^cb[a-z0-9]{1,20}$')
    if not (1 <= owners <= MAX_OWNERS and 1 <= units <= MAX_UNITS and 0 < duration <= 600):
        raise ValueError('bounded owners, units and unit duration required')
    # Spread the owner's units over at most ~10 minutes of capture so every unit stays fresh.
    step = min(duration, 600.0 / units)
    return [
        WorkItem(
            segment_id=segment_id(run_id, o, u),
            owner_id=owner_id(run_id, o),
            capture_at=now - 60.0 - (units - u) * step,
            audio_uri=f'gs://claim-bench.invalid/{run_id}/{segment_id(run_id, o, u)}',
            duration_seconds=duration,
            priority=Priority.FRESH,
        )
        for o in range(owners)
        for u in range(units)
    ]


def seed(scheduler: Scheduler, items: list[WorkItem], *, now: Callable[[], float], threads: int) -> int:
    """Enqueue every unit; one owner's units go in capture order on one thread."""
    by_owner: dict[str, list[WorkItem]] = {}
    for item in items:
        by_owner.setdefault(item.owner_id, []).append(item)

    def enqueue_one(item: WorkItem) -> bool:
        # Owners hashed to one shard share its control document, so concurrent seeding contends
        # there; seeding is setup, not the measurement, so it retries with jitter.
        for attempt in range(SEED_ATTEMPTS):
            try:
                return bool(scheduler.enqueue(item, now()))
            except Exception:
                if attempt == SEED_ATTEMPTS - 1:
                    raise
                time.sleep(random.uniform(0.05, 0.3) * (attempt + 1))
        return False

    def enqueue_owner(owned: list[WorkItem]) -> int:
        return sum(enqueue_one(item) for item in owned)

    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        return sum(pool.map(enqueue_owner, by_owner.values()))


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))], 4)


def drive(
    make_scheduler: Callable[[int], Scheduler],
    *,
    lanes: int,
    total: int,
    batch: int,
    hold: float,
    deadline_s: float,
    now: Callable[[], float] = time.time,
    lane_offset: int = 0,
    idle_stop_s: float = IDLE_STOP_S,
    accept: Callable[[WorkItem], bool] = lambda item: True,
) -> dict:
    """Run ``lanes`` pull/settle loops until ``total`` units settle, the deadline passes, or
    (after the first lease) no lane in this process has leased for ``idle_stop_s``: with several
    processes, each drains its share and stops once the shared backlog is empty."""
    lock = Lock()
    done = Event()
    pulls: list[float] = []
    settles: list[float] = []
    lease_times: list[float] = []  # wall-clock, so processes merge on one axis
    counts = {'leased': 0, 'settled': 0, 'rejected': 0, 'foreign': 0, 'nonempty_pulls': 0}
    errors: dict[str, int] = {}
    started = time.monotonic()
    deadline = started + deadline_s
    last_lease = [None]

    def idle() -> bool:
        with lock:
            return last_lease[0] is not None and time.monotonic() - last_lease[0] > idle_stop_s

    def lane(index: int) -> None:
        scheduler = make_scheduler(lane_offset + index)
        while not done.is_set() and time.monotonic() < deadline and not idle():
            t0 = time.monotonic()
            try:
                leases = scheduler.pull(now(), batch)
            except Exception as error:  # Counted by class; the lane keeps pulling.
                with lock:
                    errors[type(error).__name__] = errors.get(type(error).__name__, 0) + 1
                    stop = sum(errors.values()) >= MAX_ERRORS
                if stop:
                    done.set()
                time.sleep(ERROR_SLEEP_S)
                continue
            elapsed = time.monotonic() - t0
            with lock:
                pulls.append(elapsed)
                if leases:
                    counts['nonempty_pulls'] += 1
                    counts['leased'] += len(leases)
                    lease_times.extend([time.time()] * len(leases))
                    last_lease[0] = time.monotonic()
            if not leases:
                time.sleep(EMPTY_PULL_SLEEP_S)
                continue
            for lease in leases:
                if not accept(lease.item):
                    # Someone else's unit in the shared namespace: hand it back with the attempt
                    # refunded (a refund defer, as on shutdown; due again after 1 s) and end the run, since the
                    # measurement is no longer the bench's own backlog.
                    done.set()
                    try:
                        scheduler.defer(lease.item.segment_id, lease.token, now(), retry_after=0)
                    except Exception as error:
                        with lock:
                            errors[type(error).__name__] = errors.get(type(error).__name__, 0) + 1
                    with lock:
                        counts['foreign'] += 1
                    continue
                if hold:
                    time.sleep(hold)
                t1 = time.monotonic()
                try:
                    # Settle with a refund defer parked past the run, never ``complete``: a
                    # result_ready job is merge work, and staging's serving loop would commit and
                    # project it. One lease-fenced job transaction, as complete costs.
                    accepted = scheduler.defer(lease.item.segment_id, lease.token, now(), retry_after=SETTLE_PARK_S)
                except Exception as error:
                    with lock:
                        errors[type(error).__name__] = errors.get(type(error).__name__, 0) + 1
                    continue
                with lock:
                    settles.append(time.monotonic() - t1)
                    counts['settled' if accepted else 'rejected'] += 1
                    if counts['settled'] >= total:
                        done.set()

    threads = [Thread(target=lane, args=(i,), daemon=True) for i in range(lanes)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()) + 30.0)
    wall = time.monotonic() - started
    return {
        **counts,
        'lanes': lanes,
        'wall_s': round(wall, 3),
        'timed_out': counts['settled'] < total,
        'errors': errors,
        'pull_calls': len(pulls),
        'pull_wall_s': round(sum(pulls), 3),
        'pull_p50_s': _quantile(pulls, 0.5),
        'pull_p95_s': _quantile(pulls, 0.95),
        'settle_p50_s': _quantile(settles, 0.5),
        'settle_p95_s': _quantile(settles, 0.95),
        'lease_times': lease_times,
        **_rates(counts, wall, lease_times, pulls),
    }


def _rates(counts: dict, wall: float, lease_times: list[float], pulls: list[float]) -> dict:
    """Drain rate (first to last lease) plus the steady rate between the 10th and 90th percentile
    lease. Wall time includes the idle tail and is reported, not used as a rate."""
    steady = drain = None
    ordered = sorted(lease_times)
    if len(ordered) >= 2 and ordered[-1] > ordered[0]:
        drain = round((len(ordered) - 1) / (ordered[-1] - ordered[0]), 3)
    if len(ordered) >= 10:
        t10, t90 = ordered[len(ordered) // 10], ordered[(9 * len(ordered)) // 10]
        if t90 > t10:
            steady = round((len(ordered) * 0.8) / (t90 - t10), 3)
    return {
        'drain_s': round(ordered[-1] - ordered[0], 3) if ordered else None,
        'drain_leased_per_s': drain,
        'steady_leased_per_s': steady,
        'leases_per_nonempty_pull': (
            round(counts['leased'] / counts['nonempty_pulls'], 3) if counts['nonempty_pulls'] else 0.0
        ),
        'pull_wall_per_lease_s': round(sum(pulls) / counts['leased'], 3) if counts['leased'] else None,
    }


def merge(parts: list[dict], total: int) -> dict:
    """Combine per-process drive results (each lane offset distinct) into one fleet result."""
    counts = {
        key: sum(part.get(key, 0) for part in parts)
        for key in ('leased', 'settled', 'rejected', 'foreign', 'nonempty_pulls')
    }
    errors: dict[str, int] = {}
    for part in parts:
        for name, count in part['errors'].items():
            errors[name] = errors.get(name, 0) + count
    wall = max(part['wall_s'] for part in parts)
    lease_times = [t for part in parts for t in part['lease_times']]
    pull_calls = sum(part['pull_calls'] for part in parts)
    pull_wall = sum(part['pull_wall_s'] for part in parts)
    rates = _rates(counts, wall, lease_times, [])
    rates['pull_wall_per_lease_s'] = round(pull_wall / counts['leased'], 3) if counts['leased'] else None
    return {
        **counts,
        'lanes': sum(part['lanes'] for part in parts),
        'processes': len(parts),
        'wall_s': wall,
        'timed_out': counts['settled'] < total,
        'errors': errors,
        'pull_calls': pull_calls,
        'pull_wall_s': round(pull_wall, 3),
        'pull_p95_s_max': max((part['pull_p95_s'] or 0.0) for part in parts),
        'settle_p95_s_max': max((part['settle_p95_s'] or 0.0) for part in parts),
        **rates,
    }


def cleanup(client, namespace: str, run_id: str, *, owners: int, units: int) -> dict:
    """Delete this run's documents by derived id: jobs, any result rows, owner queues and fences,
    pseudo-users. Settling never writes a result; the result delete is a backstop."""
    counts = {'jobs': 0, 'results': 0, 'queues': 0, 'owners': 0, 'users': 0}
    for o in range(owners):
        uid = owner_id(run_id, o)
        if not bench_owner(uid, run_id):
            raise BenchRefused('refusing to delete a non-bench owner')
        key = owner_key(uid)
        for u in range(units):
            client.collection(f'{namespace}_jobs').document(segment_id(run_id, o, u)).delete()
            counts['jobs'] += 1
            client.collection(f'{namespace}_results').document(segment_id(run_id, o, u)).delete()
            counts['results'] += 1
        client.collection(f'{namespace}_queues').document(f'{int(Priority.FRESH)}_{key}').delete()
        counts['queues'] += 1
        client.collection(f'{namespace}_owners').document(key).delete()
        counts['owners'] += 1
        client.collection('users').document(uid).delete()
        counts['users'] += 1
    return counts


def require_staging() -> None:
    if os.getenv('OMI_DEPLOYMENT') != 'staging' or os.getenv('FIRESTORE_DATABASE_ID') != 'staging':
        raise BenchRefused('claim bench requires OMI_DEPLOYMENT=staging and FIRESTORE_DATABASE_ID=staging')
    from utils.staging_fence import StagingFenceError, assert_staging_isolation

    try:
        assert_staging_isolation()
    except StagingFenceError as error:
        # The message names variables and reason codes only, never values.
        raise BenchRefused(str(error)) from error


def _seed_users(client, run_id: str, owners: int) -> int:
    for o in range(owners):
        uid = owner_id(run_id, o)
        if not bench_owner(uid, run_id):
            raise BenchRefused('refusing to seed a non-bench owner')
        client.collection('users').document(uid).set(
            {
                'id': uid,
                'private_cloud_sync_enabled': True,
                'data_protection_level': 'standard',
                'loadgen': True,
                'loadgen_run': 'claim_bench',
            },
            merge=True,
        )
    return owners


def _store():
    from database.batch_pipeline_store import FirestoreStore

    return FirestoreStore(NAMESPACE)


def _process_drive(args: tuple) -> dict:
    lanes, offset, total, batch, hold, deadline_s, run_id = args
    store = _store()
    return drive(
        lambda lane: Scheduler(store, worker_id=f'claim-bench-{lane}'),
        lanes=lanes,
        total=total,
        batch=batch,
        hold=hold,
        deadline_s=deadline_s,
        lane_offset=offset,
        accept=lambda item: bench_owner(item.owner_id, run_id),
    )


def _emit(event: str, **fields) -> None:
    print(json.dumps({'event': event, **fields}, sort_keys=True), flush=True)


def run(args) -> int:
    require_staging()
    from database._client import get_firestore_client

    client = get_firestore_client()
    items = plan(args.run_id, owners=args.owners, units=args.units, duration=args.duration, now=time.time())
    try:
        _seed_users(client, args.run_id, args.owners)
        t0 = time.monotonic()
        seeded = seed(Scheduler(_store()), items, now=time.time, threads=args.seed_threads)
        _emit(
            'claim_bench_seeded',
            owners=args.owners,
            units=len(items),
            enqueued=seeded,
            seed_s=round(time.monotonic() - t0, 2),
        )
        per = math.ceil(args.lanes / args.processes)
        jobs = [
            (min(per, args.lanes - i * per), i * per, len(items), args.batch, args.hold, args.seconds, args.run_id)
            for i in range(args.processes)
            if args.lanes - i * per > 0
        ]
        # Each process carries its own Firestore channel, as each GPU worker does.
        with multiprocessing.get_context('spawn').Pool(len(jobs)) as pool:
            parts = pool.map(_process_drive, jobs)
        # Every lane counts toward one shared drain target, so a process may stop early on its
        # deadline while others finished; the merged result is the fleet's.
        result = merge(parts, len(items))
        _emit(
            'claim_bench_result',
            run_id=args.run_id,
            owners=args.owners,
            units_per_owner=args.units,
            unit_seconds=args.duration,
            batch=args.batch,
            hold_s=args.hold,
            **result,
        )
    finally:
        _emit('claim_bench_cleanup', **cleanup(client, NAMESPACE, args.run_id, owners=args.owners, units=args.units))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('run', 'cleanup'):
        p = sub.add_parser(name)
        p.add_argument('--run-id', required=True)
        p.add_argument('--owners', type=int, required=True)
        p.add_argument('--units', type=int, required=True)
    r = sub.choices['run']
    r.add_argument('--lanes', type=int, default=32)
    r.add_argument('--processes', type=int, default=8)
    r.add_argument('--batch', type=int, default=8)
    r.add_argument('--hold', type=float, default=0.0)
    r.add_argument('--duration', type=float, default=120.0)
    r.add_argument('--seconds', type=float, default=600.0)
    r.add_argument('--seed-threads', type=int, default=16)
    args = parser.parse_args(argv)
    if not RUN_ID_RE.fullmatch(args.run_id):
        raise SystemExit('run id must match ^cb[a-z0-9]{1,20}$')
    if args.mode == 'cleanup':
        require_staging()
        from database._client import get_firestore_client

        _emit(
            'claim_bench_cleanup',
            **cleanup(get_firestore_client(), NAMESPACE, args.run_id, owners=args.owners, units=args.units),
        )
        return 0
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
