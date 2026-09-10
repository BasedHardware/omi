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

All nine non-streaming phases completed successfully (57 tests): CPU imports, dependency contracts, GPU smoke, synthetic diarization, VoxConverse diarization, concurrency, LibriSpeech WER, high concurrency and VRAM stress. Batch aggregate DER was 32.9% against the existing 40% gate; aggregate WER was 13.0% against the existing 15% gate. These batch measurements do not establish streaming quality or vendor parity. The workflow concluded failure, uploaded its artifacts, and completed cleanup successfully; the task-owned GPU pool and Job were confirmed absent.

The follow-up removes zero-padding from intermediate max-window and VAD drains: those drains now submit only complete chunks, preserving the persistent decoder sample timeline. Final connection flush alone finalizes partial audio. Empty deltas retain pending speech rather than dropping its anchor, and a bounded pending-speech budget closes a stalled stream so the backend can recover through vendors. Regressions assert exact input bytes across drains and bounded retention. Finalization also drains held right context at exact chunk boundaries, preserves real audio shorter than a VAD frame, and emits a retained final word once. The capacity test now includes an exact-boundary finalization probe. A fresh GPU image must verify these content fixes before capacity is accepted.

## Attempt 5: content fixed, bounded timestamp jitter rejected the harness

[Run 34466094153](https://github.com/BasedHardware/omi/actions/runs/34466094153) built source `50c9728b5caef68c0842807da1e5b3a1cc46f16e` as `gcr.io/based-hardware-dev/parakeet@sha256:e2f163a7b2ab5a140132e90cafca44985633c9ab7b04e17cdfb90215865bb1e6`. It matched the deployment cap, target, CPU budget and model settings. All 32 smoke/dependency/GPU checks passed, every short run returned all four content sentinels, sustained ten-stream replay accepted ten streams for 180 seconds with no transport errors, and the exact-chunk-boundary probe completed normally.

The workflow still reported `qualification_passed=false` because its timestamp-validity check rejected segment timestamps that preceded receipt by 37–80 ms. Segment-end p95 lag remained below 1.7 seconds at levels 1, 5, 8 and 10, and text, admission and clean-drain gates passed. This is bounded clock/measurement jitter rather than negative workload lag. The harness now records the raw minimum and accepts up to 100 ms of jitter while clamping the latency sample at zero; a fresh image and rerun are required before claiming capacity.

All nine non-streaming phases again passed (57 tests; DER 32.9%, WER 13.0%, both within existing gates). Cleanup succeeded and the task-owned GPU pool and Job were absent afterward. This attempt is retained as a rejected harness run, not as release qualification.

## Attempt 6: invalid harness run

[Run 34519596599](https://github.com/BasedHardware/omi/actions/runs/34519596599) built source `2f3f708e53a91701a3e715f35baea8f080c160a2` as `gcr.io/based-hardware-dev/parakeet@sha256:12473642e25d77f17547d4c992f806536ca5951f53d4752948e96e0bcdff8ac4` and matched the cap-10 deployment settings. The streaming receiver helper raised `UnboundLocalError` for its timestamp-order state before content or transport results could be evaluated. Non-stream phases that ran passed and cleanup succeeded. This run is invalid evidence and is not counted.

## Attempt 7: exact-source qualification passed

[Run 34526605301](https://github.com/BasedHardware/omi/actions/runs/34526605301) built the current source `cf055da5307b368a61a3405bbdc9d27d95575ebd` and tested the immutable image `gcr.io/based-hardware-dev/parakeet@sha256:7021f89f415d81a1703685e1557c352fbb9b23c23408b9e9ff6e753960653791` on an isolated `g2-standard-8` L4. It matched deployment's five-second maximum speech window, six-CPU quota, TDT model identity and admission cap 10.

| Scenario | Accepted / requested | Final drain | Text + sentinels | p95 segment-end lag |
| --- | ---: | --- | --- | ---: |
| Burst level 1 | 1 / 1 | Pass | 100% / 100% | 0.340 s |
| Burst level 5 | 5 / 5 | Pass | 100% / 100% | 0.410 s |
| Burst level 8 | 8 / 8 | Pass | 100% / 100% | 1.019 s |
| Burst level 10 | 10 / 10 | Pass | 100% / 100% | 0.996 s |
| Exact two-second boundary | 1 / 1 | Pass | 100% / 100% | 0.094 s |
| Sustained level 10, 180 s | 10 / 10 | Pass | 100% / 100% | 1.527 s |

The capacity rejection probe accepted 10 of 11 streams and rejected the eleventh with WebSocket code 1013 (`capacity_full`). Stream timestamps were monotonic and within the bounded jitter gate. Peak streaming memory was 1,658 MiB on a 23,034 MiB L4. GPU smoke, dependency contracts, synthetic and 15-clip VoxConverse DER, LibriSpeech WER, high-concurrency and VRAM stress phases also passed; aggregate DER was 32.9% against the 40% gate and aggregate WER 13.0% against the 15% gate. These are transport, completeness and capacity measurements, not multilingual or whole-fleet reliability certification. Cleanup completed and the task-owned GPU pool and Job were absent afterward.

This is the first passing capacity artifact for the current source and fixes the prior decoder ownership, exact-boundary, monotonic timestamp and bounded-jitter failures. Keep the fleet rollout gated on the release checks and staged traffic plan below; do not treat one L4's 10-stream result as a 99.9% whole-fleet guarantee.

## Efficiency prescription

The current implementation submits each session's two-second decoder work to one process-wide executor worker; every streaming buffer uses batch size one. The shared NeMo model/decoding computer makes simply raising the executor thread count unsafe without a concurrency proof. The low sampled GPU utilization is consistent with underfeeding and serialized host scheduling, but CPU/throttling and queue measurements are needed to isolate causes.

Prefer profiling followed by cross-session encoder batching with independent per-session decoder state as the durable efficiency work. Budget approximately 2–4 engineering days plus GPU qualification as an estimate, not a proven delivery time. Independent model replicas with an explicit bounded dispatcher are another experiment within the observed VRAM headroom. Neither optimization is implemented or included in current capacity arithmetic. The immediate conservative fleet is deliberately expensive; approve that control/reliability premium explicitly or keep vendor-primary while pursuing this efficiency work.

Before redesigning the scheduler, profile actual PyTorch intra/inter-op thread counts and cgroup throttling, then compare bounded CPU-thread settings. Also evaluate encoder-only mixed precision against the same content and accuracy gates: the current streaming forward path has no explicit autocast region. [PyTorch documents per-operation mixed precision](https://docs.pytorch.org/docs/2.10/amp.html), but that is a basis for an experiment, not evidence of a Parakeet speedup or acceptable decoder accuracy. Test distinct simultaneous utterances to verify session isolation before introducing parallel model execution. No resulting speedup is credited here.
