# Two-lane offline sync

`backend-sync` is the upload admission service. It authoritatively classifies each homogeneous upload as:

- `fresh`: oldest capture time is at most `SYNC_FRESH_MAX_AGE_SECONDS` (default six hours). Jobs use `SYNC_TASKS_QUEUE`; inline is used only when Cloud Tasks is deliberately disabled or the request carries BYOK credentials.
- `backfill`: historical, missing, invalid, or future-skewed capture time. Jobs use `SYNC_BACKFILL_TASKS_QUEUE` and the `backend-sync-backfill` service. Backfill never falls back inline.

Capture timestamps are client assertions, so a well-formed device header alone never grants the fresh lane. For a server-created conversation on the same authenticated install, mobile first hashes the exact raw files and requests a short-lived server-signed manifest binding UID, device, conversation, filename timestamps, and SHA-256 identities. Admission verifies the signature and conversation window; after upload it verifies the bytes against the signed digests before dispatch. Uploads without that proof—including Transcribe Later and offline files—are conservative backfill. Missing, invalid, future, expired, or byte-mismatched claims cannot enter fresh.

A signed fresh manifest covers at most 20 files. Mobile detects a conversation with more than 20 pending fresh WALs before requesting a manifest and routes the whole conversation through backfill in three-file batches. It never claims one immutable fresh content set and strands the remainder behind a conflicting manifest.

Historical recovery defaults are a 30-day lookback and thirty globally concurrent Cloud Tasks dispatches capped at thirty per second. The processed-speech daily accounting caps remain available, but `SYNC_BACKFILL_ADMISSION_LIMITS=false` leaves them unenforced at upload admission. `SYNC_BACKFILL_INFLIGHT_LIMIT=false` is retired for v2: no Redis per-UID admission slot is acquired even if that setting changes. `SYNC_BACKFILL_UID_SEQUENCER=on` in dev/prod accepts eligible backfill uploads with 202, records each job in Firestore, and dispatches at most one sequenced worker job per UID. The flag's `off` kill switch sends newly accepted jobs directly to Cloud Tasks, matching the concurrent behavior after #19352 without restoring the upload 429. Queue concurrency is controlled by the shared `.github/actions/sync-backfill-lifecycle` composite.

Production deploys require `SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS` as a comma-separated list of Cloud Monitoring notification-channel resource names. The workflow provisions log-based metrics and routed alert policies at 70% and 90%, then verifies each policy has a notification channel before traffic shifts.

Backfill speech is written under the `sync_backfill` accounting source. Live hard restrictions read only `realtime` and `sync_fresh`. Existing lookback, BYOK, global capacity, and fair-use guards remain. No per-UID `backfill_paced` response is emitted by v2 admission. Mobile retains the WAL on a non-202 response and polls an accepted job normally; no client change is needed.

## Per-UID backfill dispatch

`sync_backfill_sequencer/{uid}` is a Firestore owner document with one active job, a monotonically advanced dispatch epoch while the owner exists, a 30-minute renewable lease, and a pending count. Each waiting job is its own `pending/{job_id}` document with the complete Cloud Task payload. Admission writes the job before 202; after a lost write acknowledgement it checks the registry. A confirmed write still returns 202, a confirmed absence cleans up and returns 503, and an unavailable verification fails the request while preserving the content claim and staged material for investigation. It never acknowledges 202 without a known registry write. One pending job is promoted transactionally and enqueued with a deterministic `job_id-s{epoch}` task name. Waiting jobs are selected oldest capture first, then Firestore document ID for ties. The mobile WAL sends recent batches first, so the first arrived batch can start immediately; oldest first applies among jobs already waiting and reduces cross-job conversation bridge work. It cannot reorder a job already running. Other UIDs dispatch independently into the same 30-slot global queue.

The worker checks the persisted job/epoch before any transcript work, renews its lease every two minutes, and releases ownership only after the Redis job is terminal or has expired. A stale delivery cannot enter the pipeline. Terminal success, failure, partial failure, duplicate delivery, dead-letter confirmation, and expired-job cleanup all converge through that release and a dispatch of the next waiting job. A retryable HTTP 409/500 keeps the owner; Cloud Tasks retries it. The existing per-job Redis run lock remains a second fence. Redis jobs persist `dispatch_mode=sequenced`, so polling does not mistake an intentionally waiting job for a lost direct Cloud Task; the worker's persisted retry count is reused after redrive rather than resetting the paid provider attempt budget. An old queued task without a sequencer epoch that reaches a new worker while the flag is on is marked sequenced, registered and acknowledged, then redelivered with an epoch. An already running old revision cannot be retroactively fenced; drain the old queue/revisions during dev and prod cutover before treating the one-active-job invariant as strict. Turning the flag off does not bypass ownership for jobs carrying a persisted epoch; new jobs use direct dispatch. Old Redis admission-slot keys are ignored.

The existing deploy lifecycle provisions `sync-backfill-uid-sequencer` in Cloud Scheduler every two minutes, targeting the OIDC-protected `/v2/sync-backfill-sequencer/sweep` on backend-sync. It uses the existing sync task invoker identity and audience. Each tick reads at most 100 due UID owners; an active worker renews its lease, a lost dispatch is redriven after five minutes, and an expired running lease is redriven only after its Redis run lock is absent. The old task epoch then becomes stale. A terminal or expired Redis job is delivered once more for the existing cleanup path and the next job. A 12-hour waiting age emits an error event and the production routed stall alert, before the 24-hour Redis job and staged-blob expiry. The sweep should finish well within its 180-second Scheduler deadline. Registry documents have no TTL while work is pending.

### Monitoring queries

Use Cloud Logging on project `based-hardware`, scoped to `backend-sync` and `backend-sync-backfill`. These fields are fixed-shape log tokens, with no UID metric label or raw payload:

```text
resource.type="cloud_run_revision"
(resource.labels.service_name="backend-sync" OR resource.labels.service_name="backend-sync-backfill")
"event=sync_uid_sequencer"
```

Filter `action=sample` to chart `queued_depth`, `oldest_waiting_seconds`, and `active_leases` per sampled owner; `action=sweep_summary` gives `scanned` and `errors` per tick. Filter `action=dispatch` for `latency_seconds`; `action=redrive`, `outcome=lease_expired`, `outcome=terminal_cleanup`, `outcome=expired_job_cleanup`, and `action=wait_alert` show recovery and stalls. Filter `action=finished` for completed/failed/partial_failure outcome counts. The routed `sync_backfill_uid_sequencer_stall` log metric alerts on `action=wait_alert` or `action=sweep outcome=error`. Also watch Cloud Scheduler job `sync-backfill-uid-sequencer` execution failures, `event=sync_bridge outcome=deferred|failed`, `sync_transcription_job_finalized` failures, dead-letter creation, and `/v2/sync-local-files` responses carrying `backfill_paced`; the last should be zero. A nonzero `action=delivery outcome=nonterminal_ack` is an invariant failure and needs immediate investigation.

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
that reader acquires the lease and rechecks the job. Inline jobs renew the same
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
