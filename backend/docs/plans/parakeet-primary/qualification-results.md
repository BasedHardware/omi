# GPU qualification results

## Attempt 1 — rejected, 2026-09-10

[Workflow run 34452691962](https://github.com/BasedHardware/omi/actions/runs/34452691962) built source `fe099fefe86a6f2f7672f80f7f5f0378a0b38fe0` as `gcr.io/based-hardware-dev/parakeet@sha256:7001dcf8934dcc95cf01844b2fe424e31407e1f6c2517c86b5dfcca40b98ea7c` and tested it on an isolated development `g2-standard-8` with one L4. The pod had a one-CPU request, two-CPU limit and 20 GiB memory limit. These results do **not** qualify the proposed 20/25 stream operating/admission limits.

The 18 CPU smoke, 10 dependency-contract and four GPU inference tests passed. Cold image pull took 235.76 seconds for a 25,687,296,991-byte image. Streaming startup reported ready after 52 seconds, following the preceding smoke tests' cache population. These are separate measurements; 52 seconds is not full cold node-to-readiness time.

| Concurrent streams | Accepted | Nonempty text | p95 segment-end-to-arrival latency | Clean final drain |
| --- | --- | --- | --- | --- |
| 1 | 1 | 100% | 0.476 s | Failed |
| 5 | 5 | 100% | 0.583 s | Failed |
| 10 | 10 | 100% | 3.795 s | Failed |
| 20 | 20 | 100% | 29.614 s | Failed |
| 25 | 25 | 0% | No text | Failed |

The subsequent sustained 25-stream phase admitted zero streams, returning `capacity_full`; its result and the admission-overflow probe therefore failed. Model identity matched the pinned multilingual TDT checkpoint. Peak observed GPU memory across these levels was 1,820 MiB of 23,034 MiB. A Kubernetes CPU sample during the 25-stream workload was 1,827 millicores, close to the two-core limit. That suggests CPU pressure, but does not establish the bottleneck without a controlled rerun and utilization measurements.

The latency above is measured from the reported segment end, **not** time to first visible text. At concurrency one, the single returned segment arrived about 23.966 seconds after the session began. The first harness version mislabeled the segment-end-relative value as first-text latency. It cannot establish incremental transcript responsiveness.

Investigation confirmed two lifecycle defects: finalization flushed text but omitted an explicit normal WebSocket close, producing client code 1006; raw Starlette disconnect messages were not treated as terminal. The follow-up patch adds explicit normal closure after successful final flush and terminates on disconnect, with regression tests. It preserves strict clean-close qualification rather than relaxing the benchmark.

After preserving the failed capacity results, this attempt was canceled before completing the unrelated remaining batch phases. Cancellation does not turn it into a passing qualification. The cleanup job succeeded; a subsequent read-only query confirmed both the task node pool and Job were absent.

## Next qualification

Repeat on the corrected source with the same one-L4 machine, four requested CPUs and a six-CPU limit, matching the dedicated stream deployment overlays. Keep the 4-second segment-end latency gate and require all levels, sustained load, final drain and admission recovery to pass. Include actual time-to-first-text and GPU utilization diagnostics. The operating target and fleet size remain provisional until the corrected run is evaluated; do not infer throughput improvement merely from allocating more CPU.
