# Free-allowance spend-point observation (SCA-1750, draft)

This is the observation groundwork for SCA-1750. It is **not the shared reservation** and is not ready for enforcement or the rollout acceptance gate.

The provider constructors and prerecorded calls, batch GPU authorization, one-shot route, live billing flush, PTT settlement, and processing policy call the same strict monthly-billing snapshot reader. The policy lookup has no cohort or launch-date gate. Paid plans (including trials recorded on paid plans) return before usage lookup. Deepgram request-key exemption applies only when that actual provider uses the key; managed fallbacks remain managed. Processing observes actual LLM-key funding separately.

A missing, stale-epoch, invalid, or unready monthly projection produces `usage_unavailable`. Missing identity and subscription are separate outcomes. No empty usage record becomes zero. This reader does not scan hourly history or rebuild the projection, and therefore an account with no verified monthly baseline is unavailable, including a new account. Baseline provisioning is still needed before enforcement.

## Instrumentation contract

`STT_FREE_ALLOWANCE_WATCH_ENABLED` defaults to `true`; `false`, `0`, `off`, and `no` disable observation. It controls telemetry only. It does not disable or replace an existing admission rule.

`omi_free_allowance_watch_decisions` counts observations by bounded `path`, `provider`, and `decision`. `omi_free_allowance_watch_seconds` counts the supplied duration in those same buckets. Logs contain those fields only, with no account identifiers, transcript, or audio. Async observation waits at most 2.5 seconds; batch authorization observes only sealed units with at most 100 ms of the remaining authorization budget. Timeouts are missing observations, never permission. Provider calls and existing gate results remain authoritative in this draft.

Durations are deliberately different evidence types. `live_billing` uses the existing `billable_transcription_seconds` result, including holds and resume boundaries. `ptt` uses accepted audio settled by the existing daily PTT budget, which currently differs from monthly transcription billing. `batch_gpu`, `batch_provider`, and `one_shot` carry input duration. Some prerecorded calls and live opens supply zero because their duration is not known at this point. A zero is an unknown-duration event, not evidence of zero spend.

Do not sum paths: provider attempts, dispatch authorization, and billing can describe the same work. A `would_refuse` duration is the full requested duration, not just its portion above the allowance. These counters do not prove settled over-allowance hours, model concurrency, or constitute savings evidence. An observation can precede provider failure. Summary/memory observation reads the same snapshot, but its actual gate still uses the legacy policy.

## Work still required

- Implement one atomic shared reservation across concurrent sessions and replicas, with bounded short leases, idempotency, strict baseline readiness, month rollover, erasure fences, and settlement against billing seconds.
- Carry authenticated account identity and billing duration through all worker and provider paths; measure unknown-identity and unknown-duration coverage before rollout.
- Replace the independent PTT daily-budget interpretation with the authorized common ledger contract, without changing paid/trial entitlements.
- Wire clean lease-refusal session termination and the SCA-1752 on-device activation condition. Do not reuse the existing silent-byte-suppression behavior.
- Make the actual summary/memory gate consume the shared ledger; observe-only is insufficient.
- Produce concurrent Firestore emulator evidence and route-level fault tests. Unit snapshot tests alone cannot establish reservation correctness.
- Deploy watch-only, collect a full day of aggregate-only reconciliation against settled billing/unit-cost data, and verify observation coverage and Firestore/latency cost. No production deployment or account reads have been performed for this draft.
- After that gate, enforce offline routes behind an emergency kill switch and remove their old checks. Enable live stopping only with the on-device switch. Obtain David's approval and renders for any user-visible behavior change before merge.

No prices, plan allocations, ceilings, or served admission decisions change in this draft. Keep the PR draft and SCA-1750 in progress until the missing implementation is complete; this note does not authorize rollout.
