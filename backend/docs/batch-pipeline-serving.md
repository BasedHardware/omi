# Batch intake and serving operations

All switches default off. Declaring settings or deploying an empty chart does
not select an upload; the lead explicitly enables the global admission flag and
allowlist/percentage after qualification. Agent A does not deploy or apply indexes.

## Host settings and rollback

On the selected always-CPU backend host, `BATCH_PIPELINE_SERVING_ENABLED=true` starts a supervised
20-second reconciliation loop. It recovers leases/retries, drains ordered log
entries, projects C's durable outbox and refreshes queue-age metrics. Configure
an explicit prod/dev runtime stage, customer data-plane project, shared encryption
secret and `BUCKET_BATCH_PIPELINE` durable artifact bucket. This bucket must not
inherit the legacy syncing bucket's one-day lifecycle for pending objects.
D's completion/deletion outboxes own removal; pending audio must survive backlog.

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
| `diarizer.batch_pipeline_runtime` | Separate prod worker chart: process on, one replica, autoscaling off, L4 `batch-pipeline-pool`; worker's own upload-admission gate stays false |
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
retry and persist `worker_empty_evidence.padded_retry=skipped_oversize`. Recovery
pins/persists its provider before dispatch. With the flag on, positive strict
local VAD, affirmative GPU padded-empty evidence, and a validated empty
**multilingual** response produce `no_recoverable_speech`. Oversized units that
skipped the GPU padded retry still run strict VAD and multilingual recovery, but
an empty multilingual response stays `failed_held` rather than terminal-empty.
Timeouts, malformed responses, uncertain calls, missing evidence, and provider
failures stay held. There are no additional calls after exhaustion and no
paid-intent resets.

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
segment independence or change to transcript visibility order is assumed.

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
