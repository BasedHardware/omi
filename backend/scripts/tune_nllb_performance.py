#!/usr/bin/env python3
"""NLLB Translation Server — Performance Tuning Script

Systematically tests CTranslate2 and server parameters to find the
configuration that maximizes throughput on L4 GPU while keeping latency
within the realtime budget (250ms p99 for the listen path).

Tuning parameters:
  - beam_size: 1 vs 2 vs 4 (beam_size=1 is greedy decode, fastest)
  - inter_threads: 1-4 (parallel CT2 batches)
  - intra_threads: 1-8 (CPU threads per batch, affects tokenization)
  - max_batch_size: 16-128
  - compute_type: int8, int8_float16, float16
  - uvicorn workers: 1-2

Usage:
    # Tune against a running NLLB server (restart with new config each round)
    python3 scripts/tune_nllb_performance.py \
        --nllb-url http://localhost:8080 \
        --output-dir /tmp/nllb-tuning

    # Test specific parameter overrides
    python3 scripts/tune_nllb_performance.py \
        --nllb-url http://localhost:8080 \
        --param beam_size=1 \
        --param inter_threads=2

    # Generate optimal config recommendations from a completed sweep
    python3 scripts/tune_nllb_performance.py \
        --analyze /tmp/nllb-tuning/tuning_results.json

Workflow (manual restart required):
    1. Script prints env vars for each config
    2. You restart the NLLB server with those env vars
    3. Script benchmarks the running server
    4. Repeat for all configs
    5. Script ranks all configs and recommends the best

For automated sweeps on Kubernetes:
    python3 scripts/tune_nllb_performance.py \
        --helm-mode \
        --output-dir /tmp/nllb-tuning
    # Generates helm values overrides for each config
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import the performance benchmark runner
sys.path.insert(0, os.path.dirname(__file__))
from benchmark_nllb_performance import NLLBBenchmark, BenchmarkResult, check_server, print_summary_table


@dataclass
class TuningConfig:
    name: str
    beam_size: int
    inter_threads: int
    intra_threads: int
    max_batch_size: int
    compute_type: str
    description: str = ""

    inference_workers: int = 2

    def env_vars(self) -> Dict[str, str]:
        return {
            "CT2_INTER_THREADS": str(self.inter_threads),
            "CT2_INTRA_THREADS": str(self.intra_threads),
            "CT2_COMPUTE_TYPE": self.compute_type,
            "NLLB_MAX_BATCH_SIZE": str(self.max_batch_size),
            "NLLB_BEAM_SIZE": str(self.beam_size),
            "NLLB_INFERENCE_WORKERS": str(self.inference_workers),
        }

    def helm_env(self) -> List[Dict[str, str]]:
        return [{"name": k, "value": v} for k, v in self.env_vars().items()]


@dataclass
class TuningResult:
    config: TuningConfig
    benchmark: BenchmarkResult
    beam_size: int
    score: float = 0.0


# Default tuning grid — covers the important parameter space for L4 GPU
TUNING_GRID_FULL: List[TuningConfig] = [
    # Baseline (current defaults)
    TuningConfig(
        "baseline",
        beam_size=4,
        inter_threads=1,
        intra_threads=4,
        max_batch_size=64,
        compute_type="int8_float16",
        description="Current defaults",
    ),
    # Greedy decode (beam_size=1) — fastest inference
    TuningConfig(
        "greedy",
        beam_size=1,
        inter_threads=1,
        intra_threads=4,
        max_batch_size=64,
        compute_type="int8_float16",
        description="Greedy decode (no beam search)",
    ),
    TuningConfig(
        "greedy-beam2",
        beam_size=2,
        inter_threads=1,
        intra_threads=4,
        max_batch_size=64,
        compute_type="int8_float16",
        description="Beam size 2 (balance quality/speed)",
    ),
    # Inter-thread parallelism (multiple CT2 batches)
    TuningConfig(
        "inter2",
        beam_size=1,
        inter_threads=2,
        intra_threads=2,
        max_batch_size=64,
        compute_type="int8_float16",
        description="2 parallel CT2 batches",
    ),
    TuningConfig(
        "inter4",
        beam_size=1,
        inter_threads=4,
        intra_threads=1,
        max_batch_size=64,
        compute_type="int8_float16",
        description="4 parallel CT2 batches",
    ),
    # Larger batches (GPU prefers larger batches)
    TuningConfig(
        "big-batch",
        beam_size=1,
        inter_threads=1,
        intra_threads=4,
        max_batch_size=128,
        compute_type="int8_float16",
        description="Max batch 128, greedy",
    ),
    TuningConfig(
        "big-batch-beam2",
        beam_size=2,
        inter_threads=1,
        intra_threads=4,
        max_batch_size=128,
        compute_type="int8_float16",
        description="Max batch 128, beam 2",
    ),
    # Compute type variants
    TuningConfig(
        "pure-int8",
        beam_size=1,
        inter_threads=1,
        intra_threads=4,
        max_batch_size=64,
        compute_type="int8",
        description="Pure INT8 (fastest, lower quality)",
    ),
    TuningConfig(
        "float16",
        beam_size=1,
        inter_threads=1,
        intra_threads=4,
        max_batch_size=64,
        compute_type="float16",
        description="FP16 (highest quality, more VRAM)",
    ),
    # Combined best candidates
    TuningConfig(
        "turbo",
        beam_size=1,
        inter_threads=2,
        intra_threads=2,
        max_batch_size=128,
        compute_type="int8_float16",
        description="Greedy + 2 parallel + big batch",
    ),
    TuningConfig(
        "turbo-int8",
        beam_size=1,
        inter_threads=2,
        intra_threads=2,
        max_batch_size=128,
        compute_type="int8",
        description="Greedy + 2 parallel + big batch + pure INT8",
    ),
    # CPU thread tuning
    TuningConfig(
        "intra8",
        beam_size=1,
        inter_threads=1,
        intra_threads=8,
        max_batch_size=64,
        compute_type="int8_float16",
        description="8 intra-threads for tokenization",
    ),
    TuningConfig(
        "intra1",
        beam_size=1,
        inter_threads=1,
        intra_threads=1,
        max_batch_size=64,
        compute_type="int8_float16",
        description="1 intra-thread (minimal CPU)",
    ),
]

TUNING_GRID_QUICK: List[TuningConfig] = [
    TUNING_GRID_FULL[0],  # baseline
    TUNING_GRID_FULL[1],  # greedy
    TUNING_GRID_FULL[3],  # inter2
    TUNING_GRID_FULL[5],  # big-batch
    TUNING_GRID_FULL[9],  # turbo
]

BENCH_CONCURRENCY = [1, 4, 8]
BENCH_BATCH_SIZES = [5, 10]
BENCH_DURATION = 15.0

BENCH_QUICK_CONCURRENCY = [1, 4]
BENCH_QUICK_BATCH_SIZES = [5]
BENCH_QUICK_DURATION = 8.0


def compute_score(result: BenchmarkResult, latency_budget_ms: float = 250.0) -> float:
    """Score a benchmark result. Higher is better.

    Scoring formula:
      score = throughput_snt_s * latency_factor * reliability_factor

    latency_factor: 1.0 if p99 <= budget, degrades linearly to 0.1 at 4x budget
    reliability_factor: 1.0 if error_rate == 0, degrades linearly
    """
    if result.successful_requests == 0:
        return 0.0

    throughput = result.sentences_per_second

    if result.latency_p99_ms <= latency_budget_ms:
        latency_factor = 1.0
    else:
        overshoot = result.latency_p99_ms / latency_budget_ms
        latency_factor = max(0.1, 1.0 - (overshoot - 1.0) / 3.0)

    reliability = 1.0 - result.error_rate

    return throughput * latency_factor * reliability


async def benchmark_config(
    nllb_url: str,
    config: TuningConfig,
    concurrency_levels: List[int],
    batch_sizes: List[int],
    duration: float,
) -> List[TuningResult]:
    """Run benchmark scenarios for a single config."""
    benchmark = NLLBBenchmark(nllb_url)
    results: List[TuningResult] = []

    for batch_size in batch_sizes:
        for conc in concurrency_levels:
            print(
                f"    concurrency={conc}, batch={batch_size} ...",
                end="",
                flush=True,
            )
            result = await benchmark.run_scenario(conc, batch_size, duration)
            score = compute_score(result)
            results.append(
                TuningResult(
                    config=config,
                    benchmark=result,
                    beam_size=config.beam_size,
                    score=score,
                )
            )
            print(
                f" {result.sentences_per_second:.1f} snt/s, "
                f"p99={result.latency_p99_ms:.0f}ms, "
                f"score={score:.1f}"
            )

    return results


def print_ranking(all_results: List[TuningResult], top_n: int = 10):
    """Print ranked configs by score."""
    sorted_results = sorted(all_results, key=lambda r: r.score, reverse=True)

    print(f"\n{'=' * 100}")
    print(f"{'TUNING RESULTS — TOP CONFIGURATIONS':^100}")
    print(f"{'=' * 100}")

    header = (
        f"{'Rank':>4} | {'Config':>16} | {'Beam':>4} | {'Conc':>4} | {'Batch':>5} | "
        f"{'Snt/s':>7} | {'p50ms':>6} | {'p99ms':>6} | {'Score':>7} | Description"
    )
    print(header)
    print("-" * len(header))

    for i, tr in enumerate(sorted_results[:top_n]):
        b = tr.benchmark
        print(
            f"{i + 1:>4} | {tr.config.name:>16} | {tr.beam_size:>4} | "
            f"{b.concurrency:>4} | {b.batch_size:>5} | "
            f"{b.sentences_per_second:>7.1f} | {b.latency_p50_ms:>6.0f} | "
            f"{b.latency_p99_ms:>6.0f} | {b.score:>7.1f} | {tr.config.description}"
        )

    # Best within realtime budget
    realtime_ok = [r for r in sorted_results if r.benchmark.latency_p99_ms <= 250]
    if realtime_ok:
        best = realtime_ok[0]
        print(f"\n{'RECOMMENDATION — Best within 250ms p99 budget':^100}")
        print(f"  Config:     {best.config.name}")
        print(f"  Beam size:  {best.beam_size}")
        print(f"  Throughput: {best.benchmark.sentences_per_second:.1f} sentences/sec")
        print(f"  Latency:    p50={best.benchmark.latency_p50_ms:.0f}ms, p99={best.benchmark.latency_p99_ms:.0f}ms")
        print(f"  Score:      {best.score:.1f}")
        print(f"\n  Env vars:")
        for k, v in best.config.env_vars().items():
            print(f"    {k}={v}")
    else:
        print("\n  WARNING: No configuration met the 250ms p99 budget.")
        print("  Consider: smaller model (600M), smaller batches, or additional replicas.")


def generate_helm_values(config: TuningConfig, beam_size: int) -> str:
    """Generate helm values YAML for a tuning config."""
    env_entries = "\n".join(f'  - name: {k}\n    value: "{v}"' for k, v in config.env_vars().items())
    return f"""# Tuning config: {config.name}
# {config.description}
# beam_size={beam_size} (set in source code, not env var)
env:
{env_entries}
"""


def analyze_results(report_path: str):
    """Analyze a previously saved tuning report."""
    with open(report_path) as f:
        report = json.load(f)

    results = []
    for entry in report.get("results", []):
        config = TuningConfig(**entry["config"])
        bench = BenchmarkResult(
            concurrency=entry["benchmark"]["concurrency"],
            batch_size=entry["benchmark"]["batch_size"],
            duration_seconds=entry["benchmark"]["duration_seconds"],
            total_requests=entry["benchmark"]["total_requests"],
            successful_requests=entry["benchmark"]["successful_requests"],
            failed_requests=entry["benchmark"]["failed_requests"],
            total_sentences=entry["benchmark"]["total_sentences"],
            total_chars=entry["benchmark"]["total_chars"],
            sentences_per_second=entry["benchmark"]["sentences_per_second"],
            chars_per_second=entry["benchmark"]["chars_per_second"],
            requests_per_second=entry["benchmark"]["requests_per_second"],
            latency_p50_ms=entry["benchmark"]["latency_p50_ms"],
            latency_p90_ms=entry["benchmark"]["latency_p90_ms"],
            latency_p99_ms=entry["benchmark"]["latency_p99_ms"],
            latency_max_ms=entry["benchmark"]["latency_max_ms"],
            latency_min_ms=entry["benchmark"]["latency_min_ms"],
            latency_mean_ms=entry["benchmark"]["latency_mean_ms"],
            error_rate=entry["benchmark"]["error_rate"],
        )
        score = compute_score(bench)
        results.append(TuningResult(config=config, benchmark=bench, beam_size=config.beam_size, score=score))

    print_ranking(results, top_n=20)


async def interactive_tuning(
    nllb_url: str,
    configs: List[TuningConfig],
    concurrency_levels: List[int],
    batch_sizes: List[int],
    duration: float,
    output_dir: Optional[str],
    helm_mode: bool,
):
    """Interactive tuning — tests each config against the running server.

    For configs that require server restart (different CT2 params),
    prompts the user to restart with new env vars.
    """
    server_info = await check_server(nllb_url)
    if not server_info:
        print(f"ERROR: Cannot reach NLLB server at {nllb_url}")
        sys.exit(1)

    print(f"Server: {json.dumps(server_info)}")
    print(f"\nTuning {len(configs)} configurations")
    print(f"Per-config: {len(concurrency_levels)} concurrency x {len(batch_sizes)} batch sizes x {duration}s\n")

    all_results: List[TuningResult] = []

    for i, config in enumerate(configs):
        print(f"\n[{i + 1}/{len(configs)}] Config: {config.name} — {config.description}")
        print(f"  Env: {json.dumps(config.env_vars())}")

        if helm_mode and output_dir:
            helm_path = Path(output_dir) / f"tune_{config.name}_values.yaml"
            helm_path.parent.mkdir(parents=True, exist_ok=True)
            with open(helm_path, "w") as f:
                f.write(generate_helm_values(config, config.beam_size))
            print(f"  Helm values: {helm_path}")

        if i > 0:
            print(f"\n  >>> Restart the NLLB server with the env vars above, then press Enter <<<")
            print(f"  >>> Or type 'skip' to skip this config, 'quit' to stop <<<")
            try:
                response = input("  > ").strip().lower()
            except EOFError:
                response = "quit"
            if response == "skip":
                print(f"  Skipping {config.name}")
                continue
            if response == "quit":
                break

            # Verify server is back
            for attempt in range(30):
                if await check_server(nllb_url):
                    break
                await asyncio.sleep(1)
            else:
                print(f"  ERROR: Server not responding after 30s. Skipping.")
                continue

        results = await benchmark_config(nllb_url, config, concurrency_levels, batch_sizes, duration)
        all_results.extend(results)

    # Final ranking
    print_ranking(all_results)

    # Save report
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        report = {
            "benchmark": "nllb-tuning",
            "server": server_info,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "results": [
                {
                    "config": {
                        "name": tr.config.name,
                        "beam_size": tr.config.beam_size,
                        "inter_threads": tr.config.inter_threads,
                        "intra_threads": tr.config.intra_threads,
                        "max_batch_size": tr.config.max_batch_size,
                        "compute_type": tr.config.compute_type,
                        "description": tr.config.description,
                    },
                    "benchmark": {
                        "concurrency": tr.benchmark.concurrency,
                        "batch_size": tr.benchmark.batch_size,
                        "duration_seconds": round(tr.benchmark.duration_seconds, 2),
                        "total_requests": tr.benchmark.total_requests,
                        "successful_requests": tr.benchmark.successful_requests,
                        "failed_requests": tr.benchmark.failed_requests,
                        "total_sentences": tr.benchmark.total_sentences,
                        "total_chars": tr.benchmark.total_chars,
                        "sentences_per_second": round(tr.benchmark.sentences_per_second, 2),
                        "chars_per_second": round(tr.benchmark.chars_per_second, 1),
                        "requests_per_second": round(tr.benchmark.requests_per_second, 2),
                        "latency_p50_ms": round(tr.benchmark.latency_p50_ms, 2),
                        "latency_p90_ms": round(tr.benchmark.latency_p90_ms, 2),
                        "latency_p99_ms": round(tr.benchmark.latency_p99_ms, 2),
                        "latency_max_ms": round(tr.benchmark.latency_max_ms, 2),
                        "latency_min_ms": round(tr.benchmark.latency_min_ms, 2),
                        "latency_mean_ms": round(tr.benchmark.latency_mean_ms, 2),
                        "error_rate": round(tr.benchmark.error_rate, 4),
                    },
                    "score": round(tr.score, 2),
                }
                for tr in all_results
            ],
        }
        report_path = output_path / "tuning_results.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nFull report saved to {report_path}")


async def single_config_test(
    nllb_url: str,
    params: Dict[str, str],
    concurrency_levels: List[int],
    batch_sizes: List[int],
    duration: float,
):
    """Test a single parameter override against the running server."""
    config = TuningConfig(
        name="custom",
        beam_size=int(params.get("beam_size", "4")),
        inter_threads=int(params.get("inter_threads", "1")),
        intra_threads=int(params.get("intra_threads", "4")),
        max_batch_size=int(params.get("max_batch_size", "64")),
        compute_type=params.get("compute_type", "int8_float16"),
        description="Custom parameter test",
    )

    server_info = await check_server(nllb_url)
    if not server_info:
        print(f"ERROR: Cannot reach NLLB server at {nllb_url}")
        sys.exit(1)

    print(f"Testing custom config: {json.dumps(params)}")
    results = await benchmark_config(nllb_url, config, concurrency_levels, batch_sizes, duration)
    print_ranking(results)


async def main():
    parser = argparse.ArgumentParser(
        description="NLLB Translation Server — Performance Tuning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--nllb-url", default="http://localhost:8080")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--quick", action="store_true", help="Quick sweep (5 configs, 8s each)")
    parser.add_argument("--helm-mode", action="store_true", help="Generate helm values for each config")
    parser.add_argument("--param", action="append", default=[], help="Test specific param: --param beam_size=1")
    parser.add_argument("--analyze", default=None, help="Analyze a previous tuning_results.json")
    parser.add_argument("--duration", type=float, default=None, help="Override duration per scenario")
    args = parser.parse_args()

    if args.analyze:
        analyze_results(args.analyze)
        return

    if args.param:
        params = dict(p.split("=", 1) for p in args.param)
        await single_config_test(
            args.nllb_url,
            params,
            BENCH_QUICK_CONCURRENCY if args.quick else BENCH_CONCURRENCY,
            BENCH_QUICK_BATCH_SIZES if args.quick else BENCH_BATCH_SIZES,
            args.duration or (BENCH_QUICK_DURATION if args.quick else BENCH_DURATION),
        )
        return

    configs = TUNING_GRID_QUICK if args.quick else TUNING_GRID_FULL
    concurrency = BENCH_QUICK_CONCURRENCY if args.quick else BENCH_CONCURRENCY
    batches = BENCH_QUICK_BATCH_SIZES if args.quick else BENCH_BATCH_SIZES
    duration = args.duration or (BENCH_QUICK_DURATION if args.quick else BENCH_DURATION)

    await interactive_tuning(args.nllb_url, configs, concurrency, batches, duration, args.output_dir, args.helm_mode)


if __name__ == "__main__":
    asyncio.run(main())
