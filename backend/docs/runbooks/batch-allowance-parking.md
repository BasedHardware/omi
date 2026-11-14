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
operator migration uses the same CAS helper. `allowance_holds` stores one
owner-keyed generation, active count, claim and release cursor. The backend
maintenance leader checks at most 20 owners per 30 seconds; each owner is due
no more often than five minutes when caught up. Under a large owner population,
the bounded due queue adds latency (about 55 minutes for 2,202 continuously
held owners with one leader at this rate). There is no per-recording poll.

The generation hashes the stored subscription, validity at its period end and
the UTC usage month. A metadata read detects changes from every subscription
writer, including referral/repair writers, without requiring each writer to
send a wake. Funded allowance is evaluated once per changed generation, with
unavailability retried rather than recorded as a denial. A successful change
releases existing rows in `(capture_at, segment_id)` order in pages of 100;
each transaction appends through the existing scheduler and still requires
ordinary admission before compute. A new refusal during the pass stays parked
until the next generation. The durable cursor and claim survive restart and
prevent overlapping controllers from releasing twice. Empty owners retire.

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
  COUNT, never per-row or per-scrape queries. The census registry declares this
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
mode adds the indexes in migration 0007.

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
