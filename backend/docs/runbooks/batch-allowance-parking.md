# Batch allowance parking (SCA-2195)

Current `held / allowance_exhausted` GPU jobs enter `allowance_held` with
`merge_pending=false`. Every recording, immutable identity, attempt history,
policy snapshot and obligation remains. No expiry or deletion is added. A
previous sticky hold without a current decision never qualifies. Provider-STT,
fair-use, budget-only denials, allowed/decisionless retries and worker failures
keep their existing recovery.

## Readers, writers and sweeps

Sync upload intake can establish a monthly allowance refusal after it has
selected the Omi-funded GPU route. The bounded probe uses the same batch-funded
resolver with an already verified monthly usage total. An unavailable total,
budget denial or ambiguous decision leaves the upload on the ordinary worker
path. Sync upload enforces the independent Unlimited V2 backfill day cap. The
admission transaction rechecks the release cursor and usage period before
inserting the job and owner's held count together.
New holds have no ready-queue link, so workers predating SCA-2195 cannot lease
them. Observe committed uploads with
`omi_stt_cap_dispatch_decisions_total{path="batch_intake",outcome="held",reason="allowance_exhausted"}`.
The `batch_allowance_intake` log also records the number of parked units per
commit.

`Scheduler.defer` (GPU worker and backend) parks new refusals transactionally;
`Scheduler.recover` (both services) parks old-worker retry decisions. The
operator migration and scheduler use the same CAS helper in
`database/batch_pipeline_allowance_hold.py`; the backend controller depends on
that persistence layer and the scheduler, with no reverse import or cycle. `allowance_holds` stores one
owner-keyed generation, active count, claim and release cursor. The backend
maintenance leader checks at most 20 owners per 30 seconds; each owner is due
no more often than five minutes when caught up. Under a large owner population,
the bounded due queue adds latency (about 55 minutes for 2,202 continuously
held owners with one leader at this rate). There is no per-recording poll.

The generation reads both the commercial subscription and
`referral_campaign_grant`. It hashes commercial authority/validity, campaign
enablement, the grant fields admission consumes, the shared effective plan
projection, and the UTC usage month. Grant claims/extensions and starts, expiry
or paid-coverage time boundaries therefore change discovery even without a
commercial write. Other usage counters and profile fields do not. This uses
`effective_subscription_payload`, the same promotion composition as admission;
it does not introduce an entitlement rule or require writers to send a wake. Funded allowance is evaluated once per changed generation, with
unavailability and invalid usage retried rather than recorded as a denial. A successful change
releases existing rows in `(capture_at, segment_id)` order in pages of 100;
each transaction appends through the existing scheduler and still requires
ordinary admission before compute. A new refusal during the pass stays parked
until the next generation. The durable cursor and claim survive restart and
prevent overlapping controllers from releasing twice. Empty owners retire;
conversation purges decrement the held count in the same transaction as job
deletion and refresh the shadow. A repeated purge cannot decrement it again.

Changed query membership:

- Generic retry recovery: new holds no longer match `state=retry`; recovery
  recognizes current holds written by an older worker before requeueing them.
- All pending predecessor, fresh selection and queue-age queries: parked jobs
  leave `merge_pending=true`, so even old readers cannot walk them or block a
  later entitled result. Result-log and projection predecessor fences remain.
- Retry-age samples: parking moves any historical `retry_started_at` out of
  the live index, preserving it as `allowance_retry_started_at` for restoration.
- Timeliness active/uncommitted state lists exclude `allowance_held`. Its
  separate `omi_batch_allowance_held_units` gauge uses an hourly leader-only
  COUNT, never per-row or per-scrape queries. Cloud Run GMP and both dev/prod
  Prometheus bridge allowlists export the gauge; the release must carry that
  monitoring wiring as well as the application image. The census registry declares this
  as held stock without a late-work alarm.
- Privacy revocation accepts parked jobs if release encounters a fence. Account
  erasure includes the new owner index and the Postgres shadow copy.

Deliberately unchanged: projection assignment/finish/follow-up and privacy
projection walks query **result receipts**, which an allowance-held job has
never produced; no held job enters those indexes. Quarantine/dead-letter,
provider/vendor, record-pending, input-retention and artifact-cleanup sweeps
retain their own state predicates. Explicit privacy erasure still visits all
an owner's recordings, including policy holds; parking never hides data from
deletion requested by the user. No fresh-picker or metered-provider-release
branch is changed.

## Migration and mixed versions

The release owner creates the registered Firestore indexes as step 0 and
verifies READY. Obtain rollout go before the first default-on deployment: new recovery
already parks old retries incrementally. Deploy the backend release controller
first, then every GPU
worker that writes refusals. Old workers still write retry and new recovery
parks them. Old stores/readers ignore the new state and see
`merge_pending=false`; they cannot accidentally lease, publish or expire it.
A new worker with an old backend retains the held recording until the backend
controller is upgraded. Do not revert all controllers while parked stock
exists. The new table is mirrored and included in owner purge; Postgres doc
mode adds the indexes in migration 0008; the merged owner cursor owns 0007.

Dry-run (ro-prod; all output is counts, no document scan or checkpoint write):

```sh
python backend/scripts/batch_pipeline_allowance_migration.py --stage prod --dry-run
```

`allowance_retry` is a candidate count: migration additionally refuses rows
with a live token/lease, existing result or provider route. After independent
review and the rollout lead's explicit go, the **release owner** applies with
prod-operator:

```sh
python backend/scripts/batch_pipeline_allowance_migration.py --stage prod --apply \
  --confirm-reviewed-rollout-go --max-pages 10000 \
  --concurrency 32 --max-rows-per-second 50
```

Run **one driver process only**, after stopping/waiting for any earlier driver.
`--concurrency` defaults to 1 (the original sequential path), accepts 1..32, and
limits concurrent owner groups. Within each page, rows sharing `owner_key` run
in document-ID order, including commit; different owners can finish out of order.
The shared DB executor can impose a lower worker ceiling if configured below 32.
`--max-rows-per-second` defaults to unlimited; a positive finite value sets a
single process-wide token bucket shared across pages and workers. Every row
transaction **attempt**, including SDK/contention retries and fenced/no-op rows,
takes a token before BeginTransaction, so low rates never wait with a transaction
open. Capacity is one token: at 50/s it spaces permits
by at least 20 ms and does not accumulate an idle/page burst. Already permitted
in-flight attempts can finish together; checkpoint transactions and individual
document reads are not row attempts and are outside this rate. Never multiply
the limit by running another driver. Stop on any unexpected error; in-flight
transactions drain, no new rows start, and the failed page is not checkpointed.
The stop line is `{"errors": N, "error_type": ..., "retryable": ...}`, plus
`cause_types` for the explicit cause chain (`__cause__`, and `RetryError.cause`) and `sibling_types` when other
concurrent owner groups also failed on that page. It names only exception
classes, never a message, which can name documents. `retryable: true` means
every failure on the page, through its whole cause chain, is a transient
Firestore/RPC class (Aborted, DeadlineExceeded, InternalServerError,
ResourceExhausted, ServiceUnavailable, an expired transaction), exhausted
transaction contention, or `MigrationOwnerChanged` (a discovery hint went stale
before that row was parked), and no link in any chain is a fatal RPC status such as PermissionDenied or NotFound. Because the failed page is replayed idempotently,
the release owner may relaunch such a stop from the retained checkpoint under
the standing recovery disposition on SCA-2198. Any other stop stays stopped for
the tool owner.

Each page discovers at most 100 candidate rows, rechecks every row transactionally,
and CAS-advances `<namespace>_migrations/allowance_parking_v1`. A crash can replay
one page; state-CAS prevents duplicate holds or counter increments. A failed
page does not advance progress. Re-run to resume. Completion resets the cursor,
allowing a subsequent pass to catch old-worker writes behind it. No user data,
audio, queues or entitlement authority is read by dry-run or printed by apply.
The concurrent discovery projection includes only `owner_key`; the candidate
filters, document-ID ordering, cursor and 100-row bound are unchanged. This key
is a scheduling hint, verified against the job inside every transaction attempt.
An owner mismatch fails the page before parking that row. The progress document
is written only after **every** row has finished; the CAS detects a competing
driver but is not permission to operate multiple drivers.

### Migration latency and completion planning

Release-owner production canary, started **2026-11-17T04:37Z**: approximately
400 rows in six minutes, reported **1.16 rows/s**, zero fenced and zero errors.
This is the supplied production baseline, not a new measurement of this change.
The supplied candidate stock was 1,264,556 rows; refresh count-only aggregates
before applying. At 1.16 rows/s that stock needs about **12.6 days**.

For an eligible row with no conversation and uncached live privacy checks:

| Operation | Sequential RPCs | Concurrent RPCs |
| --- | ---: | ---: |
| BeginTransaction | 1 | 1 |
| Read job and allowance-owner bookkeeping | 2 | 1 BatchGet (same two documents) |
| Privacy: account deletion, user, privacy generation | 3 | 3 |
| Commit job + allowance-owner writes atomically | 1 | 1 |
| Total per successful attempt | 7 | 6 |

Each distinct conversation/redirect hop adds its existing tombstone and
conversation reads. Cache/shadow levers, retries, SDK read retries and competing
controllers can change these counts. Page discovery adds one billed read per
candidate; page progress read, query and transactional checkpoint add about five
amortized RPCs per page. BatchGet removes one network round trip, **not** a billed
document read. The privacy decision is still checked at each row's commit fence;
never reuse a per-owner decision across transactions. The owner hold document's
`revision` and `held_count` writes make within-owner concurrency counterproductive.

The 0.862 s/row baseline does not contain an RPC latency trace. Assuming all seven
RPCs have equal latency, batching predicts 0.739 s/row. With 100-row page barriers,
distinct owners, no retries, and five page RPCs at the same assumed latency:

| Concurrency | Row-only ceiling (rows/s) | Including modeled page RPCs (rows/s) |
| --- | ---: | ---: |
| 8 | 10.4 | 9.8 |
| 16 | 19.3 | 17.3 |
| 32 | 33.8 | 28.0 |

These are planning estimates, **not sustained production results**. Faster page
RPCs could reach 30..34/s at 32 owners; the supplied baseline alone cannot establish
the 30/s target. Measure a bounded canary at 8, 16, then 32, with the rate ceiling
kept at 50 throughout. Owner skew, longer privacy chains, transaction retries,
client-to-database latency and page barriers can reduce throughput. If the
32-owner canary stays below 30/s, use a release-owner-approved runner nearer the
database or return measured RPC timings to the rollout lead; do not raise the
concurrency/rate bounds or weaken fences. The one-owner bound is still roughly
one row's latency per commit.

At measured sustained 30/s, 1,264,556 rows take **11 h 43 m**; at 50/s, **7 h 2 m**.
The existing `--max-pages 10000` cap covers at most one million candidates per
invocation. Run the command above, then resume with the same command if its last
report has `complete: false`; the stock needs approximately 12,646 pages in total,
so normally two sequential invocations. Never overlap them. Printouts remain only
examined/parked/fenced/complete counts. Runtime rollback: stop the driver, wait
for it to exit, and resume with `--concurrency 1` and the same rate ceiling. Keep
the durable progress document; do not undo safely parked rows to roll back speed.
No saving is claimed by this tool change or its synthetic/emulator tests.

## Rollback and production acceptance

Set `BATCH_ALLOWANCE_INTAKE_PARK_ENABLED=off` on upload-serving roles to stop
new intake holds. Existing holds still release and newly refused jobs still
park through the worker and recovery paths. For rollback past the original
parking protocol, turn intake parking off before disabling the controller
and worker parking below. Keep the parking-aware controller until held stock
drains.

Kill switch: `BATCH_ALLOWANCE_PARK_ENABLED=off` on **backend-integration and
every GPU worker**, read live per transition; unset/on keeps parking enabled.
The controller returns existing holds to their former `retry` path in bounded
100-row ticks, restoring `merge_pending` and the saved retry clock. This is a
deliberate gradual rollback (at most 12,000 rows/hour with 30-second ticks), not
an instant million-row requeue. Keep a new controller deployed until the
`allowance_held` count reaches zero, then old code is safe. Partial fleet rollback
can repark refusals on hosts still on; verify the switch on all writers.

Never enable `BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED`. No GPU capacity,
allowance amounts or funding rules change. No production migration has been
authorized by the command's existence.

The release owner records merged SHA, indexes, serving revisions on both planes,
migration counts and automatic release of an entitled test owner's holds. The
Firestore cost owner records matched full-day before/after reads per completed
audio-hour, over-SLA counts and requeues on SCA-2173. Compare the new held gauge
and census separately from lateness; a lower late-work count alone is not
evidence of processing. `job:batch_allowance_hold:tick` attributes controller
reads. SCA-2015 owns the residual fresh-selection defects.

## Read planning envelope (round-1 correction)

The prior 606-read release-page / <7M-day declaration understated queue-tail
and privacy reads. It is withdrawn. Tests exercise the actual
`FirestoreTransaction`, scheduler and flush on the strict document fixture:

| Path | No conversation | One conversation | Two redirects |
| --- | ---: | ---: | ---: |
| Release into an existing queue (distinct held/tail conversations) | 9 | 16 | 24 |
| Migration parking | 6 | 8 | 12 |

Counts include one discovery read per row. Release reads owner, job, control,
queue and tail, then privacy for **each distinct job identity**, not just the
released job. Conversation tombstones and redirect targets add reads. These
are synthetic source-derived measurements, not production billing evidence.

The revised planning reserve is **64 reads per released or migrated row**:
up to two attempts (one retry), short redirects (up to two per source in the
tested profiles) and shadow refresh. A release page of 100 plans 6,406 reads,
including controller metadata overhead. A 1M-row generation burst plus at most
691,200 owner metadata reads across prod/dev plans **<65M reads/day**. A separate
1M-row migration pass plans **64M reads**. If both occur together, disclose the
combined **<129M-read** planning envelope before go. Unchanged owners incur
only metadata polls; held recordings are not walked.

This is planning headroom, **not an enforced maximum**: the privacy fence can
follow up to 256 documents, and SDK/contention retries, shadow settings, repeated
passes or repeated generation bursts can cost more. The rollout lead must
accept the revised envelope alongside latency and rollback pacing before the
first default-on deployment or migration. Longer redirect chains, more than
two attempts or extra passes require remeasurement and budget revision; do not
use the earlier <7M declaration as release approval. Measure actual attributed
reads on SCA-2173 and retain count-only output. These reserves cover the new
parking/release state transactions; the existing funded-allowance usage-ledger
read once per changed generation and subsequent normal admission/projection
work remain separate measured workloads, not zero-cost operations.
