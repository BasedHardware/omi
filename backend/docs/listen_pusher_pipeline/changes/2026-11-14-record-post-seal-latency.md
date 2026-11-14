# Recent sealed recording delivery

Q12-J measures and changes the path after the recording seal. The source base
is `64797fe8b5a55b592dff17833a112e2904dde8d0`. No deployment or GPU image
change is part of this lane.

The 2026-11-14 21:38Z read-only cohort queried 23,696 job metadata rows admitted
after 21:10Z and selected recordings whose captured unit ended after 21:10Z.
It contains 259 native record units, plus 248 still-pending record obligations.
Completed units took p50/p90 12.51/22.42 seconds from intake's start timestamp
to GPU completion (192 units), 59.93/171.00 seconds from completion to ordered
merge (166), and 24.37/43.27 seconds from merge to projection (165). These are
unit-weighted completed-stage distributions, not an uncensored end-to-end SLO.
Seal, intake-claim, actual-ready and first-lease timestamps are not persisted;
those intervals cannot be separated honestly. `timing_store` identifies the
audio clock domain, not a timing trace. The consenting owner had no recordings
ending after the cutoff and no ledger transitions in that window.

Changes, all default on with explicit kill switches:

- Admission records the already-read conversation end as `record_finished_at`
  for native recordings ended within 30 minutes. `RECORD_FRESH_MERGE_ENABLED`
  stamps all their siblings fresh, including the first unit of a long capture.
  The existing fresh-first merge, predecessor chain, late-capture handling,
  provider backlog gate, privacy and sibling fences remain authoritative.
- `RECORD_NOTES_EAGER_ENABLED` enqueues recent, non-partial native record notes
  immediately and brings an existing later obligation forward through the
  outbox's existing `min` coalescing. The previous 600-second settle is already
  clipped to 120 seconds for first-summary debt; refreshes retain 600 seconds.
  Consumer-side processing holds, existing leases and revision fences still
  decide whether processing may run.
- `RECORD_FOLLOWUP_WAKE_ENABLED` hands a successfully projected, recent,
  single-unit native recording directly to the existing bounded follow-up
  slots. It does not wait for another discovery sweep. Multipart, partial and
  older recordings retain the prior discovery policy. Failure retains the
  owed hint and durable receipt; successful queueing removes the duplicate hint.
- `RECORD_SEAL_WAKE_PRESERVED_ENABLED` prevents a failed intake attempt from
  overwriting a seal's concurrent due-now wake with its stale barrier retry.
  It does not shorten a lease or retry a privacy-fenced row.

All four accept false/off/0/no as rollback. Turning off fresh classification
only affects new admissions; already-stamped jobs keep their immutable class.
See the [post-seal scheduling contract](../../listen_pusher_pipeline.mdx#recent-record-post-seal-scheduling).

There are no new queries, timers, scans, or shorter polling cadences: zero new
periodic Firestore reads/hour. The same reads/writes perform admission and
follow-up processing earlier. Moving an existing outbox obligation earlier can
leave its old task to fail its existing stale-token checks; the net production
read delta from those deliveries has not been measured. At $0.51/million reads,
1,000 additional such reads/hour would cost $0.00051/hour. Backlog discovery and
quiet-window policy remain unchanged.

The live GPU worker commits directly to Firestore. The serving completion RPC
is not its publication path, so an RPC wake would not eliminate the observed
24/43-second projection-discovery delay. A direct post-commit wake needs a
separately authorized worker change; reducing global polls would increase
backlog read cost. Existing fresh heads can still impose the 60-second head
wait. The baseline fresh-stamped cohort still had completion-to-merge p50/p90
39.90/164.04 seconds; freshness alone is not a tail-latency guarantee.

A planning budget using median observations is approximately 114 seconds after
seal: 10 seconds intake polling, 12.5 seconds combined staging/queue/GPU,
39.9 seconds merge, 24.4 seconds projection, 2 seconds targeted follow-up,
25.4 seconds notes model time. It excludes unmeasured notes dispatch/other
processing and Home/client visibility. The model-time estimate is the fleet
notes-agent histogram, not a record-cohort measurement. Thus two-minute
production delivery remains unverified, with about six seconds of nominal
headroom before those unmeasured components. Summing the corresponding p90
stage budgets gives about 299 seconds before those components; that sum is
not an end-to-end p90.

Evidence and reproducible queries live in the owning workspace run
`data/run-2026-11-15-quality-12h/q12j-evidence/`. Regression tests use synthetic
accounts and strict transaction ordering; the owner-drain suite exercises the
actual projection walk, bounded scheduler and follow-up handoff.
