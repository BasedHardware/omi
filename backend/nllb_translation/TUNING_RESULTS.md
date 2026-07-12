# NLLB 1.3B INT8 Tuning Results on L4 GPU

Tuning sweep performed on `dev-omi-gke` cluster, single NVIDIA L4 GPU (24GB VRAM).
Model: `JustFrederik/nllb-200-distilled-1.3B-ct2-int8` (1.3GB INT8 quantized).

## Benchmark Setup

- **Benchmark script**: `backend/scripts/benchmark_nllb_performance.py --quick`
- **Workload**: 50 English sentences × 5 target languages, 5s per scenario
- **Scenarios**: 12 combinations of concurrency=[1,2,4,8] × batch_sizes=[1,5,10]
- **Realtime budget**: 250ms p99 (from TranslationCoordinator batch window)

## Results Summary

All latencies measured at concurrency=1, batch=1 (single sentence, the realtime use case).

| Config | beam | compute | inter | intra | workers | p50 | p99 | Peak snt/s (any conc) |
|--------|------|---------|-------|-------|---------|-----|-----|----------------------|
| baseline | 4 | int8_float16 | 1 | 4 | 2 | 425ms | 623ms | 26.2 |
| **greedy** | **1** | **int8_float16** | **1** | **4** | **2** | **289ms** | **439ms** | **30.0** |
| inter2 | 1 | int8_float16 | 2 | 2 | 2 | 331ms | 477ms | **37.8** |
| turbo-single | 1 | int8_float16 | 1 | 1 | 1 | 319ms | **380ms** | 29.7 |
| intra8 | 1 | int8_float16 | 1 | 8 | 2 | 364ms | 485ms | 28.9 |
| float16 | 1 | float16 | 1 | 4 | 2 | 339ms | 470ms | 28.4 |

## Key Findings

1. **Greedy decoding (beam_size=1) is mandatory** — cuts latency ~32% vs beam_size=4 (289ms vs 425ms p50)
2. **int8_float16 is the optimal compute type** on L4 — pure float16 is ~17% slower, pure int8 unsupported on GPU
3. **2 inference workers optimal** — 1 worker halves throughput without improving latency; GPU serializes anyway
4. **intra_threads=4 is the sweet spot** — 1 thread slightly degrades, 8 threads actively hurts performance
5. **inter_threads=2 boosts throughput** (37.8 vs 30.0 snt/s) but hurts single-sentence latency (+14%)

## The 250ms Budget Reality

**No 1.3B configuration meets the 250ms p99 realtime target.** The fundamental bottleneck is GPU inference time for a 1.3B parameter model — even with INT8 quantization and greedy decoding, a single sentence takes ~289ms on L4.

### Options for Realtime Path

| Option | Latency | Quality (vs Google) | Trade-off |
|--------|---------|-------------------|-----------|
| **600M model** | ~100ms p50 | 56-84% | Lower quality, meets budget |
| **1.3B greedy** | 289ms p50 | 59-90% | ~15% over budget, better quality |
| **Google API** | ~200ms p50 | 100% | Best quality, external dependency + cost |

### Recommended Configuration

For **realtime** (transcribe.py listen path): Use 600M model or Google API — 1.3B can't meet 250ms.

For **batch/post-processing** (where latency is less critical): Use 1.3B with `inter2` config for maximum throughput:

```yaml
env:
  NLLB_BEAM_SIZE: "1"
  CT2_COMPUTE_TYPE: "int8_float16"
  CT2_INTER_THREADS: "2"
  CT2_INTRA_THREADS: "2"
  NLLB_INFERENCE_WORKERS: "2"
```

For **lowest latency 1.3B** (if 289ms is acceptable): Use greedy config:

```yaml
env:
  NLLB_BEAM_SIZE: "1"
  CT2_COMPUTE_TYPE: "int8_float16"
  CT2_INTER_THREADS: "1"
  CT2_INTRA_THREADS: "4"
  NLLB_INFERENCE_WORKERS: "2"
```

## Raw Benchmark Data

Full JSON reports saved in `/tmp/nllb-tuning/{baseline,greedy,inter2,turbo-single,intra8,float16}/`.
