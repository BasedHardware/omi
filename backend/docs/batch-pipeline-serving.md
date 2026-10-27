# Batch intake and serving operations

Global batch admission defaults off; quality and isolation kill switches can
ship on. Declaring settings or deploying an empty chart does
not select an upload; the lead explicitly enables the global admission flag and
allowlist/percentage after qualification. Agent A does not deploy or apply indexes.

## Host settings and rollback

### Language inheritance for sync pieces

`BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED` ships on. New batch uploads
use the bound conversation's recognized language, then the user's configured
language. Blank, auto, multi and unrecognized codes remain unknown. Only when
both are unknown does each decoded unit run the existing self/vendor LID.
This also applies to pieces under ten seconds: ambient speech cannot replace
a known English conversation language with Vietnamese or Japanese.

The decision is frozen as declared language evidence in the authenticated
audio context, so the worker's existing unsupported-language guard still
applies. Legacy eligibility and durable route ownership are unchanged.
Set the switch to `false` on backend-sync to restore the former per-piece
input selection for new intakes; already staged units retain their evidence.
No transcript rewrite or paid recovery is part of this switch.

The v1 listen transcript writer also retains the earlier capture start when
the first words arrive late or after reconnect. Segment offsets are computed
against that retained start. This writer fix needs a backend-listen release;
the v2 audio-timeline origin pin continues to follow its existing contract.

### Partial-ramp owner isolation

`BATCH_PIPELINE_RAMP_EXCLUDE_HEAVY_OWNERS` ships on; only `off` disables
it. At a new sync upload or recording reservation with `0 < percent < 100`,
`config/policy/ramp.py` excludes an owner with more than 30 open items or
more than 21,600 seconds of waiting audio. Explicit canaries follow the same
rule. Open items are recent (six-hour) unfinished, non-quarantined batch units
plus waiting `sync_backfill_pending` jobs and the sequencer's active legacy
payload, deduplicated by job ID across the dispatch transition. Audio includes their known durations
and the incoming upload's declared span. This catches both run 24's one 20-hour
upload and run 25's 42 open units before they enter a typical-user ramp.
Missing or invalid incoming WAL bounds are unknown audio, never zero. New
desktop uploads without declared bounds therefore stay on legacy during a
partial ramp. Existing batch receipt/record owners continue draining.

The database reader selects metadata only, at most 512 rows per query source
plus one active-owner metadata document. A
saturated read, unknown waiting duration or read error keeps new work on legacy
and emits `omi_batch_ramp_heavy_owner_excluded_total{reason}`; fixed reasons are
`open_backlog`, `recording_hours`, `load_unavailable`. The counter counts decisions,
not distinct owners. It has no account label. Existing batch content receipts
and native recording owners keep their original dispatcher and continue draining;
the exclusion must never start a legacy twin. Full rollout (`percent=100`) and
percent-zero explicit qualification retain their existing semantics.

Excluded owners continue receiving the legacy pipeline, with its existing
sequencer, capacity and recovery gates. The lead runs their drain as a separate
heavy-owner qualification window: report the excluded count/reasons, open count
and audio volume; keep the existing hard cap of 60; wait for backlog to fall;
then run the unchanged fleet gate with the retained accepted-work census and
by-reason failure checks. No automatic widening or new redrive is granted here.
Before a 100% step, attach that heavy-owner gate receipt separately from the
typical-cohort receipt. Roll back new-admission isolation with `=off`; accepted
work retains its saved policy. The workspace preflight vendors the pure source
and verifies its bytes against the serving release before applying exclusion.

On the selected always-CPU backend host, `BATCH_PIPELINE_SERVING_ENABLED=true` starts a supervised
20-second reconciliation loop. It recovers leases/retries, drains ordered log
entries, projects C's durable outbox and refreshes queue-age metrics. Configure
an explicit prod/dev runtime stage, customer data-plane project, shared encryption
secret and `BUCKET_BATCH_PIPELINE` durable artifact bucket. This bucket must not
inherit the legacy syncing bucket's one-day lifecycle for pending objects.
D's completion/deletion outboxes own removal; pending audio must survive backlog.

With several serving instances, the periodic ticks (the supervisor and metrics
scrapes) run maintenance (staging reap, artifact cleanup, enrichment sweep,
quarantine discovery, lease recovery and the result-ready drain) on one instance
per 60-second Firestore lease in `{namespace}_leases`. Projection sweeps and
gauge refreshes stay per instance. Explicit `POST /reconcile` and the
post-recovery drain always run. Every guarded step is already idempotent and
transaction-fenced, so the lease saves reads and enqueues only. A lease-store
error fails open to every instance running, and
`BATCH_PIPELINE_LEADER_LEASE_ENABLED=false` restores that unconditionally.

The GPU worker also needs explicit `BATCH_PIPELINE_API_URL` (HTTPS backend service base)
and `BATCH_PIPELINE_WORKER_AUDIENCE`. A's Pump composes the Google service-OIDC
client automatically for production-marked items; missing/unavailable policy
service defers work without inference or a failed-attempt penalty. Configure the
backend's expected worker service-account email and Cloud Run invoker access.

B's GPU chart uses its independent default-off worker switch, dedicated GPU pool,
matching namespace/bucket/secret, and fresh per-pull capacity. Intake packs at
most one hour; keep dedicated worker `BATCH_PIPELINE_UNIT_SECONDS` compatible
with admitted units. Shared-live remains disabled and is not this deployment.

Retire every pre-protocol intake revision and its outstanding requests before
enabling a cohort; those revisions cannot recognize a durable batch route.
Do not roll back to such an image while batch claims exist.

Rollback sets only `BATCH_PIPELINE_ENABLED=false`. Keep serving reconciliation
and GPU draining on until no admitted jobs/results remain. A content-ledger
`dispatch_protocol=batch_v1` claim survives Redis expiry and rollback; a legacy
retry follows that owner. Do not clear these claims or enqueue legacy twins.
Pending batch claims, audio and unprojected logs have no TTL. C arms completed
ledger retention; D controls artifact and metadata cleanup after projection.

A cohort retry with a preexisting legacy receipt still invokes the canonical
legacy claim/recovery path, including capped/retryable and missing-Redis owners.
Only an explicit existing legacy receipt selects this path; new/ambiguous batch
admission failures never fall through.

A status job uses `bp_` prefix and the stage-qualified `intakes/{job_id}` record.
Polling reads durable queue/ledger state. Legacy job IDs perform no new batch
store lookup and retain their existing response. Cohort intake failures return
503 with audio retained; no fallback worker is started. Late captures receive
202 and append after the committed log tail, preserving their capture clocks.
BYOK cohorts receive a retryable refusal until their worker path is qualified.

## Internal worker RPC

Routes under `/v2/batch-pipeline` require Google service OIDC with exact verified
`BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT` email and
`BATCH_PIPELINE_WORKER_AUDIENCE`. Empty configuration denies requests. These are
service endpoints, never Firebase-user endpoints. All POSTs include explicit
`stage: prod|dev`; mismatches reject before claims. Admission flags are not worker
RPC gates, so already accepted work drains after rollback.

- `POST /pull`: `{stage, limit:1..32, pool:batch|live, capacity:PoolCapacity}`;
  returns `{leases:[LeasedWork]}` using dataclass field names from contracts.
- `POST /heartbeat`: `{stage, leases:[{segment_id,token}]}` (maximum32);
  returns `{accepted:[segment_id]}`. Renew every 20s; any lost/ambiguous token
  invalidates that result. Continue draining CUDA before shutdown/reuse.
- `POST /authorize-compute`: same body as heartbeat; returns `{allowed:[segment_id],
  retry_after:{segment_id:seconds}}`. Rechecks current fresh restrictions or
  reserves the full-content audio upper bound with the existing stable-content
  backfill quota guard, immediately before GPU compute. The seal is lease-token
  fenced and required for completion.
- `POST /complete`: `{stage,token,result:{segment_id,result_uri,outcome}}`;
  returns `{accepted:bool}`. Exact duplicate completion is idempotent.
- `POST /redrive-dead`: `{stage,segment_id}`; redrives historical pending dead
  heads without skipping an ordered gap; returns `{accepted:bool}`.
- `POST /fail`: `{stage,segment_id,token}`; returns `{accepted:bool}`.
- `POST /gpu-idle`: `{stage,gpu_id,token}`; hardware owner only, after CUDA
  quiescence. Expiry/completion never proves a shared GPU idle.
- `POST /reconcile`: `{stage}`; bounded recovery/merge/projection/metrics.
- `GET /metrics`: authenticated Prometheus export and bounded reconciliation.

The dedicated GPU process currently uses the same Scheduler/Pump interface in
process. Projection remains on the backend; GPU image need not import its legacy
conversation/LLM dependencies. Shutdown stops pulling before model drain; do not
cancel a thread wrapper and assume CUDA stopped. Missing results retry, not silence.

## Declared production indexes

`database/sync_pipeline_indexes.py` owns these additions; central registry imports
them and `firestore.indexes.json` is generated. Each shape exists for both
`batch_pipeline_prod` and `batch_pipeline_dev`. All fields below are ASCENDING:

| Collection suffix | Fields | Purpose |
| --- | --- | --- |
| jobs | owner_key, merge_pending, capture_at, segment_id | Ordered pending capture |
| jobs | state, lease_until | Expired lease recovery |
| jobs | state, available_at | Due retry recovery |
| jobs | state, enqueued_at | Result-ready merge repair |
| jobs | priority, state, enqueued_at | Ready queue age |
| jobs | priority, merge_pending, enqueued_at | Pending queue age |
| jobs | next, state | D's linked-queue predecessor repair |
| results | projection_state, committed_at | C's pending/persisted/ready sweep |

Unclaimed pre-admission artifact reservations use a write_pending_until range
on the artifacts collection (single-field). After a two-hour grace, maintenance
marks unattached objects for D cleanup. Admission reads the same reservation and
rejects reclaimed objects, including an uncertain commit racing cleanup. Accepted
audio is detached from this orphan timer atomically and never expires by queue age.

Point lookups need no composite. Owner-key cleanup pages, segment artifact
lookup, artifact cleanup_after range, and reprocess-outbox due_at range use
normal single-field indexes. Executable profiles cover all serving shapes,
including the coalesced reprocess prerequisite. The legacy sequencer indexes
remain unchanged. No index exception or production apply is part of this change.

Before enablement the lead uses the existing create-only index reconciliation
lane, obtains production approval, waits for every required index to be READY,
and passes the exact-source Firestore readiness check. A generated manifest or
an emulator pass is not evidence of production readiness. Missing-index failures
must pause cohort admission; never fail over accepted work into legacy.

## Scale and acceptance

Export `omi_batch_pipeline_ready_age_seconds{priority}` and reject samples whose
`omi_batch_pipeline_metrics_refreshed_at_seconds` is stale. Fresh/recent/deep
age targets are30/300/3600s. Use B's external-metric adapter/HPA; minimum0 needs a
serving exporter outside the scaled-to-zero GPU deployment. Minimum1 is the
initial conservative setting. Cloud Run CPU utilization is not a queue signal;
use Cloud Run minimum one instance and disable CPU throttling for the periodic exporter if its
platform suspends background work between requests.

Before the first cohort, verify pending-age/owner-wait/jobs-per-second plus GPU
utilization, actual full-chain latency/memory, correct client conversations and
playback, content accounting/limits, lineage, deletion and restart/replay. Keep
VAD compaction and shared-live off until their independent quality gates pass.


## Recovery and late captures

Explicit compute failures retry with exponential backoff capped at 600s until
`BATCH_PIPELINE_MAX_ATTEMPTS` (default 5, valid 1–20) is reached. The fenced
terminal quarantine removes the failed span from ordered pending work without
publishing success/silence. Expired leases alone remain recoverable. Successful
siblings of that upload move to `quarantine_held` after persistence, preserving
the projection cursor while allowing the bounded sweep to reach later uploads.
See [the visible transcript gap and retained recovery obligations](batch-pipeline-worker.md#terminal-quarantine-and-the-visible-gap). Alert when
`omi_batch_pipeline_retry_age_seconds{priority="fresh"}` exceeds 600s (same for
recent/deep), scoped by worker_release/namespace; metric freshness must remain
under 60s. Age persists through requeue/lease until success or terminal quarantine.
Historical dead heads are redriven by authenticated `POST
/v2/batch-pipeline/redrive-dead` with `{stage, segment_id}` or by authorized
client job polling, including admission rollback. Those routes never revive terminal quarantines; only the explicit bounded-failure transition skips a gap.
A privacy-fenced lease is separately revoked to `privacy_blocked`; erasure still
belongs to the durable deletion outbox.

Late captures receive the usual202 and keep their original capture time. They
append after the committed predecessor; a separate capture high watermark stays
monotonic. Shipping app `conversations.dart:810-923` recognizes only the existing
`sync_content_in_progress`409; `local_wal_sync.dart:2127-2136` retains files on 202,
and 1756-1762 deletes only completed/synced files. No late-capture409 is emitted.

Control state uses 64 owner-hash shards, selected by indexed per-priority virtual
service, with duration DRR inside each shard. Add these composites for BOTH
batch_pipeline_prod/dev before enablement:

| Collection suffix | Fields ascending | Purpose |
| --- | --- | --- |
| jobs | priority, retry_started_at | first-failure age |
| control | pN_active, pN_service, pN_batch_available_at | dedicated pull, N=0,1,2 |
| control | pN_active, pN_service, pN_live_available_at | short live-pool pull, N=0,1,2 |

These 14 additional composite declarations require production READY evidence;
loopback tests do not prove serving index readiness. A single pull updates only
one shard. Old global rings migrate in bounded recovery transactions; normal
admission/pull never writes the global control document.

Idle-shard activation reads the maximum retained per-class service frontier
through its single-field descending index. No global document is written; an
empty/rejoin cycle cannot reset credit, and an old shard cannot penalize newly
active owners because another shard restarted its virtual clock from zero.

## David-only production config train (2026-10-16)

The production runtime overlay admits only `vi7SA9ckQCe4ccobWNxlbdcNdC23`:
`BATCH_PIPELINE_ENABLED=true`, that single UID allowlist, and
`BATCH_PIPELINE_PERCENT=0`. Code defaults remain off. Development admission,
serving and worker RPC identity bindings are explicitly off/empty. The existing
dev GPU qualification release is independent of this cohort configuration.
Merging config is not a deployment or a successful production E2E receipt.

| Consumer | Deployed host / setting |
| --- | --- |
| `routers/sync.py` → `intake.accept_upload` → `database.batch_pipeline_intake.admit` → `config.batch_pipeline.enabled_for` | Cloud Run `backend`, `backend-sync`, `backend-sync-backfill`, `backend-integration`, and the same backend image on GKE `backend-listen`; identical David-only gate on each |
| `main.py` → `start_serving_from_env` → recovery/projection/cleanup | Only Cloud Run `backend-integration`; existing deployment has minimum three instances and CPU throttling disabled. Other CPU hosts keep the pump off |
| `compute_client.from_env` | Dedicated GPU worker; HTTPS base `https://backend-sync-hhibjajaja-uc.a.run.app`, exact same OIDC audience |
| `routers/batch_pipeline.verify_worker` → spend admission | Only Cloud Run `backend-sync` is configured to accept `batch-pipeline-worker@based-hardware.iam.gserviceaccount.com` with that audience |
| `diarizer.batch_pipeline_runtime` | Separate prod worker chart: process on, two fixed replicas (one L4 node each), autoscaling off, L4 `batch-pipeline-pool`; worker's own upload-admission gate stays false |
| `pusher.main` | No batch upload admission, serving-loop or dedicated-worker consumer; no pusher flag change |

Intake and worker ceilings both stay at 3600 seconds, ASR/segmentation/VAD model
batch stays 8, and shared-live stays off. All CPU admission/projection hosts use
`based-hardware-batch-pipeline-staging` and the existing shared encryption-secret
binding. The worker chart uses the same bucket and explicit customer data plane.
The prod values intentionally leave `image.digest` empty: `gcp_diarizer.yml`
builds the prod image from merged source, resolves its immutable digest and
passes it to Helm. Never paste the dev registry digest into prod values.

Before admission deploy, the operator takes a private raw-document snapshot,
checks source-bound Firestore indexes/TTLs, confirms worker Workload Identity,
data-plane/bucket rights, and Cloud Run invoker access, then deploys the worker
and waits for joint readiness. Deploy the Cloud Run/backend-listen config only
after those gates. No account data, snapshot, IAM grant, index/TTL apply or
workload deployment is performed by this config PR. The local qualification
handoff contains the operator's snapshot, aggregate verification and restore
procedure; snapshots must never enter Git or CI artifacts.

Admission rollback sets the gate false on every sync host and clears the
allowlist/percentage. Keep the worker and integration serving loop running until
all accepted jobs and projection receipts drain. Only then stop the serving
loop/worker before any snapshot restore; otherwise a late projection could
rewrite restored data. Do not delete durable content claims to force a retry.
The 14-day snapshot covers only its recorded conversation IDs: targets outside
that set and post-snapshot live/user edits require their own before-image or
manual reconciliation, never an assumed full-account restore.

## Quarantined segment recovery

`BATCH_PIPELINE_RECOVERY_MODE=off|on` defaults to **off**. Even `on` admits
nobody without `BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST`. It is independent of new
batch admission. The existing serving pump runs one legacy STT dispatch per
allowlisted owner per sweep. Operators/schedulers can also call the existing
`POST /v2/batch-pipeline/reconcile` with `{"stage":"prod"}` using its configured
worker service-account OIDC identity and audience. The metrics endpoint performs
ordinary reconciliation only; scraping metrics never initiates legacy STT.
No laptop script, public client route, upload-wide legacy coordinator, or claim
release is involved.

The job embeds a durable recovery intent (random token, epoch, admitted privacy
generation), created only for `worker_failed` quarantine with no result/log or
assignment receipt and no active GPU lease. CAS moves `prepared` to `running`
once, rechecking privacy and the retained batch content owner. Expired ordinary
leases or historical status polls cannot authorize recovery. The unit's registered
encrypted audio goes directly to `utils.stt.pre_recorded.prerecorded_from_bytes`
with client retries disabled (`attempts=2`). Local strict Silero VAD measures
speech usage; it does not estimate usage from transcript text or capture length.
Empty VAD/STT or invalid clocks remain failures, never fabricated silence.

The encrypted output uses the intent token as its create-only object name,
registered with the erasure outbox before upload. Lost upload replies reconcile
that exact authenticated generation. A recovery-specific token CAS returns a
successful unit to `result_ready`; the ordinary owner log then appends it under
its original segment identity and capture clocks, with the existing late-capture
policy. Assignment replay uses the same batch receipt, part IDs and ledger.
Once every sibling assignment/enrichment receipt is ready, the existing
idempotent upload accounting completes, held results re-enter the sweep, and
client publication/retention resume. Failed sibling obligations never arm a
success TTL.

There is no provider idempotency key in the synchronous legacy API. Therefore a
process death after `running` commits and before a durable encrypted result is
available is **ambiguous**, not permission for a second STT call. While running,
other deliveries only look for that object; after 900 seconds with no object the
intent becomes `failed_held`. A provider exception also becomes `failed_held`.
Neither is automatically redispatched or scanned again. A successful artifact
whose DB reply was lost remains reconcilable. A late reply after terminal hold
cannot publish. Recovery logs have only a closed outcome; no owner IDs, URIs,
tokens, transcript/audio, or exception bodies. Privacy deletion/protection
changes cancel the intent and override audio retention at every boundary.

Rollout (operator-owned, not performed by this PR): first apply/verify the declared
owner/recovery-state indexes and deploy the reviewed source. Set recovery mode on
with **David's owner only** in the recovery allowlist on the serving pump host.
Run one bounded reconciliation, verify recovered assignment receipts and original
clocks/late-capture append, then all sibling receipts, one upload usage commit,
client completion and completion-only retention. Inspect content-free counts and
any held failures. Leave recovery on for that owner for future quarantines after
verification. Roll back to off to stop new dispatches; accepted normal
projection still drains. Failed/ambiguous intents require a separately reviewed
operator decision, never a blind reset to prepared.

### Client status for held uploads

The upload ledger stays `processing` while a unit is held. The status poll and a
re-upload of the same content (`durable_status`) used to answer `failed` with
`batch_worker_quarantined`; the phone re-uploaded, received the same answer and
looped. Kill switch `BATCH_PIPELINE_HELD_TERMINAL_STATUS_ENABLED` (default on)
answers instead:

- `completed` with an empty result and `reason_code: batch_unit_held` when every
  failed unit is `failed_held` with no open `speech_redrive`,
  `terminal_disposition` or `silence_disposition` intent, and every other unit
  is `committed`. Released apps ACK the WAL. A re-upload cannot change the
  outcome, and the held unit's encrypted audio stays server-side for the
  operator path above. Committed siblings are already projected; no
  conversation ID is named. Nothing is written: the ledger, jobs and
  retention keep their held state.
- `processing` when such an intent is open or a sibling is still in flight.
- Any other quarantine failure keeps `failed`/`batch_worker_quarantined`.

### Held uploads complete as partial

David ruled on 2026-10-20 that held uploads complete as partial on the ledger.
Kill switch `BATCH_PIPELINE_HELD_PARTIAL_ENABLED` (default on). Every 300 s the
serving maintenance leader scans up to 32 `held`/`failed_held` jobs
(`Projector.sweep_held`). It completes an upload as partial once every unit
without a projection receipt is **held with no recovery path left**:
`failed_held`, or `held` with a recorded recovery policy that is off and no
`recovery` intent. A unit with an open `speech_redrive`, `terminal_disposition`
or `silence_disposition` intent still blocks it. Every other unit must have a
`ready` projection receipt or be erased.

- **Ledger.** `status: partial` with `result.outcome: partial`,
  `failed_segments == held_segments` (the held span) and the projected
  siblings' visible conversation IDs. These go through the same redirect and
  privacy fences as completion. `usage_committed_seconds` records the projected
  speech that was charged, and `usage_steps` every charge boundary
  (`[0, s1, s2, …]`). The held span is never charged. Hourly usage commits in
  the partial transaction. Fair use records only after the commit, and every
  record (a scan replay, a newer partial, the ordinary upgrade) re-issues each
  stored step under its own once-key (`<content_id>` for the first,
  `<content_id>:<start_ms>` after). A Redis write lost after any commit
  therefore lands once on a later attempt, as long as that attempt comes
  within six days. `usage_step_times` records each step's commit. A step older
  than the fair-use once-key TTL (8 days) less a 2-day margin, or with no
  recorded time, is never re-issued: its key may have expired, and that speech
  is outside the 7-day fair-use read anyway. Accounting returns nothing
  while any unit can still change, so an ineligible upload is never charged.
- **Client.** The status poll and a re-upload answer `completed` with
  `reason_code: batch_unit_held`, the partial result, and
  `failed_segments` set to the held count. Released apps ACK the WAL. A
  conversation the user has since deleted answers `conversation_deleted`, as
  it does for a completed row.
- **Nothing else moves.** There is no provider call, and no job, intent,
  merge-head, owner-revision or retention write. The held units' encrypted
  audio stays for a reviewed redrive, and parked siblings keep
  `quarantine_held`. Nothing is published to the legacy Redis job, because its
  fence takes only all-success results.
- **Upgrade.** A partial row stays owned by its batch job:
  `batch_projection_ledger_owner_matches` accepts `processing` and `partial`.
  Recovery, the operator redrive tools and the ordinary completion therefore
  still run. When a held unit recovers, its projection completes the upload,
  the ledger becomes `completed`, and only the remaining speech is charged
  (hourly usage, plus fair use keyed `<content_id>:<charged_ms>`). If other
  units are still held, the next scan rewrites the partial with the smaller
  held span. A completed row is never re-partialed. Partial writes are
  idempotent: a replay of the same state writes nothing.
- **Rollback.** Setting the kill switch to false stops new partials. Existing
  partial rows keep answering `completed` and can still upgrade.

The record lane's capture listing (`list_audio_chunks(require_archive=True)`)
raises when the raw-archive pack listing fails. It never returns only the
legacy chunks, which would admit a recording whose later packs are silently
missing. The admission retries in 60 s. Conversation merge uses the same mode,
because it deletes the source audio after the copy.

Completed content whose conversation the user has since deleted answers
`completed` with an empty result and `reason_code: conversation_deleted`, on
both the poll and the re-upload claim (a legacy receipt re-upload answers the
synchronous all-success 200 shape). Every other privacy denial keeps its 409.

A unit admitted while recovery was off records `recovery_enabled=false` and used
to sit `held` forever. Kill switch `BATCH_PIPELINE_RECOVERY_POLICY_REFRESH_ENABLED`
(default on) lets the sweep and dispatch re-resolve that part while the unit is
`held` with no `recovery` intent (no paid call authorized). It adopts the fresh
part only when it is enabled; an enabled snapshot is never re-resolved.

### Dark empty-ASR disposition

`BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED=false` is the default on all roles.
Enable on the GPU worker and the CPU recovery host together after releasing the
same reviewed source. With the flag on, exhausted padded `empty_asr` and
`no_owned_words` both use the existing per-unit recovery handoff. The worker's
pyannote speech prediction and words outside a window core do not authorize
silence. CPU recovery checks the canonical unit with strict local Silero VAD:

- Affirmative no-speech emits the ordinary encrypted silence result. There is no
  provider dispatch or paid allowance requirement. Ordinary ordered merge,
  assignment receipts, all-sibling accounting and client publication still own
  completion; no completion fields are fabricated.
- Speech uses the existing legacy prerecorded client once, with client retries
  disabled. Failed/empty/invalid output remains held. The existing intent token,
  privacy checks, run owner and ambiguous-call fence remain authoritative.
- Decode/VAD failures remain failures. Nonfinite/out-of-range model probabilities
  are rejected. No empty ASR or out-of-core word clocks alone become silence.

Recovery failures persist `recovery.failure={stage,reason}`. Stages are
`audio_validation|strict_vad|provider|response_validation|payload_validation`;
reasons are closed codes defined in `recovery_disposition.py`. The content-free
`event=batch_recovery_failure` carries those two codes only. Original exception
bodies, words, identifiers, artifact references and tokens are never emitted.
A running intent abandoned after 900 seconds records `provider/abandoned_running`.

For historical `failed_held`, use
`scripts/batch_pipeline_held_disposition.py --stage prod --owner-env DAVID_UID
--quarantined-before <UTC-cutoff> --expect-count <count>` in an existing secure
runtime with `ENCRYPTION_SECRET` and `BUCKET_BATCH_PIPELINE`. Dry-run requires the
`ro-prod` tier and uses read-only transactions/GCS reads; audio is decrypted and
evaluated only in memory. It prints aggregate silent/speech counts, fraction and
a digest binding owner, cohort, immutable audio generation/run/privacy metadata
and classification. No secret retrieval, STT call, user API call or temporary
media file is involved. Missing secure material fails before cloud data reads.

Apply requires `prod-operator`, the flag on, the same recovery owner allowlist,
`--approve-plan-sha256 <reviewed-digest> --apply`. The default fixed prefix is one
silent unit; repeated commands target the same prefix. `--apply-limit <count>`
expands that prefix only after explicit approval. All units are checked again
before apply, and each silent unit is reclassified immediately before its CAS.
The operator creates a separate no-provider `silence_disposition` intent; it
never resets or modifies the original spent paid-STT intent. Its create-only
artifact token reconciles lost upload replies. A token/privacy/run-fenced CAS
restores `result_ready/merge_pending` with a silence result; the existing serving
sweep then drains it. Speech units stay held: their permitted fallback has
already been spent, so replaying paid STT would violate the no-double-call rule.

Rollback disables new dispositions on both hosts. Already persisted silence
artifacts retain their silence outcome during reconciliation even after flag
rollback. Keep ordinary serving/merge/projection draining; never clear paid
intents, claims or receipts. Stop an operator command to stop further units;
already committed completion is not reversed.

### Independent multilingual recovery for speech-empty units (dark)

`BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED=false` keeps the existing
recovery route. With it enabled on the CPU recovery host, a strict-VAD-positive
unit uses the existing Modulate prerecorded client directly, once, with
`attempts=2` (no recursive client retries). It does not return to the failed
Parakeet model when the intake language is unset. Silence still requires the
strict local VAD evidence introduced by `EMPTY_ASR_DISPOSITION`; an empty
alternate response remains `failed_held`. The existing recovery paid-intent,
privacy, allowance, result, merge and projection fences remain authoritative.
This change needs a backend/integration image release; no GPU model or decoder
change is required. Keep the new flag off until an owner-scoped canary succeeds.

`backend/scripts/batch_pipeline_speech_redrive.py` is the historical operator.
It requires one owner, a UTC cutoff, the **full original strict-VAD census
SHA256**, exact total/speech counts and explicit `--paid-epoch 2`. It caps the
approved set at 67 speech-positive units and scans at most 1000 owner jobs. The
new plan digest binds the original census (including immutable audio/run/privacy
bindings), alternate provider, operation and paid epoch. Dry-run uses only
read-only Firestore transactions and encrypted audio reads, with at most four
concurrent read operations. It never calls STT or registers/writes artifacts.

Apply also requires `--approve-plan-sha256`, the new flag and the existing
recovery owner gate. Its default `--apply-limit 1` always selects the same sorted
speech prefix. A separate `speech_redrive` intent preserves the original
`recovery` map verbatim, records paid epoch 2, and uses CAS to spend the one new
provider call. Prepared intents can resume; running intents only reconcile their
create-only encrypted result. An uncertain/lost provider response stays held;
after 900 seconds it becomes terminal without another call. A lost storage reply
can reconcile the deterministic artifact. Increasing the limit to 67 includes
already-attempted canary receipts rather than selecting 67 additional units.
Successful results use the ordinary merge/projection/client completion path.
The silence operator refuses a job that already has a speech-redrive intent.

Supply secrets using the existing secure runtime injection; scripts never fetch
or print keys. Tier names do not grant permissions: the current `ro-prod` cannot
read the batch bucket, and `prod-operator` cannot write Firestore. The lead's
existing human-tier secure runner can supply both the encryption secret and,
for apply only, the configured Modulate key. The operator accepts that tier and
still enforces all owner/digest/privacy/CAS fences. Do not substitute a user's
public API token or call `api.omi.me`.

Rollback disables `BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED` and stops the
operator. Do not erase or reset either paid epoch, content claims or result
receipts. Disabling the flag prevents new dispatches; an already-running provider
may finish. Completed transcripts are real historical writes and are not undone
by a flag rollback; correct them only through the normal reviewed content path.

### Terminal empty recognition (dark)

`BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED=false` is the CPU recovery
kill switch. Deploy the worker from the same change first: its exhausted
`RecoveryWork` now persists `worker_empty_evidence.padded_retry=empty` under the
lease CAS only when the GPU padded retry actually ran and returned empty; units
whose padded length exceeds `min(120, max_padded_seconds)` (>116s) skip that
retry and persist `worker_empty_evidence.padded_retry=skipped_oversize`. A
zero-word unit with at least 5 s of worker VAD speech whose intake-recorded STT
language (`stt_language` in the staged context) is unknown, `multi`, or outside
Parakeet TDT v3's set skips the retry too and persists
`worker_empty_evidence.padded_retry=skipped_long_speech`: repadding cannot make
Parakeet transcribe a language it lacks, so the unit goes straight to recovery
(`BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED`, kill switch, unset is on). Recovery
pins/persists its provider before dispatch. With the flag on, positive strict
local VAD, affirmative GPU padded-empty evidence, and a validated empty
**multilingual** response produce `no_recoverable_speech`. Oversized and long-speech units that
skipped the GPU padded retry still run strict VAD and multilingual recovery, but
an empty multilingual response from Modulate alone stays `failed_held` rather
than terminal-empty. Timeouts, malformed responses, uncertain calls, missing
evidence, and provider failures stay held. There are no paid-intent resets.

**Second multilingual provider (long-speech units) — retired 2026-08-27.**
This step used to spend exactly one more call, to cloud Deepgram nova-3 with
language detection (`second_transcribe`), inside the same `running` intent.
Deepgram is retired (no contract since 2026-08-27), so
`config.stt_provider_policy.HELD_RECOVERY_SECOND_PROVIDER` is `None` and
`second_provider_eligible` answers False for every unit: no second call is
spent, and an empty multilingual Modulate response settles `failed_held`
(Modulate-only recovery, the same behavior as
`BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED=false`). The wiring, flag and
metering stay so a future second batch provider can be introduced by naming it
in the policy again. Historical behavior, kept for reference:

- Deepgram returns words: the unit recovers with those words (ordinary
  `success` result).
- Deepgram also returns valid-empty: with the terminal-empty flag on, the unit
  settles `no_recoverable_speech` with `recognition_evidence`
  `{gpu_padded_retry: skipped_long_speech, multilingual_recovery: empty,
  second_multilingual_recovery: empty}`. This is the honest outcome. No one may
  listen to the audio, so the pipeline has to settle it on evidence: VAD saw
  speech-like energy, and two independent multilingual ASR systems, with
  different models and language coverage, both found no words in it. It is the
  same quality of evidence as GPU padded-empty plus Modulate-empty. Another
  `failed_held` would only say "unknown", and nothing would ever retry it.
- Deepgram errors, times out, returns a malformed answer, or the allowance
  refuses: the unit stays `failed_held` with Modulate's
  `response_validation/empty_asr` failure, as before.

A crash between the two calls leaves the intent `running`. The 900 s abandonment
rule then settles it `failed_held` without another call. Each long-speech empty
costs at most one extra Deepgram call of the unit's duration. Metering:
`omi_batch_recovery_second_provider_total{provider=deepgram,outcome=words|empty|error|refused}`,
the log `event=batch_recovery_second_provider provider=deepgram outcome=...`,
and `omi_stt_cap_provider_audio_seconds{path=sync,outcome=accepted}` for both
paid answers (`provider=modulate`, now also for valid-empty answers, and
`provider=deepgram`). `BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED=false` (kill
switch, unset is on) restores Modulate-only recovery.

This is an empty-words **terminal degradation**, distinct from silence. The
encrypted result retains validated positive VAD and closed recognition evidence.
Projection validates that artifact, assigns no words for the span, and resumes
normal ordered merge, sibling publication, ledger/client completion and retention.
This span contributes **zero transcription usage**, while the existing captured
seconds correctness counter records `event=no_recoverable_speech`. The structured
log is `event=batch_terminal_empty stage=response_validation
reason=no_recoverable_speech`; shared fallback telemetry reports `degraded`.
Completed upload responses retain the compatible `success` outcome and add
`no_recoverable_speech_segments`; an empty exhausted upload is never reported as
`expected_silence`. Existing completed results remain readable after flag rollback.

Historical tool: `backend/scripts/batch_pipeline_terminal_empty.py`. It is
one-owner, cutoff/count-bounded (at most 20), read-only by default, and digest-bound.
Use `--metadata-only` with `ro-prod` for fence/eligibility counts without audio or
secrets. Full dry-run needs securely injected `DAVID_UID`, `ENCRYPTION_SECRET` and
`BUCKET_BATCH_PIPELINE` plus batch-bucket read permission. `ro-prod` cannot read
that bucket; `prod-operator` currently cannot write Firestore. The lead's existing
authorized secure runner is required for full census/apply; never print runtime
material or use a user API. No secret fetching is embedded in the tool.

For old rows lacking provenance, `--attest-pre-provenance-exhaustion` explicitly
attests the reviewed padded-empty evidence and the multilingual-empty provenance
of legacy `response_validation/empty_asr` intents. This declaration, all original
paid intents, VAD decisions, owner, cutoff and any canary epoch are digest-bound.
It never treats generic failure as empty. The old GPU canary's **spent** epoch 1
remains intact: strict no-speech creates silence without STT. Positive VAD selects
`canary_recovery`, requiring explicit `--canary-paid-epoch 2` in both the dry-run
and approved apply. That is at most **one** independent Modulate call, with normal
provider/cap/privacy/CAS fences. Words publish normally; a definite empty response
becomes terminal-empty; an uncertain call stays held. This is separate from the
previous authorization for 67 other units. Do not enable a canary paid epoch
without the owner's authorization.

```sh
# Existing secure runtime injection; no credentials or owner printed.
nice -n 19 backend/.venv/bin/python backend/scripts/batch_pipeline_terminal_empty.py \
  --stage prod --quarantined-before 2026-10-17T10:30:00Z --expect-count 6 \
  --attest-pre-provenance-exhaustion
# If the canary is VAD-positive and epoch 2 is authorized, repeat the dry-run with
# --canary-paid-epoch 2. It changes the approval digest.
# Then repeat the SAME arguments plus --apply --approve-plan-sha256 "$PLAN" \
# --apply-limit 1; validate the canary, then increase the fixed prefix to 6.
```

Keep intake paused during this repair. Enable only the new terminal flag on
integration after deploying CPU and worker artifacts, retaining strict disposition,
multilingual recovery, serving/recovery and the existing owner fence. Do not
replace environment files or reset intake defaults. Rollback disables the new
flag and stops operator invocation; committed projections are not undone and
spent intents never become retryable. Inspect completion and terminal-empty
captured-duration rates before any ramp: terminal completion does not prove ASR
quality or make the unresolved duration disappear from correctness metrics.


## Dark projection tail controls

`BATCH_PIPELINE_HEAD_PRIORITY_ENABLED=false` and
`BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED=false` are independent accepted-work
controls, declared on the backend services and listen Helm values. They do not
admit new work or change recovery spend policy. Enable only on the qualified
5% cohort's serving/worker RPC host after release approval; neither is enabled
by this change. Rollback each to false; ordinary queue links and existing
persisted/ready receipts remain compatible with the synchronous path.

Head priority splices the owner's earliest `merge_pending` job to the front of
its existing priority queue when it is ready and found within a shared budget
of 64 head-query/link reads per shard transaction. Duration, eligible unit kind
and privacy must pass before any link changes; a head this pool cannot lease
leaves FIFO intact. The selected job still pays its actual DRR cost, passes privacy checks, and respects
fresh reservations, duration and shared-GPU capacity. It never steals a live
lease, changes priority class, invents silence, or resolves an uncertain paid
intent. Outside the bounded search it retains FIFO. Quarantine already removes
`merge_pending`, so a held quarantine unit is not an ordered-merge blocker;
settled recovery re-enters the pending set. A slow leased head must finish or
follow the existing fenced lease/recovery protocol.

Async projection keeps capture-ordered commit and the transactional predecessor
check unchanged. Only assignment (including all multipart receipts) holds the
owner claim. Its atomic persist advances the projection watermark; a later
unit can become visible only after every committed predecessor has persisted
(or its privacy erasure receipt permits progress). Captures admitted after a
later commit retain the existing explicit `late_capture` behavior. No disjoint
segment independence is assumed.

Assignment excludes `deleted_conversations` tombstones transactionally, even
when a failed DELETE left the conversation row live. If plan validation finds
deleted ancestry, one read-only re-plan excludes the denied source and its
carriers. If donor ancestry still refuses, the input's complete speech is
projected into a new deterministic identity with no inherited donor ancestry.
A no-text, zero-speech superseded receipt with `privacy_reason=conversation_deleted`
requires a transactional tombstone proof on the unit's own source/target or its
guarded redirect chain. A donor refusal alone never authorizes dropping input.
The final part advances the owner watermark; unrelated later captures continue.
An ID-free completion carries `reason_code=conversation_deleted`. Settlement
rechecks immutable binding, ledger ownership, predecessor, account and privacy
generation. No deleted source is projected.

Other recognized mutation privacy refusals (account deletion/missing account,
protection or generation changes, recording consent, redirect cycle/missing
target and the 256-document fence budget) settle as a separate **held ordering
receipt**. The same transaction rechecks the actual refusal, immutable result
binding, ledger owner and predecessor. It writes only batch control metadata,
retires follow-ups and advances ordering once; it cannot write conversations,
the user ledger, usage, derived content or audio. The original worker result,
audio identity and existing part progress remain. Unknown reasons and lost
result leases still fail closed. An unrelated donor graph/budget refusal first
tries an isolated input-only plan under all ordinary privacy fences.

Privacy holds retain `quarantine_held`, so the existing unfinished-obligation age
metric includes them. They are not client success or measured silence; unknown
held speech remains unknown. Protocol 2 plus a versioned privacy checkpoint
fences older projectors, and persisted part states retain their previous values
for repair. The owner repair planner discovers these holds and binds their
control state into its reviewed digest; unpinned policy still refuses operator
apply. After the fence is repaired, ordinary serving projection rechecks all
privacy/ownership fences, restores prior progress and reuses the retained result
without another recognizer call. Replaying an older held unit never rewinds a
newer owner watermark. No admission or runtime flag is changed by this logic.

Cascade DELETE acquires the account destructive-operation gate before writing
the conversation tombstone. Its post-intent retraction check and nested memory
retraction run under that gate. A busy gate returns the existing retryable 409
before any intent or cleanup is written; successful DELETE remains HTTP 204.

### Bounded merge head wait

David ruled on 2026-10-20 that catch-up uploads may publish newer parts of a
recording first and fold older parts in late, with a bounded wait. The app
uploads its pending backlog newest-first, so capture order and arrival order
are reversed for every catch-up owner.

`BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS` (default `60`; `off` or `<= 0`
restores strict capture order) bounds how long a ready result waits behind an
unready earlier-captured merge head. `complete` and every recovery re-entry
stamp `ready_at`. When the owner's longest-waiting ready row has waited at
least W, the merge commits the owner's ready rows in capture order past the
head. The head later appends at the log tail as `late_capture`, exactly like a
recovered quarantine. Rows without `ready_at` (written before this change)
never start a bypass. A bypass commit carries `head_wait_bypass: true` and logs
`event=batch_merge outcome=head_wait_bypass` with the head state and a wait
bucket, never an ID.

The strict commit transaction issues no new query. When it finds the head
unready, a non-transactional probe (`merge_ready_age` index) reads the owner's
longest waiter, so a still-waiting owner takes no extra transactional query
lock. Only an expired wait opens a second transaction, which re-reads the
waiter, selects the earliest-captured ready row (`merge_ready` index) and runs
the unchanged commit body. Without either index the merge records a
`firestore_read` fallback, logs `outcome=head_wait_unavailable` and keeps strict
order for five minutes. An owner-wide privacy fence that refuses the released
row leaves the owner blocked exactly as strict order would.

The commit body is unchanged: the append-only log chain, `log_sequence`,
watermark and late marking, owner revision fence, owner-serial projection in
log order, sibling completion, billing and privacy fences all hold. Fresh
traffic keeps capture order because attempt-1 compute finishes well inside W.
Log order can differ from capture order (bypassed heads are `late_capture`);
the committed result set, the final watermark and the projected conversations
converge to the strict-order state. Only intermediate states change:

- a conversation can appear with its newest part first, then grow backwards
  (earlier start, more transcript at the top) as older units land;
- a late bridging unit can briefly leave two conversations that later merge
  through the existing donor redirect;
- a summary generated on the partial conversation is regenerated through the
  coalesced reprocess outbox, and a short early fragment marked for review is
  promoted when meaningful content arrives;
- no visible first-summary push exists on the batch path; action items found
  in the partial transcript can sync silently and keep their identity across
  the regeneration.

### Fresh-first merge and GPU priority

David's fresh bar (2026-10-20): an upload whose capture ended at most 10 minutes
before admission reaches a conversation within 2 minutes p95, and is never held
by the same owner's catch-up backlog. Admission stamps `fresh_capture` on each
job from its capture end; record-lane units are classified the same way. Rows
written before this change carry no stamp and keep the plain ordered merge.

`BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH` (default `16`; `off` or `<= 0` restores
the plain ordered merge) adds two rules to commit selection, never to the
commit body:

- a catch-up commit waits while the owner already has this many committed rows
  awaiting projection (`log_sequence` minus the projection watermark row's).
  Projection stays owner-serial in log order, so a fresh row lands at most this
  many rows behind the projection head instead of behind the whole backlog.
  Privacy erase keeps `log_sequence` on the erased result so an erased
  watermark still counts; a missing watermark row never holds a commit. Every
  pump re-offers the owners it held on its 5-second maintenance tick, and the
  serving pass re-offers its own after the projection sweep. Any strict attempt
  that finds the owner at the cap with rows pending, whatever the head's state,
  also sets a durable `{namespace}_merge_holds/{owner_key}` marker (no user ID;
  owner purge deletes it). Leader maintenance pages through the markers with a
  rotating cursor, re-offers each owner, and clears a marker only once the
  owner is below the cap or has nothing pending, so neither a restart nor a
  held backlog filling the global `result_ready` page can hide a held owner;
- when a catch-up row heads the owner and the strict commit does not go
  through, a non-transactional probe reads the owner's earliest pending fresh
  rows. The earliest one commits as soon as it is ready, in a second,
  re-verifying transaction; its catch-up predecessors append later as
  `late_capture`, exactly as under the bounded head wait. Fresh rows keep
  capture order among themselves, except that once a later ready fresh row has
  waited the head-wait bound behind an unready earlier one, the earliest ready
  fresh row commits (`head_wait_bypass` too). The commit carries
  `fresh_first: true` and logs `event=batch_merge outcome=fresh_first` with the
  head state only.

The `merge_fresh` job index backs the fresh probe; without it the merge logs
`outcome=fresh_first_unavailable` and keeps the plain order (no hold, since a
hold would also hold fresh rows) for five minutes.

`BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED` (default on; `false` restores
`FRESH` for the whole lane): the sync fresh lane admits audio up to 6 hours
old, and the owner's GPU FIFO is per priority. Uploads in that lane whose
oldest capture is over 10 minutes old are admitted at `RECENT`, so they lease
after fresh uploads rather than ahead of the same owner's fresh audio. GPU
spend admission picks its policy from the upload's recorded lane, not the
priority, so these rows keep the fresh-lane fair-use checks (hard restriction,
daily audio ceiling) and never draw on the backfill speech budget.

### Recovery dispatch loop

`BATCH_PIPELINE_RECOVERY_DISPATCH_INTERVAL_SECONDS` (default `5`; `off` or
`<= 0` dispatches only from the serving pass): the serving runtime runs the
quarantine recovery sweep on its own loop beside the serving pass, on the
maintenance leader only. The pass (maintenance, projection sweep, then a
20-second sleep) had put quarantine -> recovery prepared at p50 52 s and p95
97 s. A per-instance lock keeps the pass and the loop from scanning at once.
The candidate scan restarts after a short page; resuming after the last ID of
a short page skipped every earlier candidate, new quarantines included, for a
whole pass.

The serving supervisor, explicit reconcile RPC, and metrics reconciliation all
use the same async coordinator. Their pass persists the bounded pending page,
then schedules at most four tracked follow-ups per process without awaiting
slow effects. A finished task immediately refills its slot from the bounded
page, without an additional 20-second serving sleep. Each follow-up coordinator
has a 120-second deadline, plus at most two seconds for advisory-claim cleanup.
Timeout cancels its remaining steps and frees the slot without closing the drain;
the unchanged persisted/ready receipt is retried on a later sweep. Already-running
executor calls cannot be forcibly stopped by asyncio cancellation and may finish
late; receipt/enrichment and ledger transactions retain their replay fences.
Shutdown cancellation stops refill. Persisted result receipts are the durable outbox. Partial
assignment rows do not consume follow-up slots; a rotating cursor prevents
repeated failures at the front of the page from monopolizing those slots.
A separate advisory segment claim coalesces replicas; it never owns the
assignment watermark. Each bridge, playback and enrichment step is offloaded
separately. After playback a second bridge check copies any late donor audio
if a concurrent assignment redirected the target. Native records retain their
fixed target behavior. Privacy checks and the original retained-audio policy
remain in effect. Enrichment and the ready receipt still commit together;
usage/client/content completion still requires every sibling ready and commits
atomically in the content ledger. Completion is retryable after a lost reply,
process restart, or rollback, without retranscription.

Qualification target: quarantine to **completed content ledger** p95 <=300s
for all units in the fixed fleet 5% admission cohort, including pending ages.
This removes queue inversion and owner-wide external-work serialization; it
is not a numerical production latency guarantee. A live head can renew its
lease, external effects can exceed the budget, a crashed advisory claim can
last 300s, and the existing 100-row sweep page can be saturated. Do not add
stage p95s or exclude held units. Measure the full cohort for at least one hour
with phase timings before claiming the target or increasing admission.

### Projection discovery progress

`BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED` defaults to `true` (kill switch:
`false` restores oldest-100 discovery). Assignment and async follow-ups each
advance their own bounded 100-row keyset scan across pending, persisted and
ready results. The cursor uses `(committed_at, document ID)`, so equal timestamps
and deletion of the cursor row cannot pin a page. End-of-scan wraps to the head;
restart begins at the head without dropping any durable obligations. Follow-ups
launch the whole bounded page before fetching the next one. Discovery order is
only a hint: existing transactional predecessor, privacy, all-sibling readiness,
receipt replay and paid-intent fences remain authoritative.

The query reuses the declared prod/dev results composite index:
`projection_state ASC, committed_at ASC, __name__ ASC` in
`database/sync_pipeline_indexes.py` and the generated `firestore.indexes.json`.
No new index or production index mutation is needed.

With accepted-work serving enabled, committed pending/persisted/ready debt is
rediscovered automatically after deployment; no one-time kick is needed for the
page deadlock. `quarantine_held` obligations still require their ordinary fenced
recovery to succeed; pagination neither retries uncertain paid intents nor
resolves genuine held quarantines. Monitor falling pending age/count and durable
content/client completion on the deployed release before expanding admission.

### Owner-chain wake after recovery

`BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED` defaults to `true` (kill
switch: `false` restores the generic sweep after recovery). A settled recovery
re-enters the ordered merge and commits at its owner's log tail, behind that
owner's unprojected rows, which the per-instance cursors may already have
passed. Waiting for the assignment and follow-up cursors to come back around
took 5–12 minutes for one backlog owner during the 5% ramp. After
`/recover-quarantine` returns `recovered` or `reconciled`, the handler's
reconcile now drains that owner's merge and walks the owner's result log from
its `projection_watermark`, following `previous_segment_id` links (and erased
receipts) in chain order. It stops at the first row whose assignment does not
advance the watermark, or after 64 rows or 30 seconds. The generic sweep runs
afterwards as before, and any error in the wake falls back to it.

`BATCH_PIPELINE_RECOVERED_MERGE_RELEASE_ENABLED` defaults to `true` (kill
switch: `false`). The wake's merge drain releases the recovered unit at once.
Without it, a recovered unit whose owner had an unready, earlier-captured
head waited out the head wait from its settle time (`ready_at`) plus a
maintenance tick. In the 2026-10-20 5% run 18, 46 of 54 wakes advanced no row
and held recovered units took 65–86 s from settle to commit; projection then
waited for the next 20 s sweep. The wake passes a release set: the recovered
unit, then up to 32 of its content's other units. When strict order,
fresh-first and the head wait commit nothing, the first row in the set that is
still the owner's pending, ready job commits past the head wait; the commit
transaction re-verifies the row. Only the recovered unit itself also passes
the catch-up depth hold; its siblings keep it, so a wake cannot push a burst
of catch-up rows past the cap ahead of a later fresh row. The
commit body, late marking, log chain and projection order are unchanged, and
an unready or fenced row is dropped from the set. Release commits carry
`recovered_release: true` and log `event=batch_merge outcome=recovered_release
source= head_state=` (closed labels only). `python -m
testing.recovered_release_scenario` replays the run 18 shape.

The walk is only a wakeup. Each row still passes the transactional predecessor,
privacy, receipt-replay and owner-claim fences, so ordering is unchanged. For
async projection, the persisted rows and their contents' persisted, not-ready
siblings go to the front of the follow-up queue. The recovered unit's content
goes first. The four-slot bound, segment claims and all-sibling completion
fence are unchanged. The successor lookup is two equality filters ordered by
`__name__` on `{namespace}_results`, which automatic single-field indexes serve.
Two matches fail closed.

### Sweep owner-chain continuation and pending-only assignment page

`BATCH_PIPELINE_PROJECTION_PREDECESSOR_REPLAY_ENABLED` defaults to `true`.
When a discovered successor lacks a predecessor projection receipt, the sweep
requests the owner's existing drain, or runs one bounded owner-chain walk when
the drain is off. The walk starts at the projection watermark, rebuilding the
missing predecessor before retrying successors in the same pass. This also
works when the assignment cursor has already passed the head. `false` restores
the previous blocked-page behavior. Binding, privacy, predecessor, replay and
multipart fences remain authoritative; a head blocked by one of those fences
still requires that underlying condition to be resolved. Already committed
work does not need another GPU run.

`BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED` defaults to `true` (kill switch:
`false` restores one attempt per page row). Rows from one owner's ordered chain
used to advance only while a sweep page held that owner's head. During the
2026-10-20 run 10, one owner's 190-segment burst sat idle about 60% of the time
between pages (3.2 rows/min). When the sweep now persists a row that was
`pending` when read, it calls the same walk the recovery wake uses, from that
owner's `projection_watermark`. Bounds: one walk per owner per sweep, 64 rows
and 30 seconds per walk, and 30 seconds of walking per sweep across all owners, starting with the
first walk. Page rows the walk persisted are skipped without a read and are
left out of the sweep's counts; the chain summary reports them. Every other page row,
including rows past a walk that stopped at its bound, is attempted in page
order as before. Each walked row still takes the Redis owner claim and the
transactional predecessor, privacy and receipt fences one at a time, so no
owner gains concurrency. Every async row the sweep persists is owed a follow-up, the page's own rows as
well as the walk's. The page row seeds its owner's walk. Later page rows of
an owner already walked, and rows reached once the shared budget is spent, get
a seed-only hand-off: one watermark read, no sibling scan, nothing persisted.
A walk's scan for a content's persisted, not-ready siblings stops at the walk
deadline; unscanned siblings stay durable and are rediscovered. A seed is owed only
if the watermark shows it advanced (a partial multipart did not), or if the
watermark cannot be read. Owed rows do not use the wake's priority
queue. They are held (at most 256, durable either way) until the next
follow-up discovery pass and queued behind its page, without moving its
rotation. Serving keeps scheduling follow-ups while any are owed, and a pass whose
queue drains on launch runs discovery at once. An overflow past the bound
restarts follow-up discovery at the head. So owed rows are never stranded
behind the discovery cursor, and they never jump discovered work or keep
discovery from running. A read failure inside a walk ends it with the rows it
already persisted still handed off. The finish page skips rows
this sweep already assigned or finished. The log line is `event=batch_projection action=sweep_chain
outcome=summary owners=N advanced=N`.

`BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED` defaults to `true` (kill
switch: `false` restores the single mixed assignment page). The assignment page
asks only for `pending` results, so persisted and ready receipts no longer fill
its 100 rows with replays (1,640 `ProjectionReplay` during run 10). A second
bounded page with its own cursor over `persisted`/`ready` results replaces
what the mixed page did for those rows:
- synchronous-policy rows replay assignment and finish exactly as before;
- async-policy rows are not touched there, but seeing any of them keeps
  follow-ups scheduled.

Async follow-up discovery keeps its own mixed page and cursor unchanged. All
three pages use the same `in` filter on the declared results composite index
(`projection_state, committed_at, __name__`), so no index changes are needed.

### Per-owner projection drain (Phase 1)

The sweep-shared 30 s walk budget gave each heavy owner a shrinking share of
each 20 s serving tick. With tens of catch-up owners on an instance, each
owner's duty cycle collapsed. Three switches change that, all on by default.
None relaxes ordering: the assignment transaction's predecessor, privacy,
binding and receipt fences decide every row exactly as before.

`BATCH_PIPELINE_OWNER_DRAIN_ENABLED` (kill switch; `false` restores the sweep
owner-chain walk above with every pre-check. Read-ahead and the deferred index
below have their own switches; all three off is the pre-drain behaviour):
- The sweep only discovers owners. When it persists an owner's pending head
  row, it hands the owner to this process's drain, not a budgeted walk. It
  leaves that owner's later rows on the same page to the drain, and it skips
  owners whose drain is already running here. An owner still waiting for a
  drain slot keeps its one-row-per-pass page progress. The page row's own
  follow-up hand-off is unchanged.
- `OwnerDrains` (`utils/batch_pipeline/projection_drain.py`) keeps a FIFO of
  owners and runs at most 8 at once per process. Each turn walks the owner's
  chain in blocking steps of at most 15 s on `sync_executor`, until the chain
  ends, blocks, or 120 s pass. An owner with rows left re-queues behind every
  waiting owner. Every turn takes at least one step.
- A drain step (and a recovery wake) holds the advisory Redis owner claim for
  the whole step instead of taking it per row. So one owner has one walker
  across processes, and a busy claim ends the step before any read. Firestore
  stays the authority.
- Rows the step reaches as the watermark's successor skip the two read-only
  pre-check transactions (`predecessor` and the per-part check). The step's own
  fresh read of the result row must show no receipt; a row or part that
  already has one still replays through the check. If a receipt races in, the
  assignment transaction replays it exactly as the check would have.
- A recovery wake that stops at its 64-row or 30 s bound hands the owner to
  the drain. Owed follow-ups join behind follow-up discovery, as before.
- Log lines: `event=batch_projection action=owner_drain outcome=turn steps=
  advanced= more= elapsed_ms=` per turn, and `action=owner_chain
  outcome=claim_busy`.

`BATCH_PIPELINE_PROJECTION_PREFETCH` (default `4`; `0` is the kill switch;
malformed or above 8 keeps 4). A budgeted walk reads the next N rows ahead on
`storage_executor`: their successor links, job bindings, result payloads and
audio manifests. All of these are immutable once committed. The walk still
reads each result row fresh, so receipt state is never taken from the
read-ahead. A read-ahead miss or failed load falls back to the walk's own read.
A load still running when the step's budget is spent ends the step (`more`)
and stays queued for the next step, so a slow read never runs again inline on
the sync slot. A drain turn keeps one read-ahead across its steps. The step
deadline is also checked between the parts of a multipart row; a row stopped
there resumes at its first unpersisted part on the next step. The candidate
hint lookup starts beside context and build, after the predecessor committed,
for the span the words predict. Its wait is capped by what is left of the step.
It is used only when it returns a conversation for exactly the built span;
otherwise (no match, a different span, an error or the cap) the lookup runs
inline as before.

`BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED` (kill switch; `false`
restores the inline index step). Budgeted walks no longer run the people-stats
invalidation and Typesense step inside each assignment. That step re-deleted
the canonical's whole `sync_merged_from` on every row, which made `index_ms`
grow with donors. Walks now record the canonical and its lineage (cumulative
`sync_merged_from` plus this commit's new donors from
`assign_in_transaction(absorbed=...)`). `ProjectionIndex` coalesces them and
converges each touched conversation once per flush, from durable state, through
`conversations.index_sync_assignment`. Re-deleting the lineage once per flush
keeps today's repair of a donor delete that failed or was lost. A flush runs
after each drain step and on each serving tick, one flusher at a time:
`event=batch_projection_index outcome=flushed owners= conversations= donors=
lag_ms=`. It stays fail-open. Pending work is in memory, so a process exit
loses it until the conversation's next deferral, as a Typesense outage does
today. On the drain path `sync_assignment_timing` reports `index_ms=0` and
`donors=` new donors.

`python -m testing.pipeline_sim projection-drain` runs the real walk, sweep and
drain on virtual time with modelled run-14 latencies. One 1,200-row owner:
today's sweep walk 36.7 rows/min, drain with no cuts 44.4, Phase 1 118.2. Twelve
300-row owners on one instance: 3.0 rows/min each today, 61.5-99.4 with the drain.
Every mode makes the same assignment calls and ends with the same index. The
model has no Firestore hot-document contention, so live rates stay below these.

### Assignment sub-phase timing

With `BATCH_PIPELINE_PROJECTION_TIMING_ENABLED`, projection also times
`load_result`, `manifest`, `context`, `build` and `candidate` (the
`get_closest_conversation_to_timestamps` query) as `batch_projection_phase`
phases. `assign_sync_conversation(timing=True)` emits one line per call:

`event=sync_assignment_timing outcome=completed|error attempts= live_overlap_ms=
fence_ms= plan_ms= encode_ms= persist_ms= body_ms= commit_ms= retry_ms=
index_ms= donors= total_ms= [exception_type=]`

- `attempts` counts transaction bodies, including SDK commit retries, the
  outer contention retry and size-limit retries.
- `plan_ms` is the in-transaction planner excluding `encode_ms`. Lock waits on
  transactional reads show up in `fence_ms` or `plan_ms`.
- `commit_ms` is the final commit after the last body. `retry_ms` is the rest
  of the transaction time: failed commits, rollbacks and backoff.
- `index_ms` covers the post-commit people-stats invalidation and the Typesense
  upsert plus one delete per `sync_merged_from` donor. `donors` counts those
  donors.

Fields hold durations, counts and static tokens only, never IDs. Legacy sync
callers do not pass `timing` and log nothing new.

## Per-unit policy snapshots

E1 records admission decisions on the job, outside the unchanged immutable binding. Projection,
scheduler and recovery owners each stamp their own part on first handling,
using a first-writer-wins transaction. The enrichment owner stamps first-summary
policy when creating the obligation. Each part carries its source role and hash;
subsequent handling uses that part across env changes and restarts. Live recovery
task and pagination switches, privacy/deletion fences and paid-intent fencing
remain current. Pre-E1 admission rows acquire one recorded fallback with bounded
telemetry. No admission process substitutes its env for a serving role's values.

The [policy contract](../config/policy/README.md) owns the read map, unchanged
legacy cohort assignments, nested live-STT retirement rule, explicit process/worker
exceptions, replay commands and revert procedure. This change alters no environment
values; deployment remains part of the two-lane train.
