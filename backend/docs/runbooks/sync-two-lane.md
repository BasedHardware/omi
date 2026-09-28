# Two-lane offline sync

`backend-sync` is the upload admission service. It authoritatively classifies each homogeneous upload as:

- `fresh`: oldest capture time is at most `SYNC_FRESH_MAX_AGE_SECONDS` (default six hours). Jobs use `SYNC_TASKS_QUEUE`; inline is used only when Cloud Tasks is deliberately disabled or the request carries BYOK credentials.
- `backfill`: historical, missing, invalid, or future-skewed capture time. Jobs use `SYNC_BACKFILL_TASKS_QUEUE` and the `backend-sync-backfill` service. Backfill never falls back inline.

Capture timestamps are client assertions, so a well-formed device header alone never grants the fresh lane. For a server-created conversation on the same authenticated install, mobile first hashes the exact raw files and requests a short-lived server-signed manifest binding UID, device, conversation, filename timestamps, and SHA-256 identities. Admission verifies the signature and conversation window; after upload it verifies the bytes against the signed digests before dispatch. Uploads without that proof—including Transcribe Later and offline files—are conservative backfill. Missing, invalid, future, expired, or byte-mismatched claims cannot enter fresh.

A signed fresh manifest covers at most 20 files. Mobile detects a conversation with more than 20 pending fresh WALs before requesting a manifest and routes the whole conversation through backfill in three-file batches. It never claims one immutable fresh content set and strands the remainder behind a conflicting manifest.

Historical recovery defaults are a 30-day lookback and thirty globally concurrent Cloud Tasks dispatches capped at thirty per second. The processed-speech daily accounting caps remain available, but `SYNC_BACKFILL_ADMISSION_LIMITS=false` leaves them unenforced at upload admission. `SYNC_BACKFILL_INFLIGHT_LIMIT=false` is retired for v2: no Redis per-UID admission slot is acquired even if that setting changes. `SYNC_BACKFILL_UID_SEQUENCER=on` in dev/prod is the phase-two setting (2026-09-28); `off` is the kill switch, under which eligible uploads still receive 202 and newly accepted jobs dispatch directly through Cloud Tasks as after #19352. The new admission path writes a bounded per-UID direct-job marker before enqueue, and the new worker refreshes it when direct work starts. A later config PR turns the sequencer on after the phase-one drain gate. On mode persists each accepted job in Firestore and dispatches at most one worker job per UID. Queue concurrency is controlled by the shared `.github/actions/sync-backfill-lifecycle` composite.

Production deploys require `SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS` as a comma-separated list of Cloud Monitoring notification-channel resource names. The workflow provisions log-based metrics and routed alert policies at 70% and 90%, then verifies each policy has a notification channel before traffic shifts.

Backfill speech is written under the `sync_backfill` accounting source. Live hard restrictions read only `realtime` and `sync_fresh`. Existing lookback, BYOK, global capacity, and fair-use guards remain. No per-UID `backfill_paced` response is emitted by v2 admission. Mobile retains the WAL on a non-202 response and polls an accepted job normally; no client change is needed.

## Per-UID backfill dispatch

`sync_backfill_sequencer/{uid}` is a Firestore owner document with one active job, a monotonically advanced dispatch epoch while the owner exists, and a 30-minute renewable lease. Each waiting job is its own append-only `sync_backfill_pending/{job_id}` document with the complete Cloud Task payload. Admission reads the owner to avoid re-registering an already active job but writes only the new pending document; a burst for one UID does not serialize writes on the owner. Owner writes are limited to one claim and one release per job, plus a two-minute heartbeat while active. The pending and active payload maps are exempt from unqueried single-field indexes. Admission writes the job before 202; after a lost write acknowledgement it checks the registry. A confirmed write still returns 202, a confirmed absence cleans up and returns 503, and an unavailable verification fails the request while preserving the content claim and staged material for investigation. It never acknowledges 202 without a known registry write. One pending job is promoted transactionally and enqueued with a deterministic `job_id-s{epoch}` task name. The ordered oldest-pending query is inside the owner-claim transaction, so a newly admitted earlier capture cannot be missed by a separate preselection. Waiting jobs are selected oldest capture first, then Firestore document ID for ties. The mobile WAL sends recent batches first, so the first arrived batch can start immediately; oldest first applies among jobs already waiting and reduces cross-job conversation bridge work. It cannot reorder a job already running. Other UIDs dispatch independently into the same 30-slot global queue.

The worker checks the persisted job/epoch before any transcript work, renews its lease every two minutes, and releases ownership only after the Redis job is terminal or has expired. A stale delivery cannot enter the pipeline. Terminal success, failure, partial failure, duplicate delivery, dead-letter confirmation, and expired-job cleanup all converge through that release and a dispatch of the next waiting job. A retryable HTTP 409/500 keeps the owner; Cloud Tasks retries it. The existing per-job Redis run lock remains a second fence. Redis jobs persist `dispatch_mode=sequenced`, so polling does not mistake an intentionally waiting job for a lost direct Cloud Task; the worker's persisted retry count is reused after redrive rather than resetting the paid provider attempt budget. An old queued task without a sequencer epoch that reaches a new worker while the flag is on is marked sequenced, registered and acknowledged, then redelivered with an epoch. While the flag is off, a new worker also migrates a queued direct task if that UID still has a sequenced owner or pending record. This prevents new direct work from bypassing waiting sequenced jobs during rollback. Old Redis admission-slot keys are ignored.

On an off-to-on transition, the first sequenced dispatch waits 30 minutes, the maximum Redis run-lock lifetime and longer than the 25-minute task request deadline. This covers direct workers on old revisions, which cannot register their presence. New flag-off admissions also register a 30-minute per-UID Redis direct marker before enqueue; a direct worker renews it from actual task start so queue delay cannot shorten protection. A sequenced dispatch waits for that marker even while the flag is off, preserving already pending sequenced jobs through rollback. The mode key is reset by each flag-off admission, so an off-to-on transition repeats the global wait automatically in dev and prod. Admission still returns 202 and no HTTP worker waits for the guard. Each waiting UID receives a named delayed wake task on the existing sync queue; the OIDC-protected wake route calls `kick` at the deadline. `action=cutover_wait` logs at most once per UID per five minutes with `job_id`, HMAC `uid_hash`, and the known direct job ID; `action=cutover_direct_active` records observed direct processing during transition, while `action=cutover_overlap` requires a simultaneously active sequenced owner. An old revision that somehow continues receiving direct work more than 30 minutes after traffic promotion cannot be fenced by new code; treat an overlap event as a rollout fault. The guard adds a one-time 30-minute dispatch latency on each off-to-on transition and never changes paid STT submission policy.

The existing deploy lifecycle provisions `sync-backfill-uid-sequencer` in Cloud Scheduler every two minutes, targeting the OIDC-protected `/v2/sync-backfill-sequencer/sweep` on backend-sync. It uses the existing sync task invoker identity and audience. Each tick reads at most 100 due UID owners and 100 due pending documents. Pending documents are deferred five minutes when scanned, so a heavy UID cannot occupy every sweep page indefinitely; this recovers a crash between admission's durable write and immediate kick. Even with a continuous backlog, the pending scan/defer is bounded to 72,000 document reads and writes per day across the project; an empty queue incurs no pending-document writes. An active worker renews its lease, a lost dispatch is redriven after five minutes, and an expired running lease is redriven only after its Redis run lock is absent. The old task epoch then becomes stale. A terminal or expired Redis job is delivered once more for the existing cleanup path and the next job. A 12-hour waiting age emits an error event with `job_id` and HMAC `uid_hash` before the 24-hour Redis job and staged-blob expiry. The sweep should finish well within its 180-second Scheduler deadline. Registry documents have no TTL while work is pending. Normal admission, delayed cutover wakes, and terminal completion call `kick` directly, so jobs continue to make progress without Scheduler; only a process crash or uncertain/lost dispatch requires its reconciliation. Scheduler execution failure and missing sweep heartbeats route alerts separately.

### Two-phase rollout (dev, then prod)

1. Merge the implementation with `SYNC_BACKFILL_UID_SEQUENCER=off` in both runtime environments. The `firestore.indexes.json` main-branch push triggers `gcp_firestore_indexes.yml`; approve its production environment and wait for both `sync_backfill_pending` composite indexes to report `READY` in the data-plane project before deploying the Scheduler or code that queries them. Check the workflow's READY result and independently list the index metadata with `gcloud firestore indexes composite list --project=based-hardware --database='(default)' --filter=COLLECTION_GROUP:sync_backfill_pending --format='table(name,state)'`. The backend deploy's index check is read-only. Separately dispatch that workflow with operation `field-exemptions`, environment `prod`, and confirmation `APPLY_FIRESTORE_FIELD_EXEMPTIONS` to apply the pending/active payload exemptions; this has its own approval and is a cost gate, not a query-readiness gate.
2. Deploy the new code to dev, then prod, with the flag still `off` in both admission and worker services. Auto-dev also uses this off manifest. Confirm the release vector and projected runtime env on `backend-sync` and `backend-sync-backfill`. Eligible uploads still return 202; direct admission writes a Redis marker before enqueue, and direct workers refresh it from task start. The existing lifecycle action must create/verify the `sync-backfill-uid-sequencer` two-minute Scheduler job, its OIDC target/audience, the three sequencer alerts, and the existing budget/dispatch alerts. A same-name policy with a different condition filter, duration, or notification channels fails deployment; reconcile it before traffic promotion. In Cloud Logging, verify successful Scheduler executions and `action=sweep_summary outcome=done` heartbeats, with no Scheduler failure/absence alert.
3. Before the coordinator's separate phase-two config PR, prove the pre-phase-one revisions of **both** sync services have zero traffic and have had no `/v2/sync-jobs/run` requests for at least 30 minutes after their last request. Use the old revision names from the phase-one release vector in this drain query over a 30-minute window:

   ```text
   resource.type="cloud_run_revision"
   resource.labels.service_name="backend-sync-backfill"
   (resource.labels.revision_name="OLD_BACKFILL_REVISION_1" OR resource.labels.revision_name="OLD_BACKFILL_REVISION_2")
   httpRequest.requestUrl:"/v2/sync-jobs/run"
   ```

   Also confirm no old `backend-sync` admission revision has traffic. A queued direct task still targeting the service URL will reach new code: it writes/refreshes its marker while off, or migrates before processing if on. The 30-minute no-old-worker interval exceeds the 25-minute task deadline; new-code direct workers remain covered by their marker and the next step's quiet window. If old revision traffic or requests recur, restart this drain clock.
4. After the drain proof, the coordinator changes only the runtime flag to `on` in a later config PR, deploys dev, soaks it, and then deploys prod. The first on-mode kick enforces a new 30-minute global quiet window; per-UID markers can extend it. Confirm `action=cutover_wait` and delayed wakes, one active job per UID, independent-UID progress, bounded oldest wait, terminal release, and zero `action=cutover_overlap`. Watch the production acceptance signals below over 24 hours. If rollback sets `off`, keep Scheduler enabled until persisted sequenced jobs drain; a later off-to-on flip repeats this drain and quiet-window check.

### Monitoring queries

Use Cloud Logging on project `based-hardware`, scoped to `backend-sync` and `backend-sync-backfill`. These fields are fixed-shape log tokens, with no UID metric label or raw payload:

```text
resource.type="cloud_run_revision"
(resource.labels.service_name="backend-sync" OR resource.labels.service_name="backend-sync-backfill")
"event=sync_uid_sequencer"
```

Filter `action=sample` to chart capped `queued_depth` (up to 100), `oldest_waiting_seconds`, and `active_leases` per sampled owner; `action=sweep_summary` gives owner/pending scans and errors per tick. Filter `action=dispatch` for `latency_seconds`; `action=redrive`, `outcome=lease_expired`, `outcome=terminal_cleanup`, `outcome=expired_job_cleanup`, `action=wait_alert`, `action=cutover_wait`, and `action=cutover_overlap` show recovery, stalls and cutover risk. Filter `action=finished` for completed/failed/partial_failure outcome counts. The routed `sync_backfill_uid_sequencer_stall` log metric alerts on `action=wait_alert` or `action=sweep outcome=error`. The same deploy composite provisions `sync_backfill_uid_sequencer_scheduler_failure` from `cloud_scheduler_job` ERROR `AttemptFinished` logs and `sync_backfill_uid_sequencer_scheduler_heartbeat` as a 10-minute absence alert on `action=sweep_summary`. Investigate any of these alerts before queued Redis jobs or staged blobs expire. Also watch `event=sync_bridge outcome=deferred|failed`, `sync_transcription_job_finalized` failures, dead-letter creation, persistence-phase Firestore `Aborted`, fenced reprocessing/superseded jobs, and `/v2/sync-local-files` responses carrying `backfill_paced`; the last should be zero. Compare `partial_failure` with the flag-off 5% observation (versus 1.6% before concurrent heavy-UID uploads); per-UID sequencing should remove the cross-job contribution. A nonzero `action=delivery outcome=nonterminal_ack` is an invariant failure and needs immediate investigation.

```text
resource.type="cloud_scheduler_job"
resource.labels.job_id="sync-backfill-uid-sequencer"
severity>=ERROR
jsonPayload."@type"="type.googleapis.com/google.cloud.scheduler.logging.AttemptFinished"
```

For a missing tick, query `resource.type="cloud_run_revision" AND resource.labels.service_name="backend-sync" AND "event=sync_uid_sequencer action=sweep_summary outcome=done"` over the last ten minutes. No results should match the heartbeat absence alert. The failure and heartbeat alert policies are provisioned by the same lifecycle composite as the Scheduler job; they have no UID label.

## Transcription completion contract

VAD is the eligibility owner for offline sync. A batch for which VAD produces
zero segments is a valid `expected_silence` completion. Every file passed to
the provider after segmentation is speech-eligible; when the provider returns
no words, or normalization yields no transcript, the worker makes exactly one
identical bounded `prerecorded` retry (`attempts=0`, same URL, language,
keywords, and speaker count). If the retry also yields nothing the segment is
`expected_silence` — VAD over-reports on noise, so an empty result is valid
rather than a failure. No conversation or partial-result checkpoint is
written for it, but its processed markers are persisted under the same
lease/epoch guard as successful segments, so a Cloud Tasks redelivery skips
it without another provider call; a job that still completes persists its
content ledger normally. An exception on the retry keeps the normal failure
classification, and a recovered retry continues through the original
processing path exactly once.

The terminal job states have one acknowledgement meaning across mobile and
macOS:

| Job status | Meaning | Client WAL action |
| --- | --- | --- |
| `completed` | Every required segment succeeded, or VAD found no eligible speech | Mark synced and release local retry material |
| `partial_failure` | At least one required segment failed | Retain the file and return it to the retryable state |
| `failed` | Every required segment failed, or the job cannot currently progress | Retain the file and return it to the retryable state |

Duplicate Cloud Task delivery is deduplicated by the content ledger and
per-segment processed markers. A failed segment never receives a processed
marker, and a job-level content claim is released whenever any required
segment fails. This is what makes re-upload after `partial_failure` or `failed`
safe without duplicating successful conversation mutations.

Cloud Tasks enqueue is acknowledgement-sensitive. After GCS staging succeeds,
admission retries the deterministic task name once; `AlreadyExists` is a
successful enqueue. If acknowledgement remains uncertain, admission returns
the pollable job as `queued` but retains its GCS blobs, Redis job, and Firestore
claim. It never launches an inline fallback, terminalizes the job, or deletes
staged blobs, because the first request may already have created a runnable
task. Operators investigate `event=sync_dispatch outcome=enqueue_uncertain`
and `omi_sync_dispatch_attempts_total{mode="enqueue_uncertain"}`. A staging
failure before any enqueue removes partial blobs, marks the job failed, and
returns 503 for a normal WAL retry.

## Failure telemetry

Structured sync logs carry fixed-shape diagnostic fields, never metric labels
and never exception text, audio, transcript, path, or UID. Segment and job
events emit `phase` from a closed token set (`download`, `decode`, `vad`,
`provider_select`, `provider_call`, `parse`, `assignment`, `persistence`,
`postprocess`, `usage`, `finalize`, `unknown`, with `none` when no failure
context exists) and `exception_type` from a closed exception-class allowlist
that collapses anything else to `OtherException`. `job_ref` correlates the
job's UUIDv4 identifier and `attempt_ref` is a fresh random UUIDv4 per
coordinator invocation — never a run token, uid, content id, or path — so
Cloud Tasks retries of one job stay joinable without high-cardinality labels.
The terminal `sync_transcription_job_finalized` event adds the first failed
segment's bounded `failure_phase` and `failure_class`; successful and
speech-free jobs log `none`.

### Repeated content failures

The 45-day content ledger counts only whole-job, same-content deterministic
failures: `sync_invalid_audio` after decode finds no usable audio, or a
persistence data-shape exception with the same bounded phase and subtype on
each attempt (for example, `persistence:ValueError`). Unknown exceptions,
provider invalid-input verdicts, assignment conflicts, and mixed segment
failures do not count. Three consecutive matching failures within 24 hours
pause that content for 24 hours. A different or unclassified failure resets
the streak; an expired window starts at one.
Firestore `Aborted` (including exhausted contention wrappers), timeouts,
service outages, provider 5xx, and superseded/fenced jobs remain retryable.
The first three attempts use the existing STT path unchanged. Successful
content is still acknowledged through the normal completed ledger.

Admission checks the ledger before dispatch. Either cap creates a terminal
`failed` job and returns the existing HTTP 202 job contract with
`reason_code=sync_repeat_failure_paused` on the polled job. No capped job enters
paid STT. Shipped mobile parses arbitrary reason-code strings and treats this
one as a per-WAL retryable failure: it keeps the local file, consumes that
WAL's retry budget, and does not set the account-wide rate limiter. The sync
reconciler schedules subsequent attempts; exhausted WALs remain available for
the UI's manual Retry. A
plain upload 400 would mark the WAL `uploadRejected` and show only Delete in
the current UI; a `backfill_capacity` 503 would pause unrelated uploads.
First decode failures still use `sync_invalid_audio` and the existing terminal
job semantics.

Monitor `event=sync_repeat_failure_cap outcome=paused` grouped by the bounded
`failure_key` and lane. The event includes only `device_hash`, never UID,
content ID, file names, or exception text. Also monitor
`sync_transcription_job_finalized` with `failure_phase=persistence` and
`failure_class`, and `sync_transcription_job outcome=invalid_input` with
`reason_code=sync_invalid_audio`. A rising cap rate means clients still have
retained audio requiring investigation; it is not a success count.
`event=sync_persistence_exception` exposes a bounded exception subtype when
the closed telemetry class is `OtherException`, without exception text.

## Run ownership and recovery

### Epoch-fence rollout modes

`SYNC_LEDGER_FENCE_MODE` is a protected Cloud Run environment variable shared
by `backend`, `backend-sync`, and `backend-sync-backfill`. Its safe default is
`legacy`; a job persists the mode that admitted it as `ledger_fence_mode`, so a
later setting change cannot silently reinterpret existing retry material.

| Runtime mode | New admission / task behavior | Per-job protocol |
| --- | --- | --- |
| `legacy` | Normal admission while the old-revision fleet may still exist | Jobs are marked `legacy` and use the generic lock plus tokenless ledger calls. New revisions use raw-JSON CAS so a terminal state cannot be resurrected by another new legacy worker; a still-running old binary can only be retired by the cutover barrier, so this is intentionally not an epoch-safety claim. |
| `standby` | `/v1` and `/v2` admission return 503 before app-managed raw persistence or a content claim; task delivery returns 503 before lock/download | Polling remains available. Queued tasks and local WAL stay recoverable. |
| `active` | Normal admission | New jobs are marked `active` and use the epoch/token protocol below. Existing `legacy` jobs drain through the legacy branch after old revisions have been retired. |

Never set `active` on a normal deploy while old revisions may run. The
protected two-phase `Sync ledger fence cutover` workflow requires an operator
to set the environment variable `legacy` → `standby`, stage all three services,
pause `sync-jobs` and `sync-backfill`, promote standby traffic, and delete then
prove absent every prior zero-traffic revision. It deliberately leaves queues
paused on any failure. Only after that barrier does an operator set
`standby` → `active` and approve the activation job; activation promotes all
three active revisions, retires remaining standby revisions, then resumes only
queues that were running before the pause. Do not roll back to an old revision
after retirement—WAL and Cloud Tasks are the recovery boundary.

Each job records its dispatch owner. Cloud Tasks jobs use the run lease for
delivery serialization and can be stale-finalized by a polling read only after
that reader acquires the lease and rechecks the job. `get_sync_job` is read-only:
an old progress timestamp cannot authorize a Redis failure write, dead-letter
record, or cleanup. The authenticated status route performs recovery through
the existing finalizer after acquiring ownership. HTTP coverage in
`tests/unit/test_sync_status_read_ownership.py` exercises the real reader,
run-lease operations, and finalizer together so a mocked lookup cannot hide a
second transition owner. Inline jobs renew the same
lease while their coordinator is alive, but a poller never stale-finalizes an
inline job: a cancelled coordinator can have an executor leaf still writing,
and a lease renewal alone is not a terminal-write fence. Renewal errors or
timeouts fail closed before the last known-good lease reaches its safety
margin; cancellation preserves the run lease, staged/local retry material, and
content claim until their TTLs expire rather than allowing a concurrent retry.

For jobs admitted in persisted `active` mode, every worker-owned Redis update
is token-fenced: processing/stage/progress, partial results, terminal status,
Cloud Tasks retry reset, and processed-segment markers all compare the current
run token before writing. A rejected fence stops the old worker without
cleanup, terminal publication, claim release, or retry-marker mutation.
Successful full completion writes the durable content ledger before the fenced
`completed` transition. A failed or partial terminal transition is fenced first
and only its winning owner then releases the retry claim. Firestore
partial-result and segment-ID checkpoints remain job-ID idempotent nonterminal
records; the Redis fence prevents a stale task from authorizing a retry skip or
visible terminal state. `legacy` jobs deliberately retain the pre-fence
protocol until the hard revision-retirement cutover is complete. The raw-CAS
terminal guard makes the new legacy implementation monotone, but cannot
intercept a historical binary's plain Redis write; do not claim the strict
epoch guarantee until the protected barrier has proved those revisions absent.

This deliberately makes inline recovery a degraded, durable-retry path, not a
ten-minute promise. The job status remains queryable for 24 hours; after an
unknown/expired job the client retains and re-uploads its local WAL. A content
claim can suppress a duplicate upload until its 48-hour ledger expiry, so an
operator must not tell a customer that every inline failure will retry within
ten minutes. Cloud Tasks remains the preferred path for bounded automatic
retry; monitor `event=sync_inline_lease outcome=renew_error|lost` for inline
lease degradation.

The content ledger is stored at `users/{uid}/sync_content_ledger/{content_id}`. Its `expires_at` field is retained for 45 days; both the manual and auto-dev deploy paths provision and verify the Firestore TTL policy via `sync-backfill-lifecycle`. The stable content ID is an HMAC over UID plus each stable capture filename and raw-audio digest, preventing identical silence at different capture times from collapsing; `SYNC_CONTENT_ID_SECRET` may be set independently, otherwise `ENCRYPTION_SECRET` is used. Metering uses content-keyed atomic Redis/Firestore increments so a worker crash cannot double-count a retry. A job-level partial result is checkpointed before each processed-segment marker and hydrated on retry, so an accounting retry still returns the conversations created by the first attempt.

`backend-sync-backfill` clones the complete live `backend-sync` runtime env and secret-reference contract, then applies the checked-in backfill overlays. This keeps Redis, STT, storage, and service-auth bindings aligned without exposing secret values. BYOK historical uploads fail closed and remain on-device because request-scoped keys cannot be serialized into the isolated task; fresh BYOK retains the legacy inline path.

## Rollback

Pause `sync-backfill` in Cloud Tasks or set the global daily allowance to a value below current usage. Do not route backfill into `sync-jobs`, disable lane-specific accounting, or enable inline fallback. Fresh uploads remain operational while the historical queue is paused.

## Release acceptance

Upload a synthetic eight-day backlog and then create a current recording. Verify the current recording reaches a terminal job first, historical jobs never exceed thirty concurrent dispatches, live fair-use totals exclude `sync_backfill`, and replaying the same raw upload returns the durable completed result without new metering.
