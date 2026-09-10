# Parakeet-primary STT: proposed implementation plan

Status: draft design for review, 2026-09-10. **No activation or production change is authorized by this document or its merge.**

Source baseline: `4e1f98cbe1fdf02ecb051e14f3e2ddb6d6078902`. This PR changes documentation only. It contains prescriptions for subsequent implementation, capacity qualification and explicitly approved rollout; it does not claim the target design exists today.

## Recommendation

Promote Parakeet first for **qualified English, single-channel backend live transcription**, keep Modulate then Deepgram cloud as fallbacks, and scale a dedicated realtime GPU fleet before admitting traffic. Preserve existing Parakeet-first batch service. Qualify PTT separately; preserve on-device, explicit-provider and BYOK behavior. Exclude multi-channel and unsupported language/feature combinations until separately qualified.

Approve an isolated two-replica L4 streaming qualification as the next engineering milestone, not a global provider-order flip. Target one `g2-standard-8` / L4 per streaming replica initially; compare cheaper shapes only after CPU, memory and diarizer headroom are measured. Retain the existing batch fleet independently. For an approved pilot, propose two warm streaming replicas and a four-replica ceiling, plus schedulable rolling-update surge capacity. These are proposed values, not manifests changed by this PR. They must shrink or grow if qualification shows different safe capacity.

Use a provisional hard cap of 25 streams per streaming pod and an operating/HPA target of 20, **only if the full quality/latency suite proves those values**. A cap protects a resource; it does not prove the model can meet latency at that load. Size each expansion from measured eligible demand, 30% demand reserve, one-replica loss and node/model warmup. Do not increase the per-pod cap just to fit more users.

Do not promise savings yet. Public Modulate rates are low enough that a lightly utilized redundant GPU fleet may cost more. Require a fully loaded cost decision at measured occupancy before approving broad scale. If reliability or control justifies a premium, approve that premium explicitly.

## Current source and required change

| Surface/boundary | Current source | Prescription |
| --- | --- | --- |
| Live default | `modulate-velma-2,dg-nova-3,parakeet` | Eligible cohort: Parakeet → Modulate → Deepgram; preserve current vendors for all other requests |
| Actual fallback wiring | Shared helper has fixed fallback order, but Parakeet-primary listen caller supplies only Modulate | Wire and test Deepgram for initial connection and mid-session exhaustion; config ordering alone is insufficient |
| Batch / catch-up | `parakeet,modulate-velma-2` | Preserve; separate its capacity from realtime, verify contention and overflow |
| PTT | `modulate-velma-2,parakeet`; only these two dispatchers | Separate English-first trial; new Deepgram PTT adapter is optional later scope |
| Model capability | RNNT 1.1b realtime/PTT, English-only; TDT 0.6b v3 batch, 25 languages | Do not use batch capability as proof of multilingual live support |
| Multi-channel | Different initialization/send path, without the same single-channel failover monitor | Exclude initially; budget a separate continuity design |
| Capacity | Existing service-owned per-pod admission and shared batch/stream GPU architecture | Separate fleets; retain admission; replace batch-driven realtime scaling assumptions with qualified stream-demand scaling |

Authoritative code: [provider policy](../../../config/stt_provider_policy.py), [connection helper](../../../utils/stt/streaming.py), [listen receiver](../../../routers/listen/receiver.py), [PTT](../../../routers/chat.py), [batch selector](../../../utils/stt/pre_recorded.py), [Parakeet service](../../../parakeet/README.md), [chart](../../../charts/parakeet/), [runtime environment](../../../deploy/runtime_env.yaml).

## Review packet

- [Capacity and infrastructure prescriptions](capacity-plan.md): fleet separation, scaling controls, absolute budgets, node headroom and failure/drain design.
- [Benchmark plan](benchmark-plan.md): corpus, quality, speaker identity, client continuity, latency, reliability, capacity and fault gates.
- [Cost and effort](cost-and-effort.md): public pricing, utilization sensitivity, fully loaded cost and capacity-inclusive implementation estimate.
- [Rollout and rollback](rollout-plan.md): admission, vendor fallback, separate surface canaries and release-vector recovery.

## Proposed implementation sequence

| Slice | Files / responsibility | Reviewable exit |
| --- | --- | --- |
| 1. Demand and quality baseline | Existing `backend/scripts/stt/` benchmarks, metrics and test corpus manifest | Eligible load and coverage; paired quality report; no routing changes |
| 2. Independent realtime capacity | `backend/parakeet/` startup/readiness/drain; `backend/charts/parakeet/`; model-specific endpoint/config declarations | Isolated streaming/batch releases, trained/warm readiness, leak-free admission, replica-loss test |
| 3. Correct routing and fallback | `backend/config/stt_provider_policy.py`, `backend/utils/stt/streaming.py`, `backend/routers/listen/receiver.py`, associated unit tests | Qualified single-channel Parakeet-primary path reaches both vendors without lost/duplicate text |
| 4. Scaling and deployment contract | Parakeet HPA/service monitoring, metric adapter rules, canonical runtime env and existing release validation | Live-stream scaling metric proven end-to-end; manifest parity; stage budget, drain and rollback rehearsed |
| 5. Qualification and activation decision | Existing unit/container gates, consented client runs, aggregate results | Model/capacity/cost gates pass, exact release artifact and explicit promotion approval |

Keep each implementation PR independently dark and testable. No new CI workflow is prescribed; extend the existing owning lanes. Do not remove or weaken admission, capability policy or deployment recovery to make the new route pass. Optional Deepgram batch/PTT expansion, multilingual live models and multi-channel failover do not silently enter the initial slice.

## Decisions proposed for morning review

Adopt the architecture, English-first eligibility and qualification gates above; fund capacity qualification before routing work; reserve an initial isolated test budget up to $500 after computing the exact resource/run cap. This proposed budget is not spend authorization; obtain separate approval before paid compute/API execution. Withhold production allocation and purchases/commitments. The next go/no-go is the measured quality + safe capacity + fully loaded economics packet. A failure there means retain vendor-primary while improving the candidate, not promote it anyway.

No live production throughput, invoice amounts, internal service identities or customer recordings are published here. Public scenarios are explicitly illustrative. Operational measurements and negotiated financial inputs stay in the private coordination record; they must be refreshed before execution.
