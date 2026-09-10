# Parakeet-primary transcription

Implementation and research record, 2026-09-10. This PR changes executable routing, serving, capacity and release configuration. It is a draft pending integrated qualification; no production deployment has been performed by this task.

## Decision

Use Parakeet TDT v3 first for single-channel backend live transcription in its 25 supported languages, including the default multilingual mode, then Modulate and Deepgram cloud. Keep vendor routing for unsupported languages and multi-channel sessions; BYOK and supported explicit-provider paths retain their contracts. This changes the deployed stream model as well as provider order: the old English RNNT model would bypass most default multilingual sessions. PTT uses Parakeet then Modulate; its dispatcher does not implement Deepgram. Batch keeps Parakeet then Modulate and its separate TDT model.

Separate realtime and batch GPU fleets. A streaming replica loads one TDT v3 instance, VAD and speaker embedding dependencies without a second batch instance, and cannot accept batch requests. Batch releases cannot accept streaming requests. The image retains a mixed mode for existing standalone installations. The dedicated stream endpoint takes precedence over the historical shared endpoint.

The production streaming manifest specifies 99 warm L4 replicas and a ceiling of 125; development specifies 2–4. One GPU and one process own each pod's admission cap. The production floor covers a planning envelope of 600 concurrent eligible streams, 30% reserve and one node failure at an operating target of 8 streams per pod. The TDT checkpoint and Silero source are pinned for repeatability. The hard cap of 10 and target of 8 remain qualification assumptions until the exact image passes sustained realtime testing. These are not measured throughput results.

## What ships

| Boundary | Implementation |
| --- | --- |
| Provider policy | Parakeet-first live/PTT defaults; language/surface eligibility retained |
| Live fallback | Both vendor callbacks wired from Parakeet; previously failed providers excluded during session rebuilding |
| Serving | Explicit mixed/batch/stream modes; stream model warmup readiness, admission metrics and bounded drain |
| Capacity | Dedicated GPU selectors, hostname anti-affinity, warm floor, disruption budget, zero-unavailable rolling updates and one surge GPU |
| Autoscaling | Per-pod active streams plus recent capacity rejections through the existing Prometheus adapter; absent metrics remain absent |
| Endpoint contract | Dedicated `HOSTED_PARAKEET_STREAM_API_URL`; existing batch URL retained |
| Qualification | Existing GPU workflow extended with exact-source image build and isolated realtime load tests, immutable digest and result artifacts |

Code authorities: [provider policy](../../../config/stt_provider_policy.py), [connection helper](../../../utils/stt/streaming.py), [listen receiver](../../../routers/listen/receiver.py), [Parakeet service](../../../parakeet/README.md), [chart](../../../charts/parakeet/), [runtime environment](../../../deploy/runtime_env.yaml).

## Review packet

- [Capacity](capacity-plan.md): replica arithmetic, GPU pool limits, metrics, readiness and failure assumptions.
- [Measured results](qualification-results.md): rejected first run, runtime fixes and qualification limits.
- [Benchmark](benchmark-plan.md): executable capacity test and broader quality evidence required for promotion.
- [Cost and effort](cost-and-effort.md): first-party prices, utilization sensitivity and remaining qualification work.
- [Release and recovery](rollout-plan.md): capacity-before-routing ordering and production approval boundary.

Do not claim cost savings from raw model throughput. At the researched public G2 price, 99 continuously warm GPUs cost approximately $61,691/month for compute alone. This exceeds Modulate even at the proposed hard per-GPU capacity using public reference rates. The 20/25 assumption failed real load testing; the lower 8/10 prescription prioritizes the requested primary routing with explicit failure reserve. Review the premium alongside latency, quality and control benefits.

## Acceptance boundary

A merge changes the deployable implementation. The repository's production release still requires its existing release eligibility and explicit production gate. No production gate is bypassed by this PR. Before promotion, the release must establish warm, schedulable capacity and current custom metrics; unit tests or desired replica counts alone cannot establish that the fleet sustains users.

The representative quality corpus, vendor invoice reconciliation, sustained GPU capacity results and production failure/rollback evidence have separate evidentiary value. Keep missing results explicit. Do not represent a short public-fixture load test as a multilingual, speaker-quality or whole-user-base certificate. Live customer measurements and negotiated rates remain in the private coordination record.
