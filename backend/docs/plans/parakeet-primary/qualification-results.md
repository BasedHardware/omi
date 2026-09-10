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

## Attempt 2 — rejected, six-CPU corrected runtime

[Run 34456218244](https://github.com/BasedHardware/omi/actions/runs/34456218244) built corrected source `f8a6a0d3d99d78a55823b68f638813418144d1cd` as `gcr.io/based-hardware-dev/parakeet@sha256:67fb07d8919e971bcc655f8340a05b01593b817080584ab591ef1535d46fba9d`. The pod requested four CPUs, with an observed cgroup quota of six CPUs, one L4 and the same 20 GiB memory limit. This attempt still used the runtime default `PARAKEET_MAX_SPEECH_S=30`, while deployment sets five seconds; its numbers are diagnostic and do not qualify the deployed configuration. All 32 smoke/dependency/GPU tests passed. Streaming readiness took 52 seconds after preceding smoke tests.

| Streams | Clean final drain | p95 segment-end lag | p95 actual time to first text | Mean sampled GPU utilization |
| --- | --- | --- | --- | --- |
| 1 | Passed | 0.613 s | 24.103 s | 1.4% |
| 5 | Passed | 0.546 s | 24.036 s | 7.5% |
| 10 | Passed | 1.017 s | 24.507 s | 8.5% |
| 20 | Passed | 10.974 s | 34.464 s | 11.0% |
| 25 | Passed | 18.708 s | 42.198 s | 10.6% |

All short levels returned text and basic English sentinels passed. The normal-close fix resolved the initial short-run drain failure. The sustained 25-stream workload still failed: p95 segment-end lag reached 24.536 seconds and sessions did not complete the intended 180-second replay. The subsequent rejection probe could not establish correct recovery. Peak sampled GPU utilization over the sustained phase was 32%, with 1,970 MiB peak GPU memory. These measurements do not establish that the GPU compute itself is saturated; serialized host work and scheduling need profiling. They conclusively reject 20/25 as the production capacity prescription for this runtime.

The attempt was canceled after retaining the failed stream artifact, before all remaining batch phases completed. Cleanup succeeded. It is not a passing release qualification.

## Attempt 3 — stopped for configuration mismatch

[Run 34458880423](https://github.com/BasedHardware/omi/actions/runs/34458880423) reused the corrected image with a ten-stream cap and eight-stream target. It was stopped during smoke testing after an audit found the five-second deployment utterance limit was absent from the benchmark environment. No stream-capacity result from this attempt is claimed.

## Next qualification — match deployment settings

Repeat with the same immutable corrected image at a ten-stream admission cap and eight-stream operating target, testing levels 1, 5, 8 and 10, sustained ten-stream replay and rejection above the cap. Explicitly set `PARAKEET_MAX_SPEECH_S=5` to match deployment. Four requested/six allowed CPUs, model identity, memory, fixture and the four-second segment-end latency gate remain unchanged. A contract test now compares the benchmark's model, inference mode, utterance limit, CUDA graph setting and resource budget against the deployment values.

The revised fleet prescription is 99 warm L4 replicas: `ceil(600 × 1.30 / 8) + 1`. Its maximum is 125 plus one surge GPU. This is still provisional until the matched lower-capacity run passes. At public reference rates it costs approximately $61,691/month for compute alone; the cost review explicitly rejects a savings claim. A merge must not activate an undersized fleet by retaining the old 40-node arithmetic.

## Attempt 4: matched segmentation exposes missing text — rejected

[Run 34461408198](https://github.com/BasedHardware/omi/actions/runs/34461408198) reused the immutable `f8a6a0d3d99d78a55823b68f638813418144d1cd` image above with `PARAKEET_MAX_SPEECH_S=5`, admission cap 10 and target 8. All 32 image/dependency/GPU smoke checks passed; streaming readiness took 53 seconds after those checks.

| Concurrent streams | p95 segment-end lag | p95 first visible text | Clean completion | All four content sentinels |
| ---: | ---: | ---: | --- | --- |
| 1 | 0.4094 s | 6.0094 s | Yes | No |
| 5 | 0.4643 s | 5.9674 s | Yes | No |
| 8 | 1.7173 s | 6.2383 s | Yes | No |
| 10 | 1.0357 s | 6.4266 s | Yes | No |
| 10, sustained 180 s | 1.7875 s | 7.3738 s | Yes | Yes across repeated fixture |

The sustained replay took 182.0745 seconds including final drain, with ten accepted streams and zero transport errors. The overflow probe accepted ten of eleven and rejected one, then drained normally. Nevertheless `qualification_passed=false`: all short runs omitted the known phrase `after early nightfall`. The one-stream result contains no emitted segment for approximately 16.03–21.28 seconds despite speech in that interval. Repetition eventually producing a phrase is not proof that every occurrence survived. This is a correctness failure even though latency and protocol completion pass, and the release gate rejects it. Do not weaken the content check or credit this run as qualified capacity.

The follow-up removes zero-padding from intermediate max-window and VAD drains: those drains now submit only complete chunks, preserving the persistent decoder sample timeline. Final connection flush alone finalizes partial audio. Empty deltas retain pending speech rather than dropping its anchor, and a bounded pending-speech budget closes a stalled stream so the backend can recover through vendors. Regressions assert exact input bytes across drains and bounded retention. Finalization also drains held right context at exact chunk boundaries, preserves real audio shorter than a VAD frame, and emits a retained final word once. The capacity test now includes an exact-boundary finalization probe. A fresh GPU image must verify these content fixes before capacity is accepted.

## Efficiency prescription

The current implementation submits each session's two-second decoder work to one process-wide executor worker; every streaming buffer uses batch size one. The shared NeMo model/decoding computer makes simply raising the executor thread count unsafe without a concurrency proof. The low sampled GPU utilization is consistent with underfeeding and serialized host scheduling, but CPU/throttling and queue measurements are needed to isolate causes.

Prefer profiling followed by cross-session encoder batching with independent per-session decoder state as the durable efficiency work. Budget approximately 2–4 engineering days plus GPU qualification as an estimate, not a proven delivery time. Independent model replicas with an explicit bounded dispatcher are another experiment within the observed VRAM headroom. Neither optimization is implemented or included in current capacity arithmetic. The immediate conservative fleet is deliberately expensive; approve that control/reliability premium explicitly or keep vendor-primary while pursuing this efficiency work.
