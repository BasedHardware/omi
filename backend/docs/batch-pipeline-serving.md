# Batch intake and serving operations

All switches default off. Declaring settings or deploying an empty chart does
not select an upload; the lead explicitly enables the global admission flag and
allowlist/percentage after qualification. Agent A does not deploy or apply indexes.

## Host settings and rollback

On the backend sync host, `BATCH_PIPELINE_SERVING_ENABLED=true` starts a supervised
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
409 `sync_capture_before_watermark`; retain local audio for explicit recovery.
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
  returns `{accepted:[segment_id]}`. Renew every20s; any lost/ambiguous token
  invalidates that result. Continue draining CUDA before shutdown/reuse.
- `POST /authorize-compute`: same body as heartbeat; returns `{allowed:[segment_id],
  retry_after:{segment_id:seconds}}`. Rechecks current fresh restrictions or
  reserves the full-content audio upper bound with the existing stable-content
  backfill quota guard, immediately before GPU compute. The seal is lease-token
  fenced and required for completion.
- `POST /complete`: `{stage,token,result:{segment_id,result_uri,outcome}}`;
  returns `{accepted:bool}`. Exact duplicate completion is idempotent.
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
