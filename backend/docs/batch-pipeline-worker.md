# Batch pipeline worker

Default-off PR 1 contract. Claude owns deployment; Grok reviews pushes.

## Current flow and evidence

`POST /v2/sync-local-files` stages uploads, claims the content ledger, creates a
Redis progress job and dispatches a Cloud Task. `sync_backfill_sequencer` can
serialize backfill before compute. The worker decodes, runs VAD/STT and merges
conversations inside the request. The 45-day content ledger checkpoints results
and metering; Redis run epochs fence retries. `diarizer/batch_main.py` is a
separate batch-only GPU service; its v2 admission caps remain independent.

Lead's October 15 aggregate snapshot: ~1.07M jobs, 983 owners, oldest ~6 days;
David's reported wait is 47 hours. Unbound/LEGACY capture classification routes
~99% to backfill. One job per owner, queue concurrency 40 (now 60), and Cloud Run
18 instances × 6 concurrency at ~13 seconds/job constrain dispatch. GPUs average
~7% utilization. Supplied batch RTFs are ~0.04 on T4 for pyannote and 0.0025 on L4
for Parakeet. These are supplied measurements.
`SYNC_LEGACY_FRESH_ENABLED` remains independently owned and unchanged.

## Target and ownership

Uploads persist immutable work records; GPU workers pull bounded batches across
owners. Compute can run concurrently for one owner. Strict priority is fresh,
recent backfill, deep backfill. Existing lane classification is authoritative:
legacy-fresh promotion happens upstream; this queue does not reinterpret it.
Recent backfill means a known recording age ≤7 days; older or unknown age is deep.
Missing usable capture clocks are refused before acceptance; the client retains audio.
Backfill uses idle slots only. Already running GPU work is not preempted; each
new pull checks fresh before selecting backfill.

A owns `config/batch_pipeline.py`, `database/batch_pipeline*.py`,
`utils/batch_pipeline/{contracts,capacity,scheduler,merge,metrics}.py`, matching unit tests,
and this document. B owns `diarizer/batch_pipeline*`, GPU-chain tests and its
benchmark records. B may add a dedicated provider config module; coordinate any
contract changes through this document before changing A's files. Neither agent
edits the other's paths. Both commit explicit paths and rebase before pushing.

## Durable state and fairness

Firestore namespaces must match explicit prod/dev runtime stage; test namespaces
require loopback-bound emulator clients. Jobs record protocol version 1 and immutable segment ID,
owner, capture timestamp, priority, estimated audio cost, staged-audio reference,
admission time; mutable state contains attempt, fencing token, lease deadline,
retry deadline, immutable versioned encrypted result reference and merge status. Audio/transcript bodies remain
outside scheduler metadata. Stable segment IDs deduplicate admission.

A scheduler control record keeps bounded active-owner rings per priority;
per-owner/class documents keep deficit and linked FIFO head/tail. Jobs are
individual documents, so queue length does not grow a document. Duration-based
deficit round robin adds a 30-second quantum; cost is bounded to the existing
7,200-second audio limit. Owner activation and each pull transact with the
control record, giving fleet-wide fairness and a strict priority decision.
The control record requires load qualification before expansion. Active-owner capacity is
bounded and admission fails explicitly rather than dropping accepted jobs.

Leases have unique tokens, heartbeat extends only an unexpired current lease,
and completion rejects expired/replaced tokens. Expiry returns work through
exponential backoff; five attempts dead-letter. Dead letters retain references
and block ordered merge until explicit operator redrive;
never silently drop audio. Recovery scans are bounded and idempotent.

## Ordered merge and crash boundary

Per-owner pending records sort by `(capture_at, segment_id)`. A transaction reads
the earliest pending item and commits only a completed result, advances the owner
watermark and creates a result-log entry with the stable segment ID. Admission
and commit both read/write the owner fence, so concurrent admission cannot insert
an earlier item unnoticed. Duplicate IDs are checked before the watermark; identical re-admission and
re-commit return existing state, conflicting immutable fields fail. A capture older than the committed watermark is rejected for explicit
late-capture handling; it must never silently corrupt ordering. Lead must ratify
that late-capture policy before rollout. Ordering covers admitted work, not
unknown audio still on a device.

The durable result log is the atomic commit boundary and resumable outbox.
Conversation projection/metering must consume stable segment IDs idempotently;
external callbacks cannot be made exactly-once by a completion marker. Before serving intake, atomically bind the durable job/protocol to the existing
content ledger, retain staged audio beyond queue residence, and resolve retries
from durable state even after Redis expiry or flag rollback. Preserve lookback,
fair-use and backfill speech caps; qualify projection and account deletion. Rollback stops new
admission, drains accepted records with their recorded protocol, and retains
staging/results. Never send an accepted item concurrently through the old worker.

## B's interface

`utils.batch_pipeline.contracts.WorkItem`: `segment_id`, `owner_id`,
`capture_at` (UTC epoch seconds), `audio_uri`, `duration_seconds`, `priority`.
`LeasedWork`: `item`, `token`, `attempt`, `lease_until`.
`WorkResult`: `segment_id`, `result_uri` (durable encrypted result reference),
`outcome` (`success` or `silence`).
B implements `process_batch(items: Sequence[WorkItem]) -> Sequence[WorkResult]`.
Exactly one result per successful item, identified by ID, independent of input
order; every omitted/failed item retries through `Scheduler.fail`. Decode failure
never means silence. The reference retains codec/provenance for B’s decoder. A worker heartbeats each lease throughout model work,
then submits results with the matching token. Decode once → VAD → words provider
(default Parakeet) → pyannote. No cloud credentials or model initialization at
import. Batch size/audio limits are B-owned; scheduler bounds pulls to 32 items.

## Flags, rollout and rollback

`BATCH_PIPELINE_ENABLED=false`, `BATCH_PIPELINE_UID_ALLOWLIST=''`,
`BATCH_PIPELINE_PERCENT=0`; read at call time, deterministic owner cohorts.
Global false wins; allowlist OR SHA-256 owner bucket below percent admits.
Invalid percentages fail closed; percentage cohorts nest. Disabled admission
invokes the original callback with identical args
and no queue/store calls. Existing sync routes remain unchanged until the
projection integration is qualified; enabling config alone is insufficient.
Workers recover already accepted protocol records even if admission is disabled.

Lead's sequence: hermetic fake/emulator → isolated dev synthetic data → David
only → 1% → 5% → all. Hold **at least 12 hours at every live step**, compare
quality, duplicate side effects, stuck merges, retries, backlog and GPU capacity.
Dev identities can reach production Firestore: never run dev real-user writes.
On regression disable new admission, retain readers and recovery workers, drain
or explicitly migrate accepted jobs under fences; do not delete queue state.

## Metrics and queue-age scaling

Export `omi_batch_pipeline_oldest_age_seconds{priority}` including leased,
retrying and merge-blocked work; ready-age is separately exported for capacity.
Record per-owner wait in an unlabeled histogram (no UID labels), completed jobs/s,
lease expiry/retry/dead-letter counts and merge lag. Compare GPU utilization from
the existing exporter. Missing/stale queue metrics are an alarm, not zero backlog.

Use GKE external-metric HPA (Prometheus adapter) on ready-item age, target 30s
fresh, 300s recent and 3600s deep; clamp to qualified GPU min/max and use 300s
scale-down stabilization. Keep one warm replica for pulling/metrics; use a
separate backfill pool/quota so deep age cannot consume reserved fresh capacity.
Cloud Run CPU/concurrency autoscaling does not directly consume queue-age metrics:
a scheduler/controller must set bounded minimum instances or use GKE workers.
No production chart or autoscaler is changed by this PR. A stale metric must retain last capacity and alert. Capacity and signal freshness require a dev load
receipt before David's canary. Hold on any duplicate visible side effect, lost
accepted item, stuck merge >12h, stale metrics >60s, or fresh p95 lease wait >30s.
Keep model admission/memory limits and reserved fresh capacity in qualification;
already-running long backfill can violate the fresh latency target.

## Capacity-aware worker integration

Queue units are conversations/capture spans (target ≤1h, hard ceiling 7200s),
never internal ASR windows. Dedicated batch GPUs own conversation-sized jobs.
`Scheduler.pull(..., capacity=PoolCapacity(...))` caps leases to available slots
and protects fresh reservations. Samples expire after 15s; invalid samples close
admission. No-snapshot pulls are dedicated-batch-only. An off-peak trough
(~25% lower listen load near 03:00Z, lead evidence) is a forecast, not slack.

Shared-live borrowing defaults off (`BATCH_PIPELINE_SHARED_LIVE_ENABLED=false`).
It requires an exclusive grant from the live pool admission owner, one slot,
no live queue, <50% GPU utilization and ≥8GiB memory headroom. Only one ≤120s
item may lease; longer spans wait for dedicated GPUs and are never split into
new merge units. The external owner must prevent concurrent/reused grants.
These conservative thresholds are unqualified; retain the kill switch until
model-memory and live-latency acceptance. Exporters must derive grants from
live queue age, GPU utilization/headroom and in-flight ownership, never CPU.

`Scheduler` exposes enqueue/pull/heartbeat/complete/fail/recover/redrive_dead;
`OrderedMerge` exposes commit_next/committed_result. Heartbeat ≤30s for 120s
leases, recover every 5s, refresh one QueueMetrics registry every 15s. Discard
results after lease loss. Bounded deficit accrual may return empty before long
items earn credit; continue polling. Ring cap: 1024 active owners per class.

Expose the registry through the worker exporter; adapter max-ready-age signals
must exclude samples older than 60s. HPA External Value targets are 30/300/3600s
by class with qualified pool min/max. Throughput is completed-event rate;
ambiguous replies may undercount receipts, so durable state is authoritative.
Ten declared stage indexes need READY receipts. Emulator contention verifies
transactions, not production throughput. Serving pump, ledger projection,
deletion, late-capture policy and backlog migration remain qualification gates.

Strict priority is a **compute admission** guarantee. Within one owner, an
unfinished earlier backfill item still blocks publication of later fresh results.
Fresh publication latency therefore needs a separately ratified bounded merge
window/stream policy if it must overtake that owner's backlog; this PR does not
silently weaken capture ordering to make that claim.
