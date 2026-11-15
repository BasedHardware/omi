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

Cuts 1 and 3 default on. Cuts 2 and 4 default off in code and have explicit false dev/prod CPU bindings:

- Admission records the already-read conversation end as `record_finished_at`
  for native recordings ended within 30 minutes. `RECORD_FRESH_MERGE_ENABLED`
  stamps all their siblings fresh only when explicitly true, including the first unit of a long capture.
  The existing fresh-first merge, predecessor chain, late-capture handling,
  provider backlog gate, privacy and sibling fences remain authoritative.
- `RECORD_NOTES_EAGER_ENABLED` is staged OFF. Off writes no completion-owner
  marker, creates no fallback and uses the main settle and delivery paths.
  The opt-in implementation must first prove lease-mode-off revision custody,
  reopened-record delivery safety, canonical holds and the paid-run bound.
  The lease-off producer revision is currently a known opt-in blocker.
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

With cuts 2 and 4 off there are no new queries, timers, scans, or shorter polling cadences: zero new
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


## Staged enablement after review (2026-11-15)

Only cuts 1 and 3 and stage instrumentation ship enabled. Turning notes off
ignores completion-owner markers during projection; already-created cut-2
producer maps are ignored by both consumers while off. Ordinary main settle
obligations carry no cut-2 producer map, never call that fence, and never gain
its deferral or dormancy outcome. Dormant receipt reuse drops retired producer
metadata. The dormant active-hold bug fix remains in place.

The sibling guard and bounded bypass are gated together behind cut 4. Off
returns before any predecessor lookup and never issues the new ready query;
main's existing merge selection and partial completion remain in effect.
Cuts 1 and 3 do not read either staged switch. Stage clocks still piggyback the
existing writes and retain the existing recording-end clock.

All four controls retain explicit bindings on dev/prod Cloud Run backend,
backend-integration, backend-sync, backend-sync-backfill and GKE backend-listen.
Dedicated GPU merge reads cut 4 only; its chart also binds that guard explicitly false. The helper flag
budget retains four owned exceptions and the seeded limit of 161. The lead
must verify every CPU/GPU merge writer has the sibling guard before enabling
cut 4, and prove lease-off intake through notes delivery, reopen safety and paid
run bounds before enabling cut 2. The revision must be snapshotted regardless
of token-lease mode, and custody reads must share the outbox claim transaction. Image-only listen rolls default both off when
unset; explicit live true values still require readback. No GPU image change.

The earlier 114-second arithmetic budget assumed eager notes. It does not apply
to tonight's staged configuration: main's first-summary deadline remains 120
seconds and refresh settle remains 600 seconds, plus holds and compute. There
is no new two-minute production acceptance claim.

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


Large size-rollover output sets are prepared in groups of at most 128 outbox
writes. A larger set checkpoints the prepared IDs on the already-read content
ledger (one extra checkpoint write per non-final group); ready result receipts
remain on the existing finish-discovery page. A restart continues with unprepared
outputs, never creating another version for prepared outputs. This keeps the
128-sibling completion and notes writes within Firestore's commit ceiling.
Single-output captures add no checkpoint write or additional read.


## Integration and staged enablement (2026-11-15)

Integration source is `lane/q12-integration` at `d0d81aba1875`, containing main
`8614ee4cad33`. The pending-job claim clears `record_intake_retry_at` and writes
the claim clock together. Deferral preserves a concurrent due-now seal wake;
otherwise its existing lease can become a certified retry only when both
`RECORD_SEAL_REPAIR_FRESH_ENABLED` and `BATCH_HELD_DEAD_LETTER_ENABLED` are on.

`RECORD_FRESH_MERGE_ENABLED=false` is explicit in dev/prod runtime overlays
for Cloud Run backend, backend-integration, backend-sync, backend-sync-backfill,
and GKE backend-listen. The dedicated GPU entrypoint does not import these four controls, so its unused chart bindings are removed.
The code default is off, including when GKE image-only rolls leave the variable absent. This is staged enablement: the GPU worker image
will not roll tonight, so no newly broadened fresh class may reach its old
merge writer. The union flag inventory is 291 declarations with the seeded
budget unchanged at 161 and four separately owned helper-backed exceptions;
no budget increase or combined rollback control is needed.

There are two live merge/commit implementations of the same source:

- All five CPU hosts call `start_serving_from_env` at `main.py:247`; the
  declared prod config enables its periodic serving loop on backend-integration
  only. API/worker batch RPC and provider callbacks can also construct the same
  `Serving`, which owns `OrderedMerge` and `Projector`
  (`utils/batch_pipeline/serving.py:91`, `:412`). Bind every potential reader,
  including disabled periodic hosts. These services currently consume
  `gcr.io/<compute-project>/backend`, built
  from `backend/Dockerfile`; role-specific image declarations are not proof
  that those separate role images serve traffic.
- `diarizer/batch_pipeline_runtime.py:259` builds `Pump` with a direct
  `Scheduler` and no projection callback. `pump.py:109` constructs its own
  `OrderedMerge`, committing directly to Firestore. Its image is
  `gcr.io/<compute-project>/batch-pipeline-worker`, built from
  `backend/diarizer/Dockerfile.batch-pipeline`; all L4/T4/Spot/borrow variants
  and every supervised child process share that image.

Cut 2 (complete-record notes dispatch) and cut 3 (bounded projection follow-up
wake) run only through CPU `Projector`/`ProjectionStore`/owner drains. The
dedicated GPU pump has neither a projector nor an `on_committed` callback.
They remain enabled in CPU configuration, as does cut 1 (intake due-now guard);
unused worker bindings are harmless and retained for uniform rollback. The
independent seal-repair/sweeper deployments also consume the batch-worker image
from the same chart; a CPU backend roll does not update their code. Keep their
existing image tonight rather than silently crossing the worker-image restriction.
Long
records outside the existing unit-based 600-second fresh class do not gain
cut 4 tonight. Notes eager eligibility still requires the existing fresh class.

Before any later enablement, qualify a worker image built from a commit
containing `_record_sibling_pending` and its common commit-path call, and run
`test_record_seal_latency.py` and `test_record_complete_notes.py` against that
source/image. Read back build provenance/source SHA for each immutable digest.
Then list every running worker pod (including fallback/Spot/borrow variants),
its declared image AND `status.containerStatuses[].imageID`, and exported
`BATCH_PIPELINE_WORKER_RELEASE`; all must resolve to the qualified digest/source
with the guard. Do the corresponding readback for every traffic-receiving
Cloud Run revision (traffic percentages, revision image and
`OMI_BACKEND_RELEASE_SHA`) and every backend-listen pod. A service spec or the
newest revision alone is insufficient. Keep stamping false while any old
merge writer remains; chart rendering here is not that runtime proof.

Only after that readback, flip `RECORD_FRESH_MERGE_ENABLED` to `'true'` in
both runtime overlays (all five CPU hosts per stage), both backend-listen env
lists. The GPU runtime has no admission switch; its guard-qualified image is
still required before CPU stamping can be enabled. Regenerate `runtime_env.yaml`,
deploy the admitted CPU configuration, and read back every CPU revision/pod env.
Rollback is the same values to false; already stamped jobs retain their class,
so the sibling guard must remain deployed when disabling.

### #25311 clocks

#25311 (`4566cfb42aaf`) is the client half only. Its payload sends
`last_speech_at`, `end_decided_at`, `sent_at`, and `pending_wals` to
`/v2/sync-capture-end` (`app/lib/backend/http/api/capture_end.dart:25-34`).
The reporter is observational and never seals or uploads
(`app/lib/services/capture/capture_end.dart:111-117`). At this integration
head there is no server `/v2/sync-capture-end` route or watermark reader; the
server half #25309 is not present. It therefore changes none of this lane's
`finished_at`, recording recency, ledger `end_at`, or `home_ready_at` clocks.
Admission reuses the existing conversation `finished_at` as
`job.record_finished_at` (`database/batch_pipeline_intake.py:193`) so no
parallel end timestamp is introduced. `record_sealed_at` measures the actual
server barrier closure, not the client end decision. The existing ledger
`home_ready_at` defaults to the NOTED transition time
(`database/pipeline_ledger.py:246`); it is reused for that availability clock.
The Home histogram uses existing `notes_written_at` and observes the first
READY read per process/revision, a different event that includes request idle
time and excludes client rendering. No new Firestore read or document write
is added for these clocks. The ledger admitted_at clock is capture admission
(CAPTURING), before post-seal staging; it cannot substitute for a real intake
claim or ready timestamp. The first GPU lease field will remain absent on the
unrolled old worker, so ready-to-lease measurement needs its later qualified roll.

Image-only GKE rollout safety: `RECORD_FRESH_MERGE_ENABLED` defaults off in
code as well as explicit dev/prod bindings. An absent environment variable on
backend-listen cannot enable fresh stamping. Cuts 1–3 default on. No safety
condition depends on applying a chart. Ramp only after image/source readbacks
prove every CPU and GPU merge writer has the sibling guard; the lead then sets
`RECORD_FRESH_MERGE_ENABLED=true` explicitly across all admission readers.
Cloud Run continues to receive the rendered false binding.

Cross-service deploy readers use the recognized `default_on` helper name
for cuts 1–3. This preserves runtime defaults and lets the deploy contract
verify the actual reader on every bound host; no known-gap exception is used.

## Reviewed delivery fences (2026-11-15)

Native completion-owned notes persist their source capture and admitted upload
revision on the existing outbox row. At delivery, after privacy admission and
before leasing or any paid callback, the source must still be sealed, have no
upload sessions, and match the projected revision. Reopening and resealing
without projecting the new revision cannot buy notes. The existing task/outbox
re-arm uses its existing 120-second cadence, bounded at the obligation's
first_pending_at + MAX_HOLD_SECONDS (3600). If custody never clears, the outbox
parks dormant and the lifecycle ledger records failed:timeout in its independent
fenced transaction; a new real projection can reopen the obligation. This adds
one source document read per source capture per due delivery (at most 30
scheduled checks per hour-long first-summary episode, excluding transport
retries), plus the normal ledger write on timeout. No additional poller exists.
Main's older settle callback also lacks a producer-barrier delivery check; this
change closes that pre-existing gap for the new completion-owned obligations.

A dormant receipt's retired hold cannot supply a None settle deadline. Active
canonical holds move refresh wakes to their absolute deadline and carry sync
or merge hold provenance into the consumer, so an arrival after completion
can defer again before paid work without restarting quiet.

The sibling guard remains active with fresh stamping off, protecting already
admitted classes. It reuses the existing partial-projection terminal-held
classification; recoverable siblings still wait, but a bounded ready-head
probe lets independent recordings pass their group. The probe uses the
existing ready-head index, at most 160 result rows plus predecessor reads per
blocked-group attempt, and runs only on that exceptional path. No healthy-path
query or recurrent polling is added. At $0.51/million reads, 30 producer checks
cost $0.0000153 per source/output; the blocked-group probe's actual count
depends on the returned page and predecessor set.

The current enrichment consumer and retained sync-task adapter share this
producer-admission rule. Redirect custody transfers union all source fences
without renewing first_pending_at, so changing dispatch route or canonical
conversation cannot drop the delivery check.
