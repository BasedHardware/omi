# Daily-summary cadence and recipient reads

`notifications-job` selects only owners whose `daily_summary_enabled == True`,
`daily_summary_hour_local == H`, and `time_zone IN chunk` match the local hour
computed from one UTC instant and tzdata. The composite is
`DAILY_SUMMARY_RECIPIENTS_QUERY` in `database/firestore_index_registry.py`.
No new index or user-data backfill is required for the cadence change.

The production Scheduler manifest previously declared `*/1 * * * *`, even
though the backend guide called the job hourly. The managed trigger now fires
at `*/15 * * * *`: **96 scheduled executions/day**. Quarter-hour ticks cover
local HH:00 in quarter-/half-hour-offset zones; hourly UTC ticks could be up
to 45 minutes late. Extra ticks also resume budget-deferred work. The minute
schedule was 1,440 nominal executions/day; the incident's Monitoring metric
reported 45,755 successes/30 days (1,525/day). That excess is not explained by
task retries and should be compared with Scheduler/audit execution counts.

## Delivery and bounded catch-up

- Recipient queries read due user documents without traversing FCM tokens.
  They retain the legacy token from that selected document; deferred lookup
  reads only the token subcollection, including when the legacy field is absent.
  Tokens are resolved only after the per-user/day lock, existing-record and
  usable-conversation guards succeed, before generation/persistence. Token
  lookup failure releases the lock and leaves no undeliverable stored record.
  Tokenless owners still get a recap and webhook.
- The cursor stores the cohort's UTC instant along with local hour and UID.
  An unfinished cohort resumes its original timezone selection and display
  date before the current cohort. The existing noon split remains unchanged:
  morning delivery summarizes the previous local day.
- A query failure propagates to the cohort coordinator and retains the cursor.
  Failed/timed-out recipients also retain the original cohort across local-hour
  boundaries, even after later batches checkpoint progress. Generation errors
  release the owned day lock. Failed pushes retain a delivery-retry marker:
  retry the stored recap without regenerating it, while ordinary repeat ticks
  still suppress the push. Zero successful FCM sends count as a failed push;
  any FCM-accepted device send completes it to avoid repushing that notification.
  Timeouts before confirmed push handling are uncertain delivery outcomes and
  retry the saved recap. An in-process acknowledgement and a metadata-only
  `notification_delivery_completed` receipt are recorded before backfill/webhook
  work. Later errors/timeouts clear the push-retry flag; a late abandoned worker's
  persisted receipt overrides even a stale cursor's true flag. Tokenless skips
  also complete push handling. This adds one receipt write per completed attempt.
  Delivery retries choose **at-least-once attempts for uncertain outcomes** over
  at-most-once attempts that could silently lose a recap. A crash or failed
  receipt write after FCM accepts the send can still cause a duplicate on retry.
  FCM acknowledgement does not prove device receipt; this is neither an
  exactly-once guarantee nor an unconditional retry queue through Redis outages.
  A contended retry remains pending until its outstanding worker finishes.
  Successful timezone chunks still run. The run lock prevents concurrent
  notification sweeps; the per-user/day lock and durable existing-record check
  prevent repeat generation/push on subsequent ticks. Existing backfill creates
  historical records without sending historical pushes.
- Each cohort retains the existing 480-second budget and eight-user batches.
  A resumed cohort plus the current cohort can consume two such budgets. The
  run lock is 55 minutes; the live Cloud Run timeout was 3,600 seconds. Redis
  outage, worker timeout, persistent overload, and a crash between persistence
  and FCM delivery retain the existing best-effort delivery limitations. The
  two-hour cursor TTL is not a durable outage queue. Do not infer delivery
  success from Cloud Run exit success or the worker `succeeded` counter.
  A persistently incomplete saved cohort delays the current cohort until it
  completes; monitor pending recipients and completion alongside budget skips.

## Deploy after review

1. Merge through a PR with a merge commit. Dispatch
   `.github/workflows/gcp_notifications_job.yml` with `environment=prod` and
   `branch=<reviewed immutable merge SHA>`. It verifies Firestore index
   readiness, builds/smokes/pushes the notifications image, deploys the exact
   seven-character source SHA tag, then applies and checks **only**
   `notifications-job-scheduler-trigger` from the checked-out manifest.
2. Verify the deployed image/source SHA and a scoped GET-only check:
   `backend/scripts/scheduler_reconcile.py --environment prod --project
   based-hardware --check --jobs notifications-job-scheduler-trigger`.
   The trigger is an existing managed resource, not `lifecycle: planned`.
   The owner workflow cannot reconcile unrelated Scheduler entries.
   The trigger's OAuth identity is the dedicated
   `notifications-job-scheduler@` account (`roles/run.invoker` on
   `notifications-job` only). The workflow identity `omi-gha-notif-job-prod@`
   holds `roles/iam.serviceAccountUser` on that account and the custom
   `omiCiSchedulerJobUpdater` role (get/list/update only); without both, the
   reconcile step's PATCH returns 403 (2026-10-03).
3. The existing `.github/workflows/gcp_scheduler_reconcile.yml` also checks
   the full main manifest; production reconciliation requires its approval
   and typed confirmation. It is unnecessary for the scoped job shipment.
   Its full check resolves secret headers; a secret-free agent tier cannot
   complete that check. Use the scoped check above for this trigger.

## Verify cost and delivery

Watch `run.googleapis.com/job/completed_execution_count` for this job over a
complete UTC day (target about 96, plus explicitly identified extra triggers),
Scheduler attempt counts, and `run.googleapis.com/job/completed_task_attempt_count`
by result/attempt. Scheduler is at-least-once; a lock prevents overlap work,
not creation of the Cloud Run execution.

Aggregate these content-free log lines by Cloud Run execution:

- `daily_summary_recipient_reads`: actual returned user-document count,
  query count, `token_docs_read=0` for selection, and partial-query completion.
- `daily_summary_job_summary`: selected recipients, attempted query chunks,
  owner sweeps, failures, timeouts, budget skips and cohort completion. A
  catch-up execution can emit two summaries; do not count lines as executions.
- `daily_summary_delivery_token_read`: owners needing a new recap and token
  count. Tokens are never logged. Token counts are not billed document reads.

Steady selection is approximately **4N user-document reads/day**, where N is
schedule-enabled owners with a valid indexed timezone, plus empty-query minimums
and catch-up/retry reads. The minute schedule queried each due hour up to 60
times/day (60N without overlap suppression). Token reads now scale with owners
actually generating a recap rather than every selected owner. Generation,
conversation, backfill and webhook reads remain separate.

The incident's Oct 2 totals imply at least 1,581,792 selected owner documents
(1,304,089 attempted + 277,703 budget-skipped) over 666 summary lines. Scaling
that sample to 96 comparable completed cohorts gives roughly **228,000 selected
owner reads/day**, about **1.35 million fewer/day (86%)**. This is a scenario,
not a billed-read measurement: retries, multiple cohorts, partial reads,
overlap suppression and cohort sizes change the result. The platform Firestore
read metric is database-wide and cannot attribute reads to this job. Validate
savings with the new job counters and database totals after deployment, alongside
budget skips/timeouts and recap delivery health.

## Schedule fields

Timezone/preference writes atomically materialize absent enabled/hour defaults
(`True`, `22`), preserving explicit `False` and `0`. The historic one-time
`scripts/backfill_daily_summary_schedule_fields.py` provided the indexed-query
cutover; `DAILY_SUMMARY_SELECTION_MODE` and legacy/shadow selectors have since
been retired. This change requires no production user-document inspection or
mutation.
