# Batch allowance parking (SCA-2195)

Current `held / allowance_exhausted` GPU jobs enter `allowance_held` with
`merge_pending=false`. Every recording, immutable identity, attempt history,
policy snapshot and obligation remains. No expiry or deletion is added. A
previous sticky hold without a current decision never qualifies. Provider-STT,
fair-use, budget-only denials, allowed/decisionless retries and worker failures
keep their existing recovery.

## Readers, writers and sweeps

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
projection, and the UTC usage month (UTC day when the optional backfill day cap
is enabled). The daily signal prevents a re-parked day-cap refusal from waiting
until next month. Discovery may reoffer a still-capped row once per day; normal
admission still refuses it, without changing entitlement or allowance amounts.
This adds at most one generation recheck/release attempt per owner per day while
that cap is enabled; repeated large daily bursts need the same cost remeasurement
as other repeated generation bursts. Grant claims/extensions and starts, expiry
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
  --confirm-reviewed-rollout-go --max-pages 10000
```

Each page discovers at most 100 document IDs, rechecks every row transactionally,
and CAS-advances `<namespace>_migrations/allowance_parking_v1`. A crash can replay
one page; state-CAS prevents duplicate holds or counter increments. A failed
page does not advance progress. Re-run to resume. Completion resets the cursor,
allowing a subsequent pass to catch old-worker writes behind it. No user data,
audio, queues or entitlement authority is read by dry-run or printed by apply.

## Rollback and production acceptance

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
