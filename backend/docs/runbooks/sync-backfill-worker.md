# Backfill pull workers (dark)

The owner/epoch registry chooses one execution drive. Cloud Tasks and pull
workers race the same owner transaction before either acquires the existing
Redis run lock. A pull winner has an unguessable worker token: task begin,
renewal and completion cannot mutate it. Expired workers cannot renew or
complete. Redrive advances the epoch and removes worker eligibility so the
Cloud Tasks fallback owns recovery. Redis's 1800-second token fence still
protects pipeline writes and slow executor leaves after cancellation.

`SYNC_BACKFILL_WORKER_PERCENT` defaults to `0`, and zero claims read no
persistence. Heartbeat/complete/fail remain available for accepted leases
after rollback. Claim also requires the sequencer enabled, active ledger
fencing, an explicitly worker-eligible backfill payload, and legacy dispatch
allowed for the account. Existing payloads are ineligible.

The private RPCs `/v2/sync-jobs/claim`, `/heartbeat`, `/complete`, `/fail`
use `SYNC_BACKFILL_WORKER_AUDIENCE` and
`SYNC_BACKFILL_WORKER_SERVICE_ACCOUNT`, with the existing OIDC verifier.
Completion rechecks terminal Redis state. Failure hands work to the sweep
only after the run lock is absent; uncertain cancellation retains the lock
and falls back after the unchanged silence TTL. A fail is never an audio
failure or permission to delete custody.

## Ramp and rollback

This PR ships dark. No production activation is part of it. After the idle
fleet and staging kit qualify, infracost owns expansion with lead approval:
synthetic/allowlisted accounts, then stable SHA-256 account cohorts at 5%,
25%, 50%, 100%. Soak at least 24h at 5% and 25%. Require zero lost speech,
zero `delivery/nonterminal_ack`, partial failure no worse than the flag-off
baseline (~5%), and no oldest-wait/depth regression at equal admission rate.
Measure node-hours versus displaced Cloud Run container-hours; savings are
estimates until that receipt exists. Review activation or continued darkness
by 2026-11-09; infracost reports any unexpanded flag as a blocker then.

Rollback: percent 0 closes intake; accepted workers finish under their
existing leases. Cloud Tasks enqueue and the sequencer sweep remain live.
Do not shorten either 1800s lease, mutate batch admission, or change ops pins.
Production and shared-data dev runtimes cannot be used as a staging sandbox:
the existing sequencer is production-stage only. A staging window must use
an isolated data plane and synthetic accounts before exercising this protocol.
