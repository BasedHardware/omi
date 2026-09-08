#!/usr/bin/env python3
"""NLLB Translation Server — Performance Benchmark

Measures throughput (TPS), concurrent connection handling, and latency
distribution under sustained load. Designed for the realtime listen path
where translation runs inside 250ms batch windows.

Usage:
    # Quick smoke test
    python3 scripts/benchmark_nllb_performance.py --nllb-url http://localhost:8080 --quick

    # Full sweep across concurrency and batch sizes
    python3 scripts/benchmark_nllb_performance.py \
        --nllb-url http://localhost:8080 \
        --concurrency 1,2,4,8,16,32 \
        --batch-sizes 1,5,10,20,32 \
        --duration 30 \
        --output-dir /tmp/nllb-perf

    # Focused test for realtime path (typical: batch=5, concurrency 1-8)
    python3 scripts/benchmark_nllb_performance.py \
        --nllb-url http://localhost:8080 \
        --concurrency 1,2,4,8 \
        --batch-sizes 1,5,10 \
        --duration 20
"""

import argparse
import asyncio
import json
import math
import os
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

SENTENCE_POOL = [
    "Hello, how are you doing today?",
    "The weather is really nice this morning.",
    "I had a great meeting with the team yesterday about the new project.",
    "Can you please send me the report by end of day?",
    "The stock market experienced significant volatility throughout the trading session.",
    "Scientists have discovered a new species of deep-sea fish in the Pacific Ocean near the Mariana Trench.",
    "I think we should grab lunch together sometime this week.",
    "The conference will be held in San Francisco next month and we need to book our flights soon.",
    "Machine learning models require large amounts of training data to achieve good performance on downstream tasks.",
    "She walked through the park, enjoying the autumn leaves falling gently around her.",
    "The restaurant on Main Street has the best pasta I've ever tasted.",
    "We need to fix this bug before the release goes out to production tonight.",
    "The new smartphone features a revolutionary camera system with advanced computational photography capabilities.",
    "Please remember to turn off the lights when you leave the office.",
    "Global temperatures have risen by approximately one point five degrees Celsius since pre-industrial times.",
    "I'm running a bit late, I'll be there in about ten minutes.",
    "The quantum computing breakthrough could revolutionize drug discovery and materials science within the next decade.",
    "Don't forget to pick up milk and bread from the grocery store on your way home.",
    "The art exhibition at the museum features works from contemporary artists across twelve different countries.",
    "Let me know if you have any questions about the proposal I sent earlier this afternoon.",
    "Renewable energy sources now account for over thirty percent of global electricity generation.",
    "The kids are playing in the backyard.",
    "Our quarterly revenue exceeded expectations by fifteen percent, driven primarily by strong international sales growth.",
    "I just finished reading an incredible book about the history of space exploration.",
    "The train from Tokyo to Osaka takes approximately two and a half hours on the bullet train.",
    "We should consider migrating our infrastructure to a cloud-native architecture for better scalability.",
    "Happy birthday! I hope you have a wonderful day filled with joy and celebration.",
    "The archaeological team unearthed artifacts dating back over three thousand years at the excavation site in southern Egypt.",
    "Can you check if the server is running properly?",
    "Traffic was terrible this morning because of the construction on the highway.",
    "The new policy requires all employees to complete cybersecurity training by the end of the quarter.",
    "I love how the sunset looks from this spot on the hill.",
    "The research paper presents a novel approach to natural language processing using transformer architectures with sparse attention.",
    "We're having a barbecue this weekend, you should come!",
    "The hospital reported a significant decrease in emergency room wait times following the implementation of the new triage system.",
    "What time does the movie start tonight?",
    "International trade negotiations between the two countries have reached a critical juncture following months of diplomatic discussions.",
    "The garden needs watering, the plants are looking a bit dry.",
    "Our team successfully deployed the microservices architecture, reducing system latency by forty percent across all endpoints.",
    "I can't believe it's already December, this year went by so fast.",
    "The symphonic orchestra performed Beethoven's Ninth Symphony to a sold-out audience at the concert hall last evening.",
    "Make sure to save your work before shutting down the computer.",
    "Researchers at the university published findings showing that regular exercise can improve cognitive function in older adults.",
    "The coffee shop around the corner makes an amazing cappuccino.",
    "Artificial intelligence is transforming healthcare by enabling earlier disease detection through advanced medical imaging analysis.",
    "I'm thinking of learning a new language, maybe Spanish or Japanese.",
    "The city council approved the new public transportation plan that includes expanded bus routes and a light rail extension.",
    "That was a really good presentation, I liked the part about market trends.",
    "The autonomous vehicle navigated through complex urban traffic scenarios with a safety record exceeding human drivers.",
    "Let's schedule a follow-up meeting for next Tuesday at two o'clock.",
]

TARGET_LANGUAGES = ["es", "de", "ja", "zh", "ru"]

WARMUP_REQUESTS = 5


@dataclass
class RequestResult:
    latency_ms: float
    sentences: int
    chars: int
    success: bool
    error: Optional[str] = None


@dataclass
class BenchmarkResult:
    concurrency: int
    batch_size: int
    duration_seconds: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_sentences: int
    total_chars: int
    sentences_per_second: float
    chars_per_second: float
    requests_per_second: float
    latency_p50_ms: float
    latency_p90_ms: float
    latency_p99_ms: float
    latency_max_ms: float
    latency_min_ms: float
    latency_mean_ms: float
    error_rate: float
    latencies_ms: List[float] = field(default_factory=list, repr=False)


def percentile(sorted_data: List[float], p: float) -> float:
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


class NLLBBenchmark:
    def __init__(self, nllb_url: str):
        self.nllb_url = nllb_url.rstrip('/')
        self._stop = False

    def _make_batch(self, batch_size: int) -> Tuple[List[str], str, int]:
        sentences = [random.choice(SENTENCE_POOL) for _ in range(batch_size)]
        target = random.choice(TARGET_LANGUAGES)
        total_chars = sum(len(s) for s in sentences)
        return sentences, target, total_chars

    async def _send_request(self, client: httpx.AsyncClient, batch_size: int) -> RequestResult:
        sentences, target, total_chars = self._make_batch(batch_size)
        payload = {
            "contents": sentences,
            "target_language_code": target,
            "source_language_code": "en",
        }
        t0 = time.monotonic()
        try:
            resp = await client.post(f"{self.nllb_url}/v1/translate", json=payload)
            latency_ms = (time.monotonic() - t0) * 1000
            if resp.status_code == 200:
                return RequestResult(
                    latency_ms=latency_ms,
                    sentences=batch_size,
                    chars=total_chars,
                    success=True,
                )
            return RequestResult(
                latency_ms=latency_ms,
                sentences=0,
                chars=0,
                success=False,
                error=f"HTTP {resp.status_code}",
            )
        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000
            return RequestResult(
                latency_ms=latency_ms,
                sentences=0,
                chars=0,
                success=False,
                error=str(e),
            )

    async def _warmup(self, client: httpx.AsyncClient, batch_size: int):
        for _ in range(WARMUP_REQUESTS):
            if self._stop:
                return
            await self._send_request(client, batch_size)

    async def _worker(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        batch_size: int,
        results: List[RequestResult],
        end_time: float,
    ):
        while not self._stop and time.monotonic() < end_time:
            async with semaphore:
                if self._stop or time.monotonic() >= end_time:
                    break
                result = await self._send_request(client, batch_size)
                results.append(result)

    async def run_scenario(self, concurrency: int, batch_size: int, duration: float) -> BenchmarkResult:
        results: List[RequestResult] = []

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            # Warmup
            await self._warmup(client, batch_size)

            # Measurement phase
            semaphore = asyncio.Semaphore(concurrency)
            end_time = time.monotonic() + duration
            # Spawn more workers than concurrency to keep the semaphore saturated
            worker_count = concurrency * 3
            tasks = [
                asyncio.create_task(self._worker(client, semaphore, batch_size, results, end_time))
                for _ in range(worker_count)
            ]

            t_start = time.monotonic()
            await asyncio.gather(*tasks)
            actual_duration = time.monotonic() - t_start

        if not results:
            return BenchmarkResult(
                concurrency=concurrency,
                batch_size=batch_size,
                duration_seconds=actual_duration,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                total_sentences=0,
                total_chars=0,
                sentences_per_second=0,
                chars_per_second=0,
                requests_per_second=0,
                latency_p50_ms=0,
                latency_p90_ms=0,
                latency_p99_ms=0,
                latency_max_ms=0,
                latency_min_ms=0,
                latency_mean_ms=0,
                error_rate=0,
            )

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        latencies = sorted([r.latency_ms for r in successful])

        total_sentences = sum(r.sentences for r in successful)
        total_chars = sum(r.chars for r in successful)

        return BenchmarkResult(
            concurrency=concurrency,
            batch_size=batch_size,
            duration_seconds=actual_duration,
            total_requests=len(results),
            successful_requests=len(successful),
            failed_requests=len(failed),
            total_sentences=total_sentences,
            total_chars=total_chars,
            sentences_per_second=total_sentences / actual_duration if actual_duration > 0 else 0,
            chars_per_second=total_chars / actual_duration if actual_duration > 0 else 0,
            requests_per_second=len(successful) / actual_duration if actual_duration > 0 else 0,
            latency_p50_ms=percentile(latencies, 50),
            latency_p90_ms=percentile(latencies, 90),
            latency_p99_ms=percentile(latencies, 99),
            latency_max_ms=max(latencies) if latencies else 0,
            latency_min_ms=min(latencies) if latencies else 0,
            latency_mean_ms=sum(latencies) / len(latencies) if latencies else 0,
            error_rate=len(failed) / len(results) if results else 0,
            latencies_ms=latencies,
        )


async def check_server(url: str) -> Optional[Dict]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url.rstrip('/')}/health")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


def print_summary_table(results: List[BenchmarkResult]):
    header = (
        f"{'Concurrency':>11} | {'Batch':>5} | {'Requests':>8} | "
        f"{'Snt/s':>8} | {'Chars/s':>8} | "
        f"{'p50(ms)':>8} | {'p90(ms)':>8} | {'p99(ms)':>8} | "
        f"{'Max(ms)':>8} | {'Errors':>6}"
    )
    sep = "-" * len(header)
    print(f"\n{sep}")
    print(header)
    print(sep)
    for r in results:
        print(
            f"{r.concurrency:>11} | {r.batch_size:>5} | {r.successful_requests:>8} | "
            f"{r.sentences_per_second:>8.1f} | {r.chars_per_second:>8.0f} | "
            f"{r.latency_p50_ms:>8.1f} | {r.latency_p90_ms:>8.1f} | {r.latency_p99_ms:>8.1f} | "
            f"{r.latency_max_ms:>8.1f} | {r.error_rate:>5.1%}"
        )
    print(sep)


def find_peak(results: List[BenchmarkResult]):
    if not results:
        return
    best_snt = max(results, key=lambda r: r.sentences_per_second)
    best_rps = max(results, key=lambda r: r.requests_per_second)
    lowest_p50 = min(
        (r for r in results if r.successful_requests > 0),
        key=lambda r: r.latency_p50_ms,
        default=None,
    )

    print("\n=== Peak Performance ===")
    print(
        f"  Max throughput:  {best_snt.sentences_per_second:.1f} sentences/s "
        f"({best_snt.chars_per_second:.0f} chars/s) "
        f"@ concurrency={best_snt.concurrency}, batch={best_snt.batch_size}"
    )
    print(
        f"  Max request TPS: {best_rps.requests_per_second:.1f} req/s "
        f"@ concurrency={best_rps.concurrency}, batch={best_rps.batch_size}"
    )
    if lowest_p50:
        print(
            f"  Lowest p50:      {lowest_p50.latency_p50_ms:.1f}ms "
            f"@ concurrency={lowest_p50.concurrency}, batch={lowest_p50.batch_size}"
        )

    # Realtime suitability check (250ms batch window budget)
    print("\n=== Realtime Suitability (250ms budget) ===")
    realtime_ok = [r for r in results if r.latency_p99_ms <= 250]
    if realtime_ok:
        best_rt = max(realtime_ok, key=lambda r: r.sentences_per_second)
        print(
            f"  Best within 250ms p99: {best_rt.sentences_per_second:.1f} snt/s "
            f"@ concurrency={best_rt.concurrency}, batch={best_rt.batch_size} "
            f"(p99={best_rt.latency_p99_ms:.0f}ms)"
        )
    else:
        closest = min(results, key=lambda r: r.latency_p99_ms) if results else None
        if closest:
            print(
                f"  No configuration met 250ms p99. Closest: p99={closest.latency_p99_ms:.0f}ms "
                f"@ concurrency={closest.concurrency}, batch={closest.batch_size}"
            )


def build_report(results: List[BenchmarkResult], server_info: Optional[Dict]) -> Dict:
    return {
        "benchmark": "nllb-performance",
        "server": server_info,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": [
            {
                "concurrency": r.concurrency,
                "batch_size": r.batch_size,
                "duration_seconds": round(r.duration_seconds, 2),
                "total_requests": r.total_requests,
                "successful_requests": r.successful_requests,
                "failed_requests": r.failed_requests,
                "total_sentences": r.total_sentences,
                "total_chars": r.total_chars,
                "sentences_per_second": round(r.sentences_per_second, 2),
                "chars_per_second": round(r.chars_per_second, 1),
                "requests_per_second": round(r.requests_per_second, 2),
                "latency_p50_ms": round(r.latency_p50_ms, 2),
                "latency_p90_ms": round(r.latency_p90_ms, 2),
                "latency_p99_ms": round(r.latency_p99_ms, 2),
                "latency_max_ms": round(r.latency_max_ms, 2),
                "latency_min_ms": round(r.latency_min_ms, 2),
                "latency_mean_ms": round(r.latency_mean_ms, 2),
                "error_rate": round(r.error_rate, 4),
            }
            for r in results
        ],
    }


async def main():
    parser = argparse.ArgumentParser(
        description="NLLB Translation Server — Performance Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--nllb-url",
        default="http://localhost:8080",
        help="NLLB service URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--concurrency",
        default="1,2,4,8,16,32",
        help="Comma-separated concurrency levels (default: 1,2,4,8,16,32)",
    )
    parser.add_argument(
        "--batch-sizes",
        default="1,5,10,20,32",
        help="Comma-separated batch sizes (default: 1,5,10,20,32)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30,
        help="Seconds per scenario (default: 30)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for JSON report output",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: 5s duration, fewer combinations",
    )
    args = parser.parse_args()

    if args.quick:
        concurrency_levels = [1, 2, 4, 8]
        batch_sizes = [1, 5, 10]
        duration = 5.0
    else:
        concurrency_levels = [int(x) for x in args.concurrency.split(",")]
        batch_sizes = [int(x) for x in args.batch_sizes.split(",")]
        duration = args.duration

    # Check server
    print(f"Checking NLLB server at {args.nllb_url} ...")
    server_info = await check_server(args.nllb_url)
    if not server_info:
        print(f"ERROR: Cannot reach NLLB server at {args.nllb_url}")
        sys.exit(1)
    print(f"  Server: {json.dumps(server_info)}")

    benchmark = NLLBBenchmark(args.nllb_url)

    # Handle graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: setattr(benchmark, '_stop', True))

    total_scenarios = len(concurrency_levels) * len(batch_sizes)
    print(
        f"\nRunning {total_scenarios} scenarios "
        f"(concurrency={concurrency_levels}, batch_sizes={batch_sizes}, "
        f"duration={duration}s each)"
    )
    print(f"Estimated time: {total_scenarios * (duration + 3):.0f}s\n")

    all_results: List[BenchmarkResult] = []
    scenario_num = 0

    for batch_size in batch_sizes:
        for conc in concurrency_levels:
            if benchmark._stop:
                print("\nStopped by signal.")
                break
            scenario_num += 1
            print(
                f"[{scenario_num}/{total_scenarios}] "
                f"concurrency={conc}, batch={batch_size}, "
                f"duration={duration}s ...",
                end="",
                flush=True,
            )
            result = await benchmark.run_scenario(conc, batch_size, duration)
            all_results.append(result)
            print(
                f" {result.sentences_per_second:.1f} snt/s, "
                f"p50={result.latency_p50_ms:.0f}ms, "
                f"p99={result.latency_p99_ms:.0f}ms, "
                f"err={result.error_rate:.0%}"
            )
        if benchmark._stop:
            break

    # Print results
    print_summary_table(all_results)
    find_peak(all_results)

    # Save report
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report = build_report(all_results, server_info)
        report_path = output_dir / "nllb_performance.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
