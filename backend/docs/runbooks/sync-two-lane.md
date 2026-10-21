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

### Newest-first rollout

`SYNC_BACKFILL_ORDER=oldest|newest` defaults to `oldest`; unknown values also
retain oldest-first behavior. With `newest`, `SYNC_BACKFILL_ORDER_PERCENT`
(default 100) selects a stable SHA-256 UID cohort, plus the comma-separated
`SYNC_BACKFILL_ORDER_UID_ALLOWLIST`. Set percent 0 for an allowlist-only pilot.
Neither knob changes `SYNC_BACKFILL_UID_SEQUENCER`.

For durable waiting jobs, selection uses the existing `uid` equality and
`sort_at` field in descending order, inside the same fenced transaction.
This also applies to persisted waiting jobs drained by sweep/wake while the
sequencer admission flag is off. Active jobs are never preempted. A recording
is not cheaply grouped in the historical pending model: job payloads may
contain multiple files and have no indexed recording group. We therefore use
the descending-job fallback, including for separate jobs from one recording.
Within each job, VAD segments still assign chronologically through the ordered
turnstile. Across jobs, atomic interval intake finds preceding and following
adjacent chunks, rebases transcript offsets to the earliest start, and coalesces
unattended donors transactionally. Late earlier chunks and intervening bridges
converge on one conversation. Device/source/lock partitions, user curation,
explicit live targets and document-size rollover retain their existing fences;
newest-first does not promise consolidation across those boundaries.

Direct Cloud Tasks uploads use the same cohort policy with no Firestore reads.
Their `schedule_time` is admission time plus capture age / 288, rounded up to
a second and capped at five minutes (unknown age takes the maximum).
For uploads admitted together, newer captures become eligible earlier; retrying
enqueue preserves the deadline. Already selected sequenced tasks and fresh
tasks receive no delay. Cloud Tasks has no priority among eligible tasks:
this is a bounded scheduling preference, not a strict execution-order guarantee,
and it cannot reorder already queued tasks. No new queue is required.

Keep `SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM=true` for retirement. In newest
cohorts the existing bounded pending sweep page also checks entries accepted
over 24 hours ago, including while newer work owns the UID. Age alone never
retires a job: exact Redis absence, an acquired run lock, and the existing
transactional unbound-ledger proof are mandatory. Retirement removes only the
pending record and releases its matching unbound content claim; an active
owner is preserved byte-for-byte. Audio and conversation data are untouched.
The expired job remains a poll 404, permitting WAL re-upload.

Deploy prerequisite: build the declared composite on `sync_backfill_pending`:
`uid ASC, sort_at DESC, __name__ DESC`. It is owned by
`database/sync_pipeline_indexes.py` and generated into `firestore.indexes.json`.
Wait for READY before enabling any cohort. The query still reads one head;
there is no added admission/worker Firestore lookup or recording-group scan.

After source release and index readiness, an authorized operator sets the
order flag on both sync services, starts with an allowlist and percent 0,
then ramps 5% → 25% → 100% after observing freshness, fragmentation/new-row
and bridge/merge counts, persistence `Aborted`, partial failures and the
expired-retirement counter. Preserve the independently operated sequencer OFF
setting. Compare against the oldest cohort; sustained older-work starvation
is a reason to reduce the cohort or restore `oldest`. Rollback restores
oldest selection immediately for future claims/enqueues; direct tasks already
scheduled retain at most their original five-minute delay.

`sync_backfill_sequencer/{uid}` is a Firestore owner document with one active job, a monotonically advanced execution epoch retained across empty queues, and a 30-minute renewable running lease. Each waiting job is its own append-only `sync_backfill_pending/{job_id}` document with the complete Cloud Task payload. Admission transactionally writes the pending document and creates a missing owner or wakes a parked owner without resetting its epoch. An existing discoverable owner needs no admission write. Completion and retirement check pending presence in their transaction: owners with waiting work stay discoverable, while empty owners retain their epoch without a `reconcile_at` field, excluding them from the hot range query. An empty claim and stale deferral also park empty owners transactionally; a concurrent active claim or admission cannot be hidden by parking. Owner writes also cover dispatch claims, releases and active two-minute heartbeats. The pending and active payload maps are exempt from unqueried single-field indexes. Admission writes the job before 202; after a lost write acknowledgement it checks the registry. A confirmed write still returns 202, a confirmed absence cleans up and returns 503, and an unavailable verification fails the request while preserving the content claim and staged material for investigation. It never acknowledges 202 without a known registry write. One pending job is promoted transactionally and enqueued with a deterministic `job_id-s{epoch}` task name. The ordered oldest-pending query is inside the owner-claim transaction, so a newly admitted earlier capture cannot be missed by a separate preselection. Waiting jobs are selected oldest capture first, then Firestore document ID for ties. The mobile WAL sends recent batches first, so the first arrived batch can start immediately; oldest first applies among jobs already waiting and reduces cross-job conversation bridge work. It cannot reorder a job already running. Other UIDs dispatch independently into the same bounded global queue (Train 1 source configuration: 90 concurrent / 15 dispatches per second).

The worker checks the persisted job/epoch before any transcript work, renews its lease every two minutes, and releases ownership only after the Redis job is terminal or has expired. A stale delivery cannot enter the pipeline. Terminal success, failure, partial failure, duplicate delivery, dead-letter confirmation, and expired-job cleanup all converge through that release and a dispatch of the next waiting job. A retryable HTTP 409/500 keeps the owner; Cloud Tasks retries it. The existing per-job Redis run lock remains a second fence. Redis jobs persist `dispatch_mode=sequenced`, so polling does not mistake an intentionally waiting job for a lost direct Cloud Task; the worker's persisted retry count is reused after redrive rather than resetting the paid provider attempt budget. An old queued task without a sequencer epoch that reaches a new worker while the flag is on is marked sequenced, registered and acknowledged, then redelivered with an epoch. While the flag is off, direct deliveries run immediately, including for UIDs with existing sequenced work (#21909). Existing owners and pending entries continue draining; direct work can overlap that drain. Old Redis admission-slot keys are ignored.

On an off-to-on transition, the first sequenced dispatch waits 30 minutes, the maximum Redis run-lock lifetime and longer than the 25-minute task request deadline. This covers direct workers on old revisions, which cannot register their presence. New flag-off admissions also register a 30-minute per-UID Redis direct marker before enqueue; a direct worker renews it from actual task start so queue delay cannot shorten protection. A sequenced dispatch waits for that marker even while the flag is off, preserving already pending sequenced jobs through rollback. The mode key is reset by each flag-off admission, so an off-to-on transition repeats the global wait automatically in dev and prod. Admission still returns 202 and no HTTP worker waits for the guard. Each waiting UID receives a named delayed wake task on the existing sync queue; the OIDC-protected wake route calls `kick` at the deadline. `action=cutover_wait` logs at most once per UID per five minutes with `job_id`, HMAC `uid_hash`, and the known direct job ID; `action=cutover_direct_active` records observed direct processing during transition, while `action=cutover_overlap` requires a simultaneously active sequenced owner. An old revision that somehow continues receiving direct work more than 30 minutes after traffic promotion cannot be fenced by new code; treat an overlap event as a rollout fault. The guard adds a one-time 30-minute dispatch latency on each off-to-on transition and never changes paid STT submission policy.

The existing deploy lifecycle provisions `sync-backfill-uid-sequencer` in Cloud Scheduler every two minutes, targeting the OIDC-protected `/v2/sync-backfill-sequencer/sweep` on backend-sync. It uses the existing sync task invoker identity and audience. Each tick reads at most 100 due UID owners and 100 due pending documents. Pending documents are deferred five minutes when scanned, so a heavy UID cannot occupy every sweep page indefinitely; this recovers a crash between admission's durable write and immediate kick. Even with a continuous backlog, the pending scan/defer is bounded to 72,000 document reads and writes per day across the project; an empty queue incurs no pending-document writes. An active worker renews its lease. A lost dispatch is redriven after five minutes with the same execution epoch and a persisted incrementing dispatch attempt in its task name (`job_id-s{epoch}-d{attempt}`); repeating an attempt is idempotent, while a fresh attempt bypasses any deleted-task name tombstone. Late queued deliveries remain valid regardless of queue delay. Only an expired running lease is redriven with a new epoch, after its Redis run lock is absent; that old execution epoch then becomes stale. A terminal or expired Redis job is delivered once more for the existing cleanup path and the next job. A 12-hour waiting age emits an error event with `job_id` and HMAC `uid_hash` before the 24-hour Redis job and staged-blob expiry. The sweep should finish well within its 180-second Scheduler deadline. Registry documents have no TTL: parked epoch documents persist but have no `reconcile_at` and never occupy a due-owner page. Normal admission, delayed cutover wakes, and terminal completion call `kick` directly, so jobs continue to make progress without Scheduler; only a process crash or uncertain/lost dispatch requires its reconciliation. Scheduler execution failure and missing sweep heartbeats route alerts separately.

#### Expired-head retirement (Train 1)

`SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM` defaults false in code/dev and true in the production sync-service manifest. Before a normal claim, the sequencer retires at most 50 Redis-absent pending entries. It uses raw `EXISTS` (corrupt JSON is still present), takes the existing compare-delete job lock, rechecks absence, and transactionally rechecks owner/pending/ledger before deleting pending work and releasing only the same unbound processing claim to retryable. A live/protected head is claimed only if the transactional oldest entry still matches the job whose Redis key was inspected. A changed head defers to the next kick. Running or bound work is preserved; Redis errors propagate without retirement. No audio, conversation, metering or completed result is deleted. Newer claims survive. A worker's concurrent begin wins the dispatching-owner transaction race.

The sweep also retires Redis-absent dispatching owners before their retry deadline, then considers the next head. Sweep kicks use one pending retirement per UID rather than 50 to bound the 100-owner scheduler pass; admission/completion kicks retain the50-head budget. Exhaustion leaves remaining work durable for another kick/sweep. Counter `sync_backfill_expired_retired_total` and `event=sync_backfill_expired_retired` distinguish pending/dispatching retirement from successful transcription. Flag off restores the original dispatch path but cannot recreate retired metadata. Retained client WALs recover expired job IDs through the existing 404/re-upload flow.

## Two-phase rollout (dev, then prod)

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
`sync_assignment_target outcome=size_rollover` (with `trigger=estimate` or
`trigger=commit_limit`) and `omi_fallback_event component=sync_dispatch
to=size_rollover` count it, `outcome=size_limit_retry` counts the one commit
backstop retry, and `outcome=size_rollover_unavailable` means the speech had no
safe home, so the original write was attempted unchanged. `firestore_error=document_size_limit`
should then be rare; when it still occurs it names `sync_day_index`, `sync_recent`,
a `donor`, or a `conversation` rejected a second time after the backstop retry.
`excluded` on the rollover event counts the full conversations the committed plan
stepped past. When the only id the chunk can create a conversation under is its own
existing or redirected anchor, there is no safe home: fences hold, but the write
can fail again after the backstop, so `size_rollover_unavailable` is not a recovery.

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
A chain that leaves the lineage, cycles, or crosses a non-tombstone still
conflicts. `event=sync_ancestry_flatten outcome=rejected reason=...` and
`event=sync_bridge outcome=source_rejected kind=...` name what was left. Kill
switch: `CONVERSATION_SMART_MERGE_FLATTEN_CHAIN_REPAIR=off` restores the strict
one-hop check (`ancestry_flatten_rejected` / `bridge_source_not_tombstone`).

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

Every accepted `sync_backfill_pending` entry has a durable
`sync_backfill_sequencer` owner. Admission creates missing owners in the same
transaction, including duplicate admission of a legacy orphan. Completion and
active retirement clear the active reservation but retain an idle owner and its
fencing epoch. The release transaction rechecks pending presence; an empty
owner has no `reconcile_at` field and is excluded from the hot range query
indefinitely. A non-empty idle owner remains due, with heartbeat deferral after
a blocked attempt. Deferral rechecks current ownership and pending presence in
a transaction, so a stale sample cannot park a new active reservation or revive
an empty document. Admission wakes parked owners in its own transaction. Owners
are retained to keep epochs monotonic across empty queues; storage remains one
small document per participating UID.

The reconcile job's existing due-pending scan repairs missing owners before
attempting dispatch, at most one transaction per distinct UID in its bounded
page (maximum 500 entries per tick). Deferring pending entries rotates the scan
through the backlog. Repair transactionally rechecks pending presence and never
overwrites an existing active owner. Each repaired owner gets a random
`reconcile_at` from 1 second through the repair window (default 30 minutes),
plus the same `repair_not_before` deadline. The shared
`SYNC_BACKFILL_OWNER_REPAIR_WINDOW_SECONDS` setting configures that window.
The self-heal tick does not kick newly repaired owners; both normal claims and
expired-head inspection honor `repair_not_before`, so the pending fallback
cannot collapse repairs onto the next tick. A successful claim removes that
marker. Each repair emits `event=sync_backfill_owner_repaired`
and increments `sync_backfill_owner_repaired_total`; sweep outcomes also count
`owner_repaired`. The existing cutover guards, run locks and Redis-expiry checks
still control dispatch and retirement.

An operator can review and run `scripts/repair_sync_backfill_owners.py` from
`backend/`. It reads only UID projections while paging pending documents by ID,
then uses the same transactional owner-creation primitive as admission and the
scheduled sweep. It prints aggregate counts only, caps reads at `--limit`
(default 1,000,000 entries), and rate-limits UID probes (default 5/second,
maximum 20). `--page-size` is capped at 500. `--repair-window-seconds` can
override the shared repair window for this operator invocation; the default is
30 minutes unless the environment sets a different shared window. Dry-run is the default and uses
read-only Firestore transactions; apply recreates owners but does not dispatch
tasks or touch Redis, ledgers, audio, or pending payloads. Reruns are idempotent.
If `scanned_entries` reaches `--limit`, raise the limit for a complete pass.
Counts cover the selected bounded scan, not a point-in-time fleet snapshot;
concurrent admission/completion can change them.

Prepared procedure (requires explicit operator review before apply):

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
OMI_ENV_STAGE=prod PYTHONPATH=. .venv/bin/python scripts/repair_sync_backfill_owners.py --project based-hardware --dry-run
# After review, select the authorized operator credentials outside the script.
OMI_ENV_STAGE=prod PYTHONPATH=. .venv/bin/python scripts/repair_sync_backfill_owners.py --project based-hardware --apply
```

Compare `missing_owners`, `repaired_owners` and `errors`; rerun dry-run after
apply. A nonzero error count returns a failing exit code without printing
exception details or identities. The background reconcile job picks up repaired
owners on ticks after their staggered deadlines. Do not apply a repair before
the empty-owner exclusion and stagger-aware reconcile code is deployed. No one-off repair is part of deploying this code.

### Durable expiry custody (dark)

`SYNC_DURABLE_REDRIVE_GUARD=false` and
`SYNC_LEGACY_COMPLETION_CONVERGENCE=false` default off in code/dev and are enabled on production `backend-sync` and `backend-sync-backfill` in `backend/deploy/runtime_env/prod.overlay.yaml`. Change only through a
reviewed configuration rollout. The guard independently enables the existing
bounded missing-key/run-lock scan even when
`SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM=false`. Its transaction removes an expired
request from dispatch only after retaining the exact accepted payload under
`sync_redrive_required/{job_id}` with `status=redrive_required`. A canonical
completed ledger permits retirement without a handoff. Bound runs and competing
content owners refuse transfer. Partial results and processed segment IDs remain
on the ledger. A missing-job worker ACK follows durable custody and retains
staged bytes; a custody write failure propagates and keeps the task retryable.

The Scheduler reads durable `sync_redrive_stats/backlog` into
`sync_redrive_required`, `sync_redrive_nearest_deadline_timestamp_seconds`, and
`sync_redrive_unknown_deadline`. The nearest timestamp is an exact source
custody deadline when known, otherwise a conservative attention deadline at
acceptance. It is **not** a promise of recoverable source bytes. A positive
unknown count requires source inventory/preservation. These are unresolved
handoff counts, not transcription successes. No automatic redriver, source hold,
release or abandonment is enabled by this PR. An operator resolving custody
must reconcile the aggregate and nearest deadline transactionally; never delete
handoff rows to make the gauge fall.

Legacy convergence reads the canonical completed result after acquiring the
worker run lock and before download/provider work. It finalizes Redis using
that same token via the existing compare-and-set finalizer without binding a
ledger epoch or changing dispatch mode. Invalid/held results continue the
ordinary path; read errors and lost tokens fail closed. Flag rollback restores
legacy behavior but does not remove durable custody records. Leave protective
holds intact until delivery/explicit abandonment is verified.
