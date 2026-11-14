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
At measurement time seal, intake-claim, actual-ready and first-lease timestamps were not persisted;
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


## FIX-FIRST corrections (2026-11-14)

The fresh head-wait bypass now checks all earlier siblings in the same immutable
native-record binding inside the committing transaction. A later ready sibling
cannot commit until each predecessor is committed; unrelated older stock can
still be passed through the existing fresh-first machinery. The check covers
both transactional and fallback fresh selection and recovery release.

Notes dispatch is owned by recording completion, after every sibling projection
receipt is ready. Admission stamps that durable owner on every recent full-record
sibling; an unstamped in-flight binding gets a one-time ledger upgrade on its
first eligible receipt. Aging out or changing the urgency switch cannot return
later siblings to per-unit dispatch. Completion replay creates no new outbox
revision. Applicable producer, processing, sync and merge holds retain settle.
The normal one-conversation recording creates one automatic notes obligation,
even with 128 units: zero extra notes runs from sibling count. A true size
rollover into K distinct conversations requires K obligations, one per output,
prepared before any outbox writes. Model/tool turns and provider/empty-output
retries within those runs retain existing budgets; this change does not claim
an absolute cap on all paid model calls for a recording.

All four independent controls have rendered true/false bindings on both dev
and prod CPU serving hosts and the dedicated worker chart. The helper flag
budget adds four owned registry exceptions reviewed by 2026-12-14, leaving the
seeded budget at 161. The worker must include the unconditional sibling guard
before the fresh-classification change activates on CPU hosts; no GPU image
change or deployment is authorized in this lane.

New measurement fields and their write costs:

| Field/metric | Existing operation | Additional reads | Additional document writes |
| --- | --- | ---: | ---: |
| `record_sealed_at` | Conversation closure patch on pusher, repair, orphan registration | 0 | 0 |
| `record_intake_claimed_at` | Existing pending-job claim; copied to admitted siblings | 0 | 0 |
| `record_ready_at` | Existing staged-unit admission write | 0 | 0 |
| `record_first_leased_at` | Existing first GPU lease write | 0 | 0 |
| `omi_record_notes_to_home_read_seconds` | Existing Home list row projection | 0 | 0 |

Home uses the existing `notes_written_at` field in the same list projection.
The histogram is first observation per process/revision with bounded local
cache, not unique globally and not client screen paint. No synthetic historic
seal timestamps are backfilled. Seal and claim may overlap if a seal lands
while a claim is in flight; such samples are overlapping intervals.

The sibling correctness guard adds at most i predecessor-job reads for unit i
(zero for a single-unit capture); a full N-unit commit sequence has at most
N(N-1)/2 such reads, excluding retries/refused probes. At N=128 this is 8,128
reads, $0.00414528 at $0.51/million. Per-hour cost is $0.00000051 times the
actual extra reads/hour, not a newly recurring poll. Refused later-unit probes
stop at the first uncommitted predecessor. Notes completion replaces per-unit
outbox mutations with one per canonical output. A legacy unstamped binding's
one-time owner upgrade adds one ledger write, no read; new admissions add none.
Instrumentation itself adds zero periodic reads/hour and zero document writes.
