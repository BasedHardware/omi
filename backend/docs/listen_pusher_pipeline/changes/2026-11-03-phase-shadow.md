# Read-only conversation and episode phase shadow

Step 1 of David's [explicit-state design](https://claude.ai/artifact/7srvSdinev4M8oiSKotRiU).
`utils/conversations/phase.py` derives only legacy persisted facts; no phase writes,
backfill, reader flips, cloud calls, or runtime deployment are part of this change.

Seven readers compare their existing verdict with a phase projection:
Home visibility, settling hold, episode member retention, processing attention,
summary repair eligibility, record-audio admission barrier, and episode composer.
The legacy return values, exceptions and response payloads stay authoritative.

`omi_phase_shadow_total{reader,derived_phase,agrees}` counts sampled reader verdicts,
including policy disagreements (curation, feature gates, backoff and freshness).
Home/member visibility projects complete/settled/dead_letter/failed; settling and
attention project sealed/processing/transcribed; repair projects transcribed;
admission projects sealed; composition projects closed. Nested calls each count.
Counters are reads, not a census of unique recordings. There are no UID/ID labels.
`omi_phase_shadow_errors_total{reader}` counts caught shadow exceptions, including
metric failures; even an error-collector failure cannot change legacy behavior.

The existing 2-hour timeliness sampler has batch jobs and projection receipts,
never conversation documents (even its BatchGet selects only job enqueue times).
It cannot be shadow-compared without extra IO and is intentionally unchanged.
Similarly, quarantined is reserved in the conversation enum: its evidence currently
lives on separate batch receipts and cannot be inferred from a conversation alone.

`omi_phase_age_seconds{phase}` samples existing started_at,
processing_admitted_at, summary_first_pending_at (the summary-debt clock for transcribed
rows; it may predate or follow transcription), summary_completed_at, wrap_up_requested_at, closed_at and composed_at.
These are reader-sampled ages, not transition durations. There is no persisted
seal timestamp, so no sealed age is fabricated from recording end or creation time.
The buckets include 1800, 3600 and 7200 seconds to preview seal, summary and batch
budgets; trustworthy sealed dwell requires a later writer migration.

Rollback: `PHASE_SHADOW_ENABLED=false` (also 0/off/no, case insensitive); default on.
Off skips derivation and observation entirely. This is an env-only telemetry kill
switch registered in the [backend flag registry](../../feature-flag-registry.md).
Only the rollout lead deploys; implementers do not access production.
