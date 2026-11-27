# Two-lane offline sync

`backend-sync` is the upload admission service. It authoritatively classifies each homogeneous upload as:

- `fresh`: oldest capture time is at most `SYNC_FRESH_MAX_AGE_SECONDS` (default six hours). Jobs use `SYNC_TASKS_QUEUE`; inline is used only when Cloud Tasks is deliberately disabled or the request carries BYOK credentials.
- `backfill`: historical, missing, invalid, or future-skewed capture time. Jobs use `SYNC_BACKFILL_TASKS_QUEUE` and the `backend-sync-backfill` service. Backfill never falls back inline.

Capture timestamps are client assertions, so a well-formed device header alone never grants the fresh lane. For a server-created conversation on the same authenticated install, mobile first hashes the exact raw files and requests a short-lived server-signed manifest binding UID, device, conversation, filename timestamps, and SHA-256 identities. Admission verifies the signature and conversation window; after upload it verifies the bytes against the signed digests before dispatch. Uploads without that proof—including Transcribe Later and offline files—are conservative backfill. Missing, invalid, future, expired, or byte-mismatched claims cannot enter fresh.

A signed fresh manifest covers at most 20 files. Mobile detects a conversation with more than 20 pending fresh WALs before requesting a manifest and routes the whole conversation through backfill in three-file batches. It never claims one immutable fresh content set and strands the remainder behind a conflicting manifest.

Historical recovery defaults are a 30-day lookback (prod sets `SYNC_BACKFILL_MAX_AGE_SECONDS=5184000`, 60 days, because the lookback is checked once at upload admission and backlogs that older app builds or slow drains cannot clear within 30 days get a terminal 422 on the phone; staging lifecycle ages count from upload, not capture) and thirty globally concurrent Cloud Tasks dispatches capped at thirty per second. The processed-speech daily accounting caps remain available, but `SYNC_BACKFILL_ADMISSION_LIMITS=false` leaves them unenforced at upload admission. `SYNC_BACKFILL_INFLIGHT_LIMIT` and its unused admission primitive are retired after C6: no Redis per-UID admission slot is acquired. Token-fenced release remains for slots left by older revisions. `SYNC_BACKFILL_UID_SEQUENCER=on` in dev/prod is the phase-two setting (2026-09-28); `off` is the kill switch, under which eligible uploads still receive 202 and newly accepted jobs dispatch directly through Cloud Tasks as after #19352. The new admission path writes a bounded per-UID direct-job marker before enqueue, and the new worker refreshes it when direct work starts. A later config PR turns the sequencer on after the phase-one drain gate. On mode persists each accepted job in Firestore and dispatches at most one worker job per UID. Queue concurrency is controlled by the shared `.github/actions/sync-backfill-lifecycle` composite.

Production deploys require `SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS` as a comma-separated list of Cloud Monitoring notification-channel resource names. The workflow provisions log-based metrics and routed alert policies at 70% and 90%, then verifies each policy has a notification channel before traffic shifts.

Backfill speech is written under the `sync_backfill` accounting source. Live hard restrictions read only `realtime` and `sync_fresh`. Existing lookback, BYOK, global capacity, and fair-use guards remain. No per-UID `backfill_paced` response is emitted by v2 admission. Mobile retains the WAL on a non-202 response and polls an accepted job normally; no client change is needed.

## Per-UID backfill dispatch

Deleted with legacy sync on 2026-11-17 (plan C C9-C11): the UID backfill sequencer, its sweep/wake routes, the `sync-backfill-uid-sequencer` Scheduler job, the owner repair script and the `SYNC_BACKFILL_*` ordering, owner and expiry flags no longer exist. Per-owner ordering is OrderedMerge's job in the batch pipeline. See [legacy-dark.md](legacy-dark.md) for the cleanup checklist.

### Newest-first rollout

Deleted with legacy sync on 2026-11-17; see [Per-UID backfill dispatch](#per-uid-backfill-dispatch).

#### Expired-head retirement (Train 1)

Deleted with legacy sync on 2026-11-17; see [Per-UID backfill dispatch](#per-uid-backfill-dispatch).

## Two-phase rollout (dev, then prod)

Deleted with legacy sync on 2026-11-17; see [Per-UID backfill dispatch](#per-uid-backfill-dispatch).

### Monitoring queries

Deleted with legacy sync on 2026-11-17; see [Per-UID backfill dispatch](#per-uid-backfill-dispatch).

## Poll contract

`GET /v2/sync-local-files/{job_id}` admits at most 40 requests per authenticated
UID per 20-second Redis fixed window, shared across jobs and replicas. This
ceiling bypasses generic rate-limit boost and shadow settings. Current Dart
polling admits at most 18 requests/minute per app instance with a 20-second
minimum per job; two simultaneous instances still fit the ceiling. A hot loop
receives HTTP 429 with `Retry-After: 20`, before job lookup or stale recovery.
Redis limiter errors fail open with shared fallback telemetry. The counters
`omi_sync_job_poll_requests_total` and `omi_sync_job_poll_throttled_total` have
no labels. Unknown/expired jobs retain HTTP 404 (`Sync job not found or expired`);
clients retain local audio for re-upload. The 200 schema and terminal status
strings are unchanged. Failed/partial backfill polls can also perform durable
claim/dead-letter cleanup; healthy in-progress polls only read Redis job state.

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

The 45-day content ledger counts only same-content classified failures:
`sync_invalid_audio` after decode finds no usable audio (whole job), or a
classified persistence failure with the same bounded fingerprint on each
attempt. Classified persistence failures are the data-shape exception classes
(for example, `persistence:ValueError`), named assignment conflicts, and the
recognized Firestore document-size marker. Every `SyncAssignmentConflict` raise
site names its reason (`failure_subtype`). Structural reasons
(`provenance_mismatch`, `redirect_cycle`, `redirect_chain_too_long`,
`donor_tombstone_no_redirect`, `ancestry_flatten_rejected`,
`corrected_speech_changed`, `record_target_retired`,
`record_route_owner_changed`, `record_privacy_changed`) strike on every lane.
Reasons that wait on another writer (`live_target_not_persisted`,
`lineage_ownership_ambiguous`, `record_target_missing`,
`record_finalize_pending`) strike only on backfill, whose capture is hours old.
Projection owner drains making no progress on `live_target_not_persisted` are held
out of admission for 30, 60, 120, 240, then at most 300 seconds. Expiry only
re-admits the owner for its next sweep request, never wakes it; any progress or other stop resets
the attempt count, without changing the existing hold deadline or dispositions.
Set `PROJECTION_DRAIN_LIVE_TARGET_BACKOFF=off` to restore ordinary `head_error`
retries; `omi_batch_projection_live_target_backoffs_total` counts applied delays.
One classified segment failure is enough for the batch to
earn the strike, even beside successful siblings; differing fingerprints in one
batch share `persistence:mixed`. Unknown exceptions, provider invalid-input
verdicts, the unlabeled `other` conflict, finalize-phase conflicts, and unknown
Firestore `InvalidArgument` do not count. Three consecutive matching failures within 24 hours
pause that content for 24 hours, then it is admitted again automatically;
there is no permanent pause. A different or unclassified failure resets
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
`event=sync_persistence_exception` exposes a bounded exception subtype, a
bounded `firestore_error` class and a bounded `firestore_doc_kind` for every
persistence failure, without exception text, paths or ids.

A canonical conversation near Firestore's 1 MiB limit rolls new speech over to
another conversation instead of failing after paid transcription:
`sync_assignment_target reason=size_rollover outcome=rolled_over` (with `trigger=estimate` or
`trigger=commit_limit`) and `omi_fallback_event component=sync_dispatch
to=size_rollover` count it, `reason=size_limit_retry outcome=rejected` counts the one commit
backstop retry, and `reason=size_rollover_unavailable outcome=unavailable` means the speech had no
safe home, so the original write was attempted unchanged. `firestore_error=document_size_limit`
should then be rare; when it still occurs it names `sync_day_index`, `sync_recent`,
a `donor`, or a `conversation` rejected a second time after the backstop retry.
`excluded` on the rollover event counts the full conversations the committed plan
stepped past. When the only id the chunk can create a conversation under is its own
existing or redirected anchor, there is no safe home: fences hold, but the write
can fail again after the backstop, so `size_rollover_unavailable` is not a recovery.

Size observations carry hashed `job_ref`/`attempt_ref`, the rejected plan's
`segments_bucket`/`speech_seconds_bucket`, and closed
`rollover_target_kind=new_row|sibling_row|none`. `stage=commit` confirms a rollover;
`stage=plan` is only a transaction-body observation. A final size exception keeps
the last rejected document's buckets with `outcome=rejected`. Absent job context
uses `none` refs. See the [size attribution contract](../../utils/sync/ARCHITECTURE.md#conversation-size)
for bucket boundaries and the change from normalized to hashed refs.

### Internal failures are not `upstream_error`

A persistence or finalize failure never reached an STT vendor. Sync segment and
job metrics and logs record it as `outcome=internal_error` with a bounded
`failure_reason` (`storage_rate_limited`, `quota_exhausted`,
`firestore_contention`, `assignment_conflict`, `persistence_error`,
`finalize_error`), counted in
`omi_sync_internal_failures_total{kind,lane,failure_reason}`. A job is internal
only when no segment error came from a provider. The job `errors` codes are
`sync_storage_rate_limited` (GCS 429) and `sync_firestore_contention`
(exhausted assignment contention); other internal causes keep
`sync_persistence_failed`/`sync_finalize_failed`. Vendor dashboards read
`outcome=upstream_error` alone.

Sync bridges copy donor audio idempotently: one destination listing per bridge,
skip an object with the same crc32c and size, create or replace only under a
generation precondition, and back off a GCS 429 with jitter (four attempts).
`omi_sync_bridge_audio_copy_total{outcome=copied|skipped|rate_limited|raced}`
shows the split; `raced` is a concurrent bridge that already wrote the same
bytes.

Fresh jobs take a per-(uid, candidate conversation) Redis turn around
persistence and finalize, so concurrent fresh jobs for one conversation stop
contending (`omi_sync_fresh_conversation_turn_total{outcome}`). `timeout` and
`unavailable` proceed unserialized; the assignment transaction stays
authoritative. Kill switch: `SYNC_FRESH_CONVERSATION_TURN=off`.

Ordinary sync absorbs re-point only the rows they match, while the canonical's
`sync_merged_from` stays cumulative, so an absorbed row's own ancestors can keep
redirecting at it (a multi-hop chain inside one lineage). When a chunk later lands
on a smart-merge survivor and matches that row, the one-hop flatten re-points
every hop of such a chain at the survivor in the same transaction. The finalize
bridge accepts a chain that stays inside the survivor's lineage and ends at it.
A chain that leaves the lineage, cycles, or crosses a non-tombstone is left alone.
`event=sync_ancestry_flatten outcome=rejected reason=...` names what the flatten
declined. A source that the bridge can no longer redirect at its survivor —
missing, hard-deleted, no longer a tombstone, or a chain that left the lineage —
is terminal: the bridge logs `event=sync_bridge outcome=source_terminal kind=...`,
counts `omi_sync_bridge_terminal_total{outcome}`, leaves both rows untouched, and
still settles the sources that resolve. It does not raise, so one stale ancestry
entry can no longer fail an enrichment resume. A later append re-reads the entry,
so a source that does become a tombstone is cleaned up then. Kill
switch: `SYNC_FINALIZE_TARGET_RECOVERY_ENABLED=off` restores the strict
`event=sync_bridge outcome=source_rejected` / `bridge_source_not_tombstone`
failure for every bridge caller. Separately,
`CONVERSATION_SMART_MERGE_FLATTEN_CHAIN_REPAIR=off` restores the strict one-hop
check and leaves same-lineage chains to the same terminal path
(`ancestry_flatten_rejected`).

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
pause `sync-jobs` and `sync-backfill` (in prod also `sync-jobs-fresh` and
`sync-backfill-fresh`, which carry live dispatch since the 10-18/10-19
stalls), promote standby traffic, and delete then
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

### Backfill owner repair

Deleted with legacy sync on 2026-11-17; see [Per-UID backfill dispatch](#per-uid-backfill-dispatch).

### Durable expiry custody (dark)

Deleted with legacy sync on 2026-11-17; see [Per-UID backfill dispatch](#per-uid-backfill-dispatch).
