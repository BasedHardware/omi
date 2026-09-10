# Promotion and fallback contract

Action class: proposed implementation and release design; all activation is withheld.
Evidence cutoff: 2026-09-10 (source-informed proposal, no live validation).

## Policy and product invariants

One policy owner must resolve surface, language, feature needs, explicit provider/BYOK selection, cohort, health and capacity. Preserve existing explicit-user selection semantics. Qualifying Parakeet as default must not remove working vendor fallbacks or silently lower speaker/language functionality. Audit actual callers before changing defaults.

Proposed live order for eligible sessions: Parakeet → Modulate → Deepgram cloud. Noneligible requests use the current working vendor order. Batch remains Parakeet → Modulate until existing Deepgram batch helpers are integrated into the selector, policy-admitted and qualified. PTT is initially Parakeet → Modulate only for qualified English; its current dispatcher does not implement Deepgram. Retaining Deepgram globally does not mean pretending it can serve every endpoint.

The existing connection helper in `omi:backend/utils/stt/streaming.py` has a fixed Modulate → Deepgram → Parakeet fallback order independent of the configured primary list. The Parakeet-primary listen caller currently supplies only the Modulate connection callback, so the proposed three-provider live chain requires wiring and testing a Deepgram leg, including when both Parakeet and Modulate fail before a usable connection. This is core implementation scope. Test actual runtime selection as well as config rendering. Single-channel listen has mid-session rebuilding; multi-channel does not have the same path. Exclude multi-channel from the initial cohort until its continuity path is explicitly qualified, or fund that hardening as additional scope.

Admission remains enforced at the Parakeet serving resource, with unconditional release on socket construction failure, normal completion, cancellation, send/receive failure and finalize timeout. Never multiply a process-local listener cap across replicas. Size for uneven long-lived connection distribution and N+1 failure, not only total cluster average. Protect batch capacity from streaming starvation and vice versa; decide separate pools versus reserved scheduling from mixed-load evidence.

Fallback must work both before the first transcript and after partial output. Use bounded replay with audio sequence/timestamp ownership, committed-segment deduplication, speaker remapping, monotonic transcript times and terminal finalization. Do not replay acknowledged audio as new text or lose buffered final words. Keep provider retries bounded and exclude failed providers during a session. If all providers fail, expose an explicit recoverable outcome and preserve the existing catch-up contract; silence is not success.

Use the shared `record_fallback` contract (`omi:.github/agent-docs/fallback-telemetry.md`) for every provider/mode change. Include bounded reason labels for unsupported capability, admission/capacity, unhealthy, connection, timeout, midstream failure and exhausted chain. Record attempted, admitted, productive, rejected and completed sessions; successful audio hours; billed retries; first/final transcript latency; GPU/queue state and ready-replica capacity. No raw audio/transcripts or user IDs in metric labels. Separate server-send proof from client receipt/render proof.

## Planned release gates

| Stage | Evidence required to proceed | Activation boundary |
| --- | --- | --- |
| Scope review | Agreement on English-first eligibility, speaker/readability bar and total cost model | Docs only; this draft |
| Isolated qualification | Benchmark gates pass, fault paths exercised, capacity and costs measured | Future implementation/test work; no production traffic |
| Dark implementation | Reviewed code, existing policy/runtime rendering tests and client continuity tests pass; promotion allocation remains zero | Separate code PRs and release approval |
| Consented dogfood | Explicit test identities, verified data plane, aggregate client/server outcomes and rollback rehearsal | Separate approval; no implicit production shadowing |
| Production canary | Exact release vector and approved policy; fallback quotas and recovery ready | Explicit production approval before any production allocation |
| Expansion | Per-slice gates, no silent loss, cost and capacity headroom sustained | Subsequent explicit decision; no automatic expansion |

Suggested post-approval cohorts: 1% → 5% → 25% → 50% → 100% of **qualified single-channel live sessions**, stable assignment and exclusions preserved. PTT needs a separate qualification verdict and separately approved cohort schedule; batch retains its current primary and is monitored for contention, while multi-channel remains excluded. Report eligible hours / all incoming hours and actual Parakeet productive share, so “100% eligible” cannot masquerade as universal coverage. Each stage requires at least 24 hours including a peak period plus enough observations for its reliability claim; low traffic extends the stage. Percentages alone do not cap load: bind each stage to an absolute admitted concurrency/audio budget.

## Stop and recovery

Immediately halt expansion on silent audio loss, duplicated committed text, wrong-speaker identity, unsupported-language routing, exhausted admission leases, or failed fallback. Also stop on a benchmark/SLO threshold breach sustained for five minutes, capacity above the qualified headroom boundary, fallback rate above the modeled budget, or divergence of serving policy/release vector. No-data is inconclusive.

Before activation, record the known-good provider order, cohort allocation, admission limits, model/container digests, Cloud Run/GKE vector and fallback credential versions (names only). Rehearse the actual route-revert mechanism and measure propagation; environment-backed changes require deployment/rollout and are not instantaneous toggles. Proposed target is recovery of new-session vendor routing within five minutes, subject to rehearsal. Maintain enough vendor quota to absorb 100% of the canary plus plausible wider incident demand.

Recover new sessions to the approved vendor order; drain existing healthy Parakeet sessions or switch them with tested replay/dedup semantics. Restore compatible infrastructure/config when a partial deployment changed more than routing. Read back the entire serving vector and verify client transcript continuity with real accepted audio before calling recovery complete. Do not delete Parakeet or vendor resources as part of emergency recovery.

## Acceptance and closure

Promotion is complete only when approved eligible traffic is primarily served by Parakeet across peak and failure conditions, both vendor fallback paths remain exercised, actual fully loaded cost and quality meet the agreed decision, exceptions are explicit, and rollback has evidence. A green build, ready pod, successful config write or docs merge cannot close this project.
