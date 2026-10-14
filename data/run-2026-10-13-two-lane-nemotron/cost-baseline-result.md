# Cost baseline — 2026-10-14

Measured net billing averages: October 7–11 UTC; telemetry: October 7–13. FinOps is settled only through October 11; October 13 billing is incomplete. Dollars/hour below means **fleet wall-clock hour**; allocated audio averages **$0.0694/transcription-hour**, versus the earlier ~$0.062.

| Component | $/hour | Basis | GPU mean % / FB GiB | Nodes min–max; CA min–max |
|---|---:|---|---|---|
| Listen, GKE | 2.415 | measured | — | — |
| Pusher, GKE | 1.030 | measured | — | — |
| Parakeet L4 A | 2.288 | measured | 6.6 / 2.44 | 2–4; 2–4 |
| Parakeet L4 B | 1.562 | measured | 6.9 / 2.42 | 1–4; 1–3 |
| NLLB L4 | 0.597 | measured | 8.8 / 1.14 | 1–1; 0–2 |
| VAD T4 v2 | 0.853 | measured | 21.3 / 3.06 | 1–3; 0–10 |
| Diarizer T4 | 0.533 | measured | 11.2 / 2.47 | 1–2; 0–10 |
| Backend-sync, Cloud Run | 7.212 | measured | — | — |
| Audio GCS | 7.746 | measured | — | — |

**Split, estimated:** five-day allocation regression gives $372/day fixed + $0.0139/transcription-hour: approximately 80% fixed, 20% variable at observed volume. This is noncausal, low-confidence; hourly cost/concurrency R²≈0 cannot establish marginal cost. Allocation includes nonprod; backend-sync is separate. See [plot](cost-baseline-plot.png) and [reconciliation](cost-baseline-method.md).

**Fleet:** 168 hourly DCGM means/pool; node history has 167 snapshots. Listen/pusher hour-of-day means trough ~312 at 03:00 UTC, peak ~408 at 18:00, 1.31×. Current HPA: Parakeet 3–7, active requests=2/GPU or GPU=35%; NLLB 1–2 CPU=70%; VAD/diarizer 1–10, p99 targets=2000/300ms; down stabilization 600s except NLLB default.

**Batch, estimated:** ASR service RTF=0.0331, a mixed-live-window proxy; pyannote L4=0.03. At [L4 $0.8536/hour](https://cloud.google.com/products/compute/pricing/accelerator-optimized), 24kbps Opus uses 10.8MB/hour; [30-day regional GCS + one PUT](https://cloud.google.com/storage/pricing) costs ~$0.00021; ingress is free. `C(f)=f×[0.8536×(0.0331+0.03)+0.00021]`: **$0.0541/$0.0270/$0.0178 per worn-hour** at f=1/0.5/0.33; excludes orchestration, retries, and idle floors.

**Policy:** retain admission; trial Parakeet queue/request target changes with real DCGM and qualified p95<3s. Floor=max(3,ceil(peak-demand/qualified-capacity)+1); stabilize down 900s, drain sessions. Keep NLLB/VAD/diarizer floor=1; qualify queue/GPU scaling with latency guards. Batch uses a yielding worker lane; PriorityClass/preemption applies to separate spare-node pods, or checkpointed spot L4. Scenario: mean live GPUs 6.2→4–5 saves **$18–33/day allocated**, low-confidence; guaranteed cash savings $0 under commitments. Risks: burst latency, GPU availability, preemption.

**Exact weekly queries:** [SQL/PromQL appendix](cost-baseline-queries.md), [collector](cost-baseline-receipt.py), [analyzer](cost-baseline-analyze.py). No production changes.
