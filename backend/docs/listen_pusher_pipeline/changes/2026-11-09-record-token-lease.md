# Producer custody token leases (Part A)

Contract: [record custody](../../../utils/batch_pipeline/CONTRACT.md#record_audio-custody-and-conversation).
Supersedes #24832: no completed-age exemption is retained. Its chart locations
and identity/status/boundary tests are adapted to three quiet lease clocks.

`RECORD_TOKEN_LEASE_MODE=off|shadow|serve` defaults off. Off performs no lease IO
and ignores inert fields. Shadow stamps/renews but only reports would-expire.
Serve uses the fresh `record-token-lease` uid salt and explicit
`RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT` (default 0). Unlike the older refactor
modes, shadow never serves, and serve still honors the percentage.

`RECORD_TOKEN_LEASE_SECONDS` defaults 3600 (bounded 1800–7200). Frame batches
renew at most once per lease/2 per conversation on receive and projection,
including queued drain batches after socket close. An async conversation lock
coalesces concurrent receive/projection renewals; custody appends renew before
admission, including memoized retry waits. No users.py or client-state changes.
A renewal outage returns retryable custody refusal; the phone retains WAL/audio.
`RECORD_TOKEN_LEASE_DEPLOYED_AT` is a fixed release epoch (pinned by the release owner with the shadow flip and
inherited by children), not process-start time. The Helm guard refuses an enabled
mode without that epoch; off keeps the inert default zero. Bind the same epoch
on every pusher/custody writer through runtime_env and on repair through
recordTokenLease.deployedAt, so late stock renewals compute the same lapse and
revision bump as repair. Identified legacy tokens use
max(finished_at, refusal, abandoned_at, job available_at, deployment epoch);
bare True and malformed tokens remain fenced. Missing epoch fails closed.

Dark deployment → shadow for **48h** → serve **1 → 10 → 50 → 100%**.
Lead2 approves every step; P4 auto-revert guards every step after a full clean
lookback. Retune at 10% from the signal-gap histogram using
clamp(3 × p99(gap), 1800, 7200). Before 100%, **RECORD_GAP_FILL_PERCENT >= 10**
is required on custody intake. Keep late-appends zero, oldest-unsealed falling,
and immediate reactivation churn absent. Roll back with mode shadow/off.
The new split alerts file is reviewable here; the lead must incorporate it into
the combined import after #24893, whose alert-rules.json is fenced in this lane.

Late signals before seal bump upload revision and re-fence; apply transactions
re-read the exact token map. Live custody leases override stale pod/abandon proof
because uploaders can outlive the pusher. Tail/partial/privacy gates still apply;
late bytes after seal remain retained and are counted for gap-fill/revert.
Part B discovery and indexes are unchanged. Land after #24866 rebase/merge.

Implementation review risk: the design's stock seed includes the job's current
`available_at`. The pending drainer advances that retry wake every minute, so
such stock can remain fenced indefinitely even with an old deployment epoch.
This lane preserves the written formula, including matching plan/apply anchor
reads. The lead must resolve whether post-deployment retry wakes should be
excluded before relying on stock drainage. No age-only escape is layered on.
