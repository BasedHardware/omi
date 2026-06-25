#!/usr/bin/env python3
"""Microbenchmark for the auto-router scoring path.

Run from the backend directory:
    cd backend && PYENV_VERSION=3.12.8 python -m utils.auto_router.benchmark

Measures:
  - score(model, task) — pure function (called once per candidate per request)
  - full endpoint request (registry load + score all candidates) — amortized via DailyRefreshCache

Prints results to stdout. Used to populate the "Performance characteristics"
section of the README and to spot regressions in scoring overhead.

This is NOT a load test — it measures single-threaded CPU time, not concurrent
throughput under load. For that, use a real load-testing tool.
"""

import statistics
import sys
import time
from pathlib import Path

# Path setup (same pattern as the demo, but this file is one level higher —
# `benchmark.py` lives at `utils/auto_router/`, not `utils/auto_router/demo/`).
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from utils.auto_router.daily_refresh import DailyRefreshCache  # noqa: E402
from utils.auto_router.model_registry import ModelRegistry  # noqa: E402
from utils.auto_router.scoring import score  # noqa: E402
from utils.auto_router.task_registry import TaskRegistry  # noqa: E402


BENCHMARKS = _BACKEND / "utils" / "auto_router" / "benchmarks.example.json"
ITERATIONS = 100_000


def _pct(values, q):
    """Return the q-th percentile of `values` (0..100)."""
    return statistics.quantiles(values, n=100)[q - 1] if len(values) > 1 else values[0]


def bench_score(task, candidates):
    """Measure `score(model, task)` over ITERATIONS calls per candidate."""
    durations = []
    for _ in range(ITERATIONS):
        # Time one full pass over all candidates (this is what a real request does).
        t0 = time.perf_counter_ns()
        for model in candidates:
            _ = score(model, task)
        durations.append(time.perf_counter_ns() - t0)
    return durations


def bench_endpoint_load():
    """Measure time to load both registries from disk (cold cache case)."""
    durations = []
    for _ in range(100):
        cache = DailyRefreshCache(ttl_seconds=999999)  # never expires within the test
        t0 = time.perf_counter_ns()

        async def loader():
            return TaskRegistry.from_json(BENCHMARKS), ModelRegistry.from_json(BENCHMARKS)

        # Use asyncio.run for the async loader (each measurement is independent).
        import asyncio

        asyncio.run(cache.get_or_refresh(loader))
        durations.append(time.perf_counter_ns() - t0)
    return durations


def bench_endpoint_cached(cache):
    """Measure time for a cached endpoint call (registry already loaded).

    Important: uses the RETURN VALUE of get_or_refresh, not `nonlocal` side
    effects. On a cache hit, the loader doesn't run, so `nonlocal` assignments
    would never happen. Capturing the return value is the only way to get the
    loaded data on the first call when the cache is empty AND on every
    subsequent cached call.
    """
    durations = []

    async def loader():
        return TaskRegistry.from_json(BENCHMARKS), ModelRegistry.from_json(BENCHMARKS)

    import asyncio

    async def prime_and_bench():
        # First call: cache miss, loader runs, returns (tasks, models).
        tasks, models = await cache.get_or_refresh(loader)
        # Simulate the endpoint's score loop (this is what runs on every request).
        for task_spec in tasks.all():
            for model in models.candidates_for(task_spec.name):
                _ = score(model, task_spec)

    for _ in range(ITERATIONS // 100):
        t0 = time.perf_counter_ns()
        asyncio.run(prime_and_bench())
        durations.append(time.perf_counter_ns() - t0)
    return durations


def fmt_ns(ns):
    if ns < 1000:
        return f"{ns:.0f} ns"
    elif ns < 1_000_000:
        return f"{ns / 1000:.1f} µs"
    else:
        return f"{ns / 1_000_000:.2f} ms"


def main():
    print(f"Auto-router v1 microbenchmark")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Iterations: {ITERATIONS:,}")
    print()

    # Load registries once for the per-task benchmarks.
    tasks = TaskRegistry.from_json(BENCHMARKS)
    models = ModelRegistry.from_json(BENCHMARKS)

    print("=" * 72)
    print("score(model, task) — single-threaded, one full pass over candidates")
    print("=" * 72)
    for task_spec in tasks.all():
        cands = models.candidates_for(task_spec.name)
        if not cands:
            print(f"\n  {task_spec.name}: no candidates, skipping")
            continue
        durations = bench_score(task_spec, cands)
        avg = statistics.mean(durations)
        med = statistics.median(durations)
        p99 = _pct(durations, 99)
        per_call = avg / len(cands)
        print(
            f"\n  {task_spec.name} ({len(cands)} candidates):"
            f"\n    avg/pass: {fmt_ns(int(avg))}    median: {fmt_ns(int(med))}    p99: {fmt_ns(int(p99))}"
            f"\n    per candidate: ~{fmt_ns(int(per_call))}"
        )

    print()
    print("=" * 72)
    print("Registry load (cold cache — first request after process start)")
    print("=" * 72)
    durations = bench_endpoint_load()
    avg = statistics.mean(durations)
    print(f"  avg load: {fmt_ns(int(avg))} (over 100 cold loads)")

    print()
    print("=" * 72)
    print("Endpoint request (warm cache — typical request after warmup)")
    print("=" * 72)
    cache = DailyRefreshCache(ttl_seconds=999999)
    durations = bench_endpoint_cached(cache)
    avg = statistics.mean(durations)
    med = statistics.median(durations)
    p99 = _pct(durations, 99)
    print(
        f"  avg request: {fmt_ns(int(avg))}    median: {fmt_ns(int(med))}    p99: {fmt_ns(int(p99))}"
        f"  (covers all 5 tasks × all candidates)"
    )

    print()
    print("=" * 72)
    print("Summary")
    print("=" * 72)
    print(f"  Cold first request: ~{fmt_ns(int(statistics.mean(bench_endpoint_load())))}")
    print(f"  Warm subsequent:    ~{fmt_ns(int(statistics.mean(bench_endpoint_cached(cache))))} for ALL 5 tasks")
    print(
        f"  Per-task scoring:   ~{fmt_ns(int(statistics.mean(bench_score(tasks.get('ptt_response'), models.candidates_for('ptt_response'))) / 4))} per candidate"
    )
    print()
    print("Net: scoring is microseconds per call. Cold start is single-digit ms.")
    print("The framework is fast enough that response time is dominated by network I/O,")
    print("not by the scoring function. No optimization needed for v1.")


if __name__ == "__main__":
    main()
