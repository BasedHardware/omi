# Batch pipeline worker

Default-off PR #21674. Claude leads shipment; Grok reviews pushes. Local tests,
index declarations, GPU benchmarks and production qualification are separate evidence.

## Current flow and measured bottlenecks

The legacy sync router saves uploads, claims a 45-day content ledger, creates
Redis progress and dispatches Cloud Tasks. The backfill sequencer serializes
owners before decode/VAD/STT and conversation merge. Redis run epochs fence
worker mutations. `diarizer/batch_main.py` is an independent batch service.

Lead's October 15 aggregate snapshot: approximately 1.07M jobs, 983 owners,
oldest six days; David reports 47 hours. Unbound/LEGACY capture classification
routes approximately 99% to backfill. One job per owner, queue concurrency
40 (now 60), and 18 Cloud Run instances × 6 concurrency at approximately
13 seconds/job constrain dispatch. Supplied GPU utilization is approximately
7%; batch pyannote T4 RTF is 0.04 and Parakeet L4 RTF 0.0025. The supplied
1.5 seconds/audio-hour batch estimate is not qualified full-chain capacity.
`SYNC_LEGACY_FRESH_ENABLED` remains independently owned; its classification
feeds this queue unchanged.

## Target, ownership and work units

Uploads land before compute; dedicated GPU workers pull across owners. Fresh
has strict priority over recent backfill (known age ≤7 days), then deep backfill
(older/unknown age). Duration-cost deficit round robin prevents one heavy owner
from monopolizing admission to compute. Compute is parallel per owner; merge
and projection preserve the order of admitted captures.

A owns cohort config, intake, scheduler/store, ordered log, serving supervision,
heartbeat, metrics, query/index declarations and associated tests. B owns GPU
chain, encrypted artifact adapters, model/runtime packaging and dedicated GPU
chart. C owns legacy-compatible projection, content-ledger integration,
enrichment and client completion. D owns deletion/protection fences, erasure
and retention. Shared types meet in `utils.batch_pipeline.contracts`; commits
name owned paths, preserve peers' edits and never stash or force-push.

Intake strictly decodes every uploaded frame to canonical PCM WAV, retaining
capture clocks. Consecutive files are packed into conversation/capture spans
up to one hour; small gaps become silence, larger gaps/overlaps start another
unit. Longer captures split at exact sample boundaries. These are queue units,
not five-minute chunks; B independently packs short model windows by length.
Original geolocation, recording-lineage and capture proof metadata are frozen
in a bounded ancillary WAV context chunk, encrypted with the audio.
Malformed/missing capture clocks or incomplete decode refuse the upload.
BYOK refuses cloud batch intake until a private worker path exists.

## Durable model and admission

Production/dev namespaces match explicit runtime stage and customer-data
Firestore; test namespaces require injected loopback emulator clients.
Jobs contain immutable segment/owner/capture identity, duration, priority,
unit kind, source conversation, privacy generation and encrypted audio URI.
Mutable state contains attempt, fenced token/deadline, retry time, result URI,
queue link and merge status. No transcript/audio bodies enter queue metadata.

One transaction binds content-ledger `dispatch_protocol=batch_v1`, the complete
sibling set and frozen projection binding, queue entries and durable
`intakes/bp_<job>` status. Simultaneous legacy/batch claims serialize on that
same content document. A duplicate follows its existing owner. Legacy claim,
bind and release paths refuse batch ownership even after Redis expiry or
cohort rollback. Pending batch claims have no TTL; completion starts retention.
An ambiguous admission reply never releases or dispatches a legacy twin.

Owner/class queues store linked FIFO head/tail and duration deficit. Bounded
priority rings live in scheduler control; a 30-second quantum pays each job's
cost. Owner admission and pull transact through control, providing fleet-wide
priority/fairness. Owner capacity and transaction size fail explicitly before
acceptance; control contention needs load qualification.

## Lease, merge and late-capture policy

Leases last 120 seconds. The pump renews every 20 seconds concurrently with
blocking GPU work; unresolved timeout/lost ownership forbids result publication. Transient failures
keep renewing; a successful token-fenced renewal restores permission. Fenced
queue heads rotate without content writes, allowing other owners to progress. Results
carry the original token. Expiry retries with exponential backoff; attempt five
becomes a retained dead letter. Explicit redrive is required; no accepted audio
is silently dropped. Shutdown stops pulling and drains non-preemptible compute
with heartbeat intact.

Ordered merge commits only the earliest pending `(capture_at, segment_id)`.
Admission and commit share the owner revision fence. The result log records a
stable segment ID and predecessor; C's transactional projection cursor follows
that predecessor, so replay cannot append or mark enrichment twice. Bounded
recovery scans repair crashes after compute, log commit and projection writes.

The simplest safe late rule is implemented: a new capture at/before the
committed watermark receives HTTP 409 `sync_capture_before_watermark` before
admission. Client audio remains retained for explicit recovery. No historical
rewrite, silent acceptance or legacy fallback occurs. Identical existing
content/segment retries resolve before this check. Ordering covers admitted
work, not unknown audio remaining on a device. Lead must account for this
explicit recovery limitation when choosing a cohort.

## Worker and protection interfaces

`WorkItem` names segment/owner, capture time, encrypted audio URI, duration,
priority, unit kind, optional conversation and pinned privacy generation.
`LeasedWork` adds token/attempt/deadline. B implements
`process_batch(Sequence[WorkItem]) -> Sequence[WorkResult]`; results may arrive
out of order. Each result supplies segment ID, encrypted URI and success/silence.
Missing/failed items retry; decode/provider failures never become silence.

B's dedicated process composes A's `Pump`, a fresh `PoolCapacity` callback and
CUDA synchronization. Optional service-OIDC pull/heartbeat/complete/fail APIs
use the same contract. Production jobs require an OIDC compute-admission seal from the backend before
inference. Fresh restrictions are rechecked; backfill reserves the full-content
audio upper bound with existing content-idempotent policy. Refusals defer without
using failure attempts. No configured policy client means no GPU spend.
C projection runs on the backend, including durable
sweep and legacy playback/enrichment. D checks account/source deletion,
protection and generation inside each mutation transaction. Encrypted,
owner-bound, generation-pinned objects have a pre-upload deletion outbox.
Completion-only retention never expires pending results or dead letters.

## Capacity and autoscaling

Conversation units run only on dedicated batch GPUs. Shared-live stays off;
future admission requires explicit capture spans ≤120 seconds, fresh slack,
empty live queue, utilization/memory headroom and one durable reservation per
physical GPU. Expired compute leases do not release GPU ownership: only the
hardware owner acknowledges CUDA idle. Non-preemptible work never moves onto
live Parakeet pods merely because it is 03:00Z. The approximately 25% listen
trough is an opportunity to measure slack, not permission to run.

Export oldest pending/ready age per class, freshness, admission-to-lease owner
wait, transition rates/jobs per second, and GPU utilization/headroom. No owner
labels. Autoscale on ready-age with fresh/recent/deep targets 30/300/3600 seconds;
reject stale samples. B's dedicated chart documents the external-metric HPA.
CPU is not the scale signal; non-preemptible batch latency still needs bounds.

## Flags, rollout and rollback

Admission requires `BATCH_PIPELINE_ENABLED=true` plus explicit UID allowlist or
stable SHA-256 percentage; defaults are false/empty/zero. Configuration of
providers alone cannot select real uploads. `BATCH_PIPELINE_SERVING_ENABLED`
and B's worker switch independently default off. Enable qualified drain/worker
infrastructure before a cohort; keep them enabled during admission rollback.
Shared-live and VAD compaction remain off.

Lead's rollout: hermetic/emulator → isolated dev synthetic identity → David
only → 1% → 5% → all, at least 12 hours between cohorts. Require production
indexes READY, retirement of pre-protocol intake revisions, privacy/deletion,
playback, accounting, lineage and full-chain
quality/capacity acceptance before expansion. Inspect per-class age, per-owner
wait, throughput, GPU use, errors, duplicate/projected receipts and live latency.
General captures containing disconnected speech groups still require multipart
projection/deletion qualification; the initial safe projector refuses them.
Turning admission off returns new unowned uploads to legacy; existing batch
claims drain through their recorded protocol. Never copy in-flight work into
legacy or purge pending artifacts to roll back. Detailed RPC/index/operator
settings are in `batch-pipeline-serving.md`; no merge/deploy is authorized here.
