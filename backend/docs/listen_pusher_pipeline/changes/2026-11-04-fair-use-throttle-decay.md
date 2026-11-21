# Fair-use throttle decay (explicit-state program F1)

The fair-use read normalizer now completes throttle → warning → none. Each
transition persists its entry time and next deadline. Restrict expiry still
returns throttle on the same read, now with a fresh seven-day throttle deadline.
An expired, absent, or malformed throttle deadline moves to warning on the first
uncached state read; warning receives a seven-day quiet period starting at that
exit, then clears on a second read after the deadline. Qualifying violations
renew a warning's quiet period without changing upward escalation thresholds.
Legacy warnings use their last violation plus seven days; unknown ages receive
one seven-day period on first read. New decay writes compare the authoritative
row in a Firestore transaction, preserving concurrent escalations and renewals.
Warning renewal also reads the current stage transactionally: it re-enters
warning if decay committed first, or preserves a concurrently higher stage.
The violation event records that transaction's actual previous stage and action.

`FAIR_USE_THROTTLE_DECAY_ENABLED` defaults on; `false`, `off`, or `0` restores the
previous restrict-only behavior, including its original writes. Stage-cache
hits retain the existing 60-second TTL. Sync and listen restrict gates are
unchanged. Only the rollout lead deploys; this PR does not access production.

`omi_fair_use_stage_dwell_seconds{stage}` samples the last authoritative row read
for each of four fixed stage labels. It uses `stage_entered_at`, falling back to
`last_violation_at` then `updated_at` for legacy rows; rows without a usable age
do not fabricate a dwell sample. This is a last-read gauge, not a population
percentile or a full scan. `omi_fair_use_stage_decay_total{from_stage,to_stage}`
counts persisted decay transitions with three fixed label pairs. Missing or
malformed throttle deadlines also emit the existing `malformed_doc` fallback
telemetry. The metric does not itself install a fleet dwell alert.

Evidence: [F1 / explicit-state initiative](https://claude.ai/artifact/7srvSdinev4M8oiSKotRiU).
The 658 throttled users are the supplied November 3 audit count, not a fresh
production measurement. Recovery takes two uncached reads per expired legacy
throttle row, with seven quiet days between them; no batch migration is needed.
