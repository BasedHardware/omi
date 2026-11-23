# Bound floor-off processing retries at the durable and live boundaries

With `NOTES_SHORT_CLIP_FLOOR=false`, below-floor speech reaches full notes
processing. Provider timeouts and deterministic processing failures must not
reset the live retry budget indefinitely. The triggering investigation is
`refactor-lead/floor-retry-storm-cause-2026-11-11.md` (lead2 `5ce019`, supplied
with the task; this host did not read production logs).

The [retry contract](../../listen_pusher_pipeline.mdx#7-timing-constants)
now caps every conversation generation's sends, including reconnect replays.
The durable worker dead-letters deterministic processing failures after one
burst through the existing fenced terminal transition; it does not grant them
a delayed second budget. Typed provider timeouts/connections and provider
429/5xx retain bounded recovery. Result delivery and journey publication after
a commit cannot turn that commit into another processing attempt. Shared
fallback telemetry covers those fail-open branches and recovery cooldowns.

Text-only integration input bypasses speaker retry admission without assuming
`transcript_segments`. No feature flag or rollout gate is introduced; the
short-clip floor's existing setting remains authoritative.

Hermetic coverage in `test_processing_retry_boundary.py` drives opcode 104
through the worker, real persisted finalizer and notes admission, and opcode
201 back through the live session, using strict Firestore transactions. It
covers floor-off deterministic errors, provider timeout recovery, and completed
job replay. Session tests cover the send cap under sustained timeouts and
reconnects. The existing short-clip rollout lane exercises external integration
input through the processing coordinator.

The Cloud Tasks dispatch route applies the same typed processing classification
and four-attempt deterministic limit as the live worker. Its configured
transient budget remains unchanged. Strict transaction tests exercise the
route's deterministic terminal transition (including reset retry headers) and
provider timeout/5xx exhaustion through exactly one delayed second budget.
Failed pusher recovery writes emit shared fallback telemetry while retaining
the leased obligation for durable replay.

Every generic `processing_failed` wrapper enters the shared classifier on both
finalization paths, whether its original error is in `__cause__`, `__context__`
(including suppressed context), or absent. An explicit cause takes precedence.
Unknown or cyclic chains are not proven transient: they use the deterministic
four-attempt cap (or an earlier configured task cap), with no delayed second
budget. Typed provider timeouts/connections and provider 429/5xx still retain
their bounded recovery; special finalization codes keep their existing policy.
