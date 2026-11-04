"""Plan A3 contention bench: the real Scheduler over one batch Store under R replicas x T pull threads.

Throughput is a local measurement, not a production claim; the correctness counters are the gate:
every job leased, none held by two live leases at once, no pull or admission error.

    cd backend && OMI_TEST_POSTGRES_DSN='host=127.0.0.1 port=5432 user=postgres dbname=postgres' \\
        python -m testing.jobstore_contention --replicas 4 --threads 2 --owners 200 --jobs 10

``--backend emulator`` runs the same load on a loopback Firestore emulator (``firebase emulators:exec``).
Synthetic owners in a throwaway ``batch_pipeline_test_*`` namespace only.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import threading
import time

import testing.pipeline_sim._env  # noqa: F401  (hermetic constants before product imports)


def _ms(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))] * 1000, 1)


def _stores(backend: str, replicas: int, pool_size: int):
    if backend == 'postgres':
        from database.jobstore.connection import Pool
        from database.jobstore.postgres_store import PostgresStore
        from testing.store_fixtures import make_postgres, postgres_connect

        harness = make_postgres()
        stores = [
            PostgresStore(
                harness.namespace,
                pool=Pool('', size=pool_size, connect=postgres_connect()),
                customer_client=harness.customer.client,
                harness_customer_tables=True,
            )
            for _ in range(replicas)
        ]
        return harness, stores
    from database.batch_pipeline_store import FirestoreStore
    from testing.store_fixtures import _emulator_client, make_emulator

    harness = make_emulator()
    return harness, [FirestoreStore(harness.namespace, firestore_client=_emulator_client()) for _ in range(replicas)]


def run(args: argparse.Namespace) -> dict:
    os.environ['BATCH_SHARD_SPREAD_ENABLED'] = args.spread
    from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
    from utils.batch_pipeline.scheduler import Scheduler

    harness, stores = _stores(args.backend, args.replicas, args.pool)
    rng = random.Random(args.seed)
    items = []
    for o in range(args.owners):
        uid = harness.seed_user(f'u{o}')
        for j in range(args.jobs):
            segment = f's{o}-{j}'
            items.append(
                WorkItem(
                    segment,
                    uid,
                    1000.0 + j * 60 + rng.random(),
                    f'gs://synthetic/{segment}',
                    rng.choice((20.0, 45.0, 90.0, 300.0)),
                    rng.choice((Priority.FRESH, Priority.DEEP, Priority.DEEP, Priority.DEEP)),
                )
            )
    seeded, late = (items, []) if not args.admitters else (items[: len(items) // 2], items[len(items) // 2 :])
    lock = threading.Lock()
    errors: collections.Counter = collections.Counter()
    pull_seconds: list[float] = []
    enqueue_seconds: list[float] = []
    leased: collections.Counter = collections.Counter()
    live: dict[str, str] = {}
    doubles: list[str] = []
    empty = [0]
    stop = threading.Event()

    def enqueue(scheduler, item):
        started = time.monotonic()
        try:
            scheduler.enqueue(item, time.time())
        except Exception as error:  # noqa: BLE001  (counted, never raised: the bench reports)
            with lock:
                errors[f'enqueue:{type(error).__name__}'] += 1
        with lock:
            enqueue_seconds.append(time.monotonic() - started)

    seed = Scheduler(stores[0])
    for item in seeded:
        enqueue(seed, item)

    def admit(index):
        scheduler = Scheduler(stores[index % len(stores)])
        for item in late[index :: args.admitters]:
            if stop.is_set():
                return
            enqueue(scheduler, item)

    def pull(replica):
        scheduler = Scheduler(stores[replica], worker_id=f'r{replica}')
        while not stop.is_set():
            started = time.monotonic()
            try:
                got = scheduler.pull(time.time(), 1)
            except Exception as error:  # noqa: BLE001
                with lock:
                    errors[f'pull:{type(error).__name__}'] += 1
                continue
            with lock:
                pull_seconds.append(time.monotonic() - started)
                if not got:
                    empty[0] += 1
            if not got:
                time.sleep(0.05)
                continue
            for lease in got:
                segment = lease.item.segment_id
                with lock:
                    if segment in live:
                        doubles.append(segment)
                    live[segment] = lease.token
                    leased[segment] += 1
                accepted = scheduler.complete(
                    WorkResult(segment, f'gs://synthetic/r/{segment}'), lease.token, time.time()
                )
                with lock:
                    live.pop(segment, None)
                    if not accepted:
                        errors['complete:refused'] += 1

    threads = [
        threading.Thread(target=pull, args=(r,), daemon=True) for r in range(args.replicas) for _ in range(args.threads)
    ]
    threads += [threading.Thread(target=admit, args=(i,), daemon=True) for i in range(args.admitters)]
    started = time.time()
    for thread in threads:
        thread.start()
    while time.time() - started < args.seconds:
        time.sleep(0.25)
        with lock:
            if len(leased) >= len(items):
                break
    stop.set()
    for thread in threads:
        thread.join(timeout=30)
    elapsed = time.time() - started
    try:
        harness.close()
    finally:
        for store in stores:
            if hasattr(store, 'pool'):
                store.pool.close()
    return {
        'config': vars(args),
        'jobs': len(items),
        'leased': len(leased),
        'leased_twice': sum(1 for count in leased.values() if count > 1),
        'concurrent_double_leases': len(doubles),
        'leases_per_second': round(sum(leased.values()) / elapsed, 1),
        'seconds': round(elapsed, 1),
        'pull_calls': len(pull_seconds),
        'empty_pulls': empty[0],
        'pull_ms': {q: _ms(pull_seconds, p) for q, p in (('p50', 0.5), ('p95', 0.95), ('p99', 0.99))},
        'enqueue_ms': {q: _ms(enqueue_seconds, p) for q, p in (('p50', 0.5), ('p95', 0.95), ('p99', 0.99))},
        'errors': dict(errors),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--backend', choices=('postgres', 'emulator'), default='postgres')
    parser.add_argument('--replicas', type=int, default=4)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--owners', type=int, default=200)
    parser.add_argument('--jobs', type=int, default=10)
    parser.add_argument('--admitters', type=int, default=0, help='concurrent enqueue threads during the pull phase')
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--spread', choices=('true', 'false'), default='true')
    parser.add_argument('--pool', type=int, default=4)
    parser.add_argument('--seed', type=int, default=7)
    print(json.dumps(run(parser.parse_args()), indent=1))


if __name__ == '__main__':
    main()
